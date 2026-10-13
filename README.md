# tm-cbp-gha-sweep

An **out-of-tree** copy of the `standalone_tm` CBP2025 benchmark, set up so that
a parameter sweep can run on **GitHub Actions** instead of on `ku`.

## Why this repo exists

`ku` is a 4-core / 8-thread Ryzen 7 3750H with a *measured* effective parallel
speedup of **3.2-3.5x**. A full 105-trace sweep takes **~149 minutes** there and
saturates the machine, so nothing else can run meanwhile.

GitHub Actions on a public repository gives **20 concurrent jobs x 4 vCPU = 80
vCPU in flight, free, with unlimited minutes on standard runners**. That is a
nominal **10x** the thread count of `ku`.

## What is in here

```
.github/workflows/sweep.yml   the workflow (gate job + 20-shard matrix)
scripts/prepare_traces.py     RUN ON ku - shards the runlist, builds bundles/
scripts/run_shard.py          runs one shard's traces inside a runner
shards.json                   shard index -> trace names (generated)
bundles/shard-NN.tar.gz       the trace data, one bundle per shard (generated)
sample_traces/                the two 1M-instruction samples, for the gate
```

Everything else (`*.cc`, `*.h`, `lib/`, `Makefile`, `runlist_*.txt`) is a copy of
the benchmark at the commit recorded in `PROVENANCE.txt`.

## The determinism gate

The first job in every workflow run rebuilds the simulator and replays the two
sample traces, then asserts the results are **bit-identical** to the values
recorded in `AGENTS.md` section 10.3 on `ku`:

| metric | `sample_int_trace` | `sample_fp_trace` |
| --- | ---: | ---: |
| `TM right` | 124142 | 107985 |
| `TM wrong` | 4713 | 3255 |
| `TM MPKI` | 4.72575 | 3.26237 |

If the gate fails, **every number produced by that run is incomparable to the
`ku` baseline** and the sweep job is not even started. This is the single most
important check, because the whole value of the existing baseline is that it
reproduces the original author's CSV bit for bit (105/105 traces, deviation 0),
which means any deviation is caused by a real change rather than noise.

## Running a sweep

1. `python3 scripts/prepare_traces.py --runlist ... --traces-root ... --shards 20`
2. commit `shards.json` and `bundles/`
3. push, then trigger the workflow from the Actions tab (or `gh workflow run`)
4. collect the per-shard artifacts; each contains raw per-trace stdout plus a
   `shard-N.csv`

## Cost / caveats

- Free-plan concurrency for standard runners is **20 jobs**; larger runners are
  always billed and are organisation-only.
- Each runner has a **14 GB** disk, so the traces are split across shards rather
  than staged whole.
- GitHub's terms forbid using Actions for "any other activity unrelated to the
  production, testing, deployment, or publication of the software project".
  Running *this project's own* benchmark matrix is the intended use; using it as
  a general-purpose compute farm is not. Do not create throwaway repositories to
  multiply quota.
