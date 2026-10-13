# AGENTS.md — TM_CBP_SIM

Orientation for AI coding agents (and humans) working in this repository.
Everything below was verified by actually building and running the simulator, not inferred from docs.

<!-- engineering-log hook | 请勿删改本段 -->
> **本项目受《工程日志规程》约束。**
> 工程文档在 `.dsh/logs/` 下（**只允许追加**，不得编辑、不得删除任何已有条目）。
> 凡涉及工程日志的读取、追加、备份，**必须先加载 skill：`engineering-log`**。

---

> **本文档当前描述 `standalone_tm` 分支**（本地 HEAD 已领先 `origin/standalone_tm` `a120022` 若干**未 push** 的
> 文档 / 注释 commit；**预测器算法本身与 `a120022` 完全一致** —— 这些 commit 只加文档与注释，没动过一行逻辑）。
> 各分支的代码结构差别很大，切换分支后本文的 §7/§8/§9/§10 可能失效 —— 见 §1 的分支对照表，
> 以及 §12「分支操作」。`main` 分支的对应版本在 `git show main:AGENTS.md`。

---

## 0. 一页速览（中文）

- **这是什么**：用 **Tsetlin Machine (TM)** 做**条件分支方向预测**的研究/毕设 benchmark，宿主是 **CBP2025** 官方模拟器。本分支（`standalone_tm`）研究的是**把一个小 TM 当作独立预测器**，与同为 8 KB 量级的 **GShare** 和 **CBP2016 TAGE-SC-L (8.22 KB)** 对比，拼的是面积/能耗而不是绝对 MPKI。
- **代码在哪跑**：仓库物理位置在 **另一台 Linux 机器 `ku`** 的 `/data/tm_cbp_sim`，Windows 侧工作目录 `\\ku.tail391654.ts.net\tmsim` 只是它的 SMB 挂载（同一份文件的两个视角）。
- **绝对不要在 Windows 侧编译**：本机没有 `make`，MinGW 是 32 位且没有 zlib 头文件；仓库里的 `.o` / `libcbp.a` / `cbp` 全是 **x86-64 Linux ELF**。
- **编译/运行方式**：`ssh ku`，然后 `cd /data/tm_cbp_sim`，`make clean && make -j8`，`./cbp -E 1000000 <trace>.gz`。干净全量编译实测 **约 11 秒**。
- **本分支谁在被测**：`get_cond_dir_prediction()` 返回的是 **8 KB TAGE-SC-L** 的预测，所以模拟器原生表里的 `CondDirect` MPKI 是 **TAGE-SC-L 的**；TM 和 GShare 的 MPKI 是代码里手工打印的，**不会**出现在模拟器原生表里。
- **trace 已就位**：105 条官方训练 trace 已在 `training_traces/<category>/`（15 GB）。因为 `.gitignore` 的 `*.gz`，它们是 ignored 文件，**所有分支共用**。另有 2 条 sample trace 可做 15 秒冒烟测试。**别用 `git clean -x`** —— 那会删掉这 15 GB。
- **批量评测**：`python3 test_harness.py`（纯标准库，可用；本分支采集 `Integrated Predictor MPKI` / `TM MPKI` / `GShare MPKI`）。`cbp_provided_scripts/trace_exec_training_list.py` 需要 `pandas`，**`ku` 上没装**。
- **本项目的既定目标（必读）**：方向是 **IC 设计 × 机器学习** 交叉；**现阶段只做纯算法**，总目标是**把 TM 的预测正确率提上去**。硬件成本量化（路线 A：CBP-NG + HARCOM）是**后续**步骤，现在不要提前引入。详见 **§14 FYP 路线图**。
- **基线已就绪，别再重新下载或重跑**：105 条官方 trace 已就位（§5.1），全量基准已跑完并存档于 `.dsh/logs/baseline/`（§10）。**做任何改动前先看 §10** —— 那里有本机的权威回归数字，以及与原作者逐位一致的复现性证明。
- **练手项目的结论已搬进来（2026-10-09，新增）**：一个手写最小 TM 的练手项目跑了约 **20 万次训练**，查清了**反馈概率的两个真实 bug**、**`s`（惩罚概率）的机制**、以及**参数强耦合**；并给出 8 条针对本仓库 `tm.cc` 的**待验证假设**（其中"relax / push-out 拆开"只差一行改动）。入口：**`.dsh/logs/design/practice_tm_lessons.md`**（详见 **§15**）。
  ⚠️ **先读它的 §1**：练手项目的 `S`/`s` 与本仓库的 `S`/`NUM_STATES` **字母错位**，读反会得出相反结论。
- **表示能力诊断已完成（2026-10-09，新增）**：用现成的 `DUMP_STATE_CSV` + 输入组消融，实测出**当前 TM 的实际行为** —— 它不是全局历史预测器，而是「**32 条规则的 PC / 4 位局部历史预测器**」：去掉 24 位全局历史，`int_0` 上 MPKI 反而**改善 2.0%**；去掉 4 位局部历史涨 **65.6%**；去掉 32 位路径历史几乎无影响。机制：relax 把子句触发频率钉在 `q* = 1/S = 20%`，稀有的长历史合取式**一形成就被拆掉**。入口：**`.dsh/logs/design/tm_bp_diagnosis.md`**（详见 **§16**）。
  ⚠️ **不要再靠扫 `T`/`s`/`NUM_CLAUSES` 去追赶 TAGE** —— 这 3× 的差距是**结构性的**，不是超参数问题。
- **测试集与调参协议（2026-10-13，新增）**：调参**只用 T6**（`runlist_tune.txt`，6 条，每领域一条）；**结论只能来自 V13**（`runlist_validate.txt`，13 条）；**全集 105**（`test_runlist.txt`）是开启硬件设计前的最后一道闸。纪律见 **§17**，完整规范 + 每条基线数字见 **`.dsh/logs/design/test_sets_and_protocol.md`**。**动任何参数之前必读。**
- **本文件受工作区指令预算约束（≲64 KB，超出会被截断，尾部的 §17 最先被砍）**：**新增内容请写进 `.dsh/logs/design/`**，本文件只留索引。

---

## 1. What this repository is

A research fork of the CBP2025 simulation framework used to evaluate **Tsetlin Machines as branch direction predictors**.

- Upstream base: <https://github.com/ramisheikh/cbp2025>
- This fork: <https://github.com/mihkel-reb/tm_cbp_sim> (`origin`)
- Full research write-up: **`README.md` exists only on `main`/`zhang`, not on this branch.** Read it with `git show main:README.md` — it contains the findings tables, the 9 TM input configurations evaluated, and the list of selection mechanisms tried and rejected. **Do not skip it.**

### Branch layout

| Branch | Idea | Base predictor | Interface returns |
| --- | --- | --- | --- |
| **`standalone_tm`** (checked out) | Small TM as the **sole** predictor, compared against equal-ish-budget GShare and 8 KB TAGE-SC-L | CBP2016 TAGE-SC-L **8.22 KB** (`cbp2016_tage_sc_l_8kb.h`) | **TAGE-SC-L** (TM/GShare only record stats) |
| `main` | TM as an **H2P specialist** beside a reduced TAGE-SC-2025, plus a selector | TAGE-SC-2025 **169.69 KB** (`my_cond_branch_predictor.h`) | **selector hybrid** |
| `classify_tage_wrong` | TM classifies *whether* TAGE-SC will be wrong | — | — (largely abandoned) |
| `papers` | Branch-prediction / TAGE papers | — | reference only |
| `runs` | Raw CSV dumps of promising results | — | data only |

Local branches on `ku`: `main`, `standalone_tm`, and **`zhang`** (`45cd9e0 "new start, new hope"`; a personal branch holding `AGENTS.md`, `.dsh/logs/工程日志.md`, `logs/`, and the `cbp` binary). `zhang` is based on `main`.

> **Branch divergence is large.** Switching between `main` and `standalone_tm` adds/removes whole files:
> `standalone_tm` has `tm_predictor.*`, `gshare_predictor.*`, `cbp2016_tage_sc_l_8kb.h`;
> `main` has `tm_side_predictor.*`, `selector.*`, `tage_sc_state.h`, `my_cond_branch_predictor.h`, and `README.md`.
> **Always `make clean && make -j8` after switching branches** — stale `.o` files from the other branch will otherwise break the link.

`lib/` (the simulator core) is **byte-identical between `main` and `standalone_tm`**; only the contestant-side files differ.

---

## 2. Execution environment (read this before running anything)

### 2.1 Topology

```
   Windows workstation            Tailscale              Linux compute host
   ┌────────────────────┐                                ┌──────────────────────────┐
   │ hostname: muuhaha  │      100.98.175.26             │ hostname: ku             │
   │ (this DSH session) │◄──────────────────────────────►│ Ubuntu, x86-64           │
   │                    │                                │ AMD Ryzen 7 3750H        │
   │  CIFS/SMB mount    │                                │ 4 cores / 8 threads      │
   │  \\ku...\tmsim ────┼───────────────────────────────►│ 30 GB RAM                │
   │  == /data/tm_cbp_sim on ku (same files!)            │ /data: 358 GB, 311 GB free│
   └────────────────────┘                                └──────────────────────────┘
```

- The working directory `\\ku.tail391654.ts.net\tmsim` **is** `/data/tm_cbp_sim` on `ku`. Same inodes, two views — edit a file on either side and the other sees it immediately.
- The SMB share is defined in `/etc/samba/smb.conf` as `[tmsim]`; setup script `~/add_samba_tmsim.sh` on `ku`.
- **`ku` is the only machine that can build and run this project.**

### 2.2 Toolchain

| | `ku` (Linux) — **use this** | `muuhaha` (Windows) — cannot build |
| --- | --- | --- |
| g++ | 15.2.0 (`/usr/bin/g++`), x86-64 | 15.2.0 MinGW-w64 **i686 (32-bit)**, `E:\gcc\mingw32` |
| make | GNU Make 4.4.1 | **not installed** |
| zlib dev | `/usr/include/zlib.h`, `libz.so`/`libz.a` ✅ | **no `zlib.h`, no `libz.a`** (only `libz.dll`) ❌ |
| python3 | 3.14.4 | 3.14.3 |
| pandas | ❌ not installed | ✅ 2.3.3 |
| gdown | ❌ not installed | ❌ not installed |
| cores | 8 threads | 16 threads |
| notes | `cbp` is `ELF 64-bit LSB pie executable, x86-64` | WSL `Ubuntu` exists, but **cannot see the UNC path** (`wsl` fails to translate `\\ku...`) |

### 2.3 How to run commands on `ku`

SSH key auth is already configured. `~/.ssh/config` on Windows has:

```
Host ku
    HostName 100.98.175.26
    User chenyoo
```

```powershell
ssh ku 'cd /data/tm_cbp_sim && make -j8'
```

> **Two quoting traps** — both cost real debugging time here:
>
> 1. **CRLF.** PowerShell here-strings are CRLF, and PowerShell appends CRLF to every line it pipes into a native process's stdin. Feeding a multi-line script via `ssh ku bash -s` delivers stray `\r` that corrupts the *last argument of a line* (symptoms: `head: parse error: 0`, `gep: command not found`, `cat: '...sh\r': No such file or directory`). **Fix** — note the doubled backslash so `tr` receives `\r`, not a literal `r`:
>    ```powershell
>    $script = @'
>    cd /data/tm_cbp_sim && ./cbp sample_traces/int/sample_int_trace.gz
>    '@
>    $script | ssh ku 'tr -d "\\r" | bash -s'
>    ```
> 2. **`ssh ku '...'` strips inner quotes.** PowerShell removes the outer single quotes and ssh joins the remaining arguments with spaces, so any `"`, `|`, `(`, or `$` inside gets re-interpreted by the remote shell — or silently eaten locally. For anything beyond a trivial one-liner, **use the here-string + `bash -s` form above**, or write a script file and run `ssh ku bash /data/tm_cbp_sim/<script>.sh`.
>
> Diagnosis hint: if a bash `for` loop over a list prints blanks and every `git cat-file -e` "succeeds", the loop variable was eaten locally — the check is meaningless, not passing.

### 2.4 Git quirk from the Windows side

The SMB mount is owned by `ku`'s UID, which Windows does not map, so plain `git` fails with
`fatal: detected dubious ownership`. Prefix with the override:

```powershell
git -c safe.directory='*' status
git -c safe.directory='*' log --oneline -20
```

Over SSH on `ku` there is no such problem. (Do **not** permanently add `safe.directory` to the global config just for this.)

---

## 3. Build

Two-stage build. Run from the repo root **on `ku`**.

```bash
cd /data/tm_cbp_sim
make clean && make -j8      # full clean rebuild ≈ 11 s wall on ku
```

| Stage | What it does |
| --- | --- |
| root `Makefile` | Compiles the *contestant* side with `-std=c++17 -O3`, then links `cbp` with `-L./lib -lcbp -lz` |
| `lib/Makefile` | Builds the *simulator core* into `lib/libcbp.a` (`cbp.o uarchsim.o cache.o bp.o parameters.o my_value_predictor.o resource_schedule.o gzstream.o`) with `-I.. -I../lib -DGZSTREAM_NAMESPACE=gz -O3` |

The root `Makefile`'s object list is **branch-specific**:

| Branch | `OBJ` | `DEPS` |
| --- | --- | --- |
| **`standalone_tm`** | `cond_branch_predictor_interface.o tm.o tm_predictor.o gshare_predictor.o` | `cbp.h cond_branch_predictor_interface.h tm.h tm_predictor.h gshare_predictor.h cbp2016_tage_sc_l_8kb.h` |
| `main` | `cond_branch_predictor_interface.o tm.o tm_side_predictor.o selector.o` | `... my_cond_branch_predictor.h tm_side_predictor.h selector.h` |

- `lib` is an **order-only** prerequisite of `cbp` (`cbp: $(OBJ) | lib`), so editing only `lib/` sources will **not** relink `cbp`. Always `make clean` after touching `lib/`, or delete `cbp` explicitly.
- ⚠️ **本仓库的 `make` 不跟踪任何头文件依赖 —— 改 `.h` 后必须 `make clean`。**
  根 `Makefile` 的 `DEPS` 里列了 `cond_branch_predictor_interface.h`，而**该文件在本仓库从来不存在**
  （`git ls-files | grep cond_branch` 只有 `.cc`；`git log --all` 查无此文件）。GNU make 在隐式规则搜索时
  要求模式规则的前置条件都存在，于是判定 `%.o: %.cc $(DEPS)` **不适用**、回退到内置的 `%.o: %.cc`（**没有 DEPS**）。
  后果：改 `.cc` 会重编，**改 `.h` 不会**；而 `tm.h` 是所有旋钮（`NUM_CLAUSES`/`NUM_STATES`/`S`/`THRESHOLD`/输入配置）所在，
  于是会得到「改旋钮 → `make` → 结果与 §10.1 基线**逐位相同** → 以为旋钮无效」这个**看起来极其可信的假结论**。
  **实测证据**：打开 `tm.h` 的 `DUMP_STATE_CSV` 后跑 `make -j8`，`cbp` 与 `tm.o` 的 mtime 停在旧时间完全不动；
  `make clean && make -j8` 才更新。**唯一可信的姿势是 `make clean && make -j8`**（全量约 11 s，代价可接受）。
  修法与「暂不修改」的决定：见 **§16.3**。
- `DEBUG=1 make` adds `-ggdb3` to both stages.
- **Dependencies:** g++ ≥ C++17, GNU make, **zlib development package** (`-lz`; used by the bundled LGPL `gzstream`). `lib/spdlog` is vendored header-only — no external install needed. No other third-party libraries.
- `my_cond_branch_predictor.cc` does **not** exist on any branch; predictors are header-only here by design (deviating from the CBP2025 convention — see `main`'s README §General Notes).

---

## 4. Run

```bash
cd /data/tm_cbp_sim
./cbp -E 1000000 training_traces/int/int_0_trace.gz
```

The trace argument is **required** and must be **gzip-compressed** (read through `lib/gzstream`).

### CLI options (`lib/cbp.cc::parseargs`)

| Flag | Meaning |
| --- | --- |
| `<trace.gz>` | **required**, positional, gzip trace |
| `-E <n>` | enable per-epoch conditional-branch stats every `n` instructions (harness uses `1000000`) |
| `-d` | perfect data cache |
| `-b` | perfect branch prediction (all branch types) |
| `-P` | enable stride prefetcher in L1D |
| `-F <fw>,<fnb>,<sai>,<sat>,<sic>` | fetch width / num branches / stop-at-indirect / stop-at-taken / model icache |
| `-I <log2_ic_size>,<assoc>,<blocksize>` | L1 I-cache config |
| `-D <13 values>` | L1$/L2$/L3$/main-memory geometry and latencies |
| `-w <window_size>` | reorder window |
| `-M <n>` / `-A <n>` | LD/ST lanes / ALU lanes |

`-i` and `-f` are commented out in this version. Running `./cbp` with no arguments prints the usage block and exits 0.

### What to read in the output

1. **`===== Standalone TM Stats =====`** — printed by `tm_predictor.cc`: `TM wrong`, `TM right`, `TM accuracy`, **`TM MPKI`**, `Measured # of instructions`.
2. **`===== Standalone GShare Stats =====`** — printed by `gshare_predictor.cc`: `GShare wrong/right/accuracy`, **`GShare MPKI`**.
3. On startup, each predictor prints its own size:
   - `GShare size: 65551 bits, 8.00183 KB` (from `gshare_predictor.cc`)
   - `(TOTAL 2016TAGE-SC-L Size 67349 bits 8.22 KB)` (from `cbp2016_tage_sc_l_8kb.h`; `PRINTSIZE` is enabled)
   - `TM initialised with size 5184 bytes (5.06 Kbytes)` (from `tm.cc`)
4. **`BRANCH PREDICTION MEASUREMENTS (Full Simulation …)`** — the simulator's own table. Because `get_cond_dir_prediction()` returns the **8 KB TAGE-SC-L** prediction on this branch, the `CondDirect` row is **TAGE-SC-L's** MPKI, *not* the TM's. This is the row `test_harness.py` scrapes as `Integrated Predictor MPKI`.
5. `DIRECT CONDITIONAL BRANCH PREDICTION MEASUREMENTS` appears in several variants (Last 10M / Last 25M / **50 Perc instructions** / Full Simulation / Per Epoch). The **50 Perc** variant is the official CBP2025 warm-up convention and is what `cbp_provided_scripts/trace_exec_training_list.py` parses.
6. **No CSV side effect on this branch:** `DUMP_STATE_CSV` is **commented out** in `tm.h`. A leftover `tm_ta_states.csv` may exist in the repo root from a `main`-branch run — it is stale, not regenerated here.

---

## 5. Traces

`training_traces/<category>/` holds a tracked `readme.txt` (Arm copyright notice). The traces themselves are **git-ignored** (`*.gz`) and are downloaded separately.

### 5.1 Official training set — 105 traces ✅ **已下载并就位**

**状态（2026-09-29）：105 条 trace 已在 `training_traces/<category>/`，共 15 GB。**

因为 `.gitignore` 有 `*.gz`，它们是 **ignored 文件** —— **所有分支共用**：`git checkout` 切换分支时既不会被删也不会被动，`test_harness.py` 与 `test_runlist.txt` 在所有分支都无需改一行。这正是把它们放在 `training_traces/` 而不是别处的原因。

> ⚠️ **`git clean -xfd` 会连 ignored 文件一起删掉这 15 GB。别对仓库用 `-x`。**

**只有在需要重新获取时**才执行以下步骤：

```bash
cd /data/tm_cbp_sim/training_traces
# gdown 曾装在一个 venv 里（/data/cbp_trace_staging/gdownenv），不在系统 python 中：
python3 -m venv /path/to/gdownenv && /path/to/gdownenv/bin/pip install gdown
/path/to/gdownenv/bin/gdown --folder https://drive.google.com/drive/folders/10CL13RGDW3zn-Dx7L0ineRvl7EpRsZDW -O <staging>
tar -xJf <staging>/int.tar.xz -C <staging>/x   # 六个包：compress fp infra int media web
```

Google Drive 文件夹内容：**6 个分类 `.tar.xz`**（`int` 5.08 G / `web` 2.03 G / `fp` 1.95 G / `infra` 1.60 G / `compress` 1.47 G / `media` 409 M，共 **12.55 GB**）+ 一份 `CBP2025-data-dependent-branch-profiles.pdf`（Arm 的数据相关分支特征分析，见 §11）+ logo + readme。

解包后的 `.gz` 按**文件名前缀**归类（`int_0_trace.gz` → `int/`）。

| Category | Traces | | Category | Traces |
| --- | ---: | --- | --- | ---: |
| `int` | 37 | | `fp` | 14 |
| `web` | 26 | | `compress` | 8 |
| `infra` | 16 | | `media` | 4 |

`test_runlist.txt` lists exactly these 105 names, **without** the `.gz` suffix (identical on both branches).

Individual traces are ~90–210 MB gzipped; total **14.0 GB**. `/data` has 311 GB free.

### 5.2 Sample traces — present in the working tree ✅

Two 1M-instruction sample traces downloaded from upstream live in `sample_traces/`:

```
sample_traces/fp/sample_fp_trace.gz    1.2 MB   (997,741 instrs, ~7 s)
sample_traces/int/sample_int_trace.gz  1.4 MB   (997,301 instrs, ~7 s)
```

They are **untracked** (ignored via `*.gz`), so they survive branch switches. Smoke test:

```bash
cd /data/tm_cbp_sim
./cbp -E 1000000 sample_traces/int/sample_int_trace.gz
```

`test_harness.py` walks `training_traces/` only, so these samples are **not** picked up by the harness — invoke `./cbp` directly, or copy them under `training_traces/{int,fp}/`.

---

## 6. Batch evaluation

### 6.1 `test_harness.py` — use this one

Pure Python standard library (`os`, `subprocess`, `csv`, `concurrent.futures`). Runs every trace named in `test_runlist.txt`, resolved by basename under `training_traces/`, and writes `run_<YYYYmmdd_HHMMSS>.csv`.

```bash
cd /data/tm_cbp_sim
python3 test_harness.py
```

- Command per trace: `./cbp -E 1000000 <path>` (uses `./cbp.exe` if `os.name == "nt"`).
- **`NUM_PARALLEL = 32` by default — tune this down.** `ku` has 8 threads, so set it to `8`. (The README's "~25 min on an AWS `c8a.8xlarge` with `NUM_PARALLEL = 32`" assumes 32 real cores.)
- **`STATS_TO_COLLECT` differs per branch** — scrape keys are matched by exact `startswith(stat + ":")`:
  - `standalone_tm`: `Integrated Predictor MPKI` (= `CondDirect` row), `TM MPKI`, `GShare MPKI`
  - `main`: `Integrated Predictor MPKI`, `TM overrides`, `Perfect-Select Hybrid MPKI`
  If you rename any of those prints, update `STATS_TO_COLLECT` or the CSV silently loses the column value.
- A trace that fails to locate returns `None` and is reported as `<name>: failed`.

**实测全量耗时（2026-09-29，见 §10.1）：** 105 条、8 并发，**9044 s ≈ 2 h 31 min，0 错误**。
上游参考硬件的单线程串行估算是 12.5 h（均值 ~429 s/trace）；`ku` 上 `int_0` 单条 279 s，与参考硬件几乎同速。

> **建议不要直接用 `test_harness.py` 做长扫描。** 它只在最后写一个 CSV：中途挂掉要从头重跑，而且**丢弃原始 stdout**（官方 **50 Perc** 指标只能从原始输出解析）。
> 本次基线用的是「逐条存 stdout + 按完成标记断点续跑」的方式，脚本在 `/data/cbp_trace_staging/{one.sh,sweep.sh}`，105 份原始日志在 `/data/cbp_trace_staging/trace_logs/`。**改 `tm.h` 后重跑时请沿用这套**，否则失败一次就白等 2.5 小时。

### 6.2 `cbp_provided_scripts/trace_exec_training_list.py` — upstream script, needs pandas

Organisers' script: patched for Windows paths and `shell=False`, runs **serially**, parses the **50 Perc** section into a 29-column CSV with per-workload aggregates.

```bash
python3 trace_exec_training_list.py --trace_dir sample_traces/ --results_dir sample_results
```

**Blocked on `ku`:** `import pandas` → `ModuleNotFoundError`. Install with `pip install pandas`, or prefer `test_harness.py`. It skips traces whose `.log` already exists, so it is resumable.

---

## 7. Code map (`standalone_tm`)

### 7.1 Files you will actually edit

| File | Role |
| --- | --- |
| **`tm.h`** | TM shape and hyperparameters. On **this branch**: `NUM_INPUTS 81`, `NUM_CLAUSES 32`, `NUM_STATES 100`, `THRESHOLD 6`, `S 5`. Input layout (`TM_PC_BITS 21`, `TM_G_HIST_BITS 24`, `TM_LOCAL_BITS 4`, `TM_PATH_BRANCHES 4`, `TM_PATH_PC_BITS 7`, `TM_LOCAL_ENTRIES 1024`, PC start bit 2). `typedef struct { uint8_t automata[NUM_CLAUSES][NUM_INPUTS*2]; } tm_t;` → **sizeof = 5,184 B = 5.06 KB**. `DUMP_STATE_CSV` is **commented out** here (on `main` it is enabled). |
| **`tm.cc`** | TM core, identical logic across branches: `tm_init` / `tm_vote` / `tm_predict` / `tm_update` (Type-I and Type-II feedback), deterministic RNG (`std::mt19937 rng(1u)`), optional TA-state CSV dump. `TM_INPUT_NAMES[]` labels the 81 inputs. |
| **`tm_predictor.h/.cc`** | `class TMPredictor` — the standalone predictor. `assemble_input()` builds the 81-bit vector; `predict()` snapshots input + prediction under the branch's unique id; `resolved_update()` scores and **trains on every branch** (`// standalone TM trains on every branch`). `print_stats()` emits accuracy + MPKI. (This is the branch-local sibling of `main`'s `tm_side_predictor.*`, which instead trains only on TAGE-SC misses.) |
| **`gshare_predictor.h/.cc`** | `class GSharePredictor` — the baseline. `GSHARE_ENTRIES 32768`, `GSHARE_HISTORY_BITS 15`, 2-bit saturating counters, index = `(pc>>2) ^ g_hist`. |
| **`cbp2016_tage_sc_l_8kb.h`** | The 8.22 KB CBP2016 TAGE-SC-L, 1,586 lines, header-only, global object `cbp2016_tage_sc_l_8kb`. This is the predictor **actually wired into the simulator interface** on this branch. `PRINTSIZE` is on. Note its `history_update` / `TrackOtherInst` take an extra `pred_dir` argument compared with `main`'s `my_cond_branch_predictor.h`. |
| **`cond_branch_predictor_interface.cc`** | The 10 CBP2025 callbacks. Owns static `TMPredictor` and `GSharePredictor`, defines `get_unique_inst_id()` **locally** (since `my_cond_branch_predictor.h` is absent here), and in `get_cond_dir_prediction()` runs all three predictors but **returns `tage_8kb_prediction`**. |
| **`cbp.h`** | **Frozen interface contract.** Do not change signatures. |
| **`test_harness.py`** / **`test_runlist.txt`** | Batch runner + the 105-trace list. |

### 7.2 Simulator core (`lib/`) — treat as read-mostly, identical on both branches

`cbp.cc` (main + CLI) · `uarchsim.{h,cc}` (pipeline, the `step()` loop) · `bp.{h,cc}` (branch stats/sections) · `cache.{h,cc}` · `parameters.{h,cc}` (globals + defaults) · `resource_schedule.{h,cc}` · `trace_reader.h` (gzip trace decoder) · `gzstream.{h,cc}` (LGPL, zlib) · `ittage.h`, `stride_prefetcher.h`, `fifo.h`, `my_value_predictor.*` (unused value-prediction path) · `spdlog/` (vendored, header-only) · `sim_common_structs.h` (`InstClass`, `DecodeInfo`, `ExecuteInfo`).

### 7.3 Sizes, as built and reported

| Predictor | Reported size | Notes |
| --- | --- | --- |
| TM | **5.06 KB** (5,184 B) | 32 clauses × 81 inputs × 2 literals × 1 B |
| GShare | **8.00183 KB** (65,551 bits) | *accounted* as 2 bits/entry + 15-bit history |
| TAGE-SC-L | **8.22 KB** (67,349 bits) | CBP2016 winner, scaled down |

> **Implementational caveat worth knowing before making area claims:** `GSharePredictor::table` is declared
> `std::array<uint8_t, 32768>` — one **byte** per entry — while `init()` accounts it as **2 bits** per entry.
> The reported 8 KB is the *architectural* budget; the actual in-memory footprint is **32 KB**, 4× larger.
> The TM's 5.06 KB figure, by contrast, is the real `sizeof(tm_t)`. Compare them with that in mind.

---

## 8. Data flow (per conditional branch)

```
fetch ──► notify_instr_fetch          → total_instructions++  (piece == 0)
          │
predict ─► get_cond_dir_prediction
          │     tage_8kb_prediction = cbp2016_tage_sc_l_8kb.predict(seq_no, piece, pc)
          │     prediction_id       = get_unique_inst_id(seq_no, piece)
          │     tm_prediction       = tm_predictor.predict(prediction_id, pc)
          │                              └─ assemble_input(pc) + snapshot input & prediction
          │     gshare_predictor.predict(prediction_id, pc)      ← result discarded
          ▼     return tage_8kb_prediction   ← the simulator measures TAGE-SC-L, not the TM
spec ────► spec_update                 → cbp2016_tage_sc_l_8kb.history_update / TrackOtherInst
          │                              (both take pred_dir as well as resolve_dir here)
execute ─► notify_instr_execute_resolve
          │     cbp2016_tage_sc_l_8kb.update(...)
          │     tm_predictor.resolved_update(prediction_id, resolve_dir)
          │       ├─ score tm_right / tm_wrong
          │       ├─ tm_update(tm, snapshot_input, resolve_dir)   EVERY branch (unconditional)
          │       └─ rotate g_hist / local_history / prev_branch_{pc,dir}
          │     gshare_predictor.resolved_update(prediction_id, resolve_dir)
          │       ├─ score gshare_right / gshare_wrong
          │       ├─ update 2-bit counter
          │       └─ rotate its own g_hist
          ▼
end ─────► endCondDirPredictor → tm_predictor.print_stats(), gshare_predictor.print_stats(),
                                 cbp2016_tage_sc_l_8kb.terminate()
```

**Why snapshots matter:** the TM is trained with the *exact* 81-bit input vector that existed at prediction time, not the input at resolution time. Both predictors keep an `unordered_map<prediction_id, snapshot_t>` for in-flight branches. Each resolved branch produces exactly one TM update — there is no replay buffer and no batch training.

**Note the two independent histories.** `TMPredictor` and `GSharePredictor` each maintain their own `g_hist`; the TM's is 24 bits, GShare's is 15 bits. Neither reads the other's, and neither reads TAGE-SC-L's history.

---

## 9. Invariants and gotchas

1. **`cbp.h` signatures are frozen.** Required by the CBP2025 organisers. Same for the `extern` contract.
2. **The simulator does not measure the TM on this branch.** `get_cond_dir_prediction()` returns the 8 KB TAGE-SC-L prediction, so the `CondDirect` MPKI row is TAGE-SC-L's. Use the manually printed `TM MPKI` / `GShare MPKI` for the TM/GShare comparison. Do not report `CondDirect` as "the TM's MPKI".
3. **Branch switching requires `make clean`.** `OBJ`/`DEPS` differ per branch and the source files themselves differ; stale objects from the other branch will fail to link or silently mix architectures.
4. **TM input width is enforced by a `static_assert`** in `tm_predictor.cc`:
   `TM_PC_BITS + TM_G_HIST_BITS + TM_LOCAL_BITS + TM_PATH_BRANCHES*(TM_PATH_PC_BITS+1) == NUM_INPUTS`.
   Change `tm.h`'s input config and this fires. You must *also* hand-edit `TM_INPUT_NAMES[]` in `tm.cc` — a second `static_assert` guards its length. Nothing auto-generates it.
5. **GShare's accounting ≠ its footprint** (see §7.3). Don't quote 8 KB as the GShare's memory cost without checking.
6. **Platform-dependent results.** `rand_01()` uses `std::mt19937` seeded with `1` — deterministic on a given libstdc++, but the README documents small measurable differences going from UCRT64/Windows to Ubuntu. **Never compare MPKI across platforms; always re-baseline on `ku`.**
7. **`make` will not relink after `lib/` edits** (order-only prerequisite). Use `make clean && make`.
8. **No CSV dump on this branch** — `DUMP_STATE_CSV` is commented out in `tm.h`. A `tm_ta_states.csv` in the repo root is a leftover from a `main` run. Re-enable the define if you want TA-state dumps (useful for analysing what the TM learned).
9. **Git-ignored:** `*.o`, `*.a`, `*.exe`, `*.csv`, `*.gz`, `sample_results/`, `.vscode/`, and **`/cbp`** (added 2026-09-29 — `zhang` had accidentally committed the binary before that; it is 536 KB and fully rebuildable in 11 s).
   Note `*.gz` also covers all 105 traces: **`git clean -xfd` would delete 15 GB of them.**
10. **Untracked files follow you across branches.** `AGENTS.md`, `.dsh/`, `sample_traces/`, `cbp` are untracked on this branch, so `git checkout` leaves them alone. Conversely, going **from a branch that tracks them to one that doesn't deletes them from the working tree** — see §12.
11. **Snapshot maps may leak.** `prediction_snapshots` are only erased when a branch resolves. Predictions made on a wrong path that is squashed may never reach `notify_instr_execute_resolve`, so their entries could persist. Nobody has verified this — if you see memory growth over long traces, this is the first place to look. (Same pattern in `main`'s predictors.)
12. **Traces are highly non-stationary.** The README notes that pre-training the TM or carrying TA state across runs did not help, because learned patterns stop matching later phases of the same trace.
13. **行尾陷阱：从 Windows 侧编辑会炸掉 diff。** 同学写的预测器文件是 **CRLF**（`tm.h`、`tm_predictor.*`、`gshare_predictor.cc`、`test_harness.py`；只有未被改动的上游 `cond_branch_predictor_interface.cc` 是 LF），并且 `tm.cc` / `tm_predictor.cc` 的**最后一行没有末尾换行符**。仓库**没有** `.gitattributes`，`core.autocrlf` 与 `core.eol` 均未设置。后果：用 LF 写回这些文件会**静默重写整份文件的行尾**，`git diff` 从"加几行"变成"删 243 行 / 增 447 行"（实测数字）。**改完必须用 `git diff --numstat <file>` 检查删除数是否为 0**；不为 0 就先修行尾、再谈内容。（所有者 2026-10-09 决定暂不处理，见 §16.3。）
14. **RNG 调用顺序是隐式状态，重构会改结果。** `tm.cc` 的 `rand_01()` 固定种子 `1u`，但每一步调用它的**次数与顺序**决定了后续所有随机数：`tm_fb_type2` 一次都不调，`tm_fb_type1` 对 162 个文字逐个调用，`tm_update` 对 32 个子句各调用一次。任何"看起来无害"的重构（换循环顺序、提前 return、挪动一次抽样）都会改变整条随机序列、结果全变 ⇒ **A/B 实验必须用 commit 锁定代码版本**（用 `git show <rev>:<file>` 取出并核对 blob，不要信工作区）。
15. **`tm_eval_clause` 的空子句在两条路径上不对称。** `predict = true`（推理，`tm_vote` 调用）时空子句**不投票**；`predict = false`（训练，`tm_update` 调用）时空子句**算作触发**。这个不对称正是机器能从"全空"启动的机制：初始 `vote = 0` ⇒ `p = 0.5` ⇒ 空子句拿到 Type I 反馈并开始招募文字。但 Granmo 参考实现与练手项目在**两条路径上都是恒真**（都会投票）—— **是否有意为之尚未确认**（§15.2 第 3 条）。

---

## 10. Verified baseline — `standalone_tm`

### 10.1 全量基线（105 条）— **权威回归参照**

2026-09-29 在 `ku` 上实测。代码 = commit `6e6d30a`（= `origin/standalone_tm` `a120022` + 文档 commit，**未改任何预测器代码**），
`make clean && make -j8`，g++ 15.2.0 `-O3`，命令 `./cbp -E 1000000 <trace>.gz`，**8 并发，全量 9044 s ≈ 2 h 31 min，0 错误**。

| 产物 | 位置 |
| --- | --- |
| 本机基线 CSV（105 行） | **`.dsh/logs/baseline/standalone_tm_6e6d30a_ku_20260929.csv`** |
| 逐条原始 stdout（105 份） | `/data/cbp_trace_staging/trace_logs/<trace>.log` ← 可用于重算官方 **50 Perc** 指标、可断点续跑 |
| sweep 日志 | `.dsh/logs/baseline/sweep.log` |

**总体算术平均 MPKI：**

| 预测器 | 大小 | MPKI | 相对 TAGE-SC-L |
| --- | --- | ---: | ---: |
| 8 KB TAGE-SC-L | 8.22 KB | **4.6880** | 1.00× |
| **5.06 KB TM** | 5.06 KB | **13.4154** | 2.86× |
| 8 KB GShare | 8.00 KB (arch.) | **22.0221** | 4.70× |

**按类别平均 MPKI：**

| 类别 | 条数 | 8KB TAGE-SC-L | 5.06KB TM | 8KB GShare | TM/GShare |
| --- | ---: | ---: | ---: | ---: | ---: |
| `int` | 37 | 5.7623 | 14.7557 | 26.1007 | 0.565 |
| `fp` | 14 | 4.5026 | 11.9818 | 17.6325 | 0.680 |
| `web` | 26 | 5.1588 | 16.9842 | 26.7348 | 0.635 |
| `media` | 4 | 1.3807 | 5.9452 | 9.2205 | 0.645 |
| `compress` | 8 | 2.9830 | 6.5489 | 11.0463 | 0.593 |
| `infra` | 16 | 3.2801 | 11.0718 | 17.4611 | 0.634 |
| **全部** | **105** | **4.6880** | **13.4154** | **22.0221** | **0.609** |

**关键观察：**

- **TM 逐条赢了 GShare 99/105 条（94.3 %）**，只输 6 条。优势最大 `int_18`（5.54×），劣势最大 `infra_1`（0.54×，TM 7.646 vs GS 4.107）。
  README 的「5KB TM 显著优于 8KB GShare」在**全量上成立**。
- **但 TM 平均是 8 KB TAGE-SC-L 的 2.86 倍 MPKI**（逐条比值中位数 2.97×，最好 1.16×，最差 20.12×）。与 README 结论一致：打不过 TAGE，打得过 GShare。
- **最该盯的改进目标**（TM MPKI 最高）：`int_21` 36.346、`int_19` 32.688、`web_24` 32.649、`web_20` 30.157、`fp_6` 27.732。
  其中 **`int_19` 最可疑**：TM 32.688 / GShare 21.532 / TAGE **1.625** —— TAGE 几乎完美而 TM 灾难性。**单独分析这条可能是最高的性价比切入点。**
- TM MPKI 最好的 5 条：`fp_5` 1.216、`media_2` 1.786、`infra_2` 2.989、`int_13` 3.119、`compress_2` 3.177。

### 10.2 复现性：与原作者的 `runs` CSV **逐位相同**

把本次 105 条结果与原作者 `runs` 分支的 `standalone_tm_run.csv` 逐条比对（`int_0` 起就完全一致，全量复核后）：

> **105/105 条 trace、三个指标全部逐位相同，最大绝对偏差 = 0。**

含义（重要）：

1. **原作者的配置与当前代码完全一致** —— 他 CSV 表头标的「5.02KB TM」只是**过时标签**，实际就是现在 5.06 KB 的 TM。对比是公平的，不必去找配置差异。
2. **平台差异为零。** README 警告过 UCRT64/Windows 与 Ubuntu 之间有可测量差异，说明他当年也是在 Linux 上跑的；`std::mt19937` 固定种子在此平台上完全确定。
3. **这是理想的可测量条件**：今后任何改动，只要结果偏离这份基线，**必定是改动本身造成的，不是噪声**。`int_0` 单条只要 279 s，`sample_traces/` 两条只要 ~15 s。

### 10.3 冒烟测试基线（2 条 sample，约 15 秒）

用于**快速回归**，不替代 10.1。命令 `./cbp -E 1000000 sample_traces/<t>.gz`。

| Metric | `int/sample_int_trace` | `fp/sample_fp_trace` |
| --- | ---: | ---: |
| Instructions | 997,301 | 997,741 |
| TM size / GShare size (reported) / TAGE-SC-L size | 5.06 KB / 8.00183 KB / 8.22 KB | same |
| `TM right` / `TM wrong` | 124,142 / 4,713 | 107,985 / 3,255 |
| **`TM accuracy`** | **96.3424 %** | **97.0739 %** |
| **`TM MPKI`** | **4.72575** | **3.26237** |
| `GShare right` / `GShare wrong` | 125,029 / 3,826 | 97,680 / 13,560 |
| `GShare accuracy` | 97.0308 % | 87.8101 % |
| **`GShare MPKI`** | **3.83635** | **13.5907** |
| `CondDirect` = **8 KB TAGE-SC-L** (NumBr / MispBr / MR / **MPKI**) | 128,874 / 272 / 0.2111 % / **0.2727** | 111,265 / 1,228 / 1.1037 % / **1.2308** |
| Wall time, single run | ~7.3 s | ~7.3 s |

**注意这两条 sample 的结论与全量不完全同向**（`int` sample 上 TM 输给 GShare，而全量 105 条上 TM 赢 94.3 %）—— 再次说明 **1M 指令的样本不能代表全量**，判断改动是否有效必须看 10.1。

### 10.4 单位与口径（别读错）

- 「算术平均 MPKI」= 105 条各自 MPKI 的简单平均，**未按指令数加权**。原作者 README 也是这个口径，故可比。
- `CondDirect` 是 **8 KB TAGE-SC-L**，不是 TM（见 §9 第 2 条）。
- `TM accuracy` 的分母是「有 snapshot 的已解析分支」，与 `CondDirect` 的 NumBr 略有出入（在途分支未统计）。

---

## 11. Where the project stands

> **⚠️ 2026-10-09 更新（实测，优先级高于本节其余内容）：`standalone_tm` 的瓶颈已经定位清楚了。**
> 当前 5.06 KB TM **不是全局历史预测器**，而是「32 条规则的 PC / 4 位局部历史预测器」。
> 三条 trace（`sample_int` / `sample_fp` / `int_0`）的输入组消融：
> **去掉 24 位全局历史，`int_0` 上 MPKI 反而改善 2.0%**（10.9876 → 10.7687）；去掉 4 位局部历史涨 **65.6%**；
> 去掉 32 位路径历史几乎无影响。TA 状态转储显示 **81 个输入里 47–49 个从未被任何子句包含**，
> 全局历史只占被包含文字的 **2.8%–6.7%**。
> **机制**：`tm.cc` 的 relax（子句未触发 → 所有文字 −1）把子句**触发频率**钉在
> `q* = p_dec/(p_inc+p_dec) = 1/S = 20%`，而 `log2(5) ≈ 2.3` —— 一个子句最多扛得住约 2.3 个独立二元条件，
> **稀有的长历史合取式无法存活**。同向第二条机制：`p_clause_fb` 在机器自信时 → 0，TM 会**过早冻结**
> 在一个"还凑合"的 PC + 局部历史解上。
> ⇒ **这 3× 的差距是结构性的，扫 `T`/`s`/`NUM_CLAUSES` 补不上。**
> 全文、边界声明与方向菜单：**`.dsh/logs/design/tm_bp_diagnosis.md`**（本节末尾的 `int_19` 线索正是这个诊断的起点，
> 而结论比"某条 trace 异常"更彻底：**全部 trace 上 TM 都在解一个更简单的问题**）。

From `main`'s README (`git show main:README.md`) plus what this branch is set up to test:

- **`main`'s core problem is the selector.** There, the TM reaches ~70 % "TM right when TAGE-SC is wrong", and perfect
  selection would cut MPKI ~3.8× — but **six** different selection mechanisms all failed, because the TM (trained only on
  TAGE-SC misses) never gets corrective feedback on the other 99.8 % of branches, so its confidence signal is meaningless.
  The README author's own conclusion: *"I don't believe that a selector with high enough recovery rates and low enough
  false-override rates to beat Full TAGE-SC2025 is possible in this context, but I do hope that you can prove me wrong."*
- **`standalone_tm` sidesteps the selector entirely** and reframes the question as efficiency: can a TM that scales down
  gracefully compete with light/mid-weight predictors on area, energy, and hardware complexity rather than raw MPKI?
  The README calls this "likely the most interesting branch" and notes the scaling was done naively — inputs were held
  constant (and inputs dominate TM size) and `T`/`s` were not retuned per size. **That is the obvious open work.**
- The README also flags that the most complex part of a hardware TM is the **training algorithm**, and that no open-source
  RTL implementation exists — a plausible FYP direction if the target is hardware efficiency.
- **Material now on disk:** `/data/cbp_trace_staging/dl/CBP2025-data-dependent-branch-profiles.pdf` — Arm's data-dependent
  branch characterisation of the CBP2025 traces (the file upstream README points at). Likely the most relevant reading for
  choosing TM input features.
- **A concrete lead from our own 105-trace baseline (§10.1):** `int_19_trace` is the standout anomaly —
  TM 32.688 / GShare 21.532 / TAGE-SC-L **1.625**. TM is 20× worse than TAGE while GShare is only 13× worse, and TM is
  *worse than GShare* there. The other four worst are `int_21`, `web_24`, `web_20`, `fp_6`. Checking whether these share a
  structural cause (e.g. a trace phase where the 32-clause TM saturates) is probably higher-value than blind hyperparameter
  sweeps, because §10.1 now gives an exact, noise-free yardstick for whatever you change.

---

## 12. Branch operations (learned the hard way)

This repo has already been damaged once by a wrong git command; the log entry for it is
`.dsh/logs/工程日志.md` @ `2026-09-29T15:10+01:00`. Read that before doing anything clever.

**`git pull <branch>` is a MERGE, not a switch.** Running `git pull origin standalone_tm` while on `main` merges the
branch into `main` and hands you a pile of conflicts you never asked for. To *get* a branch:

```bash
git fetch origin
git checkout standalone_tm          # creates a local tracking branch if absent
```

To *undo* an unwanted merge:

```bash
git merge --abort                   # only valid while the merge is unresolved
```

**Why files vanished.** `AGENTS.md`, `.dsh/`, `sample_traces/` and `cbp` are untracked on `standalone_tm`, but **were
committed on `zhang`**. `git checkout main` from `zhang` therefore *deleted them from the working tree* — git removes
files that the target branch doesn't track when they were tracked on the source branch. They were not lost (they are in
`zhang`'s `45cd9e0`), but they disappeared from disk. Recover a specific path without switching branches:

```bash
git restore -s zhang -W -- AGENTS.md .dsh/logs/工程日志.md   # worktree only, leaves them untracked
git show zhang:AGENTS.md                                     # or just read it from that branch
```

Current local branch inventory on `ku`: `main`, `standalone_tm`, `zhang` (= `main` + `45cd9e0`, containing
`AGENTS.md`, `.dsh/logs/工程日志.md`, `logs/sim_int.log`, `logs/sim_fp.log`, and the `cbp` binary).

---

## 13. Practical suggestions for whoever works here next

- **trace 与基线都已就绪**（§5.1、§10）—— 不要再下载 trace，也不要重复跑基线；直接拿 §10.1 的数字当参照。`sample_traces/` 只用于 15 秒冒烟。
- **Set `NUM_PARALLEL = 8`** in `test_harness.py` for `ku`, and run sweeps as background jobs.
- **Re-baseline before you optimise**, and keep the raw `run_*.csv` a claim is based on. Report TM and GShare MPKI
  *separately from* `CondDirect` — they are different predictors on this branch.
- **Before quoting areas, fix the GShare accounting** (§7.3) — `uint8_t` per entry vs. 2 bits claimed.
- **The scaling study is the real opening here**: retune `NUM_CLAUSES`, `THRESHOLD`, `S`, *and* the input configuration
  (inputs dominate TM size) rather than only clause count, and compare against GShare / 8 KB TAGE-SC-L / a perceptron.
  ⚠️ **但先读 §11 的 2026-10-09 更新与 §16**：实测表明差距主要在**表示能力**上，纯扫参数收益有限
  （README 的 scaling 表也印证：16→128 子句 = 4× 面积只换 27% MPKI）。
  更有价值的入口是 §16.4 的方向菜单：**B**（拆开 reward / punishment 概率）与 **D**（给子句指定几何历史长度）。
- **改完任何东西，回归流程固定三步**：① `make clean && make -j8`（**必须 clean**，见 §3 的头文件陷阱）；
  ② `./cbp -E 1000000 sample_traces/int/sample_int_trace.gz` 看是否仍是 `TM MPKI 4.72575`（15 秒冒烟）；
  ③ 有实质改动再上 §10.1 的 105 条。**改动前先 `git diff --numstat` 确认没被行尾污染**（§9 第 13 条）。
- **Design documents belong in `.dsh/logs/`** (e.g. `.dsh/logs/design/xxx.md`) so they are mirrored to the Obsidian vault
  alongside the engineering log — not in the vault directly.

---

## 14. FYP 路线图（本项目的既定目标）

> 本节由项目所有者（human）于 `2026-09-29T16:06+01:00` 确定，记录在 `.dsh/logs/工程日志.md`。
> **它描述的是项目意图，优先级高于本文其他章节的"建议"。** 改动前请与所有者确认。

### 14.1 方向定位

**IC 设计 × 机器学习 的交叉路线。**

落点是：为处理器设计一个**用 Tsetlin Machine 实现的分支预测器**，并最终论证它在硬件代价（面积 / 能耗 / 延迟）上的价值。

⚠️ **但本仓库只覆盖算法层。** 它只考 MPKI，硬件代价仅以「存储位数预算」粗略约束（见 §7.3 的 GShare 记账问题）。硬件层面的量化属于本路线**后续阶段**，不在当前范围内。

### 14.2 阶段性目标

| 阶段 | 目标 | 状态 |
| --- | --- | --- |
| **第 1 周** | **吃透本仓库**：环境、构建、trace、运行流程、代码结构 | ✅ 基本完成（§3 / §7 / §9 / §10；`tm.cc` 与 `tm_predictor.cc` 已加中文注释） |
| **第 2 步** | 搞清楚三件事：**为什么用 TM** · **TM 的优点是什么** · **TM 本身的原理是什么** | 🟡 原理部分完成（§15 + §16 + 两个文件的注释）；「为什么用 TM」的**论证仍未成文** |
| **第 3 步（当前）** | **定位"TM 为什么不准"** | ✅ **定位完成**：瓶颈是**表示能力**（`q* = 1/S` 限死子句特异性 + 自信即冻结），不是超参数（§11 / §16） |
| **下一步（待定）** | **动手解决**：从 §16.4 的方向菜单 A–F 里选（推荐 A → B → D） | ❌ 全部未动手 —— 所有者 2026-10-09 决定"先只写文档、不动代码" |
| **总目标** | **把 TM 的预测正确率提上去** | 未开始 |
| 后续 | 引入硬件成本模型，把"效率"从纸面数字变成硬件指标（路线 A） | 未开始 |

### 14.3 明确边界（重要）

- **现阶段只做纯算法。** 不写 RTL、不综合、不引入 HARCOM、不下载 CBP-NG。
- 不要因为读到 §14.4 就提前搭硬件工具链 —— 那是下一个阶段的事。
- 判断标准：本阶段任何改动，都应该能用 `./cbp` 跑出 MPKI，证明它让 TM 更准了。

### 14.4 路线 A：引入硬件成本模型（后续阶段，**现在不做**）

**动机。** 本仓库的"效率"目前只是个纸面数字：CBP2025 只给 192 KB 存储位数预算，连 GShare 面积算错 4 倍都发现不了（§7.3）。要支撑"TM 更省"这个论断，必须换成真正建模硬件代价的工具。

**方案。** 迁移到 **CBP-NG**（Next-Generation Championship in Branch Prediction，Ampere Computing 主办），用 **HARCOM**（HARdware COMplexity）C++ 库实现预测器。

| 项目 | 说明 |
| --- | --- |
| 模拟器仓库 | <https://github.com/AmpereComputing/cbp-ng> |
| 比赛官网 | <https://cbp-ng.bpchamp.com> |
| **HARCOM 建模对象** | **能耗、延迟、面积**。用不透明类型表示 `reg`（寄存器）/ `arr`（SRAM 数组）/ `val`（中间值）；类型不可直接读写，必须用 `select` 做 mux 而非 `if-else` |
| HARCOM 手册 | 仓库内 `docs/harcom.pdf` |
| **单 trace 输出字段** | trace 名 / 指令数 / 分支数 / 条件分支数 / block 数 / 额外周期 / P1-P2 分歧 / 与 block 末尾重合的 P1-P2 分歧 / P2 误预测 / **P1 延迟(周期)** / **P2 延迟(周期)** / **每指令动态能耗 (fJ)** |
| 预测器接口 | 两级预测：`predict1()` / `predict2()` / `reuse_predict1()` / `reuse_predict2()` / `reuse_prediction()`，支持预测流水化；预测器自己决定 prediction block 长度 |
| 示例预测器 | `predictors/` 下有 bimodal、gshare、perceptron、TAGE 参考实现；公共组件在 `predictors/common.hpp` |
| **评分方式** | **VFS（Voltage-Frequency-Scaled Speedup）**，综合准确率 + 能效 + 实现复杂度；由 Pierre Michaud 的 `docs/vfs.pdf` 定义 |
| 参考预测器 | CBP2025 的 TAGE-SC-L（`reference.cpp` / `seznec_cbp2025.h`），**只给准确率，无延迟/能耗** |
| 训练 trace | 官方 **168 条**：<https://drive.google.com/file/d/1kLKn_iKVBP-YxRpC4WiCy-ca-agU0BFG/view> |
| 编译要求 | GCC ≥ 12 或 Clang ≥ 19（`ku` 是 GCC 15.2.0，满足） |

**为什么这条路线对 IC 方向的毕设关键：** 它把"TM 面积小、能耗低"从定性说法变成可测数字（fJ/指令、周期），这正是 IC × ML 交叉方向需要的证据。**没有它，你只能说"TM 效果一般"；有了它，你才能说"TM 每焦耳能多预测对多少"。**

**迁移代价（预期）：** CBP-NG 的接口与 CBP2025 **不兼容**，是重写而非移植。`tm.cc` 里的 TM 投票/反馈**算法逻辑**可以参考复用，但数据结构（`tm_t` 的裸数组）与适配层必须按 HARCOM 的不透明类型重写。

**出处：** 本路线不是我们自己想出来的 —— `main` 的 `README.md` §"Avenues to explore" 里原作者就点名了 CBP-NG + HARCOM，并指出 **TM 训练算法至今没有公开的 RTL 实现**（见 §11）。

### 14.5 备选路线（**未采纳**，仅记录备查）

| 路线 | 内容 | 备注 |
| --- | --- | --- |
| **B：写 RTL** | Verilog/SystemVerilog 实现 TM 的训练 + 推理；FPGA 上板（LUT/FF/BRAM + 频率）或 ASIC 流程（Yosys + OpenLane + Sky130 → 面积/时序/功耗） | novelty 强：README 明确说 **TM 训练算法的 RTL 目前无公开实现** |
| **C：混合** | 本仓库（或 CBP-NG）做算法验证 + RTL 做硬件验证，两边共同支撑结论 | 工作量最大，视导师方向与进度再定 |

**当前决定：先走算法层 → 路线 A 作为第一个硬件量化步骤 → B/C 后续再议。**

### 14.6 下一步的具体抓手（供参考，未定稿）

- **为什么用 TM / TM 的优点 / TM 原理** —— 材料来源：`main` 的 `README.md`（`git show main:README.md`）、`papers` 分支、`tm.cc` 与 `tm.h` 本体、`lib/` 里 TAGE 的实现做对照。
- **提高 TM 正确率的可调旋钮**（都在 `tm.h`）：`NUM_CLAUSES`（现 32）、`THRESHOLD`（现 6）、`S`（现 5）、`NUM_STATES`（现 100），以及输入配置 `TM_PC_BITS` / `TM_G_HIST_BITS` / `TM_LOCAL_BITS` / `TM_PATH_*`。
- **README 已指出的现成缺口**：此前的缩放很粗糙 —— 输入配置被固定不动（而**输入数量主导 TM 体积**），`T`/`s` 也没按尺寸重新调优。原始作者自己说这值得进一步探索。

---

## 15. 练手项目钩子：Simple Tsetlin Machine（手写最小 TM）

> **本节是钩子，不是正文。** 结论全文在 `.dsh/logs/design/practice_tm_lessons.md`，**动手改 `tm.cc` 之前请先读它。**

**它是什么。** 一个**独立于本仓库**的练手项目：Windows 侧手写 C++ 最小 TM（3 个输入、8 行真值表、
无 trace、无模拟器），用来回答 §14.2 的那三个问题 —— *为什么用 TM · TM 原理 · 怎么把正确率提上去*。
跑了约 **20 万次训练**（两个目标函数 OR 与 `(A+B)⊕C`）+ 修复后 6 轮 A/B + 一组逐事件探针。

| 项 | 值 |
|---|---|
| **练手项目路径** | **`D:\projects\simple_tsetlin_machine`**（Windows 机 `muuhaha` 本地仓库；**不在 `ku` 上，不是 SMB 挂载**） |
| 来源版本（搬运时） | 分支 `fix-type2-feedback-p` @ `465fad6` |
| OR 阶段归档 | `D:\projects\simple_tsetlin_machine_OR_archive\`（2026-10-09 实测 79 文件 / 6.10 MB，含通用扫描器 `sweep_param.exe`、占空比测量 `diag_duty.cc`） |

**已复制到本仓库的文件**（**全部落位在 `.dsh/logs/` 下，随工程日志一起镜像到 Obsidian**）：

| 本仓库路径 | 来源 | 说明 |
|---|---|---|
| `.dsh/logs/design/practice_tm_lessons.md` | 新写 | **总结文档**：进度 + 机制 + 19 条坑 + 8 条待验证假设（含与本仓库 `tm.cc` 的逐行对照） |
| `.dsh/logs/design/practice_tm_src/tm.h` | 逐字节复制 | 最小 TM 的类声明 |
| `.dsh/logs/design/practice_tm_src/tm.cc` | 逐字节复制 | 实现，**含 Type II 修复后的注释**（修复本身是那轮的分水岭） |
| `.dsh/logs/design/practice_tm_src/main.cc` | 逐字节复制 | 训练程序（`C=64, T=8, s=1, S=3, epochs=40`） |
| `.dsh/logs/design/practice_tm_src/test.cc` | 逐字节复制 | 验证程序（8 行真值表） |
| `.dsh/logs/design/practice_tm_src/README.md` | 新写 | 副本清单 + SHA256 + 来源版本 |

**没有复制过来、需要时去原仓库拿的**：练手项目的 `agents.md`（58 KB 上下文入口）、
`punish_mechanism.md`（惩罚概率 `1/s` 的机制）、`.scratch/`（全部原始数据 / 图 / 扫描器，12 MB）。

### 15.1 ⚠️ 第一件必须知道的事：参数名撞车

**两个项目用了同一批字母表示不同的东西。** 读练手项目的任何结论之前先过一遍这张表：

| 概念 | 练手项目 | 本仓库 `tmsim` |
|---|---|---|
| 状态预算（`状态 > 阈值` 即"包含该文字"） | `S_`（状态 ∈ `[1, 2S]`） | **`NUM_STATES` = 100**（状态 ∈ `[1, 200]`） |
| 特异性 / 惩罚速率 | `s_`（`P(relax) = P(push-out) = 1/s`） | **`S` = 5**（`p_dec = 1/S = 0.2`） |
| 初始化 | 抛硬币，或"全 0"（全停在阈值 → 空子句） | `tm_init()` 全写成 `NUM_STATES` → **≡ 练手项目的"全 0"** |

即 `tmsim.NUM_STATES ↔ practice.S_`、`tmsim.S ↔ practice.s_`。**读反会得出相反结论。**

### 15.2 与本仓库最直接相关的 3 条（详见总结文档 §3）

1. **`relax` 与 `push-out` 现在共用同一个 `p_dec = 1/S = 0.2`**（`tm.cc` 的 `tm_fb_type1`）。
   练手项目的手术刀 A/B 表明**这两个速率应该分开且方向相反：relax 要慢、push-out 要快**
   （只放慢 push-out → 崩到 38%）。这是**一行改动**，也是目前最便宜的一个假设。
   ⚠️ 但 relax 慢 = 结构锁死 = **可能伤泛化**（练手项目自己标注为最大风险），**改完必须跑 105 条对照 §10.1**。
2. **`NUM_STATES = 100` 可能让子句"锁死"到学不回来**：状态推到 200 后要连续 ~100 次成功 relax（每次 0.2）
   才退出子句。练手项目测出的好区间是**状态预算 3~6**（=1 最差、再大只增方差）。
   零成本第一步：打开 `tm.h` 里被注释掉的 `DUMP_STATE_CSV`，统计顶在 `2*NUM_STATES` 的状态比例。
   > ❌ **2026-10-09 更正（实测）：这条假设在本仓库不成立。** 已按上面那句话做了 ——
   > `int_0` 与 `sample_int` 上顶在状态上限（即真的"锁死"）的比例都是 **0.0%**（压在**下限**的比例是 7.9% / 22.9%）。
   > 真正的瓶颈不是"退不出来"，而是"**进不去**"：触发频率设定点 `q* = 1/S` 让稀有的长历史文字
   > 根本无法积累到被包含。详见 **§16**。
3. **`tm_eval_clause` 的 `predict` 形参**：预测时空子句**不投票**，训练时**恒真**。
   练手项目与 Granmo 参考实现两边都恒真。**需要确认是否有意为之**，否则它是一个干净的 A/B 变量。

**本仓库已经核对过、确认没问题、别再怀疑的两处**：`p` 的分母已写成 `2.0 * THRESHOLD`（**没有**整数除法截断）；
`tm_update` 用**单一 p 同时控制两个方向** —— 这正是练手项目用 500 种子证明正确的形态，**不要改回去**。

### 15.3 维护约定

- **练手项目是只读来源。** 本仓库不修改它、不把它纳入构建（`Makefile` 不引用 `practice_tm_src/`）。
- 结论文档的**权威副本在本仓库**（`.dsh/logs/design/`），Obsidian 侧只是镜像；要给练手项目补结论，
  在本仓库追加，不要往 vault 写。
- 练手项目是 **Windows + MinGW 32 位 + `std::rand()`**，本仓库是 **Linux x86-64 + `std::mt19937(1u)`**，
  **随机数序列不同** —— "练手项目里种子 7 能满分"这类结论不要往本仓库套。

---

## 16. 表示能力诊断（2026-10-09）

> **本节是钩子。** 全文（含方法、边界声明、证据位置）在 **`.dsh/logs/design/tm_bp_diagnosis.md`**。
> **在动 `tm.cc` 的训练规则之前请先读它。**

**一句话。** `standalone_tm` 上那个 5.06 KB 的 TM，**实际上不是全局历史预测器**，
而是「**32 条规则的 PC / 4 位局部历史预测器**」。它 2.86× 落后于 8 KB TAGE-SC-L，
不是"差一点"，而是**在解另一个更简单的问题**。

### 16.1 实测证据（三条 trace：`sample_int` / `sample_fp` / `int_0`）

输入组消融（把整组输入永久置零，TM 在剩下的输入上重新学）：

| 消融掉的组 | 位数 | `sample_int` | `sample_fp` | `int_0` |
| --- | ---: | ---: | ---: | ---: |
| — 基线 | — | 4.72575 | 3.26237 | 10.9876 |
| PC | 21 | +15.8% | +7.3% | — |
| **全局历史** | **24** | +4.1% | +1.1% | **−2.0%（反而更好）** |
| **局部历史** | **4** | **+704%** | **+291%** | **+65.6%** |
| 路径 / 前序分支 | 32 | +0.5% | +1.5% | — |

TA 状态转储（`TM_INPUT_NAMES` 那张表就是对它的解读）：子句极小（1–10 个文字，均值 2.8–3.4），
**81 个输入里 47–49 个从未被任何子句包含**（≈60% 的输入是死重量，而输入数主导 TM 体积），
`gh` 只占被包含文字的 **2.8%（`int_0`）/ 6.7%（`sample_int`）**，顶在状态上限的比例 **0.0%**。

### 16.2 机制（推导 + 可证伪预测）

`tm.cc` 的 `tm_fb_type1` 里 relax 与 recruitment 的净漂移平衡给出**子句触发频率的设定点**：

```
q* = p_dec / (p_inc + p_dec) = 1 / S            （S = 5 ⇒ q* = 20%）
```

⇒ 一个子句最多承受约 `log2(S) ≈ 2.3` 个独立二元条件，与实测子句大小吻合。
⇒ **稀有的长历史合取式一形成就被 relax 拆掉。** 24 位全局历史不是"没学好"，是**结构上不允许学**。
⇒ 同向第二条机制：`p_clause_fb = (T − y·vote)/(2T)` 在 vote 自信时 → 0，机器**过早冻结**在
PC + 局部历史的局部最优上。

**可证伪预测**：提高 `S`（⇒ `q*` 下降 ⇒ 允许更稀有的子句）应当**同时**看到
**(a)** TA 状态里 `gh` 占比上升、**(b)** MPKI 下降。**两个判据必须一起看** —— 只看 MPKI 分不清
"表示能力真的变好了"和"参数碰巧好一点"。**这条预测尚未验证。**

### 16.3 顺带登记的两处工程陷阱

1. **`make` 不跟踪头文件**（详见 §3）：`DEPS` 引用了从不存在的 `cond_branch_predictor_interface.h`。
   候选修法：① 删掉 `DEPS` 里那个名字；② 新建一个真 `.h`；③ **推荐** `-MMD -MP` + `-include $(OBJ:.o=.d)`。
   **所有者 2026-10-09 决定暂不修改 `Makefile`**，只登记；在此期间一律用 `make clean && make -j8`。
2. **行尾陷阱**（详见 §9 第 13 条）：预测器文件是 CRLF，`tm.cc` / `tm_predictor.cc` 末尾无换行符。
   **所有者 2026-10-09 决定暂不处理**（不改行尾、不加 `.gitattributes`），但改完必须查 `git diff --numstat`。

### 16.4 方向菜单（**全部未动手**）

| | 方向 | 改动量 | 机制依据 |
| --- | --- | --- | --- |
| **A** | 把消融扩到 5–6 条代表性真实 trace（含 `int_19`/`int_21`/`web_24`/`fp_6`/`infra_1`），并做**反向消融**（只留 `gh`、去掉 `lh`） | 半天，零风险 | 锁死 §16.1，排除"3 条 trace 的巧合" |
| **B** | **拆开 reward / punishment 概率**：现在同一个 `S` 同时决定 `p_inc` 与 `p_dec`（硬耦合），先把 `p_dec` 调小 | 1 小时 + 2.5 h 回归 | `q* = 1/S`（§16.2）。**判据：MPKI + TA 状态里 `gh` 占比** |
| **C** | 给子句加"有用位"（TAGE 式分配 / 驱逐）—— TM **没有任何遗忘机制**，而 trace 是非平稳的 | 中等 | §9 第 12 条 |
| **D** | **给子句指定几何历史长度（TAGE 化的 TM）**：第 k 个子句只看 `gh[0, L_k)`，而不是所有子句都在同一个 24 位向量里自由漂移 | 较大 | 触发率可控 ⇒ 稀有长历史子句不再被 relax 惩罚。**novelty 最高** |
| **E** | TM + 一张极小的 per-PC bias 表（2K×2 bit = 0.5 KB），TM 只负责历史相关性修正 | 中等 | 把 32 条子句从 PC 位里解放出来（实测 `pc` 占被包含文字的 62%） |
| **F** | 练手项目的 3 条（relax/push-out 拆分、`NUM_STATES` 扫 3~6、空子句投票对称性） | 小 | 优先级已下降：补不上 3× 差距，但能让基线更干净 |

**推荐组合：A（锁死结论）→ B（最便宜且有机制依据）→ D（真正的核心贡献）。**

### 16.5 代码注释现状

`tm.cc` 与 `tm_predictor.cc` 已加**完整中文注释**（分别 **+204 行 / +127 行**，均为**纯注释、零代码改动**：
`git diff --numstat` 删除数 = 0；去掉注释后与改动前**逐字相同**；冒烟回归与 §10.3 逐位一致）。
其余文件（`gshare_predictor.cc`、`cbp2016_tage_sc_l_8kb.h`、`cond_branch_predictor_interface.cc`）尚无同类注释。

---

## 17. 测试集规范与调参协议（2026-10-13 定稿，**动参数前必读**）

> **完整版在 `.dsh/logs/design/test_sets_and_protocol.md`**（含每条的基线数字、成本模型、三阶段流程、
> α 归一化的推导与历史证据）。本节只留**纪律**与**索引** —— AGENTS.md 有工作区指令预算（≲64 KB），放不下细节。

**四集分工 —— 唯一允许用来做决策的集合是 T6：**

| 集合 | 文件 | 条数 | 用途 |
| --- | --- | ---: | --- |
| **T6 调参集** | `runlist_tune.txt` | 6 | **唯一允许用来选参数**（每领域一条：难度取领域中位、尽量短） |
| **H6 回归集** | `runlist_regress.txt` | 6 | 已知 TM 输给 GShare 的 6 条；决赛候选跑，确认没把短板弄更烂 |
| **V13 验证集** | `runlist_validate.txt` | 13 | **定稿时跑一次**；唯一允许写进结论的数字 |
| **全集 105** | `test_runlist.txt`（原有） | 105 | 开启硬件设计（§14.4 路线 A）前的最后一道闸 |

**本节最重要的一句话：** 仿真是**确定性**的（§10.2，与原作者 CSV 偏差 = 0）⇒ **没有随机噪声**，
唯一的误差来源是**选择性偏差**（在 T6 上好 ≠ 在另外 99 条上好，而且调参时看不见）
⇒ **永远不要把 T6 上的数字当结论。**

**成本 —— 唯一货币是「trace-秒」**（`ku` 有效并行度实测 ≈ 3.5 ⇒ **墙钟 ≈ 单人估时之和 ÷ 3.5**）：
`web_11` 单条探针 72 ／ T6 1,108（≈5.3 min）／ H6 1,722 ／ V13 3,751 ／ 全集 31,297（≈149 min）。
⇒ 提速只有 **更短的 trace / 更少的配置 / 加核** 三条路；**禁止截断 trace**（非平稳，§9 第 12 条）。

**五条硬规则：**

1. **结构决策先于参数扫描** —— 输入配置、relax/push-out、子句几何历史（§16.4）会改变"什么参数算好"。
2. **`THRESHOLD` 必须写成 α = T/(C/2) 再扫。** 它在 `tm.cc:361`（全库唯一一处）是"投票幅度死区半宽"，
   绝对值依赖 `C`；原作者一直是 **α = 0.375**（64/16、128/23、32/6），**从未扫过 α**。
   C=32 时 α ≥ 1（T ≥ 16）即永不冻结；值得扫的 T = {1..12} ∪ {16,24,32}。
3. 改 `tm.h` 后一律 `make clean && make -j8`（§3），并查 `git diff --numstat` 删除数 = 0（§9 第 13 条）。
4. **⚠️ `xargs -d '\n'` 下每行是一个参数**，`-n 2` 会把两行拼成 `$1`/`$2`（2026-10-13 实测踩过：
   36 个作业全报 MISSING，脚本还退出码 0）。正确：`xargs -P 8 -n 1 -d '\n'` +
   worker 内 `T="${1%% *}"; t="${1##* }"`，**且队列前必须单作业自检**。
5. 参数扫描在 `/tmp` 的源码副本里做（`tar` 排除 trace/.git/二进制），别反复污染工作区。

**已完成的扫描（两条轴都已封盘，详见 `.dsh/logs/design/test_sets_and_protocol.md` §7.1 / §7.2）：**
- 2026-10-13 `THRESHOLD` 1→12（C=32 固定，T6）→ `.dsh/logs/sweeps/T_sweep_20261013/`。
  **U 形，最优平台 T=6..7，原作者取值距最优仅 0.11 % ⇒ 不是追赶 TAGE 的杠杆。**
- 2026-10-13 `S` 1.0→10.0 step 0.5（C=32、T=6 固定，T6）→ `.dsh/logs/sweeps/S_sweep_20261013/`。
  **最优 S=5.0 = 原作者取值（两邻居 +0.65 % 以内）⇒ 该轴封盘；且 §16.2 的"提高 S 应更好"被证伪（S>5 单调变差）。
  ⇒ `S` 同时耦合"特异性(q*=1/S)"与"学习惯性(p_dec=1/S)"，故 §16.4 方向 B（拆开 relax/push-out）升级为首要实验。**
