# full-set arm summary - `hybC_t2`

- traces: **105** (expected 105; missing 0)
- effect metric: `HYB MPKI`
- determinism gate: **PASS** (525 input-side checks vs `baseA_results/ALL.csv`, 0 mismatches)
- 1-bit identity vs `onebit_pc17`: **PASS** (315 checks, 0 mismatches)

| scope | n | base TM | HYB MPKI | delta | 1-bit |
|---|---:|---:|---:|---:|---:|
| ALL | 105 | 13.41542 | 12.92017 | -3.69% | 18.86245 |
| compress | 8 | 6.54891 | 6.78038 | +3.53% | 10.41243 |
| fp | 14 | 11.98177 | 12.34917 | +3.07% | 17.53423 |
| infra | 16 | 11.07180 | 10.94630 | -1.13% | 15.36517 |
| int | 37 | 14.75575 | 14.46870 | -1.95% | 24.12735 |
| media | 4 | 5.94517 | 6.13399 | +3.18% | 9.94778 |
| web | 26 | 16.98424 | 15.17186 | -10.67% | 18.20898 |

- per-trace better/worse vs TM: **59 / 46** (of 105)

best traces: web_24_trace -32.2%, web_20_trace -24.4%, web_11_trace -22.5%, int_15_trace -22.2%, int_36_trace -20.6%
worst traces: infra_4_trace +13.9%, infra_8_trace +15.8%, int_13_trace +16.2%, infra_7_trace +20.4%, web_7_trace +22.7%

| counter | sum over traces | mean per trace |
|---|---:|---:|
| override count | 56287045 | 536067.1 |
| rescue | 42245887 | 402341.8 |
| hurt | 14041158 | 133725.3 |

VERDICT: COMPLETE
