# full-set arm summary - `no_gh_1bit`

- traces: **105** (expected 105; missing 0)
- effect metric: `HYB MPKI`
- determinism gate: **PASS** (315 input-side checks vs `baseA_results/ALL.csv`, 0 mismatches)
- 1-bit identity vs `-`: **n/a**

| scope | n | base TM | HYB MPKI | delta | 1-bit |
|---|---:|---:|---:|---:|---:|
| ALL | 105 | 13.41542 | 11.65545 | -13.12% | 18.86245 |
| compress | 8 | 6.54891 | 6.35689 | -2.93% | 10.41243 |
| fp | 14 | 11.98177 | 11.85460 | -1.06% | 17.53423 |
| infra | 16 | 11.07180 | 9.81872 | -11.32% | 15.36517 |
| int | 37 | 14.75575 | 13.20625 | -10.50% | 24.12735 |
| media | 4 | 5.94517 | 5.74817 | -3.31% | 9.94778 |
| web | 26 | 16.98424 | 13.01076 | -23.40% | 18.20898 |

- per-trace better/worse vs TM: **97 / 8** (of 105)

best traces: web_24_trace -61.4%, int_36_trace -44.4%, web_20_trace -44.1%, int_15_trace -43.2%, web_11_trace -38.0%
worst traces: fp_5_trace +0.7%, fp_8_trace +0.9%, int_13_trace +1.6%, fp_4_trace +2.5%, infra_8_trace +5.9%

| counter | sum over traces | mean per trace |
|---|---:|---:|
| override count | 68551089 | 652867.5 |
| rescue | 50928325 | 485031.7 |
| hurt | 17622764 | 167835.8 |

VERDICT: COMPLETE
