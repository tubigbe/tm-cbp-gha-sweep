/* ============================================================================
 * tm_predictor.cc -- Tsetlin Machine <-> CBP2025 simulator adapter layer
 *
 * ── What this file does (four things) ───────────────────────────────────────
 *   TMPredictor turns "simulator branch events" into "inputs the TM can
 *   consume". It does four things:
 *     ① assemble_input()   at **prediction time**, packs PC / history into the
 *                          81-bit input vector
 *     ② predict()          calls tm_predict() for a direction, and stores
 *                          "input + prediction + pc" as a snapshot
 *     ③ resolved_update()  after the branch resolves, fetches the snapshot,
 *                          calls tm_update() to train, then advances history
 *     ④ print_stats()      computes and prints TM accuracy / MPKI
 *                          (the simulator's native CondDirect row is TAGE-SC-L's,
 *                          not the TM's)
 *
 * ── Why snapshots are required (the core design of this file) ───────────────
 *   Training must use the 81-bit input of **the moment of prediction**, not the
 *   input at resolution time. Reasons:
 *     · Between prediction and resolution more branches resolve, so global
 *       history / local history / preceding branches all move forward;
 *     · Training on the "resolution-time" input would leak information that
 *       appeared after the prediction into the training sample (an open-book
 *       exam), and the TM would learn a context it never sees when predicting.
 *   So predict() stores the input snapshot in an unordered_map keyed by
 *   prediction_id, and resolved_update() fetches it back with the same id.
 *   Normally each resolved branch produces exactly one TM update.
 *
 * ── The three history structures here are private to the TM ─────────────────
 *   g_hist (24-bit global direction history), local_history (1024 entries x
 *   4-bit local history) and prev_branch_pc/dir (a 4-deep preceding-branch shift
 *   register) are all maintained by this file alone, independently of TAGE-SC-L
 *   and GShare; the TM cannot read any of their information.
 *   ⚠️ They advance **only inside resolved_update()**, not on the speculative
 *      updates in spec_update.
 *
 * ── One fact to remember on this branch ─────────────────────────────────────
 *   The TM prediction returned by predict() is **not** sent back to the
 *   simulator: cond_branch_predictor_interface.cc returns the 8.22 KB
 *   TAGE-SC-L prediction. So the TM only affects the `TM MPKI` it prints
 *   itself, not the simulator pipeline. See AGENTS.md §9, item 2.
 *
 * ── Measured conclusions (behaviour caused by this file's input setup; see the
 *    design document for details) ────────────────────────────────────────────
 *   See .dsh/logs/design/tm_bp_diagnosis.md. Key point: the TM has in effect
 *   degenerated into a "32-rule PC / 4-bit local-history predictor" -- removing
 *   the 24-bit global history actually improves MPKI by 2.0% on int_0; removing
 *   the 4-bit local history raises MPKI by 65.6%; removing the 32-bit path
 *   history has almost no effect. The mechanism is that relax in tm.cc pins the
 *   clause firing frequency at 1/S, so rare long-history conjunctions cannot
 *   survive.
 * ==========================================================================*/
#include <iostream>
#include <cassert>

#include "tm_predictor.h"

/* Input-width contract: the input configuration in tm.h must sum to **exactly**
   NUM_INPUTS.
   21(PC) + 24(global history) + 4(local history) + 4x(7+1)(preceding branches)
   = 81.
   ⚠️ Change any TM_*_BITS in tm.h and forget to sync NUM_INPUTS (or the other
      way round) and compilation fails right here. The same change also requires
      editing TM_INPUT_NAMES[] in tm.cc (that table is guarded by its own length
      static_assert, because it is a hand-written CSV header) -- three places
      must change together. */
static_assert(
    TM_PC_BITS +
    TM_G_HIST_BITS +
    TM_LOCAL_BITS +
    TM_PATH_BRANCHES * (TM_PATH_PC_BITS + 1)
    == NUM_INPUTS,
    "TM input configuration does not match NUM_INPUTS"
);


/* Pack "current branch PC + three kinds of history" into the 81-bit input
   vector. Called **only at prediction time** (see predict()); the packed vector
   is saved in the snapshot. The bit order matches TM_*_BITS in tm.h exactly; the
   assert(wr_idx == NUM_INPUTS) at the end of the function guarantees exactly 81
   bits, no more and no less.

   ⚠️ This layout was designed by the student, it is not a CBP2025 convention.
      The original README tried 9 input configurations (the "Picking TM Inputs"
      table in `git show main:README.md`); the winning configuration 9 was chosen
      **for the task "TM as an H2P specialist"**, and it is not necessarily
      optimal when the TM is a standalone predictor -- the original author points
      this out himself (AGENTS.md §11). */
void TMPredictor::assemble_input(uint64_t pc, uint8_t* tm_input) {
    uint32_t local_idx;
    uint8_t local_hist;

    int wr_idx = 0;

    for (int i = 0; i < NUM_INPUTS; i++) { tm_input[i] = 0; }

    /* ── Full layout of the 81-bit input (bit order = write order) ───────────
     *   [ 0..20]  21 bits  bits [2..22] of the current branch PC
     *   [21..44]  24 bits  global direction history g_hist (low bit = most
     *                      recent branch)
     *   [45..48]   4 bits  local direction history of the current PC,
     *                      local_history[(pc>>2) & 1023]
     *   [49..80]  32 bits  4 preceding branches x (7-bit PC[2..8] + 1 direction
     *                      bit); prev_branch_*[0] is the **most recently**
     *                      resolved branch
     * ──────────────────────────────────────────────────────────────────────
     * In all three histories the low bits mean "most recent" (shift left when
     * updating, shift right when reading) -- do not read them backwards. */
    // bits [0, 20]: current branch PC bits [2, 22]
    for (int i = 0; (i < TM_PC_BITS) && (wr_idx < NUM_INPUTS); i++) {
        tm_input[wr_idx] = (uint8_t)((pc >> (i + TM_PC_BIT_START)) & (uint64_t)1);
        wr_idx++;
    }

    /* Global history: 24 bits; each resolved conditional branch shifts its
       direction in. bit 0 = direction of the most recently resolved branch.
       ⇒ A clause only has to pick the gh bits it wants to include, which is
       equivalent to "choosing a history length automatically" -- a potential
       advantage of the TM over TAGE (TAGE's history lengths are fixed in advance
       on a geometric scale).
       ⚠️ Measured: these 24 bits are currently almost unused; see the measured
          conclusions at the top of this file. */
    // bits [21, 44]: 24 resolved global history bits
    for (int i = 0; (i < TM_G_HIST_BITS) && (wr_idx < NUM_INPUTS); i++) {
        tm_input[wr_idx] = (uint8_t)((g_hist >> i) & (uint32_t)1);
        wr_idx++;
    }

    /* Local history: a 1024-entry per-PC direction shift register (more
       precisely, per-(pc>>2) bucket), 4 bits per entry. Its difference from
       global history is that **it is bound to the PC**, so it naturally carries
       bias information about "how this branch itself jumped recently".

       ⚠️ Measured: these 4 bits are the **main source** of the TM's current
          prediction ability. Removing them:
            TM MPKI on sample_int rises from 4.73 to 38.01 (+704%),
            int_0 rises from 10.99 to 18.20 (+65.6%).
          In other words the TM is now mostly doing "per-PC local-history
          pattern matching". */
    // bits [45:48]: 4 bits of current branch's local direction history
    local_idx = (uint32_t)((pc >> 2) & (TM_LOCAL_ENTRIES - 1)); // right shift due to instr alignment
    local_hist = local_history[local_idx];

    for (int i = 0; i < TM_LOCAL_BITS; i++) {
        tm_input[wr_idx++] = (uint8_t)((local_hist >> i) & (uint8_t)1);
    }

    /* Preceding-branch path: a 4-deep shift register holding (PC[2..8], 7 bits;
       direction, 1 bit) of the last 4 resolved branches. It expresses
       cross-branch path correlations such as "the previous branch was taken, so
       this one is more likely taken".

       ⚠️ Measured: removing these 32 bits changes MPKI by only 0.5%-1.5% --
          they are currently almost unused. */
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

/* Initialisation. One easy-to-miss ordering detail: tm_init() first writes all
   32x162 automaton states as NUM_STATES (the "include" threshold itself), so all
   32 clauses are empty, vote is always 0 and the default prediction is taken;
   this function then clears the three histories, the statistics counters and the
   snapshot table. */
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

/* Predict one conditional branch and store the "prediction scene" as a snapshot.
   Three steps:
     ① assemble_input() builds the 81-bit input from the **current** PC and
                        history;
     ② tm_predict()     votes a direction on the current automaton states;
     ③ store snapshot   key prediction_id = (seq_no << 4) | piece, that is,
                        "which dynamic branch instance", generated by the
                        interface layer.
   The return value is the TM prediction, but **on this branch it never reaches
   the simulator** -- cond_branch_predictor_interface.cc returns the TAGE-SC-L
   prediction (AGENTS.md §9, item 2). For why the snapshot is mandatory, see the
   top of this file (training must use the prediction-time input). */
bool TMPredictor::predict(uint64_t prediction_id, uint64_t pc) {
    snapshot_t snapshot;

    assemble_input(pc, snapshot.tm_input);
    snapshot.pc = pc;
    snapshot.tm_pred = tm_predict(&tm, snapshot.tm_input);

    prediction_snapshots[prediction_id] = snapshot;

    return snapshot.tm_pred;
}

/* Called after a branch resolves. This is the only place in this file that
   **trains** the TM, and the only place where the TM's three histories advance.
   Order: fetch snapshot -> score -> tm_update training -> advance g_hist ->
   advance local_history -> advance the prev_branch shift register -> erase the
   snapshot.

   ⚠️ What is passed to tm_update is snapshot.tm_input (the input **at the moment
      of prediction**), not the "current" input -- this is the line most easily
      broken in the whole file. */
void TMPredictor::resolved_update(uint64_t prediction_id, bool resolve_direction) {
    uint32_t local_idx;

    auto it = this->prediction_snapshots.find(prediction_id);

    /* Missing snapshot. When can this happen? The prediction was made on a
       **speculative path** that was later squashed -- that branch never reaches
       notify_instr_execute_resolve, so its snapshot stays in the table forever.
       (Hence this table leaks memory slowly; see AGENTS.md §9, item 11.)

       ⚠️ The handling here is **asymmetric**, and it is the easiest thing to
          overlook when reading the code: only g_hist advances, then the function
          returns. That is, this branch
            · is not scored (not counted in TM accuracy / tm_wrong)
            · does not train the TM
            · does not update local_history
            · does not update prev_branch_pc / prev_branch_dir
          Consequence: the same branch "exists" in g_hist but "does not exist" in
          the local history and preceding-branch registers. Whether this is
          intentional is unconfirmed; before changing it, first decide whether
          the three histories should stay consistent. */
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

    /* Note this is the standalone_tm setup: **every** resolved branch trains
       once, instead of training only "branches TAGE predicted wrong". The
       sibling implementation on the main branch (tm_side_predictor.*) trains only
       on TAGE's errors -- that setup leaves the TM without corrective feedback on
       the other 99.8% of branches, which is the root cause of why the main
       branch's selector never worked (see AGENTS.md §11). */
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

    /* On the normal path: each resolved branch trains exactly once and erases its
       snapshot once. (If the same prediction_id were predicted twice -- which
       should not happen -- the later snapshot would overwrite the earlier one and
       the earlier snapshot would never be trained.) */
    this->prediction_snapshots.erase(it);
}

/* Print the TM's own statistics (the simulator's native table has no TM MPKI --
   its CondDirect row is TAGE-SC-L's).
   ⚠️ The two metrics have **different** denominators; do not quote them
      interchangeably:
     · TM MPKI     = 1000 x tm_wrong / total_instrs
                     total_instrs comes from the interface layer's
                     notify_instr_fetch (accumulated when piece==0)
     · TM accuracy = 100 x tm_right / (tm_right + tm_wrong)
                     the denominator only counts "snapshotted and resolved"
                     branches ⇒ **in-flight branches are excluded**
   So the accuracy denominator is slightly narrower than the MPKI one
   (AGENTS.md §10.4).

   Also: when DUMP_STATE_CSV is enabled in tm.h, this function also dumps the TA
   states to CSV; the file name is STATE_DUMP_FILE from tm.h, written to the
   **current working directory** (the repository root by default). */
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
