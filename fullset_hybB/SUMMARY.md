# full-set arm summary - `hybB`

- traces: **105** (expected 105; missing 0)
- effect metric: `HYB MPKI`
- determinism gate: **PASS** (315 input-side checks vs `baseA_results/ALL.csv`, 0 mismatches)
- 1-bit identity vs `onebit_pc17`: **PASS** (315 checks, 0 mismatches)

| scope | n | base TM | HYB MPKI | delta | 1-bit |
|---|---:|---:|---:|---:|---:|
| ALL | 105 | 13.41542 | 11.68955 | -12.86% | 18.86245 |
| compress | 8 | 6.54891 | 6.37634 | -2.64% | 10.41243 |
| fp | 14 | 11.98177 | 11.87168 | -0.92% | 17.53423 |
| infra | 16 | 11.07180 | 9.79706 | -11.51% | 15.36517 |
| int | 37 | 14.75575 | 13.24824 | -10.22% | 24.12735 |
| media | 4 | 5.94517 | 5.75167 | -3.25% | 9.94778 |
| web | 26 | 16.98424 | 13.08632 | -22.95% | 18.20898 |

- per-trace better/worse vs TM: **95 / 10** (of 105)

best traces: web_24_trace -61.2%, web_20_trace -44.0%, int_36_trace -43.9%, int_15_trace -42.8%, web_11_trace -37.0%
worst traces: fp_8_trace +0.3%, fp_12_trace +0.5%, int_2_trace +0.6%, int_1_trace +0.6%, infra_8_trace +1.4%

| counter | sum over traces | mean per trace |
|---|---:|---:|
| override count | 68679538 | 654090.8 |
| rescue | 50934318 | 485088.7 |
| hurt | 17745220 | 169002.1 |

VERDICT: COMPLETE
