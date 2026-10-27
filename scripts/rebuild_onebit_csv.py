#!/usr/bin/env python3
"""Rebuild onebit_results/ALL.csv from the committed per-trace raw stdout.

Why: the collect job assembled ALL.csv with `cat shard-*.csv`, which is fragile -
if a shard CSV is stale (old column layout) the header and the data rows disagree
and every later column shifts silently.  The raw stdout of all 66 runs is
committed and complete, so the authoritative table is rebuilt from it.

seconds/rc are taken from the shard CSVs when the (variant, trace) row is present
in the current layout; they are diagnostics, not measurements.
"""
import argparse
import csv
import glob
import gzip
import json
import os
import sys

FIELDS = ["shard", "trace", "variant", "mode", "seconds", "rc",
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


def scrape(text):
    out = {}
    for line in text.splitlines():
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="onebit_results")
    ap.add_argument("--plan", default="t6_onebit.json")
    a = ap.parse_args()
    d = a.results
    plan = json.load(open(a.plan))
    mode = {v["name"]: v.get("mode", "") for v in plan["variants"]}

    extra = {}
    for f in glob.glob(os.path.join(d, "shard-*.csv")):
        with open(f, newline="") as fh:
            rd = csv.DictReader(fh)
            if "override count" not in (rd.fieldnames or []):
                continue          # stale layout: do not trust it
            for r in rd:
                extra[(r.get("variant"), r.get("trace"))] = (r.get("seconds", ""), r.get("rc", ""))

    rows = {}
    for gz in sorted(glob.glob(os.path.join(d, "logs", "*.log.gz"))):
        base = os.path.basename(gz)[:-3]                  # cfg__trace.log
        if "__" not in base:
            continue
        variant, trace = base[:-4].split("__", 1)
        with gzip.open(gz, "rt", errors="replace") as fh:
            rec = scrape(fh.read())
        rec.update({"variant": variant, "trace": trace, "mode": mode.get(variant, "")})
        sec, rc = extra.get((variant, trace), ("", ""))
        rec["seconds"], rec["rc"] = sec, rc
        rows[(variant, trace)] = rec

    with open(os.path.join(d, "ALL.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for key in sorted(rows):
            w.writerow(rows[key])
    print("rebuilt %s/ALL.csv from %d raw-stdout logs" % (d, len(rows)))
    bad = [k for k, r in rows.items() if not r.get("TM MPKI")]
    if bad:
        print("::error::missing TM MPKI for", bad[:5])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
