#!/usr/bin/env python3
"""One shard of the literal-dynamics B batch (isoB_49in_53cl, 49 in / 53 cl / T=10).

Same observer, same rules as scripts/run_literal_shard.py (A batch), but the
per-run sanity numbers are plan-driven: B has 49 inputs (duty file = 50 lines
with header) and 53 clauses (total slots = updates * 53).

The variant directory must carry BOTH tm.cc (instrumented) and B's tm.h /
tm_predictor.cc / tm_predictor.h (TM_PATH_BRANCHES 0 needs the padding patch in
tm_predictor.h), so all four are copied over the repo tree before the build.

Hardened Drive download + no `cmd | head` + sha256-pinned variant, as in A.
"""
import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

FIELDS = ["variant", "trace", "seconds", "rc",
          "TM MPKI", "TM accuracy", "TM right", "TM wrong",
          "GShare MPKI", "GShare accuracy", "TAGE MPKI",
          "instructions", "GShare wrong", "resolved_updates", "stats_prefix"]


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
            if line.startswith("GShare wrong:"):
                out["GShare wrong"] = line.split(":", 1)[1].strip()
            if line.startswith("Measured # of instructions:"):
                out["instructions"] = line.split(":", 1)[1].strip()
            f = line.split()
            if len(f) >= 5 and f[0] == "CondDirect":
                out["TAGE MPKI"] = f[4]
    return out


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_category(me, traces_dir):
    url = ("https://drive.usercontent.google.com/download?id=%s&export=download&confirm=t"
           % me["gdrive_id"])
    t0 = time.time()
    tp = None
    for attempt in range(1, 4):
        cmd = ('set -o pipefail; curl -sSL --connect-timeout 30 --max-time 1800 '
               '--retry 5 --retry-delay 5 --retry-all-errors '
               '--speed-limit 100000 --speed-time 60 "%s" | tar -xJ -C %s'
               % (url, traces_dir))
        print("+ download attempt %d: %s" % (attempt, cmd), flush=True)
        rc = subprocess.run(cmd, shell=True, executable="/bin/bash").returncode
        tp = find_trace(traces_dir, me["trace"])
        print("  attempt %d: rc=%d trace_present=%s" % (attempt, rc, bool(tp)), flush=True)
        if tp is not None:
            break
        time.sleep(15)
    print("drive download+extract: %.0fs" % (time.time() - t0))
    return tp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--plan", default="literal_t6_B.json")
    ap.add_argument("--variant", default="literal_stats_B")
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--stats-dir", default="literal_stats_b")
    ap.add_argument("--out-dir", default="literal_results_b")
    a = ap.parse_args()

    plan = json.load(open(a.plan))
    me = plan["shards"][str(a.shard)]
    trace = me["trace"]
    ncl = int(plan.get("num_clauses", 32))
    duty_lines = int(plan.get("duty_lines", 82))
    print("===== shard %d: %s (%s)  [B: %d clauses, duty file %d lines] ====="
          % (a.shard, trace, me["category"], ncl, duty_lines))
    print("  expected TM MPKI: %s (string equality = bit-identity)" % me["expect_tm_mpki"])

    vdir = os.path.join("variants", a.variant)
    want = plan.get("variant_sha256", "")
    got = sha256_file(os.path.join(vdir, "tm.cc"))
    print("  variant tm.cc sha256: %s" % got)
    if want and got != want:
        print("::error::variant tm.cc sha256 %s != locked %s - refusing to build" % (got, want))
        return 2

    os.makedirs(a.traces_dir, exist_ok=True)
    tp = download_category(me, a.traces_dir)
    if tp is None:
        print("::error::trace %s missing after 3 download attempts" % trace)
        return 3
    tp = os.path.abspath(tp)

    for fn in sorted(os.listdir(vdir)):
        if fn.endswith((".h", ".cc")):
            shutil.copy(os.path.join(vdir, fn), fn)
    subprocess.run("make clean >/dev/null 2>&1 || true", shell=True)
    print("+ make -j4", flush=True)
    if subprocess.run("make -j4", shell=True).returncode != 0:
        print("::error::build failed")
        return 4

    for d in (a.logs_dir, a.stats_dir, a.out_dir):
        os.makedirs(d, exist_ok=True)
    prefix = os.path.join(a.stats_dir, "%s__%s" % (a.variant, trace))
    log = os.path.join(a.logs_dir, "%s__%s.log" % (a.variant, trace))
    env = dict(os.environ)
    env["TM_LITERAL_OUT"] = prefix
    t0 = time.time()
    with open(log, "wb") as fh:
        rc = subprocess.call(["./cbp", "-E", "1000000", tp],
                             stdout=fh, stderr=subprocess.STDOUT, env=env)
    secs = time.time() - t0
    row = {"variant": a.variant, "trace": trace, "seconds": "%.1f" % secs,
           "rc": rc, "stats_prefix": prefix}
    row.update(scrape(log))

    snap = prefix + "_clause_snapshots.csv"
    duty = prefix + "_literal_duty.csv"
    problems = []
    if rc != 0:
        problems.append("cbp rc=%d" % rc)
    upd = ""
    if not os.path.exists(snap):
        problems.append("missing snapshot CSV")
    else:
        n_lines = sum(1 for _ in open(snap))
        if n_lines < 1 + ncl:
            problems.append("snapshot CSV too short (%d lines)" % n_lines)
    if not os.path.exists(duty):
        problems.append("missing duty CSV")
    else:
        lines = open(duty).read().strip().splitlines()
        if len(lines) != duty_lines:
            problems.append("duty has %d lines (expect %d)" % (len(lines), duty_lines))
        else:
            tot = int(lines[1].split(",")[5])
            upd = tot // ncl
            row["resolved_updates"] = upd
    with open(os.path.join(a.out_dir, "GATE-shard-%02d.txt" % a.shard), "w") as fh:
        fh.write("shard=%d trace=%s expected_tm_mpki=%s got_tm_mpki=%s rc=%d "
                 "resolved_updates=%s\n"
                 % (a.shard, trace, me["expect_tm_mpki"], row.get("TM MPKI"), rc, upd))
    if row.get("TM MPKI") != me["expect_tm_mpki"]:
        problems.append("TM MPKI %r != locked 10-16 B value %r"
                        % (row.get("TM MPKI"), me["expect_tm_mpki"]))

    path = os.path.join(a.out_dir, "shard-%02d.csv" % a.shard)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerow(row)

    print("  ran %.1fs rc=%d MPKI=%s acc=%s instr=%s updates=%s"
          % (secs, rc, row.get("TM MPKI"), row.get("TM accuracy"),
             row.get("instructions"), upd))
    if problems:
        for p in problems:
            print("::error::shard %d: %s" % (a.shard, p))
        return 1
    print("--- shard %d OK: %s reproduced %s bit-identically ---"
          % (a.shard, trace, me["expect_tm_mpki"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
