#!/usr/bin/env python3
"""One shard of the literal-dynamics experiment (A config, T6 six traces).

A shard = ONE trace = ONE category tarball.  It builds the instrumented variant
(variants/literal_stats_A/tm.cc), runs the trace ONCE with TM_LITERAL_OUT set,
and gates on the published T6 MPKI for that trace by STRING equality
(bit-identity, not a tolerance).

Lessons baked in (2026-10-18..20):
  * hardened Google Drive download: connect/max-time, low-speed abort, curl
    retries, trace-completeness check, clean rc=3 when the trace set is short;
  * NO `cmd | head` anywhere in this file (SIGPIPE + pipefail = exit 2, the bug
    that killed the 10-18 collect);
  * the variant source is locked by sha256 before the build, so a shard cannot
    silently run the wrong source.

Usage:
  python3 scripts/run_literal_shard.py --shard 0 --plan literal_t6.json \
      --variant literal_stats_A --traces-dir traces --logs-dir logs \
      --stats-dir literal_stats --out-dir literal_results
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
    """Hardened Drive download, copied from f011528's run_fullset_cfg.py."""
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
    ap.add_argument("--plan", default="literal_t6.json")
    ap.add_argument("--variant", default="literal_stats_A")
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--stats-dir", default="literal_stats")
    ap.add_argument("--out-dir", default="literal_results")
    ap.add_argument("--num-inputs", type=int, default=81,
                    help="NUM_INPUTS of the variant (duty CSV row count)")
    a = ap.parse_args()

    plan = json.load(open(a.plan))
    me = plan["shards"][str(a.shard)]
    trace = me["trace"]
    print("===== shard %d: %s (%s, ~%.2f GB) ====="
          % (a.shard, trace, me["category"], me["size_gb"]))
    print("  expected TM MPKI: %s (string equality = bit-identity)" % me["expect_tm_mpki"])

    # 1. source integrity
    vdir = os.path.join("variants", a.variant)
    want = plan.get("variant_sha256", "")
    got = sha256_file(os.path.join(vdir, "tm.cc"))
    print("  variant tm.cc sha256: %s" % got)
    if want and got != want:
        print("::error::variant tm.cc sha256 %s != locked %s - refusing to build" % (got, want))
        return 2

    # 2. hardened download
    os.makedirs(a.traces_dir, exist_ok=True)
    tp = download_category(me, a.traces_dir)
    if tp is None:
        print("::error::trace %s missing after 3 download attempts" % trace)
        return 3
    tp = os.path.abspath(tp)

    # 3. install the instrumented variant and build
    for fn in sorted(os.listdir(vdir)):
        if fn.endswith((".h", ".cc")):
            shutil.copy(os.path.join(vdir, fn), fn)
    sh("make clean >/dev/null 2>&1 || true")
    print("+ make -j4", flush=True)
    r = subprocess.run("make -j4", shell=True)
    if r.returncode != 0:
        print("::error::build failed")
        return 4
    print("+ built cbp for variant %s" % a.variant, flush=True)

    # 4. run once with the per-trace statistics prefix
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

    # 5. statistics sanity
    snap = prefix + "_clause_snapshots.csv"
    duty = prefix + "_literal_duty.csv"
    problems = []
    if rc != 0:
        problems.append("cbp rc=%d" % rc)
    upd = ""
    if not os.path.exists(snap):
        problems.append("missing snapshot CSV")
    elif sum(1 for _ in open(snap)) < 33:
        problems.append("snapshot CSV too short")
    if not os.path.exists(duty):
        problems.append("missing duty CSV")
    else:
        lines = open(duty).read().strip().splitlines()
        if len(lines) != a.num_inputs + 1:
            problems.append("duty has %d lines (expect %d rows + header)"
                            % (len(lines), a.num_inputs))
        else:
            tot = int(lines[1].split(",")[5])
            upd = tot // 32
            row["resolved_updates"] = upd
    with open(os.path.join(a.out_dir, "GATE-shard-%02d.txt" % a.shard), "w") as fh:
        fh.write("shard=%d trace=%s expected_tm_mpki=%s got_tm_mpki=%s rc=%d "
                 "resolved_updates=%s\n"
                 % (a.shard, trace, me["expect_tm_mpki"], row.get("TM MPKI"), rc, upd))

    # 6. bit-identity gate
    if row.get("TM MPKI") != me["expect_tm_mpki"]:
        problems.append("TM MPKI %r != published %r"
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
