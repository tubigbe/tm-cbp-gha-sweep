#!/usr/bin/env python3
"""Full-set shard runner for ONE explicit configuration (2026-10-27 full-set wave 1).

Same execution model as run_fullset_cfg.py - one shard = one workload category, the
category tarball is streamed from Google Drive straight into `tar -xJ`, 4-way parallel
trace runs, per-trace raw stdout kept - but the CSV carries every column the
2026-10-26 arms print (1bit MPKI / HYB MPKI / override-rescue-hurt), so the full-set
comparison does not need a second pass over the logs.

The variant sources are copied over the tree exactly like run_fullset_cfg.py does:
  variants/<config>/*.h, *.cc  ->  workspace root   (tm.cc is NOT in the variant, so
                                                     the baseline TM source is used)

Usage:
  python3 scripts/run_fullset_arm.py --shard 0 --config onebit_pc17 \
      --plan fullsets_isoB.json --parallel 4 --out-dir fullset_onebit
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

FIELDS = ["shard", "category", "trace", "variant", "mode", "seconds", "rc",
          "TM MPKI", "TM accuracy", "TM right", "TM wrong",
          "1bit MPKI", "1bit accuracy", "1bit wrong", "1bit right",
          "HYB MPKI", "HYB accuracy", "HYB right", "HYB wrong",
          "override count", "rescue", "hurt",
          "GShare MPKI", "GShare wrong", "TAGE MPKI",
          "instructions", "tm_size", "onebit_size"]

PLAIN = ("TM MPKI", "TM accuracy", "TM right", "TM wrong",
         "1bit MPKI", "1bit accuracy", "1bit wrong", "1bit right",
         "HYB MPKI", "HYB accuracy", "HYB right", "HYB wrong",
         "override count", "rescue", "hurt",
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
    rc = 0
    for attempt in range(1, 4):
        cmd = ('set -o pipefail; curl -sSL --connect-timeout 30 --max-time 1800 '
               '--retry 5 --retry-delay 5 --retry-all-errors '
               '--speed-limit 100000 --speed-time 60 "%s" | tar -xJ -C %s'
               % (url, traces_dir))
        print(f"+ download attempt {attempt}: {cmd}", flush=True)
        rc = subprocess.run(cmd, shell=True, executable="/bin/bash").returncode
        print(f"  attempt {attempt}: curl/tar rc={rc}", flush=True)
        if rc == 0:
            return 0
        time.sleep(15)
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--config", required=True, help="directory name under variants/")
    ap.add_argument("--plan", default="fullsets_isoB.json")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--out-dir", default="fullset_onebit")
    ap.add_argument("--skip-download", action="store_true")
    a = ap.parse_args()

    plan = json.load(open(a.plan))
    me = plan.get(str(a.shard))
    if me is None:
        print(f"shard {a.shard}: no plan entry, exiting")
        return 0

    cat, traces = me["category"], me["traces"]
    print(f"===== shard {a.shard}: category {cat}, {len(traces)} traces, config {a.config} =====")
    print("      " + ", ".join(traces))
    sh("df -h . | tail -2")
    sh("nproc; free -g | head -2")

    os.makedirs(a.traces_dir, exist_ok=True)
    os.makedirs(a.logs_dir, exist_ok=True)
    os.makedirs(a.out_dir, exist_ok=True)

    if not a.skip_download:
        rc = download_category(me, a.traces_dir)
        print(f"drive download+extract rc={rc}")
        sh("df -h . | tail -1")

    found = sum(1 for t in traces if find_trace(a.traces_dir, t))
    print(f"found {found}/{len(traces)} traces")
    if found != len(traces):
        print("!! missing traces, listing:")
        subprocess.run(f"find {a.traces_dir} -name '*.gz' | head -50", shell=True)
        print("!! giving up on this shard: the trace set is incomplete")
        return 3

    # ---- build the one configuration ----
    vdir = os.path.join("variants", a.config)
    if not os.path.isdir(vdir):
        print(f"!! no such variant dir: {vdir}")
        return 2
    for fn in sorted(os.listdir(vdir)):
        if fn.endswith((".h", ".cc")):
            shutil.copy(os.path.join(vdir, fn), fn)
    sh("make clean >/dev/null")
    sh(f"make -j{a.parallel}")
    subprocess.run("grep -E '^#define (NUM_INPUTS|NUM_CLAUSES|THRESHOLD|TM_PATH_BRANCHES|TM_MODE|ONEBIT)' tm.h",
                   shell=True)

    rows = []

    def run(tr):
        p = find_trace(a.traces_dir, tr)
        log = os.path.join(a.logs_dir, f"{a.config}__{tr}.log")
        if p is None:
            return {"shard": a.shard, "category": cat, "variant": a.config,
                    "trace": tr, "seconds": "", "rc": 1}
        t0 = time.time()
        with open(log, "wb") as fh:
            rc = subprocess.call(["./cbp", "-E", "1000000", p], stdout=fh,
                                 stderr=subprocess.STDOUT)
        r = {"shard": a.shard, "category": cat, "variant": a.config,
             "trace": tr, "seconds": f"{time.time()-t0:.1f}", "rc": rc}
        r.update(scrape(log))
        return r

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        futs = {pool.submit(run, tr): tr for tr in traces}
        for fut in as_completed(futs):
            r = fut.result()
            rows.append(r)
            print(f"    {r['trace']:<22} {r.get('seconds',''):>8}s rc={r['rc']} "
                  f"TM={r.get('TM MPKI','-')} 1bit={r.get('1bit MPKI','-')} "
                  f"HYB={r.get('HYB MPKI','-')}", flush=True)
    print(f"  config {a.config} took {time.time()-t0:.0f}s")

    path = os.path.join(a.out_dir, f"shard-{a.shard:02d}-{cat}.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: r["trace"]):
            w.writerow(r)

    bad = [r for r in rows if r["rc"] != 0 or not r.get("TM MPKI")]
    print(f"\n--- shard {a.shard} done: {len(rows)-len(bad)}/{len(rows)} ok ---")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
