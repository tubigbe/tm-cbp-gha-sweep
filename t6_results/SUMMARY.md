# T6 check: does the web_24 optimum generalise?

T6 tuning set, 4 configs. `(5,5)` is the original coupled TM.

| trace | (5,5) BASE | (2,5) | (3,3) | (5,2) |
|---|---:|---:|---:|---:|
| compress_4_trace | 3.9909 | 3.9496 | 4.0146 | 4.0790 |
| fp_4_trace | 4.1911 | 4.0891 | 4.2145 | 4.3251 |
| infra_14_trace | 10.8152 | 10.8771 | 11.0028 | 11.0723 |
| int_1_trace | 26.0910 | 27.7217 | 28.5605 | 29.0623 |
| media_3_trace | 7.4424 | 7.4842 | 7.6599 | 7.6915 |
| web_11_trace | 18.1577 | 17.5865 | 17.5561 | 17.5736 |

| **mean** | **11.7814** | **11.9514** | **12.1681** | **12.3006** |

- `(S=2, S_RELAX=5)`: mean **+1.44%** vs (5,5); better on 3/6 traces
- `(S=3, S_RELAX=3)`: mean **+3.28%** vs (5,5); better on 1/6 traces
- `(S=5, S_RELAX=2)`: mean **+4.41%** vs (5,5); better on 1/6 traces
