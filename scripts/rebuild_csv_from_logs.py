#!/usr/bin/env python3
"""Rebuild <results>/ALL.csv from the committed per-trace raw stdout.

Why: the 2026-10-18 recovery of the 10-16 iso-area B run brought back the raw
stdout of all 105 traces, but the CSVs in that run's artifacts predate the
`instructions` / `GShare wrong` columns.  They exist only in the raw logs, so
the authoritative CSV is rebuilt from the logs; seconds/rc are carried over
from the recovered shard CSVs when present.

Usage:
  python3 scripts/rebuild_csv_from_logs.py --results-dir isoB_results
  python3 scripts/rebuild_csv_from_logs.py --results-dir baseA_results
"""
import argparse
import csv
import glob
import gzip
import os
import sys

FIELDS = ["variant", "trace", "seconds", "rc",
          "TM MPKI", "TM accuracy", "TM right", "TM wrong",
          "GShare MPKI", "GShare accuracy", "TAGE MPKI",
          "instructions", "GShare wrong"]
PLAIN = ("TM MPKI", "TM accuracy", "TM right", "TM wrong",
         "GShare MPKI", "GShare accuracy", "GShare wrong")


def scrape(text):
    out = {}
    for line in text.splitlines():
        for k in PLAIN:
            if line.startswith(k + ":"):
                out[k] = line.split(":", 1)[1].strip()
        if line.startswith("Measured # of instructions:"):
            out["instructions"] = line.split(":", 1)[1].strip()
        f = line.split()
        if len(f) >= 5 and f[0] == "CondDirect":
            out["TAGE MPKI"] = f[4]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", required=True, help="dir holding logs/ and shard-*.csv")
    a = ap.parse_args()
    d = a.results_dir

    extra = {}
    for f in glob.glob(os.path.join(d, "shard-*.csv")):
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                extra[(r.get("variant"), r.get("trace"))] = (r.get("seconds", ""), r.get("rc", ""))

    rows = []
    for gz in sorted(glob.glob(os.path.join(d, "logs", "*.log.gz"))):
        base = os.path.basename(gz)[:-3]                  # cfg__trace.log
        if "__" not in base:
            continue
        cfg, tr = base[:-4].split("__", 1)
        with gzip.open(gz, "rt", errors="replace") as fh:
            text = fh.read()
        rec = {"variant": cfg, "trace": tr}
        rec.update(scrape(text))
        s, rc = extra.get((cfg, tr), ("", ""))
        rec["seconds"], rec["rc"] = s, rc
        rows.append(rec)

    out = os.path.join(d, "ALL.csv")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["variant"], x["trace"])):
            w.writerow(r)

    missing = [r["trace"] for r in rows
               if not r.get("instructions") or not r.get("GShare wrong")]
    print("rebuilt %s: %d rows, %d lacking a new column" % (out, len(rows), len(missing)))
    return 0 if rows and not missing else 1


if __name__ == "__main__":
    sys.exit(main())
