#pragma once

#include <cstdint>
#include <unordered_map>
#include <array>

#include "tm.h"

class TMPredictor {
    private:
        typedef struct {
            uint64_t tm_right;
            uint64_t tm_wrong;
        } stats_t;

        typedef struct {
            uint8_t tm_input[NUM_INPUTS];
            bool tm_pred;
            uint64_t pc;
        } snapshot_t;

        tm_t tm;

        uint32_t g_hist;
        std::array<uint8_t, TM_LOCAL_ENTRIES> local_history; 
        std::array<uint64_t, TM_PATH_BRANCHES> prev_branch_pc;
        std::array<bool, TM_PATH_BRANCHES> prev_branch_dir;

        // accuracy stats
        stats_t stats;
        // snapshot of state for current in-flight branch so we can update TM once it resolves
        std::unordered_map<uint64_t, snapshot_t> prediction_snapshots;

        void assemble_input(uint64_t pc, uint8_t* tm_input);

    public:
        void init();
        bool predict(uint64_t prediction_id, uint64_t pc);
        void resolved_update(uint64_t prediction_id, bool resolve_direction);
        void print_stats(uint64_t total_instrs);
};