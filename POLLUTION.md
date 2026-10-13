# POLLUTION.md — exactly what was created, and what was NOT touched

Owner instruction (2026-10-13): *"千万别污染现有的仓库, 如果要污染, 请创建一个文档,
写明白你改了啥, 新增了啥, 方便我们后续删除."*

This file is that document. **Everything created by the GitHub-Actions offload
experiment is listed here, and nothing else on the machine was modified.**

## 1. `/data/tm_cbp_sim` (the real project) — **UNTOUCHED**

Verified read-only. No file was created, modified or deleted inside it.

```
$ git -C /data/tm_cbp_sim rev-parse HEAD
474cf9d0ff56b42c75a9106c2153b2a49bd050ca        # unchanged, on branch standalone_tm
$ git -C /data/tm_cbp_sim status --porcelain     # read-only, pre-existing entries only
 M AGENTS.md                                     # <- the owner's own edit, predates this work
?? .dsh/logs/design/test_sets_and_protocol.md    # pre-existing
?? .dsh/logs/sweeps/                             # pre-existing
?? .dsh/tmp/                                     # pre-existing
?? .dsh/tools/                                   # pre-existing
?? runlist_regress.txt                           # pre-existing
?? runlist_tune.txt                              # pre-existing
?? runlist_validate.txt                          # pre-existing
```

The 15 GB of traces in `training_traces/` were only **read**.
`/data/cbp_trace_staging/` (the archived sweep logs) was not touched.

> Transient files that WERE created and DELETED during earlier probing, listed
> for completeness because they briefly existed inside the project tree:
> `_probe_ku.sh`, `_probe_scale.sh`, `_probe_size.sh`, `_probe_march.sh`.
> All four were removed; `ls /data/tm_cbp_sim/_probe*` returns nothing.
> `/tmp/mt_plain`, `/tmp/mt_native` on `ku` were also removed.
> `/tmp/tb2` (the owner's own `S` sweep) was never touched.

## 2. `/data/tm_gha_sweep` — NEW directory, safe to delete wholesale

A self-contained copy of the benchmark plus the GitHub Actions scaffolding.
**Deleting this directory removes the entire experiment.**

```
/data/tm_gha_sweep/
├── .github/workflows/sweep.yml   the workflow (gate job + 20-shard matrix)
├── scripts/prepare_traces.py     run on ku: shard the runlist + build bundles
├── scripts/run_shard.py          run inside a runner: execute one shard
├── sample_traces/                the two 1M samples, copied (2.6 MB) - the gate
├── README.md                     what this is and how to run it
├── POLLUTION.md                  this file
├── bundles/, shards.json         generated later, not yet present
└── <copy of the benchmark source at the recorded commit>
```

Delete with: `rm -rf /data/tm_gha_sweep`

## 3. `/tmp` on `ku` — scratch only

`/tmp/gha_recon.sh`, `/tmp/gha_recon2.sh`, `/tmp/build_skeleton.sh`,
`/tmp/_speedtest.bin` (already removed). All safe to delete; none is referenced
by anything.

## 4. Windows side

`C:\Users\chenyoo\AppData\Local\Temp\gha_*.sh` and
`C:\Users\chenyoo\AppData\Local\Temp\gha_sweep\` — staging copies used to push
files to `ku` without CRLF corruption. Safe to delete.

## 5. GitHub

Nothing has been created on GitHub yet. When a repository is created it will be
listed here by exact name, together with:

- the trace bundles pushed to it (approximately 14 GB, the bulk of the size)
- how to delete it (`Settings -> Delete this repository`) if the experiment is
  abandoned

**No existing repository (`tubigbe/*` or `mihkel-reb/tm_cbp_sim`) is modified.**

## 6. What the project itself would need, if this is ever adopted permanently

Nothing in this document. The experiment is intentionally out-of-tree: the
sweep copy under `/data/tm_gha_sweep` is a *copy*, so the project can adopt or
discard it independently. If the owner later wants the workflow to live in the
real repo, the only file that has to move is
`.github/workflows/sweep.yml` plus `scripts/`, and that is a separate,
explicitly-approved change.
