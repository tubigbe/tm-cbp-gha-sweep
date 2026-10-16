# iso-area variant B - provenance (full 105-trace sweep)

**What this run is.** The single configuration `variants/isoB_49in_53cl` over all 105 traces
of `test_runlist.txt`, to test whether the 4.26 % T6 / 4.15 % V13 reallocation gain survives
the full set. It is NOT a new baseline and NOT a parameter sweep: the configuration was fixed
in advance by the iso-area experiment, not tuned here.

| knob | value | baseline A |
|---|---:|---:|
| `NUM_INPUTS` | **49** | 81 |
| `TM_PATH_BRANCHES` | **0** | 4 |
| `NUM_CLAUSES` | **53** | 32 |
| `THRESHOLD` | **10** | 6 |
| `S` | 5 | 5 |
| `alpha = T/(C/2)` | 10/26.5 = **0.377** | 6/16 = 0.375 |
| area `C*N*2` | **5194 B** | 5184 B |

`TM_PC_BITS 21 + TM_G_HIST_BITS 24 + TM_LOCAL_BITS 4 + 0 = 49`. The preceding-branch (path)
group and its area are exchanged for 21 extra clauses.

**Files changed vs the baseline tree (exactly four, sha256 of the bytes in this repository):**

| file | sha256 | note |
|---|---|---|
| `tm.h` | `6091623bf0a00948...` | the four knobs above |
| `tm.cc` | `c48173b632621db2...` | `TM_INPUT_NAMES[]` trimmed from 81 to 49 entries (guarded by `static_assert`) |
| `tm_predictor.h` | `340e4cc149979b61...` | `std::array<T,0>` padding fix - see below |
| `tm_predictor.cc` | `58225a92d5fe0122...` | unmodified baseline (the `TM_ABLATE` hook is NOT present here) |

**`tm_predictor.h` carries a required fix.** With `TM_PATH_BRANCHES 0`,
`prev_branch_pc/dir` would be `std::array<T,0>`; libstdc++ implements zero-size `operator[]` as
`__builtin_trap()`, and `resolved_update()` writes `prev_branch_pc[0]` unconditionally, so the
first build died with SIGILL. The members are padded to at least one slot
(`(TM_PATH_BRANCHES > 0 ? TM_PATH_BRANCHES : 1)`), a slot that is never read when the group is absent.

**Determinism gates (run before any shard starts).**
1. The committed tree must be the 81/32/4/T=6 baseline, then the two samples must reproduce
   AGENTS.md 10.3 bit-for-bit: `4.72575 / 124142` and `3.26237 / 107985`.
2. The B variant must reproduce its own `ku` smoke values: `5194 bytes`, `4.22641 / 124640 / 96.7289 %`
   on `sample_int`, and `3.21526 / 108032 / 97.1161 %` on `sample_fp`.
   This is the stronger gate - it pins cross-platform determinism of the code actually under test.

**Comparison yardstick.** The published 105-trace baseline A is
`.dsh/logs/baseline/standalone_tm_6e6d30a_ku_20260929.csv` (AGENTS.md 10.1, TM MPKI 13.4154).
GHA runners were measured bit-identical to `ku` (1.02x single-core), so the comparison is direct -
provided both gates pass.

**Source of the variant.** Produced in `/tmp/isoarea` on `ku` from base commit `1908ccf`
of `mihkel-reb/tm_cbp_sim`; locked there by git blob id (`tm.h d5c2c3d3`, `tm.cc 9ace43bf`,
`tm_predictor.h 10a9db53`, `tm_predictor.cc 45ac570c`). Blob ids differ in THIS repository only
because its `.gitattributes` normalises EOL; the byte content is identical (sha256 above).
Experiment report: `.dsh/logs/design/iso_area_experiment.md`.
