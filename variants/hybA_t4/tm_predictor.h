#pragma once

#include <cstdint>

#ifndef TM_MODE
#define TM_MODE 0            /* 0 untouched TM, 1 residual, 2 extra input bit, 3 gate */
#endif
#ifndef TM_GATE_THETA
#define TM_GATE_THETA 4      /* |vote| >= theta => trust the TM (gate arm) */
#endif
#ifndef TM_ONEBIT_INPUT
#define TM_ONEBIT_INPUT 0    /* 1 = append the 1-bit prediction as an input bit */
#endif
#include <unordered_map>
#include <array>

#include "tm.h"

#include <iostream>

/* ============================================================================
 * OneBitPredictor - the classic 1-bit direction predictor (2026-10-26 task).
 *
 * Per-entry state = 1 bit = the direction this entry produced last time.
 *   predict : return that bit
 *   update  : overwrite it with the resolved direction (no hysteresis)
 * Index:  pure per-PC  (ONEBIT_HIST_BITS == 0)
 *         or PC XOR global history (ONEBIT_HIST_BITS > 0)
 * Table stays packed: 2^ONEBIT_INDEX_BITS bits, so 2^17 = 16 KB exactly.
 * It is a *parallel* observer like GShare: it never touches TAGE's output and
 * never touches the TM's state, so adding it cannot move TM/GShare/TAGE.
 * ==========================================================================*/
#ifndef ONEBIT_INDEX_BITS
#define ONEBIT_INDEX_BITS 17
#endif
#ifndef ONEBIT_HIST_BITS
#define ONEBIT_HIST_BITS 0
#endif

#define ONEBIT_ENTRIES   (((uint32_t)1u) << ONEBIT_INDEX_BITS)
#define ONEBIT_INDEX_MASK (ONEBIT_ENTRIES - 1u)
#define ONEBIT_HIST_MASK  ((ONEBIT_HIST_BITS) > 0 ? ((((uint32_t)1u) << (ONEBIT_HIST_BITS)) - 1u) : 0u)

class OneBitPredictor {
    private:
        typedef struct {
            uint32_t index;
            bool prediction;
        } snapshot_t;

        std::array<uint64_t, ((ONEBIT_ENTRIES) + 63u) / 64u> table;
        uint32_t g_hist;
        std::unordered_map<uint64_t, snapshot_t> prediction_snapshots;
        uint64_t onebit_right;
        uint64_t onebit_wrong;

    public:
        void init() {
            table.fill(0);
            g_hist = 0;
            prediction_snapshots.clear();
            onebit_right = 0;
            onebit_wrong = 0;

            const uint64_t size_bits = (uint64_t)(ONEBIT_ENTRIES) + (uint64_t)(ONEBIT_HIST_BITS);
            std::cout << "1bit size: " << size_bits << " bits, "
                      << (size_bits / 8.0 / 1024.0) << " KB\n";
        }

        bool predict(uint64_t prediction_id, uint64_t pc) {
            snapshot_t s;
            s.index = (uint32_t)((((pc >> 2) ^ (uint64_t)g_hist)) & (uint64_t)(ONEBIT_INDEX_MASK));
            s.prediction = (bool)((table[s.index >> 6] >> (s.index & 63u)) & 1ull);
            prediction_snapshots[prediction_id] = s;
            return s.prediction;
        }

        void resolved_update(uint64_t prediction_id, bool resolve_direction) {
            auto it = prediction_snapshots.find(prediction_id);
            if (it != prediction_snapshots.end()) {
                const snapshot_t &s = it->second;
                if (s.prediction != resolve_direction) { onebit_wrong++; } else { onebit_right++; }
                uint64_t &word = table[s.index >> 6];
                const uint64_t bit = 1ull << (s.index & 63u);
                if (resolve_direction) { word |= bit; } else { word &= ~bit; }
                prediction_snapshots.erase(it);
            }
            g_hist = (uint32_t)(((g_hist << 1) | (resolve_direction ? 1u : 0u)) & (ONEBIT_HIST_MASK));
        }

        void print_stats(uint64_t total_instrs) {
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
};

class TMPredictor {
    private:
        typedef struct {
            uint64_t tm_right;
            uint64_t tm_wrong;
        } stats_t;

        typedef struct {
            uint8_t tm_input[NUM_INPUTS];
            bool tm_pred;
            bool onebit_pred;   /* 1-bit snapshot at prediction time (hybrid arms) */
            int  vote;          /* TM vote at prediction time (gate arm) */
            uint64_t pc;
        } snapshot_t;

        tm_t tm;

        uint32_t g_hist;
        std::array<uint8_t, TM_LOCAL_ENTRIES> local_history; 
        std::array<uint64_t, (TM_PATH_BRANCHES > 0 ? TM_PATH_BRANCHES : 1)> prev_branch_pc;
        std::array<bool, (TM_PATH_BRANCHES > 0 ? TM_PATH_BRANCHES : 1)> prev_branch_dir;

        // accuracy stats
        stats_t stats;
        uint64_t hyb_right, hyb_wrong;   /* hybrid output (TM_MODE != 0) */
        // snapshot of state for current in-flight branch so we can update TM once it resolves
        std::unordered_map<uint64_t, snapshot_t> prediction_snapshots;

        void assemble_input(uint64_t pc, uint8_t* tm_input, bool onebit_pred);

    public:
        void init();
        bool predict(uint64_t prediction_id, uint64_t pc, bool onebit_pred = false);
        void resolved_update(uint64_t prediction_id, bool resolve_direction);
        void print_stats(uint64_t total_instrs);
};