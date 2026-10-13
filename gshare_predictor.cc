#include <iostream>

#include "gshare_predictor.h"

void GSharePredictor::init() {
    table.fill(2);
    g_hist = 0;
    prediction_snapshots.clear();

    stats = {};

    const uint64_t size_bits =  (uint64_t)GSHARE_ENTRIES * 2 +  GSHARE_HISTORY_BITS;
    std::cout << "GShare size: " << size_bits << " bits, " << (size_bits / 8.0 / 1024.0) << " KB\n";
}

bool GSharePredictor::predict(uint64_t prediction_id, uint64_t pc) {
    snapshot_t snapshot;
    uint64_t pc_index;

    pc_index = pc >> 2;

    snapshot.index = (uint32_t)((pc_index ^ g_hist) & (GSHARE_ENTRIES - 1));

    snapshot.prediction = (table[snapshot.index] >= 2);

    prediction_snapshots[prediction_id] = snapshot;

    return snapshot.prediction;
}

void GSharePredictor::resolved_update(uint64_t prediction_id, bool resolve_direction) {

    auto it = prediction_snapshots.find(prediction_id);

    if (it == prediction_snapshots.end()) {
        g_hist =
            ((g_hist << 1) |
            (resolve_direction ? 1u : 0u))
            & GSHARE_HISTORY_MASK;

        return;
    }

    const snapshot_t &snapshot = it->second;

    if (snapshot.prediction != resolve_direction) {
        stats.gshare_wrong++;
    } else {
        stats.gshare_right++;
    }

    uint8_t &counter = table[snapshot.index];

    if (resolve_direction) {
        if (counter < 3) {
            counter++;
        }
    }
    else {
        if (counter > 0) {
            counter--;
        }
    }

    g_hist = ((g_hist << 1) | (resolve_direction ? 1u : 0u)) & GSHARE_HISTORY_MASK;

    prediction_snapshots.erase(it);
}

void GSharePredictor::print_stats(uint64_t total_instrs) {
    double gshare_mpki = 1000.0 * (double)stats.gshare_wrong / (double)total_instrs;
    uint64_t total_predictions = stats.gshare_right + stats.gshare_wrong;
    double gshare_accuracy =  100.0 * (double)stats.gshare_right / (double)total_predictions;

    std::cout << "===== Standalone GShare Stats =====\n";
    std::cout << "GShare wrong: " << stats.gshare_wrong << "\n";
    std::cout << "GShare right: " << stats.gshare_right << "\n";
    std::cout << "GShare accuracy: " << gshare_accuracy<< "%\n";
    std::cout << "GShare MPKI: " << gshare_mpki << "\n";
    std::cout  << "Measured # of instructions: " << total_instrs << "\n";
    std::cout << "===============================\n";

}