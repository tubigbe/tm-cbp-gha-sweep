/* ============================================================================
 * tm_predictor.cc -- hybB 的实现：1-bit per-PC 预测器 + TM 适配/训练
 *
 * ── 一个条件分支的完整生命周期（按时间顺序）────────────────────────────────
 *  ① 预测：接口层 get_cond_dir_prediction() 被调用
 *       a. onebit.predict()      问 1-bit 表：这个 PC 上次往哪走？ -> onebit_pred
 *       b. assemble_input()      把「PC + 三套历史 + onebit_pred」拼成 82 位
 *       c. tm_predict()          TM 用当前自动机状态投票            -> tm_pred
 *       d. 存快照                 (82 位输入, tm_pred, pc)，键 = prediction_id
 *       e. **返回 tm_pred**       hybB 的最终预测就是 TM 的投票
 *  ② 解析：接口层 notify_instr_execute_resolve() 被调用
 *       f. 按 prediction_id 取回快照
 *       g. 计分：tm_pred 与真实方向比对（右/错各加一）
 *       h. tm_update()           用**快照里的**82 位输入训练一次
 *       i. 推进三套历史          g_hist / local_history / prev_branch_*
 *       j. 1-bit 表更新          把那一位改写成真实方向（在 OneBitPredictor 里）
 *       k. 删掉快照
 *
 * ── 为什么必须有快照（本文件最核心的设计）─────────────────────────────────
 *   从"预测"到"解析"之间，别的分支会陆续解析，三套历史都在往前走。
 *   如果训练时用"现在"的输入，就等于把预测之后才发生的信息喂进模型（开卷考试），
 *   模型会学到一个它在预测时根本看不到的上下文。
 *   所以 predict() 把 82 位输入原样存进 unordered_map，resolved_update() 用同一个
 *   prediction_id 取回来。正常路径下：每个解析的分支恰好训练一次、删一次快照。
 *
 * ── 2026-10-29 清理（只删代码，不改行为）──────────────────────────────────
 *   删掉的：
 *     · TM_MODE 1（训练残差标签 y'=(1-bit 猜错)）与 TM_MODE 3（投票门控）两条分支
 *     · TM_ABLATE 环境变量消融钩子（那是 10-14 输入组消融用的临时脚手架）
 *     · 只有门控才需要的 vote 快照（原来 predict() 每分支多算一遍 tm_vote）
 *     · override count / rescue / hurt 三个诊断计数器 + 整个 HYB 统计块
 *     · 1-bit 预测器里没用上的历史索引（ONEBIT_HIST_BITS 一直是 0）
 *   保留的：1-bit 预测器、TM、三套历史、快照机制、TM 统计打印。
 *   验收：6 条 T6 trace 上输出逐位同值（见 ../data/t6/META.txt 与 ../../RESULTS.md）。
 * ==========================================================================*/

#include <iostream>
#include <cassert>
#include <cstdio>
#include <cstdlib>

#include "tm_predictor.h"

#if TM_OBP_BITS > 0
/* 2026-11-01 交叉表落盘：<TM_LITERAL_OUT>_cross_table.csv。
   一个指标一行，便于 GHA 那边直接收 CSV 不用解析 stdout。*/
static void tm_write_cross_table(const uint64_t ct_inbit[2][2],
                                 const uint64_t ct_obp[2][2],
                                 uint64_t agree_total, uint64_t agree_count,
                                 uint64_t disagree_total, uint64_t disagree_tm_right) {
    const char *prefix = getenv("TM_LITERAL_OUT");
    if (prefix == NULL || prefix[0] == '\0') { return; }
    char path[4096];
    snprintf(path, sizeof(path), "%s_cross_table.csv", prefix);
    FILE *f = fopen(path, "w");
    if (f == NULL) { return; }
    fprintf(f, "bucket,n_right,n_wrong,acc_pct\n");
    const char *ib[2] = {"inbit_wrong", "inbit_correct"};
    for (int i = 0; i < 2; i++) {
        const uint64_t r = ct_inbit[i][1], w = ct_inbit[i][0];
        const double a = (r + w) ? 100.0 * (double)r / (double)(r + w) : 0.0;
        fprintf(f, "%s,%llu,%llu,%.6f\n", ib[i],
                (unsigned long long)r, (unsigned long long)w, a);
    }
    const char *ob[2] = {"obp_wrong", "obp_correct"};
    for (int i = 0; i < 2; i++) {
        const uint64_t r = ct_obp[i][1], w = ct_obp[i][0];
        const double a = (r + w) ? 100.0 * (double)r / (double)(r + w) : 0.0;
        fprintf(f, "%s,%llu,%llu,%.6f\n", ob[i],
                (unsigned long long)r, (unsigned long long)w, a);
    }
    const double agree_pct = agree_total ? 100.0 * (double)agree_count / (double)agree_total : 0.0;
    const double d_tm_pct = disagree_total ? 100.0 * (double)disagree_tm_right / (double)disagree_total : 0.0;
    fprintf(f, "agree,%llu,%llu,%.6f\n",
            (unsigned long long)agree_count, (unsigned long long)(agree_total - agree_count), agree_pct);
    fprintf(f, "disagree,%llu,%llu,%.6f\n",
            (unsigned long long)disagree_tm_right,
            (unsigned long long)(disagree_total - disagree_tm_right), d_tm_pct);
    fclose(f);
}
#endif

/* ---- 输入宽度契约 --------------------------------------------------------
 * tm.h 里那几段输入配置加起来必须**恰好**等于 NUM_INPUTS：
 *     21(PC) + 24(全局历史) + 4(局部历史) + 4×(7+1)(前序分支) + 1(1-bit) = 82
 * 任何一处改动而忘了同步 NUM_INPUTS（或反过来），编译就在这里失败。
 * 这是好事：输入位宽错一位，TM 学到的就完全是另一个问题，而且 MPKI 不会报错，
 * 只会悄悄变差。*/
static_assert(
    TM_PC_BITS +
    TM_G_HIST_BITS +
    TM_LOCAL_BITS +
    TM_PATH_BRANCHES * (TM_PATH_PC_BITS + 1) +
    TM_OBP_BITS             /* ← 1-bit 预测器的 N 位（变体用 tm.h 的 TM_OBP_BITS 切换）*/
    == NUM_INPUTS,
    "TM input configuration does not match NUM_INPUTS"
);

/* ============================================================================
 * OneBitPredictor -- 1-bit 方向预测器
 * ==========================================================================*/

/* 建表。表是 2^17 个 bit；每项初值 0，含义是"上次没跳"（not taken）。
   ⚠️ 初始值为 0 意味着**冷启动默认预测 not-taken**。这个选择影响不小：
      全 105 条 trace 的 cond 分支里 taken 只占 40.3%，所以 not-taken 是更常见的
      方向；2026-10-20 的统计里"默认 taken"的冷启动代价是 +0.279 MPKI，
      "默认 not-taken"只有 +0.131 MPKI。*/
void OneBitPredictor::init() {
    table.fill(0);
    prediction_snapshots.clear();
    onebit_right = 0;
    onebit_wrong = 0;

    /* 打印表大小，方便和记录里的 `onebit_size` 列对账（131072 bits = 16 KB）。*/
    std::cout << "1bit size: " << ((uint64_t)ONEBIT_ENTRIES * TM_OBP_BITS) << " bits, "
              << ((uint64_t)ONEBIT_ENTRIES * TM_OBP_BITS / 8.0 / 1024.0) << " KB\n";
}

/* 预测：查表 + 存快照，两件事。
 *   index = (pc >> 2) & (2^17 - 1)
 *     - 右移 2 位：指令至少 4 字节对齐，PC 的低 2 位恒为 0，不右移就浪费 2 个索引位。
 *     - & mask：只保留低 17 位 —— 也就是说"PC 的 bit[2..18]"，同一段代码的不同执行
 *       实例、以及不同模块里索引撞车的 PC，共用同一个表项（这正是"别名"的来源）。
 *   ⚠️ 索引里**没有历史**：这个预测器只知道"这个 PC 上次怎么跳"。
 *      想看加上全局历史会怎样，见 points/onebit_gshare17（结果更差：20.34 vs 22.22）。*/
uint8_t OneBitPredictor::predict(uint64_t prediction_id, uint64_t pc) {
    snapshot_t s;
    s.index = (uint32_t)((pc >> 2) & (uint64_t)ONEBIT_INDEX_MASK);
#if TM_OBP_BITS == 1
    s.bits = (uint8_t)((table[s.index >> 6] >> (s.index & 63u)) & 1ull);
#else
    s.bits = (uint8_t)(table[s.index] & (uint8_t)((1u << TM_OBP_BITS) - 1u));
#endif

    prediction_snapshots[prediction_id] = s;
    return s.bits;
}

/* 解析后训练：把快照里那一位改写成真实方向。
 *   没有饱和计数器（2-bit 那种"要错两次才翻"的迟滞），没有 tag，没有历史 ——
 *   就是"记住上一次"。所以它对**方向偏置强**的分支几乎完美，对**规律性变化**
 *   （比如交替 taken/not-taken）则完全学不会。
 *   例：web_11 上它 10.58 MPKI，比基线 TM 的 18.16 还好；但全 105 条平均是 18.86，
 *       比 TM 的 13.42 差得多 —— 它是"一半 trace 很好、另一半很差"的预测器。*/
void OneBitPredictor::resolved_update(uint64_t prediction_id, bool resolve_direction) {
    auto it = prediction_snapshots.find(prediction_id);
    if (it != prediction_snapshots.end()) {
        const snapshot_t &s = it->second;

        const bool predicted_taken = (s.bits & 1u) != 0;
        if (predicted_taken != resolve_direction) { onebit_wrong++; } else { onebit_right++; }

#if TM_OBP_BITS == 1
        /* 位操作：找到那个 uint64_t，置位或清位。*/
        uint64_t &word = table[s.index >> 6];
        const uint64_t bit = 1ull << (s.index & 63u);
        if (resolve_direction) { word |= bit; } else { word &= ~bit; }
#else
        /* 移位历史：新方向进 bit0，旧位左移，超出 N 位的丢掉。*/
        const uint8_t mask = (uint8_t)((1u << TM_OBP_BITS) - 1u);
        table[s.index] = (uint8_t)(((table[s.index] << 1) | (resolve_direction ? 1u : 0u)) & mask);
#endif

        prediction_snapshots.erase(it);
    }
}

/* 打印 1-bit 自己的统计。它和 TM 一样是"只看不投"的观察者：
   它的预测不送到模拟器（模拟器的那张表量的是 TAGE-SC-L），
   这个 MPKI 只是让我们知道"这个组合里那个简单的部分有多强"。*/
void OneBitPredictor::print_stats(uint64_t total_instrs) {
    const uint64_t total = onebit_right + onebit_wrong;
    std::cout << "===== Standalone 1-bit Stats =====\n";
    std::cout << "1bit wrong: " << onebit_wrong << "\n";
    std::cout << "1bit right: " << onebit_right << "\n";
    std::cout << "1bit accuracy: "
              << (total ? 100.0 * (double)onebit_right / (double)total : 0.0) << "%\n";
    std::cout << "1bit MPKI: "
              << (total_instrs ? 1000.0 * (double)onebit_wrong / (double)total_instrs : 0.0)
              << "\n";
    std::cout << "==================================\n";
}

/* ============================================================================
 * TMPredictor -- 拼输入 / 预测 / 训练 / 打印
 * ==========================================================================*/

/* 把「当前 PC + 三套历史 + 1-bit 的预测」拼成 82 位输入向量。
 * 只在**预测时**调用一次（见 predict()）；拼出来的向量随后被存进快照。
 * 函数末尾的 assert 保证 82 位一位不多一位不少。*/
void TMPredictor::assemble_input(uint64_t pc, uint8_t* tm_input, uint8_t onebit_bits) {
    uint32_t local_idx;
    uint8_t local_hist;

    int wr_idx = 0;

    for (int i = 0; i < NUM_INPUTS; i++) { tm_input[i] = 0; }

    /* ── 82 位输入布局（位序 = 这里的写入顺序，一一对应）───────────────────
     *    [ 0.. 20]  21 位  当前分支 PC 的 bit[2..22]
     *    [21.. 44]  24 位  全局方向历史 g_hist（bit0 是最近一次）
     *    [45.. 48]   4 位  当前 PC 的局部方向历史
     *    [49.. 80]  32 位  前 4 个分支 × (7 位 PC[2..8] + 1 位方向)
     *    [81]        1 位  1-bit 预测器的预测  ← hybB 的全部改动就是这一位
     * ────────────────────────────────────────────────────────────────────────
     * 三套历史都是"低位 = 最近"（更新时左移、读取时右移），别读反。*/

    /* [0..20] 当前分支 PC：右移 2 位（指令对齐），取 21 位。*/
    for (int i = 0; (i < TM_PC_BITS) && (wr_idx < NUM_INPUTS); i++) {
        tm_input[wr_idx] = (uint8_t)((pc >> (i + TM_PC_BIT_START)) & (uint64_t)1);
        wr_idx++;
    }

    /* [21..44] 全局方向历史：24 位，每解析一个条件分支左移进来。
     * 一个子句只要"挑它想包含的那几位 gh"，就等价于自己选了一个历史长度 ——
     * 这是 TM 相对 TAGE 的潜在优势（TAGE 的历史长度是预先按几何级数定死的）。
     * ⚠️ 实测：这 24 位目前基本没被用上（去掉它们全集 MPKI 反而好 0.36%）。*/
    for (int i = 0; (i < TM_G_HIST_BITS) && (wr_idx < NUM_INPUTS); i++) {
        tm_input[wr_idx] = (uint8_t)((g_hist >> i) & (uint32_t)1);
        wr_idx++;
    }

    /* [45..48] 局部方向历史：一张 1024 项的表，每项 4 bit，索引是 (pc>>2)&1023。
     * 和全局历史的区别是**它绑定在 PC 上**，所以天然携带"这个分支自己最近几次
     * 怎么跳"的偏置信息。
     * ⚠️ 实测：这 4 位是当前 TM 预测能力的**主要来源** —— 去掉它 V13 平均 MPKI +89%。*/
    local_idx = (uint32_t)((pc >> 2) & (TM_LOCAL_ENTRIES - 1)); // 右移：指令对齐
    local_hist = local_history[local_idx];

    for (int i = 0; i < TM_LOCAL_BITS; i++) {
        tm_input[wr_idx++] = (uint8_t)((local_hist >> i) & (uint8_t)1);
    }

    /* [49..80] 前序分支路径：4 深移位寄存器，每个分支记 (PC[2..8], 方向)。
     * 用来表达"上一条跳了，所以这一条更容易跳"这类跨分支相关性。
     * ⚠️ 实测：去掉这 32 位，MPKI 只差 0.5%~1.5%（略有反效果）—— 近乎死重。*/
    for (int i = 0; (i < TM_PATH_BRANCHES) && (wr_idx < NUM_INPUTS); i++) {
        uint64_t path_pc = prev_branch_pc[i];

        for (int j = 0; (j < TM_PATH_PC_BITS) && (wr_idx < NUM_INPUTS); j++) {
            tm_input[wr_idx++] = (uint8_t)((path_pc >> (j + TM_PATH_PC_BIT_START)) & (uint64_t)1);
        }

        if (wr_idx < NUM_INPUTS) {
            tm_input[wr_idx++] = prev_branch_dir[i] ? 1 : 0;
        }
    }

    /* [81] ← 这就是 hybB：把 1-bit 预测器"这一票"变成 TM 的一个输入位。
     * 为什么有用：这一位等价于告诉 TM「如果只按 PC 的经验猜，答案是这个」。
     *   于是 32 个子句可以把力气花在"历史带来的修正"上，而不必再用子句去
     *   重新推导"这个 PC 平时偏向哪边"——那本来就是一条 1-bit 表最擅长的事。
     * 效果：全集 11.6896 vs 基线 13.4154（−12.86%），95/105 条更好，六类全好。
     * 代价：TM 多一个输入 = +64 B（5184 → 5248 B），外加大约 16 KB 的表。*/
#if TM_OBP_BITS == 1
    if (wr_idx < NUM_INPUTS) {
        tm_input[wr_idx++] = (uint8_t)(onebit_bits & 1u);
    }
#else
    /* exp6：N 位 per-PC 方向历史，bit0 = 最近一次，和 LH 的排列顺序一致。*/
    for (int i = 0; (i < TM_OBP_BITS) && (wr_idx < NUM_INPUTS); i++) {
        tm_input[wr_idx++] = (uint8_t)((onebit_bits >> i) & 1u);
    }
#endif

    assert(wr_idx == NUM_INPUTS);
}

/* 初始化。一个容易忽略的顺序细节：tm_init() 先把 32×164 个自动机状态全部写成
   NUM_STATES（= "包含"的门槛本身），于是 32 个子句全是空子句、vote 恒为 0、
   默认预测 taken；这里接着把三套历史、统计计数和快照表清零。*/
void TMPredictor::init() {
    tm_init(&this->tm);

    this->g_hist = 0;
    this->prev_branch_pc.fill(0);
    this->prev_branch_dir.fill(false);
    this->local_history.fill(0);
    this->stats = {};
    this->prediction_snapshots.clear();
    for (int i = 0; i < 2; i++) {
        for (int j = 0; j < 2; j++) { this->ct_inbit[i][j] = 0; this->ct_obp[i][j] = 0; }
    }
    this->agree_total = 0;
    this->agree_count = 0;
    this->disagree_total = 0;
    this->disagree_tm_right = 0;
}

/* 预测一个条件分支，并把"预测现场"存成快照。三步：
     ① assemble_input() 用**当前**的 PC 与历史拼出 82 位输入；
     ② tm_predict()     在当前的自动机状态上投票出方向；
     ③ 存快照          键 prediction_id（接口层给的"第几个动态分支实例"）。
   返回值是 TM 的预测，hybB 把它**当作最终预测**（接口层直接 return 它，
   但模拟器原生那张表量的仍是 TAGE-SC-L —— 见 AGENTS.md §9 第 2 条）。*/
bool TMPredictor::predict(uint64_t prediction_id, uint64_t pc,
                          uint8_t tm_input_bits, bool obp_pred) {
    snapshot_t snapshot;

    assemble_input(pc, snapshot.tm_input, tm_input_bits);
    snapshot.pc = pc;
    snapshot.tm_input_bits = tm_input_bits;
    snapshot.obp_pred = obp_pred;
    snapshot.tm_pred = tm_predict(&tm, snapshot.tm_input);

    prediction_snapshots[prediction_id] = snapshot;

    return snapshot.tm_pred;
}

/* 分支解析后调用。本文件里唯一会**训练** TM 的地方，也是三套历史唯一会推进的地方。
   顺序：取快照 → 计分 → 训练 → 推进 g_hist → 推进 local_history → 推进前序分支
        → 删快照。

   ⚠️ 传给 tm_update 的是 snapshot.tm_input（**预测那一刻**的输入），不是"现在"的
      输入 —— 这是全文件最容易被改错的一行。*/
void TMPredictor::resolved_update(uint64_t prediction_id, bool resolve_direction) {
    uint32_t local_idx;

    auto it = this->prediction_snapshots.find(prediction_id);

    /* 快照缺失：预测发生在**推测路径**上、而那条路径后来被 squash 了 ——
       该分支永远走不到解析回调，快照就留在表里（所以这张表会缓慢泄漏内存）。

       ⚠️ 这里的处理是**不对称**的，读代码时最容易忽略：
          只推进 g_hist，然后直接 return。也就是说这条分支
            · 不计分、不训练 TM
            · 不更新局部历史、不更新前序分支寄存器
          后果：同一条分支在 g_hist 里"存在"，在另外两套历史里却"不存在"。
          是否有意为之未确认；要动这里先想清楚三种历史要不要保持一致。*/
    if (it == this->prediction_snapshots.end()) {
        this->g_hist = (this->g_hist << 1) | (resolve_direction ? (uint32_t)1 : (uint32_t)0);
        return;
    }

    const snapshot_t &snapshot = it->second;

    /* 计分。注意分母是"有快照且已解析"的分支，在途分支不计（见 print_stats）。*/
    if (snapshot.tm_pred != resolve_direction) {
        stats.tm_wrong++;
    } else {
        stats.tm_right++;
    }

#if TM_OBP_BITS > 0
    /* 2026-11-01 交叉表。NUM_INPUTS == 81 的对照变体没有 obp 位，这段不编译。*/
    {
        const bool inbit_ok = (((snapshot.tm_input_bits & 1u) != 0) == resolve_direction);
        const bool obp_ok   = (snapshot.obp_pred     == resolve_direction);
        const bool tm_ok    = (snapshot.tm_pred      == resolve_direction);
        ct_inbit[inbit_ok ? 1 : 0][tm_ok ? 1 : 0]++;
        ct_obp  [obp_ok   ? 1 : 0][tm_ok ? 1 : 0]++;
        agree_total++;
        if (snapshot.tm_pred == snapshot.obp_pred) {
            agree_count++;
        } else {
            disagree_total++;
            if (tm_ok) { disagree_tm_right++; }
        }
    }
#endif

    /* 训练一次。⚠️ 这是 standalone_tm 的设定：**每个**解析的分支都训练，
       而不是只训练"TAGE 预测错的分支"（main 分支上的姊妹实现才是只训 TAGE 错的，
       那个设定会让 TM 在其余 99.8% 的分支上永远得不到纠正反馈 —— 见 AGENTS.md §11）。
       这里传的是 resolve_direction（真实方向），不是残差标签：hybB 不改训练目标，
       只是把 1-bit 的预测**当输入**喂进去。*/
    tm_update(&this->tm, snapshot.tm_input, resolve_direction);

    /* 三套历史往前推一格（低位 = 最近）。*/
    this->g_hist = (this->g_hist << 1) | (resolve_direction ? (uint32_t)1 : (uint32_t)0);

    local_idx = (uint32_t)((snapshot.pc >> 2) & (TM_LOCAL_ENTRIES - 1));
    this->local_history[local_idx] = (uint8_t)((this->local_history[local_idx] << 1)
                                               | (resolve_direction ? 1 : 0));

    for (int i = TM_PATH_BRANCHES - 1; i > 0; i--) {
        this->prev_branch_pc[i] = this->prev_branch_pc[i - 1];
        this->prev_branch_dir[i] = this->prev_branch_dir[i - 1];
    }
    this->prev_branch_pc[0] = snapshot.pc;
    this->prev_branch_dir[0] = resolve_direction;

    /* 正常路径：每个解析的分支恰好训练一次、删一次快照。*/
    this->prediction_snapshots.erase(it);
}

/* 打印 TM 自己的统计（模拟器原生表里没有 TM 的 MPKI —— 那张表的 CondDirect 是
   TAGE-SC-L 的）。
   ⚠️ 两个指标的分母**不一样**，不要混着引用：
     · TM MPKI     = 1000 × tm_wrong / total_instrs
                     total_instrs 来自接口层 notify_instr_fetch（piece==0 时累加）
     · TM accuracy = 100 × tm_right / (tm_right + tm_wrong)
                     分母只有"有快照且已解析"的分支 ⇒ **在途分支不计入**
   所以 accuracy 的口径比 MPKI 略窄（AGENTS.md §10.4）。

   ⚠️ 在 hybB 里 **TM MPKI 就是混合预测器的 MPKI** —— 因为最终预测就是 TM 的投票，
      1-bit 只是它的一个输入。别再去找一个单独的 "HYB MPKI"（清理时删掉了：
      它是同一个数的副本）。*/
void TMPredictor::print_stats(uint64_t total_instrs) {
    double tm_mpki = 1000.0 * (double)stats.tm_wrong / (double)total_instrs;
    uint64_t total_predictions = stats.tm_right + stats.tm_wrong;
    double tm_accuracy =  100.0 * (double)stats.tm_right / (double)total_predictions;

    std::cout << "===== Standalone TM Stats =====\n";
    std::cout << "TM wrong: " << stats.tm_wrong << "\n";
    std::cout << "TM right: " << stats.tm_right << "\n";
    std::cout << "TM accuracy: " << tm_accuracy << "%\n";
    std::cout << "TM MPKI: " << tm_mpki << "\n";
    std::cout << "Measured # of instructions: " << total_instrs << "\n";
    std::cout << "===============================\n";

#if TM_OBP_BITS > 0
    {
        const uint64_t ic_r = ct_inbit[1][1], ic_w = ct_inbit[1][0];
        const uint64_t iw_r = ct_inbit[0][1], iw_w = ct_inbit[0][0];
        const uint64_t oc_r = ct_obp[1][1],   oc_w = ct_obp[1][0];
        const uint64_t ow_r = ct_obp[0][1],   ow_w = ct_obp[0][0];
        std::cout << "===== Cross table (2026-11-01) =====\n";
        std::cout << "inbit correct: " << ic_r << " / " << (ic_r + ic_w) << "\n";
        std::cout << "inbit wrong:   " << iw_r << " / " << (iw_r + iw_w) << "\n";
        std::cout << "obp correct:   " << oc_r << " / " << (oc_r + oc_w) << "\n";
        std::cout << "obp wrong:     " << ow_r << " / " << (ow_r + ow_w) << "\n";
        std::cout << "agree:         " << agree_count << " / " << agree_total << "\n";
        std::cout << "disagree:      " << disagree_total
                  << " (tm right " << disagree_tm_right << ")\n";
        std::cout << "====================================\n";
        tm_write_cross_table(ct_inbit, ct_obp, agree_total, agree_count,
                             disagree_total, disagree_tm_right);
    }
#endif
}
