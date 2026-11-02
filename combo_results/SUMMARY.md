# full-set arm summary - `no_gh_1bit`

- traces: **6** (expected 6; missing 0)
- effect metric: `HYB MPKI`
- determinism gate: **PASS** (18 input-side checks vs `baseA_results/ALL.csv`, 0 mismatches)
- 1-bit identity vs `-`: **n/a**

| scope | n | base TM | HYB MPKI | delta | 1-bit |
|---|---:|---:|---:|---:|---:|
| ALL | 6 | 11.78138 | 10.53937 | -10.54% | 22.22314 |
| compress | 1 | 3.99088 | 3.68245 | -7.73% | 5.97934 |
| fp | 1 | 4.19113 | 4.29799 | +2.55% | 21.81890 |
| infra | 1 | 10.81520 | 10.70600 | -1.01% | 12.04110 |
| int | 1 | 26.09100 | 26.06870 | -0.09% | 71.23720 |
| media | 1 | 7.44238 | 7.22738 | -2.89% | 11.68170 |
| web | 1 | 18.15770 | 11.25370 | -38.02% | 10.58060 |

- per-trace better/worse vs TM: **5 / 1** (of 6)

best traces: web_11_trace -38.0%, compress_4_trace -7.7%, media_3_trace -2.9%, infra_14_trace -1.0%, int_1_trace -0.1%
worst traces: compress_4_trace -7.7%, media_3_trace -2.9%, infra_14_trace -1.0%, int_1_trace -0.1%, fp_4_trace +2.5%

| counter | sum over traces | mean per trace |
|---|---:|---:|
| override count | 3458634 | 576439.0 |
| rescue | 2780002 | 463333.7 |
| hurt | 678632 | 113105.3 |

VERDICT: COMPLETE
