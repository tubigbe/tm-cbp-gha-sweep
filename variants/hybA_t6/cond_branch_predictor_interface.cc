/*
  Copyright (C) ARM Limited 2008-2025  All rights reserved.                                                                                                                                                                                                                        

  All rights reserved.

  Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

  1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

  2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

  3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/

// This file provides a sample predictor integration based on the interface provided.
#include <unordered_map>
#include "lib/sim_common_structs.h"

//#include "my_cond_branch_predictor.h"

#include "tm_predictor.h"
#include "gshare_predictor.h"
#include "cbp2016_tage_sc_l_8kb.h"

#include <cassert>

static TMPredictor tm_predictor;
static GSharePredictor gshare_predictor;
static OneBitPredictor onebit_predictor;   /* 2026-10-26 task 1/2 */
// for stats
static uint64_t total_instructions = 0;


// from CBP2025 TAGE-SC (used to keep track of snapshots for other predictors)
 uint64_t get_unique_inst_id(uint64_t seq_no, uint8_t piece)
    {
        assert(piece < 16);

        return
            (seq_no << 4) |
            (piece & 0x000F);
    }

//
// beginCondDirPredictor()
// 
// This function is called by the simulator before the start of simulation.
// It can be used for arbitrary initialization steps for the contestant's code.
//
void beginCondDirPredictor()
{
    // setup sample_predictor
    //cbp2025.setup();
    cbp2016_tage_sc_l_8kb.setup();
    tm_predictor.init();
    gshare_predictor.init();
    onebit_predictor.init();

    total_instructions = 0;
    // cond_predictor_impl.setup();
}

//
// notify_instr_fetch(uint64_t seq_no, uint8_t piece, uint64_t pc, const uint64_t fetch_cycle)
// 
// This function is called when any instructions(not just branches) gets fetched.
// Along with the unique identifying ids(seq_no, piece), PC of the instruction and fetch_cycle are also provided as inputs
//
void notify_instr_fetch(uint64_t seq_no, uint8_t piece, uint64_t pc, const uint64_t fetch_cycle)
{
    if (piece == 0) { // piece is initially set to 0 for each instr fetch
        total_instructions++;
    }
}

//
// get_cond_dir_prediction(uint64_t seq_no, uint8_t piece, uint64_t pc, const uint64_t pred_cycle)
// 
// This function is called by the simulator for predicting conditional branches.
// input values are unique identifying ids(seq_no, piece) and PC of the branch.
// return value is the predicted direction. 
//

bool get_cond_dir_prediction(uint64_t seq_no, uint8_t piece, uint64_t pc, const uint64_t pred_cycle)
{    
    //const bool tage_prediction = cbp2025.predict(seq_no, piece, pc); //cond_predictor_impl.predict(seq_no, piece, pc, tage_sc_l_pred);

    const bool tage_8kb_prediction = cbp2016_tage_sc_l_8kb.predict(seq_no, piece, pc);

    const uint64_t prediction_id = get_unique_inst_id(seq_no, piece);

    //cbp2025_predictions.emplace(prediction_id, tage_prediction);

    // 1-bit predictor first: its prediction is needed by the hybrid arms
    const bool onebit_prediction = onebit_predictor.predict(prediction_id, pc);

    // make TM prediction and save its snapshot (TM_MODE decides what it does
    // with the 1-bit prediction; TM_MODE 0 ignores it)
    const bool tm_prediction = tm_predictor.predict(prediction_id, pc, onebit_prediction);

    // gshare for comparison
    gshare_predictor.predict(prediction_id, pc);

    // return the 8 KB TAGE-SC-L prediction to the simulator
    return tage_8kb_prediction;
}

//
// spec_update(uint64_t seq_no, uint8_t piece, uint64_t pc, InstClass inst_class, const bool resolve_dir, const bool pred_dir, const uint64_t next_pc)
// 
// This function is called by the simulator for updating the history vectors and any state that needs to be updated speculatively.
// The function is called for all the branches (not just conditional branches). To faciliate accurate history updates, spec_update is called right
// after a prediction is made.
// input values are unique identifying ids(seq_no, piece), PC of the instruction, instruction class, predicted/resolve direction and the next_pc 
//
void spec_update(uint64_t seq_no, uint8_t piece, uint64_t pc, InstClass inst_class, const bool resolve_dir, const bool pred_dir, const uint64_t next_pc)
{
    assert(is_br(inst_class));
    int br_type = 0;
 switch(inst_class)
    {
        case InstClass::condBranchInstClass:
            br_type = 1;
            break;
        case InstClass::uncondDirectBranchInstClass:
            br_type = 0; 
            break;
        case InstClass::uncondIndirectBranchInstClass:
            br_type = 2;
            break;
        case InstClass::callDirectInstClass:
            br_type = 0;
            break;
        case InstClass::callIndirectInstClass:
            br_type = 2; 
            break;
        case InstClass::ReturnInstClass:
            br_type = 2;
            break;
        default:
            assert(false);
	    }

    if(inst_class == InstClass::condBranchInstClass)
    {
        //cbp2025.history_update(seq_no, piece, pc, br_type, resolve_dir, next_pc);
        
        cbp2016_tage_sc_l_8kb.history_update(seq_no, piece, pc, br_type, pred_dir, resolve_dir, next_pc);

	// cond_predictor_impl.history_update(seq_no, piece, pc, resolve_dir, next_pc);
    }
    else
    {
        //cbp2025.TrackOtherInst(pc, br_type, resolve_dir, next_pc);

        cbp2016_tage_sc_l_8kb.TrackOtherInst(pc, br_type, pred_dir, resolve_dir, next_pc);
    }

}

//
// notify_instr_decode(uint64_t seq_no, uint8_t piece, uint64_t pc, const DecodeInfo& _decode_info, const uint64_t decode_cycle)
// 
// This function is called when any instructions(not just branches) gets decoded.
// Along with the unique identifying ids(seq_no, piece), PC of the instruction, decode info and cycle are also provided as inputs
//
// For the sample predictor implementation, we do not leverage decode information
void notify_instr_decode(uint64_t seq_no, uint8_t piece, uint64_t pc, const DecodeInfo& _decode_info, const uint64_t decode_cycle)
{
}

//
// notify_agen_complete(uint64_t seq_no, uint8_t piece, uint64_t pc, const DecodeInfo& _decode_info, const uint64_t mem_va, const uint64_t mem_sz, const uint64_t agen_cycle)
// 
// This function is called when any load/store instructions complete agen.
// Along with the unique identifying ids(seq_no, piece), PC of the instruction, decode info, mem_va and mem_sz and agen_cycle are also provided as inputs
//
void notify_agen_complete(uint64_t seq_no, uint8_t piece, uint64_t pc, const DecodeInfo& _decode_info, const uint64_t mem_va, const uint64_t mem_sz, const uint64_t agen_cycle)
{
}

//
// notify_instr_execute_resolve(uint64_t seq_no, uint8_t piece, uint64_t pc, const bool pred_dir, const ExecuteInfo& _exec_info, const uint64_t execute_cycle)
// 
// This function is called when any instructions(not just branches) gets executed.
// Along with the unique identifying ids(seq_no, piece), PC of the instruction, execute info and cycle are also provided as inputs
//
// For conditional branches, we use this information to update the predictor.
// At the moment, we do not consider updating any other structure, but the contestants are allowed to  update any other predictor state.
void notify_instr_execute_resolve(uint64_t seq_no, uint8_t piece, uint64_t pc, const bool pred_dir, const ExecuteInfo& _exec_info, const uint64_t execute_cycle)
{const bool is_branch = is_br(_exec_info.dec_info.insn_class);
    if(is_branch)
    {
        if (is_cond_br(_exec_info.dec_info.insn_class))
        {
            const bool _resolve_dir = _exec_info.taken.value();
            const uint64_t _next_pc = _exec_info.next_pc;

            const uint64_t prediction_id = get_unique_inst_id(seq_no, piece);

            //const bool cbp2025_prediction = cbp2025_predictions.at(prediction_id);

            //cbp2025.update(seq_no, piece, pc, _resolve_dir, cbp2025_prediction, _next_pc);

            cbp2016_tage_sc_l_8kb.update(seq_no, piece, pc, _resolve_dir, pred_dir, _next_pc);

            // update predictors
            tm_predictor.resolved_update(prediction_id, _resolve_dir);
            gshare_predictor.resolved_update(prediction_id, _resolve_dir);
            onebit_predictor.resolved_update(prediction_id, _resolve_dir);

        }
        else
        {
            assert(pred_dir);
        }
    } 
}

//
// notify_instr_commit(uint64_t seq_no, uint8_t piece, uint64_t pc, const bool pred_dir, const ExecuteInfo& _exec_info, const uint64_t commit_cycle)
// 
// This function is called when any instructions(not just branches) gets committed.
// Along with the unique identifying ids(seq_no, piece), PC of the instruction, execute info and cycle are also provided as inputs
//
// For the sample predictor implementation, we do not leverage commit information
void notify_instr_commit(uint64_t seq_no, uint8_t piece, uint64_t pc, const bool pred_dir, const ExecuteInfo& _exec_info, const uint64_t commit_cycle)
{
 
}

//
// endCondDirPredictor()
//
// This function is called by the simulator at the end of simulation.
// It can be used by the contestant to print out other contestant-specific measurements.
//
void endCondDirPredictor ()
{  
    tm_predictor.print_stats(total_instructions);
    gshare_predictor.print_stats(total_instructions);
    onebit_predictor.print_stats(total_instructions);

    //cbp2025.terminate();
    cbp2016_tage_sc_l_8kb.terminate();

   //cond_predictor_impl.terminate();
}
