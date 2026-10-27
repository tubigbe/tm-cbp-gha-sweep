# 2026-10-26 T6 1-bit / hybrid - variant provenance

Repository: `tubigbe/tm-cbp-gha-sweep`
Base commit of this file: `2e390fa15b8cb8eb1d4c602ee6833463aa09027c`

`tm.cc` is byte-identical to the baseline in ALL arms; behaviour is selected
by macros in `tm.h` and `TM_MODE` in `tm_predictor.{h,cc}`.

Hybrid arms also print `override count` / `rescue` / `hurt`, i.e. how often the
hybrid departs from the 1-bit prediction and how that departure pays off.

| arm | file | sha256 |
|---|---|---|
| hybA_t1 | cond_branch_predictor_interface.cc | `e6cbc194b891a3d97f245f7486ba8eee817302456a5a7a37057c8e806f8b813f` |
| hybA_t1 | tm.h | `7af90a62fc4cb620bd54d72a2a594a2795b059e5134d554c64d46187734e6d3b` |
| hybA_t1 | tm_predictor.cc | `eb141831803f5d8d690dcb7ef5ac073467075128f4d51fdae9cbf5aaa76a9005` |
| hybA_t1 | tm_predictor.h | `0c4dac129acf2f5f7b19b64b2ee5d55742769aad84f4bd5ba9781a732875bcba` |
| hybA_t2 | cond_branch_predictor_interface.cc | `e6cbc194b891a3d97f245f7486ba8eee817302456a5a7a37057c8e806f8b813f` |
| hybA_t2 | tm.h | `0d0394e6e00f1b29b8f5e9eab513ac5c238d62964d5651b8248aaf283b50a4db` |
| hybA_t2 | tm_predictor.cc | `eb141831803f5d8d690dcb7ef5ac073467075128f4d51fdae9cbf5aaa76a9005` |
| hybA_t2 | tm_predictor.h | `0c4dac129acf2f5f7b19b64b2ee5d55742769aad84f4bd5ba9781a732875bcba` |
| hybA_t4 | cond_branch_predictor_interface.cc | `e6cbc194b891a3d97f245f7486ba8eee817302456a5a7a37057c8e806f8b813f` |
| hybA_t4 | tm.h | `0d5a444d28baf58dc25db821c5477ee7b643e7962e92749603a066913fd8866c` |
| hybA_t4 | tm_predictor.cc | `eb141831803f5d8d690dcb7ef5ac073467075128f4d51fdae9cbf5aaa76a9005` |
| hybA_t4 | tm_predictor.h | `0c4dac129acf2f5f7b19b64b2ee5d55742769aad84f4bd5ba9781a732875bcba` |
| hybA_t6 | cond_branch_predictor_interface.cc | `e6cbc194b891a3d97f245f7486ba8eee817302456a5a7a37057c8e806f8b813f` |
| hybA_t6 | tm.h | `b1c8cf48b84861d609a8507a8756ad37ae09885ab4c5facd8dd6faabb81fe906` |
| hybA_t6 | tm_predictor.cc | `eb141831803f5d8d690dcb7ef5ac073467075128f4d51fdae9cbf5aaa76a9005` |
| hybA_t6 | tm_predictor.h | `0c4dac129acf2f5f7b19b64b2ee5d55742769aad84f4bd5ba9781a732875bcba` |
| hybB | cond_branch_predictor_interface.cc | `e6cbc194b891a3d97f245f7486ba8eee817302456a5a7a37057c8e806f8b813f` |
| hybB | tm.h | `61bdf2853155e5ffaf410eb0898893f600394e4d51fb3081cabd1480bf2b2df3` |
| hybB | tm_predictor.cc | `eb141831803f5d8d690dcb7ef5ac073467075128f4d51fdae9cbf5aaa76a9005` |
| hybB | tm_predictor.h | `0c4dac129acf2f5f7b19b64b2ee5d55742769aad84f4bd5ba9781a732875bcba` |
| hybC_t2 | cond_branch_predictor_interface.cc | `e6cbc194b891a3d97f245f7486ba8eee817302456a5a7a37057c8e806f8b813f` |
| hybC_t2 | tm.h | `87615fd9eed7e41843f28ae9117c560122ba7c533d3b59d69b5f9684f5eef065` |
| hybC_t2 | tm_predictor.cc | `eb141831803f5d8d690dcb7ef5ac073467075128f4d51fdae9cbf5aaa76a9005` |
| hybC_t2 | tm_predictor.h | `0c4dac129acf2f5f7b19b64b2ee5d55742769aad84f4bd5ba9781a732875bcba` |
| hybC_t4 | cond_branch_predictor_interface.cc | `e6cbc194b891a3d97f245f7486ba8eee817302456a5a7a37057c8e806f8b813f` |
| hybC_t4 | tm.h | `0ce8fadb2329a94f14a3a37c90f42fd0cb8d4ad64558f7868dcd03d4b7632fe6` |
| hybC_t4 | tm_predictor.cc | `eb141831803f5d8d690dcb7ef5ac073467075128f4d51fdae9cbf5aaa76a9005` |
| hybC_t4 | tm_predictor.h | `0c4dac129acf2f5f7b19b64b2ee5d55742769aad84f4bd5ba9781a732875bcba` |
| onebit_gshare17 | cond_branch_predictor_interface.cc | `e6cbc194b891a3d97f245f7486ba8eee817302456a5a7a37057c8e806f8b813f` |
| onebit_gshare17 | tm.h | `2518a2e0f56782b82ec246662275c9398c11e2eee1d42ac3a13dd41ed8a7b2e9` |
| onebit_gshare17 | tm_predictor.cc | `eb141831803f5d8d690dcb7ef5ac073467075128f4d51fdae9cbf5aaa76a9005` |
| onebit_gshare17 | tm_predictor.h | `0c4dac129acf2f5f7b19b64b2ee5d55742769aad84f4bd5ba9781a732875bcba` |
| onebit_pc14 | cond_branch_predictor_interface.cc | `e6cbc194b891a3d97f245f7486ba8eee817302456a5a7a37057c8e806f8b813f` |
| onebit_pc14 | tm.h | `e497b73c1e17b0ae8369025abd4d206f6a6f8440ff7af837a30e473ec4921b8a` |
| onebit_pc14 | tm_predictor.cc | `eb141831803f5d8d690dcb7ef5ac073467075128f4d51fdae9cbf5aaa76a9005` |
| onebit_pc14 | tm_predictor.h | `0c4dac129acf2f5f7b19b64b2ee5d55742769aad84f4bd5ba9781a732875bcba` |
| onebit_pc17 | cond_branch_predictor_interface.cc | `e6cbc194b891a3d97f245f7486ba8eee817302456a5a7a37057c8e806f8b813f` |
| onebit_pc17 | tm.h | `c58a1bfa12c0a5af68e046bada518b8f2a37dc3f34f727338e6966a5d59b43a7` |
| onebit_pc17 | tm_predictor.cc | `eb141831803f5d8d690dcb7ef5ac073467075128f4d51fdae9cbf5aaa76a9005` |
| onebit_pc17 | tm_predictor.h | `0c4dac129acf2f5f7b19b64b2ee5d55742769aad84f4bd5ba9781a732875bcba` |
| tm_pc_only | cond_branch_predictor_interface.cc | `e6cbc194b891a3d97f245f7486ba8eee817302456a5a7a37057c8e806f8b813f` |
| tm_pc_only | tm.h | `bc3f7b88d40ca6038111a3c87f4475b8bec77d1f8873107f41671b9640f7512f` |
| tm_pc_only | tm_predictor.cc | `eb141831803f5d8d690dcb7ef5ac073467075128f4d51fdae9cbf5aaa76a9005` |
| tm_pc_only | tm_predictor.h | `0c4dac129acf2f5f7b19b64b2ee5d55742769aad84f4bd5ba9781a732875bcba` |

Baseline tm.cc sha256: `d13a27d3a808d04f07f5aa63c399ea36f6e6cb4de223cca8e95b822c4ab50982`
Baseline tm.h  sha256: `d2de1deb930c4efd2f2441c73ef87da144e0ad5433083949254e05c4a348df06`
