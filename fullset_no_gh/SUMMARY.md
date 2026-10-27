# full-set arm summary - `no_gh`

- traces: **105** (expected 105; missing 0)
- effect metric: `TM MPKI`
- determinism gate: **PASS** (315 input-side checks vs `baseA_results/ALL.csv`, 0 mismatches)
- 1-bit identity vs `-`: **n/a**

| scope | n | base TM | TM MPKI | delta | 1-bit |
|---|---:|---:|---:|---:|---:|
| ALL | 105 | 13.41542 | 13.36670 | -0.36% | - |
| compress | 8 | 6.54891 | 6.55069 | +0.03% | - |
| fp | 14 | 11.98177 | 11.94036 | -0.35% | - |
| infra | 16 | 11.07180 | 11.07685 | +0.05% | - |
| int | 37 | 14.75575 | 14.72043 | -0.24% | - |
| media | 4 | 5.94517 | 5.91714 | -0.47% | - |
| web | 26 | 16.98424 | 16.86073 | -0.73% | - |

- per-trace better/worse vs TM: **72 / 33** (of 105)

best traces: int_6_trace -2.8%, web_16_trace -1.9%, int_0_trace -1.8%, web_12_trace -1.7%, web_18_trace -1.7%
worst traces: int_12_trace +3.0%, fp_4_trace +3.2%, int_13_trace +3.5%, infra_8_trace +5.2%, int_14_trace +7.0%

VERDICT: COMPLETE
