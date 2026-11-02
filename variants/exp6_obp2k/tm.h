#pragma once

/* ============================================================================
 * tm.h -- TM 的形状与超参数（hybB：82 个输入）
 *
 * 这个文件只放"常量"：机器有多大、输入怎么切、超参数取多少。
 * 真正的行为在 tm.cc（TM 算法本体）和 tm_predictor.{h,cc}（与模拟器的适配）。
 *
 * ── 82 个输入是怎么来的 ────────────────────────────────────────────────────
 *     21 位  当前分支 PC 的 bit[2..22]
 *   + 24 位  全局方向历史（每个解析的条件分支左移进来）
 *   +  4 位  当前 PC 的局部方向历史（1024 项 × 4 bit 的表）
 *   + 32 位  前 4 个分支 ×（7 位 PC + 1 位方向）
 *   +  1 位  1-bit per-PC 预测器的预测  ← hybB 唯一新增的东西
 *   ────────
 *     82 位
 *   宽度契约由 tm_predictor.cc 开头的 static_assert 守着：这里任何一位改动而忘了
 *   同步 NUM_INPUTS，编译立刻失败。
 *
 * ── 面积 ───────────────────────────────────────────────────────────────────
 *   32 个子句 × 82 个输入 × 2 个文字（正/负）× 1 字节 = 5248 B。
 *   基线（81 输入）是 5184 B，所以这 1 个 bit 让 TM 大了 64 B。
 *   ⚠️ 另外那 16 KB 的 1-bit 表还没算进去——这是"能不能升基线"的未决问题。
 *
 * ── 为什么输入布局长这样 ───────────────────────────────────────────────────
 *   这不是 CBP2025 的官方约定，是上一届同学试了 9 种配置挑出来的（见
 *   `git show main:README.md` 的 "Picking TM Inputs" 表）。那 9 种是**在「TM 当
 *   TAGE 的 H2P 专家」这个任务上**选的，换成「TM 当独立预测器」未必最优。
 *   本项目 2026-10-09 的消融实测：真正有用的是那 4 位局部历史（去掉它 MPKI +89%），
 *   24 位全局历史几乎没用（去掉反而好 0.4%），32 位路径历史略有反效果。
 * ==========================================================================*/

#include <cstdint>

/* ---- 2026-11-01 实验插桩开关 --------------------------------------------
   0 = 不编译观察器（正常预测器构建）
   1 = 编译观察器；仍只有在 TM_LITERAL_OUT 设了前缀时才写 CSV
   观察器本身不改预测行为，所以开着它跑出来的 MPKI 必须和关着时逐位相同。*/
#ifndef TM_LITERAL_STATS
#define TM_LITERAL_STATS 0
#endif

/* 2026-11-01 实验：1-bit 预测器那一位到底在不在输入里。
   1 = 第 82 位是 obp（hybB / exp1a / exp1b / exp2 / exp4_26in）
   0 = 没有这一位（exp0 基线 / exp3 LH5 / exp4_25in）
  N > 1 = 该 PC 最近 N 次方向（exp6：位宽扫描，1=只存上次方向）
   宽度契约 static_assert 用它，所以任何变体只要改这一个数就不会算错。*/
#ifndef TM_OBP_BITS
#define TM_OBP_BITS 1
#endif

/* ---- 尺寸 ---------------------------------------------------------------- */
#define NUM_INPUTS 26
#define NUM_CLAUSES 32          /* 子句数：一半正子句、一半负子句 */
#define NUM_STATES 100          /* 自动机状态上限；状态 > NUM_STATES 表示"该文字被包含" */

/* ---- 超参数（一个都没为 hybB 重调过）------------------------------------ */
#define THRESHOLD 6             /* 投票死区半宽：|vote| <= T 时不加不减 */
#define S 5                     /* 收紧/放宽的速率：p_inc=(S-1)/S=0.8, p_dec=1/S=0.2 */

/* ---- 输入切分（必须加和等于 NUM_INPUTS）-------------------------------- */
#define TM_PC_BITS 21
#define TM_G_HIST_BITS 0
#define TM_LOCAL_BITS 4
#define TM_PATH_BRANCHES 0
#define TM_PATH_PC_BITS 7

#define TM_LOCAL_ENTRIES 1024   /* 局部历史表项数：索引 (pc>>2) & 1023 */

/* 分支 PC 从第 3 位开始取（指令至少 4 字节对齐，bit0/bit1 恒为 0）*/
#define TM_PC_BIT_START 2
#define TM_PATH_PC_BIT_START 2

/* ---- 1-bit 预测器的表大小 -----------------------------------------------
 * 2^17 项 × 1 bit = 131072 bit = 16 KB 整。
 * 索引只用 (pc>>2) 的低 17 位——纯粹的 per-PC，没有历史参与。
 * 想试更小的表就改这个数字（14 → 2 KB），07-26 的 onebit_pc14 臂就是这么做的。*/
#define ONEBIT_INDEX_BITS 14

/* 打开它会把 32×164 个自动机状态转储成 CSV（分析"TM 到底学了什么"时用）。
 * 默认关。⚠️ 现在打开会编译失败：tm.cc 的 TM_INPUT_NAMES[] 还是基线的 81 个名字，
 * 而静态断言要求它等于 NUM_INPUTS=82。要用就先给那张表补第 82 个名字。*/
//#define DUMP_STATE_CSV

/* ---- TM 的状态 ----------------------------------------------------------
 * automata[子句][文字] ∈ [1, 2×NUM_STATES]，uint8_t。
 *   文字编号：0..NUM_INPUTS-1 是正文字 x_i，NUM_INPUTS..2*NUM_INPUTS-1 是负文字 ¬x_i。
 *   状态 > NUM_STATES ⇔ 这个文字"被包含"进这个子句。
 * 整个结构就是 TM 的全部存储：5248 B。*/
typedef struct {
    uint8_t automata[NUM_CLAUSES][NUM_INPUTS * 2];
} tm_t;

/* ---- tm.cc 提供的 TM 本体接口 ------------------------------------------ */
void tm_init(tm_t *tm);                                            /* 全部状态置 NUM_STATES（= 32 个空子句）*/
int  tm_vote(const tm_t *tm, const uint8_t *input_literals);       /* 纯投票：正子句 +1、负子句 -1 */
int  tm_predict(const tm_t *tm, const uint8_t *input_literals);    /* vote > 0 则预测 taken */
void tm_update(tm_t *tm, const uint8_t *input_literals, bool taken); /* 一次在线训练（Type-I/II 反馈）*/

#ifdef DUMP_STATE_CSV
    #define STATE_DUMP_FILE "tm_ta_states.csv"
    void tm_dump_states_csv(const tm_t *tm, const char *filename);
#endif
