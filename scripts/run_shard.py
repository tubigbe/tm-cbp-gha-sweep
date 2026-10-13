#!/usr/bin/env python3
"""Run one shard of the TM CBP2025 sweep on a GitHub-hosted runner.

Design notes
------------
* Deliberately does NOT use xargs.  AGENTS.md section 17 rule 4 records a real
  incident where `xargs -d '\\n' -n 2` silently mis-parsed the job list -- every
  job reported MISSING while the script still exited 0.  A thread pool over an
  explicit list has no such failure mode.

* Raw stdout is kept per trace (logs/<trace>__r<NN>.log).  The project protocol
  requires this because the official "50 Perc" metric can only be parsed from
  the raw output, and because a failed run must be diagnosable after the fact.

* Repeats are a first-class concept.  The simulator is deterministic on a given
  platform (AGENTS.md section 10.2: 105/105 traces bit-identical to the original
  author's CSV), so running the same trace several times MUST give identical
  metrics.  This script checks that and shouts if it is ever violated -- which
  would mean the runner platform is not deterministic and the whole comparison
  is invalid.
"""
import argparse
import collections
import csv
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

CBPP = "./cbp"
CB_FLAGS = ["-E", "1000000"]

METRIC_KEYS = ("TM MPKI", "TM accuracy", "TM right", "TM wrong",
               "GShare MPKI", "Integrated Predictor MPKI")

CSV_FIELDS = ["shard", "trace", "repeat", "seconds", "rc", "error",
              "TM MPKI", "TM accuracy", "TM right", "TM wrong",
              "GShare MPKI", "Integrated Predictor MPKI"]


def find_trace(traces_dir, name):
    target = f"{name}_trace.gz"
    for root, _dirs, files in os.walk(traces_dir):
        if target in files:
            return os.path.join(root, target)
    return None


def scrape(log_path):
    out = {}
    try:
        with open(log_path, "r", errors="replace") as fh:
            for line in fh:
                for k in METRIC_KEYS:
                    if line.startswith(k + ":"):
                        out[k] = line.split(":", 1)[1].strip()
    except OSError:
        pass
    return out


def run_one(shard, name, repeat, traces_dir, logs_dir, standalone):
    """standalone=False means other processes are running concurrently, so the
    absolute seconds are inflated; we report the solo number separately."""
    suffix = "" if standalone else f"__r{repeat:02d}"
    log_path = os.path.join(logs_dir, f"{name}{suffix}.log")
    path = find_trace(traces_dir, name)
    if path is None:
        return {"shard": shard, "trace": name, "repeat": repeat,
                "seconds": "", "rc": 1, "error": "MISSING"}
    t0 = time.time()
    with open(log_path, "wb") as fh:
        rc = subprocess.call([CBPP] + CB_FLAGS + [path], stdout=fh,
                             stderr=subprocess.STDOUT)
    dt = time.time() - t0
    row = {"shard": shard, "trace": name, "repeat": repeat,
           "seconds": f"{dt:.1f}", "rc": rc, "error": ""}
    row.update(scrape(log_path))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--shards-json", default="shards.json")
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--solo-first", action="store_true", default=True,
                    help="run each distinct trace once alone first, so we get an "
                         "uncontended per-trace time to compare against the ku "
                         "single-person estimates")
    args = ap.parse_args()

    with open(args.shards_json) as fh:
        shards = json.load(fh)
    names = shards.get(str(args.shard), [])
    if not names:
        print(f"shard {args.shard}: empty shard list, nothing to do")
        return 0

    os.makedirs(args.logs_dir, exist_ok=True)
    counts = collections.Counter(names)
    print(f"shard {args.shard}: {len(names)} jobs, "
          f"{len(counts)} distinct traces, parallel={args.parallel}")
    print("  " + ", ".join(f"{n}x{c}" if c > 1 else n
                           for n, c in sorted(counts.items())))

    rows = []
    t0 = time.time()

    # ---- phase A: one SOLO run of each distinct trace -------------------
    # This is the number that is directly comparable to the ku "trace-seconds"
    # cost model, because that model is defined on uncontended runs.
    solo = {}
    if args.solo_first:
        for name in sorted(counts):
            row = run_one(args.shard, name, 0, args.traces_dir,
                          args.logs_dir, standalone=True)
            solo[name] = float(row["seconds"]) if row["seconds"] else 0.0
            row["repeat"] = "solo"
            rows.append(row)
            print(f"  SOLO {name:<12} {row['seconds']:>8}s  "
                  f"TM MPKI={row.get('TM MPKI', '-'):<10} rc={row['rc']}")

    # ---- phase B: the concurrent bulk ----------------------------------
    # One occurrence of each distinct trace was already consumed by phase A,
    # so the remaining repeats are (count - 1) each.
    bulk = []
    for name, c in sorted(counts.items()):
        for r in range(1, c):
            bulk.append((name, r))

    if bulk:
        print(f"  --- running {len(bulk)} concurrent jobs, "
              f"{args.parallel} at a time ---")
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futs = [pool.submit(run_one, args.shard, n, r, args.traces_dir,
                                args.logs_dir, False) for n, r in bulk]
            done = 0
            for fut in as_completed(futs):
                row = fut.result()
                rows.append(row)
                done += 1
                if done % 10 == 0 or done == len(bulk):
                    print(f"    {done}/{len(bulk)} done")

    wall = time.time() - t0

    csv_path = f"shard-{args.shard}.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in sorted(rows, key=lambda r: (str(r["trace"]), str(r["repeat"]))):
            w.writerow(row)

    # ---- determinism check across repeats ------------------------------
    by_trace = collections.defaultdict(set)
    for row in rows:
        if row["error"] or row["rc"] != 0:
            continue
        by_trace[row["trace"]].add(row.get("TM MPKI", "?"))
    bad = {t: v for t, v in by_trace.items() if len(v) > 1}
    if bad:
        print("\n!! NON-DETERMINISM DETECTED -- repeats of the same trace "
              "produced different TM MPKI:")
        for t, v in bad.items():
            print(f"   {t}: {sorted(v)}")
        print("!! results from this platform must not be compared "
              "against the ku baseline")
    else:
        print(f"\ndeterminism: OK -- all repeats agree "
              f"({len(by_trace)} distinct traces)")

    failures = [r["trace"] for r in rows if r["rc"] != 0 or r["error"]]
    print(f"shard {args.shard} wall clock: {wall:.1f}s ({wall/60:.1f} min) "
          f"for {len(names)} jobs")
    if solo:
        tot = sum(solo.values())
        print(f"  solo time for this shard's distinct traces: {tot:.0f}s "
              f"(sum of {len(solo)})")
    if failures:
        print(f"FAILURES: {', '.join(sorted(set(failures)))}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
