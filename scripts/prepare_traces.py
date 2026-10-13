#!/usr/bin/env python3
"""Prepare trace bundles + shard assignment for the GitHub Actions sweep.

RUN THIS ON `ku`.  It only READS from the training-trace directory and only
WRITES into the standalone sweep repo.  It never touches /data/tm_cbp_sim.

The shape of the experiment
---------------------------
We want to measure how long a *full* sweep takes on GitHub Actions, without
uploading the full 14.3 GB trace set.  The trick: wall-clock time depends only
on the TOTAL WORK and the CONCURRENCY, not on whether the work is 105 distinct
traces or 12 traces run many times.  The simulator is deterministic, so repeats
produce identical metrics -- and if they ever do NOT, that itself is a finding
(it would mean the platform is not deterministic).

So: pick a representative 12-trace subset, and repeat each trace enough times
that the total work equals the full 105-trace sweep (31,297 trace-seconds,
which takes ~149 min on `ku`).

Assignment
----------
Each shard is given exactly ONE trace, repeated R times.  One trace per shard
keeps the uploaded data small (the 12 traces total ~1 GB, versus ~18 GB if every
shard needed a mix), while still filling all 20 runners.

  * trace i is given s_i shards, with sum(s_i) = n_shards and s_i proportional
    to its solo time, so long traces are split across more runners;
  * each of those shards runs the trace R_i = round(C / T_i) times, where
    C = total_work / n_shards.  Since a shard runs `parallel` jobs at once,
    wall_i ~= (R_i / parallel) * T_i, which is near-constant across shards --
    i.e. the sweep finishes when it finishes, without stragglers.

Chunking exists because GitHub rejects individual files larger than 100 MiB on
push.  Traces over the limit are split into parts; the runner concatenates them
back into one tarball.

Traces are never truncated: AGENTS.md section 17 forbids it -- the metric
convention is "first half = warm-up", and the traces are highly non-stationary,
so a truncated prefix is a different workload.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

CHUNK_LIMIT = 95 * 1024 * 1024  # stay safely under GitHub's 100 MiB file cap
FULL_SWEEP_TRACE_SECONDS = 31297  # AGENTS.md section 17


def load_solo_times(path):
    """Read 'trace seconds' lines into a dict."""
    times = {}
    with open(path) as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                times[parts[0]] = float(parts[1])
    return times


def collect(names, traces_root):
    index = {}
    for root, _dirs, files in os.walk(traces_root):
        for f in files:
            if f.endswith(".gz"):
                index[f[:-3]] = os.path.join(root, f)
    found, missing = [], []
    for n in names:
        p = index.get(n)
        (found if p else missing).append((n, p, os.path.getsize(p)) if p else n)
    return found, missing


def allocate_shards(times, names, n_shards):
    """Give each trace 1..k shards, proportional to solo time, summing to n_shards."""
    total = sum(times[n] for n in names)
    quota = {n: max(1, round(n_shards * times[n] / total)) for n in names}
    # fix the rounding so the quotas sum to exactly n_shards, biggest share first
    order = sorted(names, key=lambda n: -times[n])
    while sum(quota.values()) < n_shards:
        for n in order:
            if sum(quota.values()) >= n_shards:
                break
            quota[n] += 1
    while sum(quota.values()) > n_shards:
        for n in reversed(order):
            if quota[n] > 1 and sum(quota.values()) > n_shards:
                quota[n] -= 1
    return quota


def build_bundle(trace_path, root, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    rel = os.path.relpath(trace_path, root)
    tar_path = os.path.join(out_dir, "_shard.tar.gz")
    subprocess.check_call(["tar", "-czf", tar_path, "-C", root, rel])
    size = os.path.getsize(tar_path)
    n_parts = max(1, (size + CHUNK_LIMIT - 1) // CHUNK_LIMIT)
    with open(tar_path, "rb") as fh:
        for i in range(n_parts):
            data = fh.read(CHUNK_LIMIT)
            with open(os.path.join(out_dir, f"part-{i:02d}"), "wb") as out:
                out.write(data)
    os.remove(tar_path)
    return n_parts, size, rel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runlist", required=True)
    ap.add_argument("--traces-root", required=True)
    ap.add_argument("--solo-times", required=True,
                    help="file of 'trace seconds' lines (measured solo on ku)")
    ap.add_argument("--shards", type=int, default=20)
    ap.add_argument("--parallel", type=int, default=4,
                    help="jobs run concurrently inside one runner")
    ap.add_argument("--total-work", type=float, default=FULL_SWEEP_TRACE_SECONDS,
                    help="target total trace-seconds; default = the full 105-trace sweep")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--skip-bundles", action="store_true")
    args = ap.parse_args()

    names = [l.strip() for l in open(args.runlist)
             if l.strip() and not l.startswith("#")]
    times = load_solo_times(args.solo_times)
    missing_times = [n for n in names if n not in times]
    if missing_times:
        print(f"ERROR: no solo time recorded for: {', '.join(missing_times)}")
        return 1

    found, missing = collect(names, args.traces_root)
    if missing:
        print(f"traces MISSING on disk: {', '.join(missing)}")
        return 1
    path_of = {n: p for n, p, _ in found}
    size_of = {n: s for n, _, s in found}

    quota = allocate_shards(times, names, args.shards)
    C = args.total_work / args.shards

    print(f"target total work : {args.total_work:,.0f} trace-seconds "
          f"(= the full 105-trace sweep, ~149 min on ku)")
    print(f"shards            : {args.shards}   C = {C:,.0f} trace-s per shard")
    print(f"parallel per shard: {args.parallel}\n")
    print(f"{'trace':<12}{'solo s':>8}{'shards':>8}{'rep/shard':>11}"
          f"{'jobs':>7}{'est wall':>10}{'bundle MB':>11}")

    # assign shard indices: trace by trace, in descending solo time
    shards = {}
    plan = []
    sid = 0
    est_walls = []
    total_jobs = 0
    bundle_bytes = 0
    for n in sorted(names, key=lambda x: -times[x]):
        s_i = quota[n]
        R = max(1, round(C / times[n]))
        per_shard_rep = max(1, round(R / s_i))
        for _ in range(s_i):
            shards[str(sid)] = [n] * per_shard_rep
            est_wall = -(-per_shard_rep // args.parallel) * times[n]
            est_walls.append(est_wall)
            total_jobs += per_shard_rep
            bundle_bytes += size_of[n]
            plan.append((sid, n, per_shard_rep, est_wall, size_of[n]))
            sid += 1

    for sid, n, rep, est, sz in plan:
        print(f"{n:<12}{times[n]:>8.0f}{quota[n]:>8}{rep:>11}"
              f"{rep:>7}{est:>9.0f}s{sz/1048576:>11.0f}")
    print(f"\ntotal jobs        : {total_jobs}")
    print(f"uploaded data     : {bundle_bytes/1048576:,.0f} MB "
          f"(the 12 traces total {sum(size_of.values())/1048576:,.0f} MB; "
          f"x{bundle_bytes/sum(size_of.values()):.1f} because long traces are "
          f"split across shards)")
    print(f"est wall (solo-T model, runner ~1.3x faster than ku): "
          f"{max(est_walls)/1.3/60:.1f} - {max(est_walls)/60:.1f} min")

    with open(os.path.join(args.out_dir, "shards.json"), "w") as fh:
        json.dump(shards, fh, indent=1, sort_keys=True)

    if args.skip_bundles:
        return 0

    root = os.path.abspath(args.traces_root)
    manifest = {}
    print("\nbuilding bundles:")
    for sid, n, _rep, _est, _sz in plan:
        out_dir = os.path.join(args.out_dir, "bundles", f"shard-{sid:02d}")
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        n_parts, size, rel = build_bundle(path_of[n], root, out_dir)
        manifest[f"shard-{sid:02d}"] = {"trace": n, "parts": n_parts,
                                        "bytes": size, "member": rel}
        print(f"  shard-{sid:02d}  {n:<12} {size/1048576:6.1f} MB -> {n_parts} part(s)")
    with open(os.path.join(args.out_dir, "bundles", "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)
    print("\nall part files are under "
          f"{CHUNK_LIMIT/1048576:.0f} MiB, so `git push` will accept them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
