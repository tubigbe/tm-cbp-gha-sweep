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

/* ============================================================================
 * 这个文件 = 模拟器的 10 个回调 + 三个预测器的"接线员"
 *
 * CBP2025 规定模拟器只通过这 10 个函数跟你说话（cbp.h 里的签名是冻结的，不能改）。
 * 我们的三个预测器都挂在这里，但它们的地位完全不同：
 *
 *   cbp2016_tage_sc_l_8kb   ← **模拟器真正使用的预测**（get_cond_dir_prediction
 *                              末尾 return 的就是它）。所以模拟器原生那张表里的
 *                              CondDirect 行量的是 TAGE-SC-L，不是 TM。
 *   tm_predictor            ← hybB 的主角。它自己统计并打印 `TM MPKI`；
 *                              在 hybB 里这就是"混合预测器"的准确率。
 *   gshare_predictor        ← 只做对照，同样只自己统计。
 *   onebit_predictor        ← 1-bit per-PC。它不直接参与最终预测，
 *                              它的一票通过 tm_predictor.predict() 变成第 82 个输入位。
 *
 * ⚠️ 一定要分清这两件事：
 *   · 模拟器的 IPC / 周期数只受 TAGE-SC-L 影响（因为它吃的是 TAGE 的预测）；
 *   · `TM MPKI` / `1bit MPKI` / `GShare MPKI` 都是各预测器**自己对的答案**，
 *     等价于"如果让这个预测器来换掉 TAGE，它的误预测率会是多少"。
 *   项目里所有"hybB −12.86 %"这类结论，比的都是这个离线口径的 MPKI，不是 IPC。
 *
 * ── 一次分支的三步（对应下面三个回调）────────────────────────────────────
 *   get_cond_dir_prediction     预测：1-bit 先给出 onebit_pred，
 *                               TM 用 (PC, 历史, onebit_pred) 投票 —— 这个投票
 *                               就是 hybB 的预测结果，但它**不返回**给模拟器。
 *   notify_instr_execute_resolve 解析：真实方向已知，训练 TM 和 1-bit，推进历史。
 *   endCondDirPredictor          收尾：打印各自的 MPKI。
 * ==========================================================================*/

static TMPredictor tm_predictor;
static GSharePredictor gshare_predictor;
static OneBitPredictor onebit_predictor;   /* 1-bit per-PC 预测器：它的一票是 TM 的第 82 个输入 */
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

    /* 顺序很重要：1-bit 必须先算，因为它的结果是 TM 的第 82 个输入位。
       两个预测器都各自存了快照（键 prediction_id），解析时各自取回。*/
    const uint8_t onebit_bits = onebit_predictor.predict(prediction_id, pc);
    const bool onebit_prediction = (onebit_bits & 1u) != 0;

    /* TM 预测：拼 82 位输入 -> 投票 -> 存快照。
       hybB 的"最终预测"就是这个返回值，但它到不了模拟器（见下面的 return）。*/
    /* 2026-11-01 归因实验：tm_input_bit 才是真正喂进 TM 的那一位。
       母本 = 真实 obp；变体可以把这一行换成随机位 / oracle。*/
    const uint8_t tm_input_bits = onebit_bits;
    const bool tm_prediction = tm_predictor.predict(prediction_id, pc, tm_input_bits, onebit_prediction);

    // gshare for comparison
    gshare_predictor.predict(prediction_id, pc);

    /* ⚠️ 返回的是 TAGE-SC-L，不是 TM 的预测（也不是 tm_prediction）。
       这是本项目一直以来的设定：三个预测器都只做"离线对答案"，
       模拟器的流水线只吃 TAGE 的预测。见文件头的说明。*/
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

            /* 三个预测器各自训练一次。顺序无所谓，因为它们互不读对方的状态；
               但注意 TM 与 1-bit 用的是**同一个** prediction_id 空间。*/
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
    /* 三个预测器各自的统计。日志里的 TM MPKI / GShare MPKI / 1bit MPKI
       就是这三行分别打印的 —— 它们都除以同一个 total_instructions，
       所以三个数可以直接比。*/
    tm_predictor.print_stats(total_instructions);
    gshare_predictor.print_stats(total_instructions);
    onebit_predictor.print_stats(total_instructions);

    //cbp2025.terminate();
    cbp2016_tage_sc_l_8kb.terminate();

   //cond_predictor_impl.terminate();
}
