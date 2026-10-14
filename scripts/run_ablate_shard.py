#!/usr/bin/env python3
"""One shard of the V13 input-ablation experiment, running inside a GHA runner.

A shard = one trace group x ONE configuration x ALL FOUR ablation modes.
Every (trace, mode) pair is one cbp run; `--parallel` of them run at a time
(the runner has 4 vCPU).

Self-checks (a shard that does not reproduce the published numbers goes red):
  1. every NONE row must equal the expected value embedded in ablatesets.json
     (baseline = 2026-09-29 ku full sweep, FPTM = 2026-10-13 GHA full-set run);
  2. the L ablation must move MPKI on at least one trace of the group, and
     P/B must move it somewhere -- otherwise $TM_ABLATE never reached the code.

The pristine tree is restored with `git checkout --` before the variant overlay
is copied, so no shard can inherit another shard's configuration (the ablation
hook itself is committed in tm_predictor.cc and is therefore preserved).
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

FIELDS = ["shard", "group", "domains", "cfg", "mode", "trace", "seconds", "rc",
          "TM MPKI", "TM accuracy", "TM right", "TM wrong",
          "GShare MPKI", "GShare accuracy", "TAGE MPKI"]


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
            for k in ("TM MPKI", "TM accuracy", "TM right", "TM wrong",
                      "GShare MPKI", "GShare accuracy"):
                if line.startswith(k + ":"):
                    out[k] = line.split(":", 1)[1].strip()
            f = line.split()
            if len(f) >= 5 and f[0] == "CondDirect":
                out["TAGE MPKI"] = f[4]
    return out


def num(d, key):
    v = d.get(key)
    if v is None:
        return None
    try:
        return float(str(v).rstrip("%"))
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--out-dir", default="ablation_results")
    ap.add_argument("--plan", default="ablatesets.json")
    a = ap.parse_args()

    plan = json.load(open(a.plan))
    me = plan["shards"].get(str(a.shard))
    if me is None:
        print(f"shard {a.shard}: no plan entry - nothing to do")
        return 0

    modes, group, cfg = plan["modes"], me["group"], me["cfg"]
    traces = me["traces"]
    print(f"===== shard {a.shard} = group {group} x cfg {cfg} x modes {list(modes)} =====")
    print(f"      domains: {', '.join(me['domains'])}   traces: {', '.join(traces)}")
    print(f"      estimated shard time: {me['est_shard_sec']}s")
    sh("nproc; free -g | head -2; df -h . | tail -2")

    os.makedirs(a.traces_dir, exist_ok=True)

    # ---- 1) stream each needed category tarball straight from Google Drive ----
    #      (no pip/gdown: Ubuntu 24.04 python is externally managed, PEP 668)
    for dom, info in me["categories"].items():
        url = ("https://drive.usercontent.google.com/download?id=%s&export=download&confirm=t"
               % info["gdrive_id"])
        t0 = time.time()
        cmd = ('set -o pipefail; curl -sSL --retry 3 --retry-delay 5 "%s" | tar -xJ -C %s'
               % (url, a.traces_dir))
        print(f"+ drive {dom} {info['tarball']} ({info['size_gb']} GB)", flush=True)
        subprocess.run(cmd, shell=True, check=True, executable="/bin/bash")
        print(f"  {dom}: download+extract {time.time() - t0:.0f}s")

    missing = [t for t in traces if find_trace(a.traces_dir, t) is None]
    if missing:
        print(f"::error::traces missing after extraction: {missing}")
        subprocess.run(f"find {a.traces_dir} -name '*.gz' | head -30", shell=True)
        return 1
    sh("df -h . | tail -1")

    # ---- 2) pristine tree + this shard's configuration overlay, then build ----
    subprocess.check_call(["git", "checkout", "--", "tm.cc", "tm.h", "tm_predictor.cc"])
    vdir = os.path.join("variants", cfg)
    applied = []
    for fn in sorted(os.listdir(vdir)):
        if fn.endswith((".h", ".cc")):
            shutil.copy(os.path.join(vdir, fn), fn)
            applied.append(fn)
    print(f"config {cfg}: applied overrides {applied if applied else '(none - baseline)'}")
    sh("make clean >/dev/null")
    sh("make -j4")

    # ---- 3) every (trace, mode) pair, `--parallel` at a time ----
    os.makedirs(a.logs_dir, exist_ok=True)
    os.makedirs(a.out_dir, exist_ok=True)
    rows = []

    def run(mode, tr):
        p = find_trace(a.traces_dir, tr)
        log = os.path.join(a.logs_dir, f"shard{a.shard:02d}__{group}__{cfg}__{mode}__{tr}.log")
        env = dict(os.environ)
        env["TM_ABLATE"] = mode
        t0 = time.time()
        with open(log, "wb") as fh:
            rc = subprocess.call(["./cbp", "-E", "1000000", p], stdout=fh,
                                 stderr=subprocess.STDOUT, env=env)
        r = {"shard": a.shard, "group": group, "domains": "+".join(me["domains"]),
             "cfg": cfg, "mode": mode, "trace": tr,
             "seconds": f"{time.time() - t0:.1f}", "rc": rc}
        r.update(scrape(log))
        return r

    t0 = time.time()
    tasks = [(m, t) for m in modes for t in traces]
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        futs = {pool.submit(run, m, t): (m, t) for m, t in tasks}
        for fut in as_completed(futs):
            r = fut.result()
            rows.append(r)
            print(f"    {r['mode']:<4} {r['trace']:<20} {r['seconds']:>8}s rc={r['rc']} "
                  f"MPKI={r.get('TM MPKI','-')} acc={r.get('TM accuracy','-')}", flush=True)
    print(f"  shard wall {time.time() - t0:.0f}s for {len(tasks)} runs")

    path = os.path.join(a.out_dir, f"shard-{a.shard:02d}-{group}-{cfg}.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["mode"], r["trace"])):
            w.writerow(r)

    # ---- 4) self-checks ------------------------------------------------------
    bad = [r for r in rows if r["rc"] != 0 or num(r, "TM MPKI") is None]
    problems = []
    if bad:
        problems.append(f"{len(bad)} runs failed or produced no TM MPKI: "
                        + ", ".join(f"{r['mode']}/{r['trace']}(rc={r['rc']})" for r in bad))

    by = {(r["mode"], r["trace"]): num(r, "TM MPKI") for r in rows}
    for tr, exp in me["expect"].items():
        got = by.get(("NONE", tr))
        if got is None:
            problems.append(f"NONE/{tr}: missing")
        elif abs(got - exp[0]) > 0.001:
            problems.append(f"NONE/{tr}: MPKI {got} != published {exp[0]}")
    print("NONE control: " + ("all rows reproduce the published MPKI" if not problems else "MISMATCH"))

    if len(traces) > 0:
        moved_L = max(abs((by.get(("L", t)) or 0) - (by.get(("NONE", t)) or 0)) for t in traces)
        moved_P = max(abs((by.get(("P", t)) or 0) - (by.get(("NONE", t)) or 0)) for t in traces)
        moved_B = max(abs((by.get(("B", t)) or 0) - (by.get(("NONE", t)) or 0)) for t in traces)
        print(f"ablation activity: max|dMPKI| P={moved_P:.4f} L={moved_L:.4f} B={moved_B:.4f}")
        if moved_L < 0.01 or moved_P < 0.001 or moved_B < 0.001:
            problems.append(f"ablation hook looks inactive (P={moved_P}, L={moved_L}, B={moved_B})")

    if problems:
        for p in problems:
            print(f"::error::shard {a.shard}: {p}")
        return 1
    print(f"--- shard {a.shard} OK: {len(rows)} runs, {len(traces)} traces x {len(modes)} modes ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
