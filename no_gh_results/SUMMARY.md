# full-set arm summary - `no_gh`

- traces: **6** (expected 6; missing 0)
- effect metric: `TM MPKI`
- determinism gate: **PASS** (18 input-side checks vs `baseA_results/ALL.csv`, 0 mismatches)
- 1-bit identity vs `-`: **n/a**

| scope | n | base TM | TM MPKI | delta | 1-bit |
|---|---:|---:|---:|---:|---:|
| ALL | 6 | 11.78138 | 11.80723 | +0.22% | - |
| compress | 1 | 3.99088 | 4.00141 | +0.26% | - |
| fp | 1 | 4.19113 | 4.32323 | +3.15% | - |
| infra | 1 | 10.81520 | 10.84400 | +0.27% | - |
| int | 1 | 26.09100 | 26.27140 | +0.69% | - |
| media | 1 | 7.44238 | 7.40203 | -0.54% | - |
| web | 1 | 18.15770 | 18.00130 | -0.86% | - |

- per-trace better/worse vs TM: **2 / 4** (of 6)

best traces: web_11_trace -0.9%, media_3_trace -0.5%, compress_4_trace +0.3%, infra_14_trace +0.3%, int_1_trace +0.7%
worst traces: media_3_trace -0.5%, compress_4_trace +0.3%, infra_14_trace +0.3%, int_1_trace +0.7%, fp_4_trace +3.2%

VERDICT: COMPLETE
