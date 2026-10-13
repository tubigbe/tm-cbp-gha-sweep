#pragma once

#include <cstdint>
#include <array>
#include <unordered_map>

class GSharePredictor {
    private:
        static const uint32_t GSHARE_ENTRIES = 32768;
        static const int GSHARE_HISTORY_BITS = 15;
        static const uint32_t GSHARE_HISTORY_MASK = (1u << GSHARE_HISTORY_BITS) - 1;

        typedef struct {
            uint32_t index;
            bool prediction;
        } snapshot_t;

        typedef struct {
            uint64_t gshare_wrong;
            uint64_t gshare_right;
        } stats_t;

        std::array<uint8_t, GSHARE_ENTRIES> table;
        uint32_t g_hist;

        std::unordered_map<uint64_t, snapshot_t> prediction_snapshots;

        stats_t stats;

    public:
        void init();
        bool predict(uint64_t prediction_id, uint64_t pc);
        void resolved_update(uint64_t prediction_id, bool resolve_direction);
        void print_stats(uint64_t total_instrs);

};