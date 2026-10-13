# RESUME.md — where the GitHub Actions offload experiment stands

Written 2026-10-13 ~20:40 by the DSH agent, before the owner restarted the
session. Nothing here depends on the DSH process; everything is on `ku`, on
GitHub, or in this directory.

## Restart safety

Restarting DSH is safe. No background job was left running. In particular:

- the owner's sweep runs under **tmux on `ku`** (session `nssweep`,
  `/data/tm_cbp_sim/.dsh/tmp/ns_sweep.sh`) and is completely independent of DSH;
- `gh` authentication is stored in the keyring on `ku`;
- the GitHub repo and this directory are both committed.

## What is DONE

| item | state |
| --- | --- |
| GitHub repo | **https://github.com/tubigbe/tm-cbp-gha-sweep** (public, 143 files, 6.4 MB) |
| `gh` CLI on ku | installed at `~/.local/bin/gh`, v2.102.0, logged in as `tubigbe` |
| `/data/tm_gha_sweep/` | git repo, pushed to `origin/main` |
| workflow | `.github/workflows/sweep.yml` — gate job + 20-shard matrix |
| scripts | `scripts/prepare_traces.py`, `scripts/run_shard.py` (syntax + `--help` verified) |
| build | verified on ku: `make -j8` OK, smoke gives **TM MPKI 4.72575** (matches AGENTS.md 10.3) |
| `/data/tm_cbp_sim` | **untouched** — still at `474cf9d`, the 8 dirty entries are the owner's own |

## What is NOT done

1. **Solo timings for 5 of the 12 traces** — `web_18`, `fp_0`, `infra_0`,
   `compress_1`, `media_1` are still unmeasured.
   *Why:* the first measurement run was corrupted by two mistakes of mine —
   `create_repo.sh` did `rm -f cbp` while the timing script was using that
   binary (5 traces returned `rc=127`), and the retry ran while the owner had
   started their own sweep, so it was contended, not solo.
2. **`shards.json` and `bundles/`** — not generated yet; they need the timings.
3. **The workflow has never been run.**

## Known solo times (the project's "trace-seconds" unit)

| trace | solo s | source |
| --- | ---: | --- |
| `int_1` | 231 | `test_sets_and_protocol.md` §2.1 |
| `fp_4` | 233 | §2.1 |
| `web_11` | 72 | §2.1 |
| `media_3` | 140 | §2.1 |
| `compress_4` | 208 | §2.1 |
| `infra_14` | 225 | §2.1 |
| `int_13` | **313** | measured 2026-10-13, uncontended |
| `web_18` | ? | |
| `fp_0` | ? | |
| `infra_0` | ? | |
| `compress_1` | ? | |
| `media_1` | ? | |

`int_13` measured 313 s solo, TM MPKI 3.11935 — note that this does **not**
match §10.1's full-sweep value for `int_13` (3.119), so the measurement looks
sane.

## Exact next steps

```bash
# 0. wait until `ku` is idle (the owner's sweep must have finished,
#    otherwise the timings are contended and useless)
ssh ku 'uptime; pgrep -c cbp'

# 1. measure the 5 missing solo times, one at a time
ssh ku 'cd /data/tm_gha_sweep && ./cbp -E 1000000 /data/tm_cbp_sim/training_traces/<cat>/<name>_trace.gz | grep "TM MPKI"'

# 2. write them into a solo-times file, e.g. solo_times.txt, as "trace seconds"

# 3. build the shard plan + bundles
ssh ku 'cd /data/tm_gha_sweep && python3 scripts/prepare_traces.py \
        --runlist runlist_gha12.txt \
        --traces-root /data/tm_cbp_sim/training_traces \
        --solo-times solo_times.txt \
        --shards 20 --parallel 4'

# 4. commit and push the data
ssh ku 'cd /data/tm_gha_sweep && git add -A && git commit -m "trace bundles" && git push'

# 5. run it
ssh ku '~/.local/bin/gh workflow run sweep.yml -f shards=20 -f per_job_parallel=4'

# 6. watch + fetch results
ssh ku '~/.local/bin/gh run list --limit 5'
ssh ku '~/.local/bin/gh run watch'
```

## What the experiment is designed to show

A full 105-trace sweep takes **~149 min on `ku`** (measured, 9044 s with 8-way
concurrency). The claim under test is that GitHub Actions gives **20 concurrent
4-vCPU runners = 80 vCPU in flight** for free on a public repo.

Because wall-clock depends only on total work and concurrency — not on whether
the work is 105 distinct traces or 12 traces repeated — the plan repeats a
representative 12-trace subset until the total equals the full sweep's
**31,297 trace-seconds**. Repeat agreement doubles as a determinism check: if
repeats of the same trace disagree, the platform is non-deterministic and no
comparison against the `ku` baseline is valid.

## Caveat on the numbers

GitHub Actions on a public repo is legitimate here only because this *is* the
project's own benchmark matrix. GitHub's terms forbid using Actions for
"any other activity unrelated to the production, testing, deployment, or
publication of the software project". Do not create throwaway repositories to
multiply quota.
