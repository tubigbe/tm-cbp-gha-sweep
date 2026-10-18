#!/usr/bin/env python3
"""Recover a failed full-set collect from an EXISTING run's artifacts.

Why this exists
---------------
The shard runs cost ~1 h of runner time and their artifacts live 14 days.  A
collect that dies after the shards finished must therefore be re-runnable
WITHOUT re-running a single shard.  This script is that re-run: it is handed
the artifact tree (downloaded by the workflow with `run-id`) and does the
collect itself.

Design rules
------------
* Fail-soft: everything is inventoried and written before anything is
  asserted, so a failure is diagnosable from the repo alone (INVENTORY.txt).
* Raw stdout is recognised by LOCATION (any regular file under a directory
  named `logs`), not by suffix: the old collect died on nothing but a suffix
  assumption, and the trace stdout is the one thing artifacts must not lose.
* The SHA256SUMS manifest hashes the UNCOMPRESSED bytes (gzip output differs
  between zlib versions, so hashing the .gz would not be reproducible).

Usage
-----
  python3 scripts/recover_collect.py --src collected_a --out baseA_results \
      --expect 105 [--strict]

Exit codes: 0 complete (or report-only), 1 incomplete with --strict.
"""
import argparse
import csv
import glob
import gzip
import hashlib
import os
import sys


def walk_files(root):
    for d, _sub, files in os.walk(root):
        for fn in sorted(files):
            yield os.path.join(d, fn)


def is_raw_stdout(path):
    """Per-trace cbp stdout = a regular file inside a directory named `logs`."""
    return os.path.basename(os.path.dirname(path)) == "logs"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", action="append", required=True,
                    help="artifact root (repeatable), e.g. --src collected_a")
    ap.add_argument("--out", required=True, help="results dir, e.g. baseA_results")
    ap.add_argument("--expect", type=int, default=0,
                    help="required number of per-trace logs; 0 = do not check")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when the collect is incomplete")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    logs_out = os.path.join(a.out, "logs")
    os.makedirs(logs_out, exist_ok=True)
    inv = []

    def say(line):
        print(line, flush=True)
        inv.append(line)

    # ---- 1. inventory: every file, every suffix, before touching anything ----
    total_files = 0
    for src in a.src:
        say("=== source %s ===" % src)
        if not os.path.isdir(src):
            say("  !! MISSING source dir %s" % src)
            continue
        n = 0
        for p in walk_files(src):
            n += 1
            say("  %10d  %s" % (os.path.getsize(p), os.path.relpath(p, src)))
        total_files += n
        say("  (%d file(s))" % n)

    # ---- 2. shard CSVs -> <out>/ ; ALL.csv ; row counts ----
    csvs, rows_by_csv = [], []
    for src in a.src:
        if not os.path.isdir(src):
            continue
        for p in sorted(glob.glob(os.path.join(src, "**", "*.csv"), recursive=True)):
            dst = os.path.join(a.out, os.path.basename(p))
            with open(p, "rb") as fh:
                data = fh.read()
            with open(dst, "wb") as fh:
                fh.write(data)
            csvs.append(dst)
            with open(dst, newline="") as fh:
                r = list(csv.reader(fh))
            rows_by_csv.append((os.path.basename(dst), max(0, len(r) - 1)))
    rows_by_csv.sort()
    n_rows = sum(r for _f, r in rows_by_csv)
    all_csv = os.path.join(a.out, "ALL.csv")
    with open(all_csv, "wb") as out:
        for f in sorted(csvs):
            if os.path.basename(f) == "ALL.csv":
                continue
            with open(f, "rb") as fh:
                out.write(fh.read())
    say("--- CSVs: %d file(s), %d data row(s) ---" % (len(csvs), n_rows))
    for f, r in rows_by_csv:
        say("  %5d rows  %s" % (r, f))

    # ---- 3. per-trace raw stdout -> <out>/logs/*.gz + SHA256SUMS ----
    manifest, n_logs, raw_total = [], 0, 0
    for src in a.src:
        if not os.path.isdir(src):
            continue
        for p in walk_files(src):
            if not is_raw_stdout(p):
                continue
            n_logs += 1
            with open(p, "rb") as fh:
                data = fh.read()
            base = os.path.basename(p).replace(".log", "")
            dst = os.path.join(logs_out, base + ".log.gz")
            if os.path.exists(dst):
                dst = os.path.join(logs_out, base + ".dup.log.gz")
            with gzip.open(dst, "wb", compresslevel=9) as fh:
                fh.write(data)
            raw_total += len(data)
            manifest.append("%s  %d  %s" % (hashlib.sha256(data).hexdigest(),
                                            len(data), os.path.basename(dst)))
    if manifest:
        with open(os.path.join(logs_out, "SHA256SUMS"), "w") as fh:
            fh.write("\n".join(manifest) + "\n")
    say("--- raw stdout: %d log(s), %d -> %d bytes in %s ---"
        % (n_logs, raw_total, sum(os.path.getsize(os.path.join(logs_out, os.path.basename(m.split()[-1])))
                                  for m in manifest), logs_out))

    # how many logs actually carry the two columns the CSV cannot hold
    carrying = 0
    for m in manifest:
        f = os.path.join(logs_out, m.split()[-1])
        with gzip.open(f, "rt", errors="replace") as fh:
            t = fh.read()
        if "Measured # of instructions" in t and "GShare wrong" in t:
            carrying += 1
    say("--- logs carrying 'instructions' + 'GShare wrong': %d ---" % carrying)

    # ---- 4. verdict ----
    ok = True
    if a.expect:
        if n_logs != a.expect:
            say("!! INCOMPLETE: expected %d log(s), got %d" % (a.expect, n_logs))
            ok = False
        if n_rows != n_logs:
            say("!! MISMATCH: %d CSV data row(s) vs %d log(s)" % (n_rows, n_logs))
            ok = False
        if carrying != a.expect:
            say("!! MISMATCH: only %d/%d log(s) carry the two comparison columns"
                % (carrying, a.expect))
            ok = False
    say("--- VERDICT: %s (files seen %d) ---" % ("COMPLETE" if ok else "INCOMPLETE",
                                                 total_files))

    with open(os.path.join(a.out, "INVENTORY.txt"), "w") as fh:
        fh.write("\n".join(inv) + "\n")
    print("wrote %s/INVENTORY.txt" % a.out, flush=True)

    if not ok and a.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
