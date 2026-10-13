/* ============================================================================
 * tm_predictor.cc —— Tsetlin Machine 与 CBP2025 模拟器之间的适配层
 *
 * ── 这个文件的职责（四件事）────────────────────────────────────────────────
 *   TMPredictor 负责把「模拟器的分支事件」翻译成「TM 能吃的输入」。它做四件事：
 *     ① assemble_input()   在**预测时**把 PC / 历史拼成 81 位输入向量
 *     ② predict()          调 tm_predict() 得到预测，并把
 *                          「输入 + 预测值 + pc」存成快照（snapshot）
 *     ③ resolved_update()  分支解析后取回快照，调 tm_update() 训练，然后推进历史
 *     ④ print_stats()      统计并打印 TM accuracy / MPKI
 *                          （模拟器原生表里的 CondDirect 是 TAGE-SC-L 的，不是 TM 的）
 *
 * ── 为什么必须有快照（本文件最核心的设计）──────────────────────────────────
 *   训练必须用**预测那一刻**的 81 位输入，而不是解析那一刻的输入。理由是：
 *     · 从预测到解析之间又会有若干分支解析，全局历史 / 局部历史 / 前序分支
 *       都会向前推进；
 *     · 若拿"解析时"的输入去训练，等于把预测之后才发生的信息泄漏进训练样本
 *       （开卷考试），TM 会学到一个它在预测时根本看不到的上下文。
 *   所以 predict() 把输入快照按 prediction_id 存进 unordered_map，
 *   resolved_update() 再用同一个 id 取回来。正常情况下每个解析的分支
 *   恰好产生一次 TM 更新。
 *
 * ── 这里的三个历史结构都是 TM 私有的 ───────────────────────────────────────
 *   g_hist（24 位全局方向历史）、local_history（1024 项 × 4 位局部历史）、
 *   prev_branch_pc/dir（4 深前序分支移位寄存器）—— 全部由本文件自己维护，
 *   与 TAGE-SC-L、GShare 各算各的；TM 读不到它们的任何信息。
 *   ⚠️ 它们**只在 resolved_update() 里推进**，不参加 spec_update 的推测更新。
 *
 * ── 在这条分支上一个必须记住的事实 ─────────────────────────────────────────
 *   predict() 返回的 TM 预测**不会**被送回模拟器：
 *   cond_branch_predictor_interface.cc 返回的是 8.22 KB TAGE-SC-L 的预测。
 *   所以 TM 只影响它自己打印的 `TM MPKI`，不影响模拟器流水线。见 AGENTS.md §9 第 2 条。
 *
 * ── 已实测结论（本文件的输入配置导致的行为，详见设计文档）──────────────────
 *   见 .dsh/logs/design/tm_bp_diagnosis.md。要点：TM 实际上退化成
 *   「32 条规则的 PC / 4 位局部历史预测器」——去掉 24 位全局历史，int_0 上
 *   MPKI 反而改善 2.0%；去掉 4 位局部历史，MPKI 涨 65.6%；去掉 32 位路径历史
 *   几乎无影响。机制原因是 tm.cc 的 relax 把子句触发频率钉在 1/S，
 *   稀有的长历史合取式无法存活。
 * ==========================================================================*/
#include <iostream>
#include <cassert>

#include "tm_predictor.h"

/* 输入宽度契约：tm.h 里的输入配置之和必须**恰好**等于 NUM_INPUTS。
   21(PC) + 24(全局历史) + 4(局部历史) + 4×(7+1)(前序分支) = 81。
   ⚠️ 改 tm.h 的任一 TM_*_BITS 而忘了同步 NUM_INPUTS（或反过来），这里直接编译失败。
      同一个改动还要改 tm.cc 的 TM_INPUT_NAMES[]（那里也有长度 static_assert 守着，
      因为那张表是手写的 CSV 表头）—— 一共三处必须一起改。*/
static_assert(
    TM_PC_BITS +
    TM_G_HIST_BITS +
    TM_LOCAL_BITS +
    TM_PATH_BRANCHES * (TM_PATH_PC_BITS + 1)
    == NUM_INPUTS,
    "TM input configuration does not match NUM_INPUTS"
);


/* 把「当前分支 PC + 三套历史」拼成 81 位输入向量。
   只在**预测时**被调用（见 predict()），拼出来的向量会被快照保存下来。
   位序与 tm.h 的 TM_*_BITS 严格对应；函数末尾的 assert(wr_idx == NUM_INPUTS)
   保证 81 位一位不多一位不少。

   ⚠️ 这套布局是同学自己设计的，不是 CBP2025 的官方约定。原始 README 里试过 9 种
      输入配置（`git show main:README.md` 的 "Picking TM Inputs" 表），其中胜出的
      配置 9 是**在「TM 当 H2P 专家」这个任务上**选出来的；换成「TM 当独立预测器」
      时未必最优 —— 原作者自己也点明了这一点（AGENTS.md §11）。*/
void TMPredictor::assemble_input(uint64_t pc, uint8_t* tm_input) {
    uint32_t local_idx;
    uint8_t local_hist;

    int wr_idx = 0;

    for (int i = 0; i < NUM_INPUTS; i++) { tm_input[i] = 0; }

    /* ── 81 位输入的完整布局（位序 = 写入顺序）───────────────────────────────
     *   [ 0..20]  21 位  当前分支 PC 的 bit[2..22]
     *   [21..44]  24 位  全局方向历史 g_hist（低位是最近的分支）
     *   [45..48]   4 位  当前 PC 的局部方向历史 local_history[(pc>>2) & 1023]
     *   [49..80]  32 位  4 个前序分支 × (7 位 PC[2..8] + 1 位方向)，
     *                     prev_branch_*[0] 是**最近**解析的那个分支
     * ──────────────────────────────────────────────────────────────────────
     * 三套历史的低位都代表"最近"（更新时左移、读取时右移），别读反。*/
    // bits [0, 20]: current branch PC bits [2, 22]
    for (int i = 0; (i < TM_PC_BITS) && (wr_idx < NUM_INPUTS); i++) {
        tm_input[wr_idx] = (uint8_t)((pc >> (i + TM_PC_BIT_START)) & (uint64_t)1);
        wr_idx++;
    }

    /* 全局历史：24 位，每解析一个条件分支就把方向左移进来。
       bit 0 = 最近一次已解析分支的方向。⇒ 一个子句只要挑它想包含的那几位 gh，
       就等价于"自动选择了一个历史长度" —— 这是 TM 相对 TAGE 的潜在优势
       （TAGE 的历史长度是预先按几何级数设定死的）。
       ⚠️ 实测：这 24 位目前基本没被用到，见本文件头部的实测结论。*/

    /* ===== 实验：折叠历史输入（TAGE 的核心 trick）=====
       原版：24 位原始 gh 直接铺成输入位 —— 一个子句要表达"历史模式"必须写出一串合取文字，
             而实测子句平均只有 2.5 个文字 ⇒ 长历史在结构上表达不了。
       折叠版：把 (PC, gh[0:L)) 折成 8 位 —— 于是**一个文字**就携带了"整个 L 位历史的一个投影"，
             这正是 TAGE 用 hash(PC, history[0:L)) 索引一个计数器的做法。
       代价：面积不变（还是 24 个输入位），只是语义变了。*/
    {
        static const int FOLD_L[3] = { 8, 16, 24 };
        static const int FOLD_BITS = 8;
        const int RAW_HEAD = 0;
        for (int i = 0; i < RAW_HEAD && wr_idx < NUM_INPUTS; i++) {
            tm_input[wr_idx++] = (uint8_t)((g_hist >> i) & (uint32_t)1);
        }
        for (int grp = 0; grp < (int)(sizeof(FOLD_L)/sizeof(FOLD_L[0])); grp++) {
            int L = FOLD_L[grp];
            uint64_t h = (L >= 32) ? (uint64_t)g_hist
                                   : ((uint64_t)g_hist & ((1ull << L) - 1ull));
            uint64_t f = 0;
            for (int b = 0; b < L; b++) f ^= ((h >> b) & 1ull) << (b % FOLD_BITS);
            uint64_t x = (pc >> 2)
                       ^ (f * 0x9E3779B97F4A7C15ull)
                       ^ ((uint64_t)(grp + 1) * 0xD6E8FEB86659FD93ull);
            x ^= (x >> 29);
            for (int b = 0; b < FOLD_BITS && wr_idx < NUM_INPUTS; b++) {
                tm_input[wr_idx++] = (uint8_t)((x >> b) & 1ull);
            }
        }
    }

    /* 局部历史：一张 1024 项的 per-PC（准确说是 per-(pc>>2) 桶）方向移位寄存器，
       每项 4 bit。它和全局历史的区别是**它绑定在 PC 上**，所以天然携带
       "这个分支自己最近几次怎么跳"的偏差信息。

       ⚠️ 实测：这 4 位是当前 TM 预测能力的**主要来源**。去掉它：
          sample_int 的 TM MPKI 从 4.73 涨到 38.01（+704%），
          int_0 从 10.99 涨到 18.20（+65.6%）。
          也就是说 TM 现在主要在做"per-PC 局部历史的模式匹配"。*/
    // bits [45:48]: 4 bits of current branch's local direction history
    local_idx = (uint32_t)((pc >> 2) & (TM_LOCAL_ENTRIES - 1)); // right shift due to instr alignment
    local_hist = local_history[local_idx];

    for (int i = 0; i < TM_LOCAL_BITS; i++) {
        tm_input[wr_idx++] = (uint8_t)((local_hist >> i) & (uint8_t)1);
    }

    /* 前序分支路径：一个 4 深的移位寄存器，记最近 4 个已解析分支的
       (PC[2..8] 共 7 位, 方向 1 位)。用来表达"上一条分支跳了、所以这一条更容易跳"
       这类跨分支的路径相关性。

       ⚠️ 实测：去掉这 32 位，MPKI 只差 0.5%~1.5% —— 目前几乎没被用上。*/
    // bits [49:80]: 4 previous branches: 7 bits of PC [2, 8] + 1 bit direction
    for (int i = 0; (i < TM_PATH_BRANCHES) && (wr_idx < NUM_INPUTS); i++) {
        uint64_t path_pc = prev_branch_pc[i];

        for (int j = 0; (j < TM_PATH_PC_BITS) && (wr_idx < NUM_INPUTS); j++) {
            tm_input[wr_idx++] = (uint8_t)((path_pc >> (j + TM_PATH_PC_BIT_START)) & (uint64_t)1);
        }

        if (wr_idx < NUM_INPUTS) {
            tm_input[wr_idx++] = prev_branch_dir[i] ? 1 : 0;
        }
    }

    assert(wr_idx == NUM_INPUTS);

}

/* 初始化。一个容易忽略的顺序细节：tm_init() 先把 32×162 个自动机状态
   全部写成 NUM_STATES（= "包含"的门槛本身），于是 32 个子句全是空子句、
   vote 恒为 0、默认预测 taken；这里接着把三套历史、统计计数和快照表清零。*/
void TMPredictor::init() {
    tm_init(&this->tm);

    // clear inputs
    this->g_hist = 0;
    this->prev_branch_pc.fill(0);
    this->prev_branch_dir.fill(false);
    this->local_history.fill(0);
    this->stats = {};
    this->prediction_snapshots.clear();
}

/* 预测一个条件分支，并把"预测现场"存成快照。三步：
     ① assemble_input() 用**当前**的 PC 与历史拼出 81 位输入；
     ② tm_predict()     在当前的自动机状态上投票出方向；
     ③ 存快照          键 prediction_id = (seq_no << 4) | piece，
                       也就是"哪一个动态分支实例"，由接口层生成。
   返回值是 TM 的预测，但**在这条分支上它到不了模拟器** ——
   cond_branch_predictor_interface.cc 返回的是 TAGE-SC-L 的预测（AGENTS.md §9 第 2 条）。
   快照为什么必须存，理由见本文件头部（训练要用预测时的输入）。*/
bool TMPredictor::predict(uint64_t prediction_id, uint64_t pc) {
    snapshot_t snapshot;

    assemble_input(pc, snapshot.tm_input);
    snapshot.pc = pc;
    snapshot.tm_pred = tm_predict(&tm, snapshot.tm_input);

    prediction_snapshots[prediction_id] = snapshot;

    return snapshot.tm_pred;
}

/* 分支解析后调用。本文件里唯一会**训练** TM 的地方，也是 TM 三套历史唯一会推进的地方。
   顺序：取快照 → 计分 → tm_update 训练 → 推进 g_hist → 推进 local_history
        → 推进 prev_branch 移位寄存器 → 删掉快照。

   ⚠️ 传给 tm_update 的是 snapshot.tm_input（**预测那一刻**的输入），不是"现在"的
      输入 —— 这是全文件最容易被改错的一行。*/
void TMPredictor::resolved_update(uint64_t prediction_id, bool resolve_direction) {
    uint32_t local_idx;

    auto it = this->prediction_snapshots.find(prediction_id);

    /* 快照缺失。什么情况会缺？预测发生在**推测路径**上，而那条路径后来被 squash 了 ——
       该分支永远走不到 notify_instr_execute_resolve，快照就一直留在表里。
       （所以这张表会缓慢泄漏内存，见 AGENTS.md §9 第 11 条。）

       ⚠️ 这里的处理是**不对称**的，读代码时最容易忽略：
          只推进 g_hist，然后直接 return。也就是说这条分支
            · 不计分（不计入 TM accuracy / tm_wrong）
            · 不训练 TM
            · 不更新 local_history
            · 不更新 prev_branch_pc / prev_branch_dir
          后果：同一条分支在 g_hist 里"存在"，在局部历史与前序分支寄存器里却"不存在"。
          是否有意为之尚未确认；将来若要动这里，先想清楚三种历史要不要保持一致。*/
    if (it == this->prediction_snapshots.end()) {
        this->g_hist = (this->g_hist << 1) | (resolve_direction ? (uint32_t)1 : (uint32_t)0);
        return;
    }

    const snapshot_t &snapshot = it->second;

    // TM accuracy stats
    if (snapshot.tm_pred != resolve_direction) {
        stats.tm_wrong++;
    } else {
        stats.tm_right++;
    }

    /* 注意这是 standalone_tm 的设定：**每个**解析的分支都训练一次，
       而不是只训练"TAGE 预测错的分支"。main 分支上的姊妹实现
       （tm_side_predictor.*）才是只训练 TAGE 出错的那些 —— 那个设定会让 TM
       在其余 99.8% 的分支上永远得不到纠正反馈，这也是 main 分支的选择器
       始终做不出来的根因（见 AGENTS.md §11）。*/
    // standalone TM trains on every branch
    tm_update(&this->tm, snapshot.tm_input, resolve_direction);

    // update global history using the resolved outcome
    this->g_hist = (this->g_hist << 1) | (resolve_direction ? (uint32_t)1 : (uint32_t)0);

    // update local history for the resolved branch
    local_idx = (uint32_t)((snapshot.pc >> 2) & (TM_LOCAL_ENTRIES - 1));
    this->local_history[local_idx] = (uint8_t)((this->local_history[local_idx] << 1) | (resolve_direction ? 1 : 0));

    // update previous-branch path history.
    for (int i = TM_PATH_BRANCHES - 1; i > 0; i--) {
        this->prev_branch_pc[i] = this->prev_branch_pc[i - 1];
        this->prev_branch_dir[i] =  this->prev_branch_dir[i - 1];
    }

    this->prev_branch_pc[0] = snapshot.pc;
    this->prev_branch_dir[0] = resolve_direction;

    /* 正常路径下：每个解析的分支恰好训练一次、删一次快照。
       （若同一个 prediction_id 被预测了两次——理论上不该发生——后一次会覆盖前一次，
        前一次的快照就再也不会被训练。）*/
    this->prediction_snapshots.erase(it);
}

/* 打印 TM 自己的统计（模拟器原生表里没有 TM 的 MPKI —— 那张表的 CondDirect 是 TAGE-SC-L 的）。
   ⚠️ 两个指标的分母**不一样**，不要混着引用：
     · TM MPKI     = 1000 × tm_wrong / total_instrs
                     total_instrs 来自接口层 notify_instr_fetch（piece==0 时累加）
     · TM accuracy = 100 × tm_right / (tm_right + tm_wrong)
                     分母只有"有快照且已解析"的分支 ⇒ **在途分支不计入**
   所以 accuracy 的口径比 MPKI 略窄（AGENTS.md §10.4）。

   另外：tm.h 的 DUMP_STATE_CSV 打开时，这里会顺带把 TA 状态转储成 CSV，
   文件名就是 tm.h 里的 STATE_DUMP_FILE，写在**当前工作目录**（默认是仓库根）。*/
void TMPredictor::print_stats(uint64_t total_instrs) {
    double tm_mpki = 1000.0 * (double)stats.tm_wrong / (double)total_instrs;
    uint64_t total_predictions = stats.tm_right + stats.tm_wrong;
    double tm_accuracy =  100.0 * (double)stats.tm_right / (double)total_predictions;

    std::cout << "===== Standalone TM Stats =====\n";
    std::cout << "TM wrong: " << stats.tm_wrong << "\n";
    std::cout << "TM right: " << stats.tm_right << "\n";
    std::cout << "TM accuracy: " << tm_accuracy << "%\n";
    std::cout << "TM MPKI: " << tm_mpki << "\n";
    std::cout  << "Measured # of instructions: " << total_instrs << "\n";
    std::cout << "===============================\n";


    #ifdef DUMP_STATE_CSV

        tm_dump_states_csv(&tm, STATE_DUMP_FILE);

    #endif
}