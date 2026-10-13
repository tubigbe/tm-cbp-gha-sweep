/* ============================================================================
 * tm.cc —— Tsetlin Machine (TM) 的核心：推理 + 在线训练
 *
 * ── 这个文件在整个项目里的位置 ─────────────────────────────────────────────
 *   模拟器 lib/uarchsim.cc
 *     └─ cond_branch_predictor_interface.cc   ← CBP2025 冻结接口的 10 个回调
 *          ├─ cbp2016_tage_sc_l_8kb.h   8.22KB 的 TAGE-SC-L ← **只有它的预测被返回给模拟器**
 *          ├─ gshare_predictor.cc       8KB GShare          ← 只统计，不参与输出
 *          └─ tm_predictor.cc           ← 本文件的使用者
 *               ├─ assemble_input()   把 PC / 历史拼成 81 位输入向量
 *               ├─ tm_predict()       ← 本文件：纯推理
 *               └─ tm_update()        ← 本文件：每个分支解析后训练一次
 *   所以：**TM 在这条分支上的预测结果不会影响模拟器的 MPKI**，它的 MPKI 是
 *   tm_predictor.cc 自己统计并打印的（`TM MPKI`）。详见 AGENTS.md §9 第 2 条。
 *
 * ── TM 是什么（把分支预测看成一个布尔函数）────────────────────────────────
 *   输入：NUM_INPUTS = 81 个布尔位 x[0..80]（布局见下面「输入向量布局」）。
 *   每个 x[i] 派生出两个「文字 (literal)」：
 *       x[i]      → 正文字  x_i
 *       NOT x[i]  → 反文字  ¬x_i
 *   全机共 NUM_INPUTS*2 = 162 个文字。
 *
 *   机器由 NUM_CLAUSES = 32 个子句 (clause) 组成。
 *   每个子句是一个「与项 (AND)」：它对自己**包含**的文字取逻辑与。
 *   子句包含哪些文字，不是用布尔量直接存的，而是用**自动机状态**间接表示的：
 *       automata[clause][literal] ∈ [1, 2*NUM_STATES]      （uint8_t）
 *           状态 >  NUM_STATES  ⇔  该文字"被包含"进这个子句
 *           状态 <= NUM_STATES  ⇔  该文字"没有被包含"
 *   也就是说 NUM_STATES 是「包含 / 不包含」的**门槛**，状态离门槛的距离就是迟滞
 *   (hysteresis) 余量 —— 这正是 Tsetlin Automaton：一个带记忆的 1 位上/下计数器。
 *
 *   子句靠**下标**分两半（没有单独的极性字段）：
 *       clause  0 .. 15  → 正子句，投「taken」票
 *       clause 16 .. 31  → 负子句，投「not taken」票
 *
 *   最终预测（tm_predict）：
 *       vote = (触发的正子句个数) − (触发的负子句个数)
 *       vote >= 0  →  预测 taken
 *   vote ∈ [−16, +16]，与 THRESHOLD = 6 配合决定"该不该学"。
 *
 * ── 训练（最容易看不懂的地方）──────────────────────────────────────────────
 *   训练是**完全在线**的：每解析一个条件分支，就用这一个样本更新一次；
 *   不攒 batch、不重放、没有梯度。tm_predictor.cc 为每个在途分支保存一份
 *   「预测那一刻的 81 位输入快照」，分支解析时用那份快照训练 —— 所以训练看到的
 *   输入与预测时**完全一致**（这是它和"普通机器学习"最大的不同）。
 *
 *   一次更新分两步：
 *     第 1 步 tm_update：先算这一轮"该不该学"，概率 p = (T − y·vote)/(2T)
 *         · 又自信又对（y·vote = +T）→ p = 0   → 本轮**所有子句都不动**（学习冻结）
 *         · 自信地错（y·vote = −T）  → p = 1   → 所有子句都拿到反馈
 *         · 拿不定主意（vote = 0）   → p = 0.5
 *         · 每个子句再独立掷一次骰子 `rand_01() <= p` 才真的更新
 *     第 2 步 tm_fb_type1 / tm_fb_type2：按「子句极性 × 真实方向」给两种反馈之一
 *         · Type I （tm_fb_type1）→ 强化/塑形，概率式 ±1 随机游走
 *         · Type II（tm_fb_type2）→ 把投错票的子句"打死"，确定式 +1
 *
 * ── 已知实测结论（不是本文件的 bug，是这套配置的行为，先知道再看代码）──────
 *   详见 .dsh/logs/design/tm_bp_diagnosis.md。两条最关键的：
 *     1. tm_fb_type1 的 ③ 号分支（子句没触发 → 所有文字 −1，即 relax）会把子句的
 *        **触发频率**钉在 q* = p_dec/(p_inc+p_dec) = 1/S 附近。S = 5 ⇒ q* = 20%，
 *        即一个子句最多扛得住 ~log2(5) ≈ 2.3 个独立的二元条件。
 *        ⇒ **稀有的长全局历史合取式一形成就被 relax 拆掉。**
 *        实测：去掉 24 位全局历史，int_0 上 MPKI 反而改善 2.0%。
 *     2. 第 1 步里 p 在机器自信时 → 0，所以 TM 会**过早冻结**在一个由 PC 位 +
 *        4 位局部历史构成的"还凑合"的解上，再也不去探索长历史。
 *   （这两条都是**推导 + 实测**，不是从注释里读出来的猜测。）
 * ==========================================================================*/

#include <random>
#include <fstream>
#include <iostream>
#include "tm.h"

/* ── 输入向量布局（必须与 tm_predictor.cc::assemble_input() 逐位对应）─────────
 *   [ 0 .. 20]  21 位  PC 的 bit[2..22]              —— 当前分支自己的地址
 *   [21 .. 44]  24 位  全局分支方向历史 g_hist        —— 最近 24 个已解析分支的方向
 *   [45 .. 48]   4 位  当前 PC 的局部方向历史（1024 项表）—— 该 PC 最近 4 次方向
 *   [49 .. 80]  32 位  4 个"前序分支"，每个 = 7 位 PC[2..8] + 1 位方向
 *   ---------------------------------------------------------------------------
 *   21 + 24 + 4 + 4*(7+1) = 81 = NUM_INPUTS
 *   tm_predictor.cc 里有 static_assert 守这个和式；改 tm.h 的输入配置必须两处一起改。
 *
 *   ⚠️ PC 从 bit 2 开始取，是因为模拟器假定指令对齐、bit 0/1 恒为 0。
 */
#ifdef DUMP_STATE_CSV
    /* TM_INPUT_NAMES 只是给 CSV 转储用的**列名标签**，对预测/训练**没有任何影响**。
       唯一作用：让 tm_dump_states_csv() 输出的表头可读（pc12 / not_gh7 / b2_dir ...）。
       ⚠️ 它是**手工维护**的：一旦改动 tm.h 的输入配置，必须同步改这个数组，
          否则下面的 static_assert 会在编译期报错（故意的，防止表头与实际输入错位）。*/
    // TM input data labels for TA state dump - must be manually modifed if input is changed
    static const char* TM_INPUT_NAMES[] = {
        // pc
        "pc2", "pc3", "pc4", "pc5", "pc6", "pc7", "pc8",
        "pc9", "pc10", "pc11", "pc12", "pc13", "pc14",
        "pc15", "pc16", "pc17", "pc18", "pc19", "pc20",
        "pc21", "pc22",

        // global history
        "gh0", "gh1", "gh2", "gh3", "gh4", "gh5",
        "gh6", "gh7", "gh8", "gh9", "gh10", "gh11",
        "gh12", "gh13", "gh14", "gh15", "gh16", "gh17",
        "gh18", "gh19", "gh20", "gh21", "gh22", "gh23",

        // local history
        "lh0", "lh1", "lh2", "lh3",

        // previous branch 0
        "b0_pc2", "b0_pc3", "b0_pc4", "b0_pc5",
        "b0_pc6", "b0_pc7", "b0_pc8", "b0_dir",

        // previous branch 1
        "b1_pc2", "b1_pc3", "b1_pc4", "b1_pc5",
        "b1_pc6", "b1_pc7", "b1_pc8", "b1_dir",

        // previous branch 2
        "b2_pc2", "b2_pc3", "b2_pc4", "b2_pc5",
        "b2_pc6", "b2_pc7", "b2_pc8", "b2_dir",

        // previous branch 3
        "b3_pc2", "b3_pc3", "b3_pc4", "b3_pc5",
        "b3_pc6", "b3_pc7", "b3_pc8", "b3_dir"
    };

    static_assert(sizeof(TM_INPUT_NAMES) / sizeof(TM_INPUT_NAMES[0]) == NUM_INPUTS, "TM_INPUT_NAMES needs exactly NUM_INPUTS names");
#endif

/* ⚠️ 这个 RNG 是本项目最重要的"隐式状态"之一。
   1) 固定种子 1 + std::mt19937 ⇒ 同一平台同一 libstdc++ 上**完全确定**：
      105 条 trace 的结果能与原作者逐位相同（AGENTS.md §10.2），
      于是"结果偏离基线"必定是代码改动造成的、不是噪声。这是本项目的核心资产。
   2) 但它是有状态的：训练中每一步调用 rand_01() 的**次数与顺序**决定了后续所有随机数。
      所以要特别小心：
        · tm_fb_type2 是**确定性**的，内部一次都不调用 rand_01()；
        · tm_fb_type1 对 162 个文字逐个调用（每个输入连掷两次）；
        · tm_update 对 32 个子句各调用一次当门槛。
      任何"看起来无害"的重构（换循环顺序、提前 return、把某次抽样挪个位置）
      都会改变整条随机数序列 → 结果全变。做 A/B 必须用 commit 锁定代码版本。*/
// deterministic "random" function
static inline double rand_01(void) {
    static std::mt19937 rng(1u);
    static std::uniform_real_distribution<double> dist(0.0, 1.0);

    return dist(rng);
}

/* Tsetlin Automaton 的状态夹取。状态是整数计数器，物理范围 [1, 2*NUM_STATES]：
     · 下界是 1 而不是 0：状态一旦掉到 0，自动机就"死"了、再也回不来，所以夹在 1；
     · 上界 2*NUM_STATES（= 200）：夹住是为了不让"包含"这个决定无限固化。
   注意 NUM_STATES（= 100）同时是**包含门槛**和**半个量程**，一个常数两个用途。*/
static inline uint8_t clamp_state(int val) {
    if (val < 1) return 1; 
    if (val > (2 * NUM_STATES)) return (uint8_t)(2 * NUM_STATES);
    
    return (uint8_t)val;
}

/* 初始化：把全部 32×162 个状态都写成 NUM_STATES（= 包含门槛本身）。
   因为"包含"的判据是 `状态 > NUM_STATES`（严格大于），所以初始时**没有任何文字被包含**
   ⇒ 32 个子句全是"空子句"。
   空子句的行为在 tm_eval_clause 里被特殊处理，是本文件最值得注意的一处不对称（见下）。*/
void tm_init(tm_t *tm) {
    for (int clause_idx = 0; clause_idx < NUM_CLAUSES; clause_idx++) {
        for (int i = 0; i < NUM_INPUTS * 2; i++) {
            tm->automata[clause_idx][i] = (uint8_t)NUM_STATES;
        }
    }

    printf("TM initialised with size %zu bytes (%.2f Kbytes)\n", sizeof(tm_t), (double)sizeof(tm_t) / double(1024));
}

/* 求一个子句的布尔输出：它**包含**的文字是否在当前输入上**全部成立**（逻辑与）。

   literal 编号规则（全文件一致，务必记住）：
       automata[clause][i]                = 正文字 x_i   （要求 input_literals[i] == 1）
       automata[clause][i + NUM_INPUTS]   = 反文字 ¬x_i  （要求 input_literals[i] == 0）

   两个特例 / 不对称，是这段代码最该看懂的地方：
   1) 一旦发现某个"被包含"的文字在当前输入上为假 → 立刻 return false（短路，省时间）。
   2) has_included_literal 记录"这个子句是否至少包含了一个文字"：
      · predict = true（推理路径，由 tm_vote 调用）→ 空子句返回 false ⇒ 空子句**不投票**；
      · predict = false（训练路径，由 tm_update 调用）→ 空子句返回 true ⇒ 空子句**算作触发**，
        因此它会拿到 Type I 反馈并被"招募"文字 —— 这就是子句从空开始长出来的机制。
      ⚠️ 这个不对称是有意还是历史遗留**尚未确认**：Granmo 参考实现与练手项目里
         空子句在两条路径上**都是恒真**（都会投票）。见 AGENTS.md §15.2 第 3 条。*/
static inline bool tm_eval_clause(const tm_t *tm, int clause_idx, const uint8_t *input_literals, bool predict) {
    bool has_included_literal = false;

    for (int i = 0; i < NUM_INPUTS; i++) {
        bool include_literal = (tm->automata[clause_idx][i] > NUM_STATES);
        bool include_literal_neg = (tm->automata[clause_idx][i + NUM_INPUTS] > NUM_STATES);

        if (include_literal || include_literal_neg) {
            has_included_literal = true;
        }

        if ((include_literal && input_literals[i] == 0) ||
            (include_literal_neg && input_literals[i] == 1)) {
            return false;
        }
    }

    if (predict && !has_included_literal) {
        return false;
    }

    return true;
}

/* 全体子句投票求和。
   前一半（0..15）是正子句，触发则 +1；后一半（16..31）是负子句，触发则 −1。
   这里用 predict = true 求值 ⇒ 空子句不投票。
   ⚠️ 返回值**没有**夹到 ±THRESHOLD；夹取发生在 tm_update 算 p 的时候（见那里）。*/

/* ===== 实验：模糊子句投票（Fuzzy-Pattern TM 的最小版本）=====
   原版：子句是硬合取式 —— 只要有一个被包含的文字不匹配，整个子句投 0。
   模糊版：投票 = max(0, min(被包含文字数, FUZZY_LF) - 失败的被包含文字数)。
   ⇒ 子句从"硬合取式"变成"其文字上的线性阈值单元"，长子句不再被一票否决。
   反馈路径**不改**（仍用二值的 tm_eval_clause 判定 ①②③），只改"读"。*/
static inline int tm_clause_vote(const tm_t *tm, int clause_idx, const uint8_t *input_literals) {
    int n_incl = 0, n_fail = 0;
    for (int i = 0; i < NUM_INPUTS; i++) {
        bool inc_pos = (tm->automata[clause_idx][i] > NUM_STATES);
        bool inc_neg = (tm->automata[clause_idx][i + NUM_INPUTS] > NUM_STATES);
        if (inc_pos) { n_incl++; if (input_literals[i] == 0) n_fail++; }
        if (inc_neg) { n_incl++; if (input_literals[i] == 1) n_fail++; }
    }
    int v = (n_incl < FUZZY_LF) ? n_incl : FUZZY_LF;
    v -= n_fail;
    return (v > 0) ? v : 0;
}

int tm_vote(const tm_t *tm, const uint8_t *input_literals) {
    int sum = 0;

    for (int clause_idx = 0; clause_idx < NUM_CLAUSES; clause_idx++) {
        int clause_output = tm_clause_vote(tm, clause_idx, input_literals);

        if (clause_idx < (NUM_CLAUSES / 2)) {
            sum += clause_output;
        } else {
            sum -= clause_output;
        }
    }

    return sum;
}

/* 最终预测：vote >= 0 ⇒ 预测 taken。
   注意 vote == 0 时也判 taken ⇒ **机器的默认预测是"跳转"**：
   初始化时全是空子句、vote 恒为 0，所以开机默认永远预测 taken。*/
int tm_predict(const tm_t *tm, const uint8_t *input_literals) {
    return (tm_vote(tm, input_literals) >= 0);
}

/* ============================== Type I 反馈 ================================
   作用：**塑形 / 强化**。用概率式的 ±1 随机游走，让子句逐步长成"能匹配的模式"。
   三个分支（clause_eval_true = 这个子句在当前样本上是否触发）：
     ① 子句触发 且 该文字在样本上为真 → 状态 +1（概率 p_inc）
        含义：这个文字"对"，往"包含"方向推（recruitment）。
     ② 子句触发 且 该文字在样本上为假 → 状态 −1（概率 p_dec）
        含义：push-out。"这个文字不该在这儿"，往"不包含"方向推。
     ③ 子句**没触发** → 该子句**所有**文字一律 −1（概率 p_dec）
        含义：relax。"这条子句整体不匹配了，把它放松、拆散一点。"

   关键结构：①② 在 clause_eval_true 分支里、③ 在 else 里，所以
   **只有子句触发时才有机会把新文字招募进来（+1）；只要它不触发，就只能被整体拆散（−1）。**
   这就是前面「已知实测结论」第 1 条的来源：罕见的（长历史）子句几乎永远走 ③，
   刚长出来的文字立刻被拆掉；稳态触发频率 ≈ p_dec/(p_inc+p_dec) = 1/S。

   概率来自 tm.h 的 S（=5）：p_inc = (S−1)/S = 0.8，p_dec = 1/S = 0.2。
   ⇒ S 同时决定了"奖励强度"和"惩罚强度"，两者**互补、无法独立调**（设计上的耦合）。

   ⚠️ 内层 j：j=0 处理正文字（state_idx = i），j=1 处理反文字（state_idx = i + NUM_INPUTS）。
      循环顺序是 i 在外、j 在内 ⇒ 每个输入连掷两次骰子，RNG 消耗量很大。
   ========================================================================= */
static void tm_fb_type1(tm_t *tm, int clause_idx, const uint8_t *input_literals, bool clause_eval_true) {
    double p_inc = (S - 1.0) / S;
    double p_dec = 1.0 / S;

    for (int i = 0; i < NUM_INPUTS; i++) {
        for (int j = 0; j < 2; j++) {
            bool literal_val = (j == 0) ? (input_literals[i] == 1) : (input_literals[i] == 0);
            int state_idx = (j == 0) ? i : i + NUM_INPUTS;

            if (clause_eval_true) {
                if (literal_val) {
                    if (rand_01() < p_inc) {
                        tm->automata[clause_idx][state_idx] =
                            clamp_state((int)tm->automata[clause_idx][state_idx] + 1);
                    }
                } else {
                    if (rand_01() < p_dec) {
                        tm->automata[clause_idx][state_idx] =
                            clamp_state((int)tm->automata[clause_idx][state_idx] - 1);
                    }
                }
            } else {
                if (rand_01() < p_dec) {
                    tm->automata[clause_idx][state_idx] =
                        clamp_state((int)tm->automata[clause_idx][state_idx] - 1);
                }
            }
        }
    }
}

/* ============================== Type II 反馈 ===============================
   作用：**专门把"错误地触发了的子句"打死**。办法很直接：往这个子句里塞一个
   在**当前样本上为假**的文字 —— 那么下次遇到同样的输入，子句就不会再触发了。

   实现上三处值得注意：
   1) 只在 clause_eval_true 时执行（子句没触发就直接 return）。没触发的子句不必打死。
   2) 是**确定性**的 +1：没有 rand_01()、没有概率参数。与 Type I 的概率式形成对比。
   3) 只对 `状态 <= NUM_STATES`（即**尚未被包含**）的文字 +1；已经包含的文字不动，
      否则会把已经生效的抑制文字顶过头。

   Type I 与 Type II 的分工（在 tm_update 里决定给谁哪一种）：
       Type I  → 给「投对了票」的那一半子句，继续强化；
       Type II → 给「投错了票」的那一半子句，把它们的错误抑制掉。
   ========================================================================= */
static void tm_fb_type2(tm_t *tm, int clause_idx, const uint8_t *input_literals, bool clause_eval_true) {
    if (!clause_eval_true) return;

    for (int i = 0; i < NUM_INPUTS; i++) {
        int pos_idx = i;
        int neg_idx = i + NUM_INPUTS;

        bool pos_literal_false = (input_literals[i] == 0);
        bool neg_literal_false = (input_literals[i] == 1);

        if (pos_literal_false && tm->automata[clause_idx][pos_idx] <= NUM_STATES) {
            tm->automata[clause_idx][pos_idx] =
                clamp_state((int)tm->automata[clause_idx][pos_idx] + 1);
        }

        if (neg_literal_false && tm->automata[clause_idx][neg_idx] <= NUM_STATES) {
            tm->automata[clause_idx][neg_idx] =
                clamp_state((int)tm->automata[clause_idx][neg_idx] + 1);
        }
    }
}

/* ============================= 一次在线训练 ================================
   输入：input_literals —— 该分支在**预测那一刻**的 81 位输入（快照，不是"现在"的）
         taken          —— 分支实际是否跳转（真值标签 y）

   ① 先算"该不该学"的概率：
        p_clause_fb = (THRESHOLD − y·vote) / (2·THRESHOLD)
      · y = +1 (taken) / −1 (not taken)；vote 是**更新前**的投票和
      · y·vote = +THRESHOLD（又自信又对）→ p = 0   → 本轮所有子句都不更新（冻结）
      · y·vote = 0（vote = 0，拿不定主意）→ p = 0.5 → 一半概率学
      · y·vote = −THRESHOLD（自信地错）   → p = 1   → 全部子句都更新
      直觉：**只从"意外"里学** —— 越自信越不改；判对了就不再折腾它。
      ⚠️ 分母写成 2.0 * THRESHOLD（浮点字面量）是**必须的**：若写成 2 * THRESHOLD，
         整数除法会在 vote = 0 时把 0.5 截断成 0 ⇒ "拿不定主意时完全收不到反馈"
         ⇒ 机器会漂成一个常数预测器。（TM 实现里最著名的坑之一，练手项目教训 #2；
         本仓库此处是**对的**，别去"简化"它。）

   ② 逐子句：`rand_01() <= p_clause_fb` 才更新 —— 每个子句独立掷一次骰子。
      注意这里用 predict = false ⇒ **空子句在此算作"触发了"**（见 tm_eval_clause）。

   ③ 极性 × 真实方向 → 反馈类型（全文件的结构核心）：

                真实 taken           真实 not-taken
        正子句   Type I  (强化)       Type II (打死)
        负子句   Type II (打死)       Type I  (强化)

      一句话：**Type I 永远给"投对了票"的那一半，Type II 永远给"投错了票"的那一半。**

   ── 与练手项目 / Granmo 参考实现的对齐 ──
   本函数用**同一个 p_clause_fb 同时控制两个方向**，这正是修复后的正确形态。
   曾经的 bug 是 Type II 用 1−p：那样每步被更新的子句数恒为 C/2、与 |vote| 无关，
   机器永不停机（练手项目实测 y=99 快照 8/8 从 92.6% 崩到 10.0%）。
   **不要把这里改回 1−p。**
   ========================================================================= */
void tm_update(tm_t *tm, const uint8_t *input_literals, bool taken) {
    const int target = taken ? 1 : -1;
    int vote = tm_vote(tm, input_literals);

    double p_clause_fb = (double)(THRESHOLD - target * vote) / (2.0 * THRESHOLD);

    if (p_clause_fb < 0.0) {
        p_clause_fb = 0.0;
    } else if (p_clause_fb > 1.0) {
        p_clause_fb = 1.0;
    }

    for (int clause_idx = 0; clause_idx < NUM_CLAUSES; clause_idx++) {
        bool clause_output = tm_eval_clause(tm, clause_idx, input_literals, false);
        bool is_pos_clause = (clause_idx < NUM_CLAUSES / 2);

        if (rand_01() <= p_clause_fb) {
            if (taken) {
                if (is_pos_clause) {
                    tm_fb_type1(tm, clause_idx, input_literals, clause_output);
                } else {
                    tm_fb_type2(tm, clause_idx, input_literals, clause_output);
                }
            } else {
                if (is_pos_clause) {
                    tm_fb_type2(tm, clause_idx, input_literals, clause_output);
                } else {
                    tm_fb_type1(tm, clause_idx, input_literals, clause_output);
                }
            }
        }
    }
}



/* TA 状态转储（**默认关闭**：tm.h 里 DUMP_STATE_CSV 那一行被注释掉了）。
   输出格式：每个子句一行；每格是 `状态 − NUM_STATES`，所以
       > 0  → 该文字被包含在这个子句里（越正 = 越"确定要包含"）
       <= 0 → 没被包含（越负 = 被推得越远）
   列名就是正文字原名，带 `not_` 前缀的是反文字（所以一列 = 一个文字）。

   用途：这是本项目**最有价值的一把手术刀** —— 直接看出 TM 到底学到了什么。
   实测样例（先打开 tm.h 的 DUMP_STATE_CSV，再跑 ./cbp）见
   .dsh/logs/design/tm_bp_diagnosis.md。

   ⚠️ 注意调用时机：它由 tm_predictor.cc::print_stats() 在**仿真结束时**调用一次，
      所以转储的是**整条 trace 跑完那一刻**的状态、不代表全程；对非平稳 trace，
      它主要反映最后一个 phase 学到的东西。*/
#ifdef DUMP_STATE_CSV
    void tm_dump_states_csv(const tm_t *tm, const char *filename) {
        std::ofstream out(filename);

        out << "clause,clause_type";

        for (int lit_idx = 0; lit_idx < NUM_INPUTS * 2; lit_idx++) {
            int input_idx = lit_idx % NUM_INPUTS;
            bool negated = (lit_idx >= NUM_INPUTS);

            out << ",";

            if (negated) {
                out << "not_";
            }

            out << TM_INPUT_NAMES[input_idx];
        }

        out << "\n";

        for (int clause_idx = 0;  clause_idx < NUM_CLAUSES; clause_idx++) {

            out << clause_idx << ",";

            if (clause_idx < NUM_CLAUSES / 2) {
                out << "positive";
            }
            else {
                out << "negative";
            }

            for (int lit_idx = 0; lit_idx < NUM_INPUTS * 2; lit_idx++) {
                out << "," << ((int)tm->automata[clause_idx][lit_idx] - NUM_STATES);
            }

            out << "\n";
        }

        std::cout << "TM TA states dumped to " << filename << "\n";
    }
#endif