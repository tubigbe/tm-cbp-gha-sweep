#pragma once

#include <cstdint>

// Parameters
#define NUM_INPUTS 81     
#define NUM_CLAUSES 32
#define NUM_STATES 100   // MAX: <127 (uint8_t)

// Hyperparams
#define THRESHOLD 6
#define S 5

// Inputs
#define TM_PC_BITS 21
#define TM_G_HIST_BITS 24
#define TM_LOCAL_BITS 4
#define TM_PATH_BRANCHES 4
#define TM_PATH_PC_BITS 7

#define TM_LOCAL_ENTRIES 1024

// Consider PCs starting from 3rd bit (instr alignment)
#define TM_PC_BIT_START 2
#define TM_PATH_PC_BIT_START 2

// Define to enable TA state dump
//#define DUMP_STATE_CSV 

typedef struct {
    uint8_t automata[NUM_CLAUSES][NUM_INPUTS * 2];
} tm_t;

void tm_init(tm_t *tm);
int tm_vote(const tm_t *tm, const uint8_t *input_literals);
int tm_predict(const tm_t *tm, const uint8_t *input_literals);
void tm_update(tm_t *tm, const uint8_t *input_literals, bool taken);

#ifdef DUMP_STATE_CSV
    #define STATE_DUMP_FILE "tm_ta_states.csv"
    void tm_dump_states_csv(const tm_t *tm, const char *filename);
#endif

/* 2026-10-26 task 3: compile-time switch for the literal observer.
   0 = observer not compiled at all (the normal predictor build);
   1 = observer compiled; still silent unless TM_LITERAL_OUT is set. */
#ifndef TM_LITERAL_STATS
#define TM_LITERAL_STATS 0
#endif
