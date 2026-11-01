#!/usr/bin/env python3
"""One shard of the obp-attribution experiment: ONE trace x ALL variants.

A shard = one T6 trace, so only that trace's category tarball is downloaded.
Every variant is built in the same tree (sequentially) and then all binaries run
in parallel with TM_LITERAL_OUT set, so each run drops

    <variant>__<trace>_clause_snapshots.csv
    <variant>__<trace>_literal_duty.csv
    <variant>__<trace>_cross_table.csv

into --stats-dir.  The observer is inert, so the MPKI must be unchanged; the
gate job in the workflow proves that on the smoke traces before this runs.
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

VARIANT_FILES = ["tm.cc", "tm.h", "tm_predictor.cc", "tm_predictor.h",
                 "cond_branch_predictor_interface.cc"]

FIELDS = ["shard", "trace", "variant", "seconds", "rc",
          "TM MPKI", "TM accuracy", "TM right", "TM wrong",
          "GShare MPKI", "GShare accuracy", "TAGE MPKI", "instructions",
          "1bit MPKI", "1bit accuracy",
          "inbit_correct_acc", "inbit_wrong_acc",
          "obp_correct_acc", "obp_wrong_acc",
          "agree_pct", "disagree_tm_acc"]


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
                      "GShare MPKI", "GShare accuracy",
                      "1bit MPKI", "1bit accuracy",
                      "Measured # of instructions"):
                if line.startswith(k + ":"):
                    out[k] = line.split(":", 1)[1].strip()
            f = line.split()
            if len(f) >= 5 and f[0] == "CondDirect":
                out["TAGE MPKI"] = f[4]
    if "Measured # of instructions" in out:
        out["instructions"] = out.pop("Measured # of instructions")
    return out


def read_cross(path):
    """<prefix>_cross_table.csv -> the six derived accuracies."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            b = r["bucket"]
            if b == "inbit_correct":
                out["inbit_correct_acc"] = r["acc_pct"]
            elif b == "inbit_wrong":
                out["inbit_wrong_acc"] = r["acc_pct"]
            elif b == "obp_correct":
                out["obp_correct_acc"] = r["acc_pct"]
            elif b == "obp_wrong":
                out["obp_wrong_acc"] = r["acc_pct"]
            elif b == "agree":
                out["agree_pct"] = r["acc_pct"]
            elif b == "disagree":
                out["disagree_tm_acc"] = r["acc_pct"]
    return out


def restore():
    subprocess.run(["git", "checkout", "--"] + VARIANT_FILES,
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def enable_observer():
    txt = open("tm.h").read()
    new = txt.replace("#define TM_LITERAL_STATS 0", "#define TM_LITERAL_STATS 1", 1)
    if new == txt:
        raise RuntimeError("could not switch TM_LITERAL_STATS on (tm.h layout changed?)")
    open("tm.h", "w").write(new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--stats-dir", default="exp_stats")
    ap.add_argument("--out-dir", default="exp_results")
    ap.add_argument("--plan", default="experiments_plan.json")
    ap.add_argument("--variants-dir", default="variants")
    a = ap.parse_args()

    plan = json.load(open(a.plan))
    me = plan["shards"].get(str(a.shard))
    if me is None:
        print("shard %d: no plan entry" % a.shard)
        return 0
    variants = plan["variants"]
    trace = me["trace"]

    print("===== shard %d: %s x %d variants =====" % (a.shard, trace, len(variants)))
    sh("nproc; free -g | head -2; df -h . | tail -2")

    os.makedirs(a.traces_dir, exist_ok=True)
    for dom, info in me["categories"].items():
        url = ("https://drive.usercontent.google.com/download?id=%s&export=download&confirm=t"
               % info["gdrive_id"])
        t0 = time.time()
        cmd = ('set -o pipefail; curl -sSL --retry 3 --retry-delay 5 "%s" | tar -xJ -C %s'
               % (url, a.traces_dir))
        print("+ drive %s %s (%s GB)" % (dom, info["tarball"], info["size_gb"]), flush=True)
        subprocess.run(cmd, shell=True, check=True, executable="/bin/bash")
        print("  download+extract %.0fs" % (time.time() - t0))
    tp = find_trace(a.traces_dir, trace)
    if tp is None:
        print("::error::trace %s missing" % trace)
        return 1
    tp = os.path.abspath(tp)

    os.makedirs("bins", exist_ok=True)
    os.makedirs(a.logs_dir, exist_ok=True)
    os.makedirs(a.stats_dir, exist_ok=True)
    os.makedirs(a.out_dir, exist_ok=True)

    built = []
    for name in variants:
        vdir = os.path.join(a.variants_dir, name)
        if not os.path.isdir(vdir):
            print("::error::variant %s missing under %s" % (name, a.variants_dir))
            return 1
        t0 = time.time()
        restore()
        for fn in sorted(os.listdir(vdir)):
            if fn.endswith((".h", ".cc")):
                shutil.copy(os.path.join(vdir, fn), fn)
        enable_observer()
        subprocess.run("make clean >/dev/null 2>&1; make -j4", shell=True, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        dst = os.path.join("bins", "cbp__" + name)
        shutil.copy("cbp", dst)
        built.append((name, dst))
        print("    built %-20s in %.0fs" % (name, time.time() - t0), flush=True)
    restore()

    def run(name, binary):
        log = os.path.join(a.logs_dir, "shard%02d__%s__%s.log" % (a.shard, trace, name))
        prefix = os.path.join(a.stats_dir, "%s__%s" % (name, trace))
        env = os.environ.copy()
        env["TM_LITERAL_OUT"] = prefix
        t0 = time.time()
        with open(log, "wb") as fh:
            rc = subprocess.call([binary, "-E", "1000000", tp], stdout=fh,
                                 stderr=subprocess.STDOUT, env=env)
        row = {"shard": a.shard, "trace": trace, "variant": name,
               "seconds": "%.1f" % (time.time() - t0), "rc": rc}
        row.update(scrape(log))
        row.update(read_cross(prefix + "_cross_table.csv"))
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        futs = [pool.submit(run, n, b) for (n, b) in built]
        for fut in as_completed(futs):
            row = fut.result()
            rows.append(row)
            print("    %-20s %8ss rc=%s MPKI=%-10s 1bit=%-10s agree=%s" % (
                row["variant"], row["seconds"], row["rc"],
                row.get("TM MPKI", "-"), row.get("1bit MPKI", "-"),
                row.get("agree_pct", "-")), flush=True)

    path = os.path.join(a.out_dir, "shard-%02d.csv" % a.shard)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: r["variant"]):
            w.writerow(r)

    # ---- anchor checks: the two reference variants must be exact -------------
    problems = []
    bad = [r for r in rows if r["rc"] != 0 or not r.get("TM MPKI")]
    if bad:
        problems.append("%d runs failed" % len(bad))
    for ref in ("exp0_baseline_obs", "exp1a_obp"):
        exp = (plan.get("expect_tm_mpki", {}).get(ref) or {}).get(trace)
        if exp is None:
            continue
        got = [float(r["TM MPKI"]) for r in rows if r["variant"] == ref and r.get("TM MPKI")]
        if not got or abs(got[0] - exp) > 0.001:
            problems.append("%s on %s: got %s expected %s" % (ref, trace, got, exp))
        else:
            print("anchor %s on %s reproduced: %s" % (ref, trace, exp))
    # every run must have dropped its observer CSVs; the cross table only exists
    # for builds with TM_HAS_OBP == 1 (the no-obp controls do not compile it)
    cross_map = plan.get("has_cross_table", {})
    for r in rows:
        p = os.path.join(a.stats_dir, "%s__%s" % (r["variant"], trace))
        need = ["_clause_snapshots.csv", "_literal_duty.csv"]
        if cross_map.get(r["variant"], True):
            need.append("_cross_table.csv")
        for suf in need:
            if not os.path.exists(p + suf):
                problems.append("%s/%s missing %s" % (r["variant"], trace, suf))
    if problems:
        for p in problems:
            print("::error::shard %d: %s" % (a.shard, p))
        return 1
    print("--- shard %d OK: %d runs ---" % (a.shard, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
