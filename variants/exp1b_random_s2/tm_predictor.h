#pragma once

/* ============================================================================
 * tm_predictor.h -- hybB 的类声明：「1-bit per-PC 预测器」+「TM 适配器」
 *
 * 两个类，各管一件事：
 *
 *   OneBitPredictor   经典 1-bit 方向预测器。每项 1 bit = "这个 PC 上次往哪走"。
 *                     2^17 项 = 16 KB。它和 TM 完全并行：自己的表、自己的快照。
 *
 *   TMPredictor       CBP2025 接口层与 TM 之间的适配器 + 训练器：
 *                     拼输入(82 位) -> 让 TM 投票 -> 存快照 -> 解析后训练一次。
 *
 * ── hybB 到底是什么 ────────────────────────────────────────────────────────
 *   把 1-bit 预测器"这一票"当成 TM 的第 82 个输入位。
 *   于是 TM 不只看「PC + 历史」，还看「如果只按 PC 猜，会猜什么」——
 *   它可以学着判断"这次该不该跟着 1-bit 走"。
 *   实测（105 条全集）：11.6896 vs 基线 13.4154 = **−12.86 %**，六个类别全部变好。
 *
 * ── 谁拥有谁 / 谁调用谁 ────────────────────────────────────────────────────
 *   cond_branch_predictor_interface.cc（模拟器的 10 个回调）里同时有
 *   `TMPredictor tm_predictor` 和 `OneBitPredictor onebit_predictor` 两个静态对象：
 *      预测：onebit.predict() -> tm.predict(..., onebit_pred)
 *      解析：tm.resolved_update(...) 和 onebit.resolved_update(...) 各调一次
 *      收尾：两个 print_stats() + GShare/TAGE 的
 *   所以这两个类互不认识，接口层负责把它们串起来——这也是为什么删掉某个组合方式
 *   只需要改 TMPredictor，不用动 OneBitPredictor。
 * ==========================================================================*/

#include <cstdint>
#include <array>
#include <unordered_map>
#include <iostream>

#include "tm.h"

/* ============================================================================
 * OneBitPredictor -- 1-bit 方向预测器
 *
 * 状态：每个 PC（按 (pc>>2) 取模）一个 bit，记"上次跳没跳"。
 *   预测：直接返回这一位。
 *   解析：把这一位改写成真实方向（没有饱和计数器、没有历史、没有 tag）。
 * 表：2^17 项 × 1 bit，用 uint64_t 数组位压缩存，正好 16 KB。
 * ==========================================================================*/
#define ONEBIT_ENTRIES    (((uint32_t)1u) << ONEBIT_INDEX_BITS)
#define ONEBIT_INDEX_MASK (ONEBIT_ENTRIES - 1u)

class OneBitPredictor {
    private:
        /* 快照：预测时记住"我查的是哪个表项"，解析后回来改写它。
           键 prediction_id = (seq_no << 4) | piece，即"第几个动态分支实例"。
           为什么要有快照：分支可能预测在被 squash 的路径上，解析时才知道是谁；
           而且解析时重新算 index 也行，但用快照更不容易出错。*/
        typedef struct {
            uint32_t index;         /* 表项下标 (pc>>2) & mask */
            bool     prediction;    /* 预测时这一位的值（只用于统计）*/
        } snapshot_t;

        /* 位压缩表：131072 bit = 16 KB。
           取第 i 位：[i >> 6] 找到那个 uint64_t，[i & 63] 找到字里的位置。*/
        std::array<uint64_t, (ONEBIT_ENTRIES + 63u) / 64u> table;

        std::unordered_map<uint64_t, snapshot_t> prediction_snapshots;

        uint64_t onebit_right;
        uint64_t onebit_wrong;

    public:
        void init();
        bool predict(uint64_t prediction_id, uint64_t pc);
        void resolved_update(uint64_t prediction_id, bool resolve_direction);
        void print_stats(uint64_t total_instrs);
};

/* ============================================================================
 * TMPredictor -- TM 的适配器与训练器
 *
 * 它持有两样东西：TM 的状态（tm_t，5248 B）和三套历史（全局/局部/前序分支）。
 * ⚠️ 这三套历史是 TM **私有的**：GShare 和 TAGE-SC-L 各有自己的一套，互不读。
 * ==========================================================================*/
class TMPredictor {
    private:
        typedef struct {
            uint64_t tm_right;
            uint64_t tm_wrong;
        } stats_t;

        /* 预测现场。三个字段缺一不可：
             tm_input  —— 预测那一刻的 82 位输入，训练时必须原样用它（见 .cc 的说明）
             tm_pred   —— 那一刻 TM 的投票，解析后用来计分
             pc        —— 解析后用来更新局部历史（局部历史的索引就是 PC）*/
        typedef struct {
            uint8_t  tm_input[NUM_INPUTS];
            bool     tm_pred;
            uint64_t pc;
            /* 2026-11-01 obp 归因实验：
                 tm_input_bit = 实际喂给 TM 的第 82 位（可能是真 obp，也可能是随机位）
                 obp_pred     = 真实 obp 的预测，只用来做交叉表统计，不一定喂进 TM */
            bool     tm_input_bit;
            bool     obp_pred;
        } snapshot_t;

        tm_t tm;    /* 32 子句 × 164 文字 × 1 B = 5248 B，TM 的全部存储 */

        uint32_t g_hist;                        /* 24 位全局方向历史，bit0 = 最近一次 */
        std::array<uint8_t, TM_LOCAL_ENTRIES> local_history; /* 1024 项 × 4 bit，按 (pc>>2) 索引 */
        std::array<uint64_t, TM_PATH_BRANCHES> prev_branch_pc;  /* 前 4 个解析分支的 PC */
        std::array<bool,     TM_PATH_BRANCHES> prev_branch_dir; /* 前 4 个解析分支的方向 */

        stats_t stats;

        /* 2026-11-01 交叉表（只在 82 输入、即真的有一个 obp 位时统计）
           ct_inbit[喂进去的位对不对][TM 对不对]
           ct_obp  [真实 obp 对不对][TM 对不对]
           agree / disagree = TM 与真实 obp 意见是否相同 */
        uint64_t ct_inbit[2][2];
        uint64_t ct_obp[2][2];
        uint64_t agree_total;
        uint64_t agree_count;
        uint64_t disagree_total;
        uint64_t disagree_tm_right;

        std::unordered_map<uint64_t, snapshot_t> prediction_snapshots;

        /* 拼 82 位输入。只有 predict() 会调它（解析时绝不能再拼一次）。*/
        void assemble_input(uint64_t pc, uint8_t* tm_input, bool onebit_pred);

    public:
        void init();
        bool predict(uint64_t prediction_id, uint64_t pc, bool tm_input_bit, bool obp_pred);
        void resolved_update(uint64_t prediction_id, bool resolve_direction);
        void print_stats(uint64_t total_instrs);
};
