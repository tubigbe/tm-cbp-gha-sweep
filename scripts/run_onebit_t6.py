#!/usr/bin/env python3
"""T6 shard runner for the 2026-10-26 1-bit / hybrid arms.

One shard = one T6 trace: download that trace's category tarball once (hardened
against the 2026-10-18 Google Drive flake), then for every arm in the plan:
restore the baseline sources, copy the variant files, `make clean && make`, and
run the trace with -E 1000000.

The per-trace raw stdout of every arm is kept in logs/<arm>__<trace>.log and the
scraped numbers go to <out>/shard-XX.csv.

Pollution gate: `GShare MPKI` and `instructions` must be identical across arms
for the same trace; the gate job checks that on sample_int before any shard runs.
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

FIELDS = ["shard", "trace", "variant", "mode", "seconds", "rc",
          "TM MPKI", "TM accuracy", "TM right", "TM wrong",
          "1bit MPKI", "1bit accuracy",
          "HYB MPKI", "HYB accuracy",
          "GShare MPKI", "GShare wrong", "TAGE MPKI",
          "instructions", "tm_size", "onebit_size"]

BASE_FILES = ["tm.h", "tm.cc", "tm_predictor.h", "tm_predictor.cc",
              "cond_branch_predictor_interface.cc"]

PLAIN = ("TM MPKI", "TM accuracy", "TM right", "TM wrong",
         "1bit MPKI", "1bit accuracy", "1bit wrong", "1bit right",
         "HYB MPKI", "HYB accuracy",
         "GShare MPKI", "GShare wrong")


def sh(cmd, **kw):
    print("+ " + (cmd if isinstance(cmd, str) else " ".join(cmd)), flush=True)
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=True, **kw)


def find_trace(root, name):
    cands = {f"{name}.gz", f"{name}_trace.gz"}
    for d, _s, files in os.walk(root):
        for c in cands:
            if c in files:
                return os.path.join(d, c)
    return None


def scrape(path):
    out = {}
    with open(path, errors="replace") as fh:
        for line in fh:
            s = line.strip()
            for k in PLAIN:
                if s.startswith(k + ":"):
                    out[k] = s.split(":", 1)[1].strip()
            if s.startswith("Measured # of instructions:"):
                out["instructions"] = s.split(":", 1)[1].strip()
            if s.startswith("TM initialised with size"):
                out["tm_size"] = s.split("size", 1)[1].strip().split("(")[0].strip()
            if s.startswith("1bit size:"):
                out["onebit_size"] = s.split(":", 1)[1].strip()
            f = s.split()
            if len(f) >= 5 and f[0] == "CondDirect":
                out["TAGE MPKI"] = f[4]
    return out


def download_category(info, traces_dir):
    url = ("https://drive.usercontent.google.com/download?id=%s&export=download&confirm=t"
           % info["gdrive_id"])
    for attempt in range(1, 4):
        cmd = ('set -o pipefail; curl -sSL --connect-timeout 30 --max-time 1800 '
               '--retry 5 --retry-delay 5 --retry-all-errors '
               '--speed-limit 100000 --speed-time 60 "%s" | tar -xJ -C %s'
               % (url, traces_dir))
        print("+ download attempt %d: %s" % (attempt, cmd), flush=True)
        rc = subprocess.run(cmd, shell=True, executable="/bin/bash").returncode
        print("  attempt %d rc=%d" % (attempt, rc), flush=True)
        if rc == 0:
            return 0
        time.sleep(15)
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--plan", default="t6_onebit.json")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--out-dir", default="onebit_results")
    ap.add_argument("--skip-download", action="store_true")
    a = ap.parse_args()

    plan = json.load(open(a.plan))
    me = plan["shards"][str(a.shard)]
    trace = me["trace"]
    arms = plan["variants"]
    print("===== shard %d: trace %s, %d arms =====" % (a.shard, trace, len(arms)))

    os.makedirs(a.traces_dir, exist_ok=True)
    os.makedirs(a.logs_dir, exist_ok=True)
    os.makedirs(a.out_dir, exist_ok=True)

    if not a.skip_download:
        for info in me["categories"].values():
            rc = download_category(info, a.traces_dir)
            if rc != 0:
                print("::error::shard %d: tarball download failed" % a.shard)
                return 3
    tp = find_trace(a.traces_dir, trace)
    if tp is None:
        print("::error::shard %d: trace %s missing after extraction" % (a.shard, trace))
        return 3
    tp = os.path.abspath(tp)

    def restore_base():
        subprocess.run(["git", "checkout", "--"] + BASE_FILES, check=True)

    # build every arm once (sequential: one tree)
    built = []
    for arm in arms:
        name = arm["name"]
        vdir = os.path.join("variants", name)
        if not os.path.isdir(vdir):
            print("::error::shard %d: missing variant dir %s" % (a.shard, vdir))
            return 3
        t0 = time.time()
        restore_base()
        for fn in sorted(os.listdir(vdir)):
            if fn.endswith((".h", ".cc")):
                shutil.copy(os.path.join(vdir, fn), fn)
        subprocess.run("make clean >/dev/null", shell=True, check=True)
        r = subprocess.run("make -j4", shell=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.STDOUT)
        if r.returncode != 0:
            restore_base()
            print("::error::shard %d: build failed for %s" % (a.shard, name))
            return 4
        dst = os.path.join("bins_%02d" % a.shard, name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy("cbp", dst)
        built.append((arm, dst))
        print("    built %-16s in %5.0fs" % (name, time.time() - t0), flush=True)
    restore_base()

    def run(arm, binary):
        log = os.path.join(a.logs_dir, "%s__%s.log" % (arm["name"], trace))
        t0 = time.time()
        with open(log, "wb") as fh:
            rc = subprocess.call([binary, "-E", "1000000", tp], stdout=fh,
                                 stderr=subprocess.STDOUT)
        row = {"shard": a.shard, "trace": trace, "variant": arm["name"],
               "mode": arm.get("mode", ""), "seconds": "%.1f" % (time.time() - t0),
               "rc": rc}
        row.update(scrape(log))
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        futs = [pool.submit(run, arm, b) for arm, b in built]
        for fut in as_completed(futs):
            row = fut.result()
            rows.append(row)
            print("    %-16s %7ss rc=%s TM=%-9s 1bit=%-9s HYB=%-9s GS=%s" % (
                row["variant"], row["seconds"], row["rc"], row.get("TM MPKI", "-"),
                row.get("1bit MPKI", "-"), row.get("HYB MPKI", "-"),
                row.get("GShare MPKI", "-")), flush=True)

    path = os.path.join(a.out_dir, "shard-%02d.csv" % a.shard)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: r["variant"]):
            w.writerow(r)

    bad = [r for r in rows if r["rc"] != 0 or not r.get("TM MPKI")]
    if bad:
        print("::error::shard %d: %d arm(s) failed" % (a.shard, len(bad)))
        return 1
    print("--- shard %d OK: %d arms ---" % (a.shard, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
