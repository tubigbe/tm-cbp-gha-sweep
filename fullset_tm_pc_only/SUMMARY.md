# full-set arm summary - `tm_pc_only`

- traces: **105** (expected 105; missing 0)
- effect metric: `TM MPKI`
- determinism gate: **PASS** (315 input-side checks vs `baseA_results/ALL.csv`, 0 mismatches)
- 1-bit identity vs `onebit_pc17`: **PASS** (315 checks, 0 mismatches)

| scope | n | base TM | TM MPKI | delta | 1-bit |
|---|---:|---:|---:|---:|---:|
| ALL | 105 | 13.41542 | 25.38129 | +89.19% | 18.86245 |
| compress | 8 | 6.54891 | 12.25592 | +87.14% | 10.41243 |
| fp | 14 | 11.98177 | 16.18980 | +35.12% | 17.53423 |
| infra | 16 | 11.07180 | 24.13779 | +118.01% | 15.36517 |
| int | 37 | 14.75575 | 27.56438 | +86.80% | 24.12735 |
| media | 4 | 5.94517 | 15.71081 | +164.26% | 9.94778 |
| web | 26 | 16.98424 | 33.51542 | +97.33% | 18.20898 |

- per-trace better/worse vs TM: **0 / 105** (of 105)

best traces: int_2_trace +1.0%, int_1_trace +1.6%, fp_5_trace +3.4%, int_22_trace +9.8%, fp_3_trace +12.1%
worst traces: infra_3_trace +303.6%, media_2_trace +390.8%, infra_2_trace +472.1%, int_14_trace +531.1%, int_15_trace +590.1%

VERDICT: COMPLETE
