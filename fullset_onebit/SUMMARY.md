# full-set arm summary - `onebit_pc17`

- traces: **105** (expected 105; missing 0)
- effect metric: `1bit MPKI`
- determinism gate: **PASS** (525 input-side checks vs `baseA_results/ALL.csv`, 0 mismatches)
- 1-bit identity vs `-`: **n/a**

| scope | n | base TM | 1bit MPKI | delta | 1-bit |
|---|---:|---:|---:|---:|---:|
| ALL | 105 | 13.41542 | 18.86245 | +40.60% | 18.86245 |
| compress | 8 | 6.54891 | 10.41243 | +58.99% | 10.41243 |
| fp | 14 | 11.98177 | 17.53423 | +46.34% | 17.53423 |
| infra | 16 | 11.07180 | 15.36517 | +38.78% | 15.36517 |
| int | 37 | 14.75575 | 24.12735 | +63.51% | 24.12735 |
| media | 4 | 5.94517 | 9.94778 | +67.33% | 9.94778 |
| web | 26 | 16.98424 | 18.20898 | +7.21% | 18.20898 |

- per-trace better/worse vs TM: **24 / 81** (of 105)

best traces: web_24_trace -60.9%, web_20_trace -47.8%, web_11_trace -41.7%, int_36_trace -30.6%, infra_12_trace -30.3%
worst traces: int_31_trace +258.7%, web_7_trace +262.2%, int_34_trace +292.0%, int_0_trace +367.7%, fp_4_trace +420.6%

VERDICT: COMPLETE
