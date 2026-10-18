#!/usr/bin/env python3
"""Post-run verification for the GHA-first pipeline.

Four separate questions, never conflated:

  Q0 self-consistency:  each GHA CSV column must equal the value scraped from the
     SAME run's committed raw stdout (gz) - catches a broken scrape/collect.
  Q1 ku<->GHA same variant:  new GHA A-baseline run vs the ku baseline raw stdout
     (105 traces; TM MPKI / right / GShare MPKI / GShare wrong / instructions).
  Q2 GHA<->GHA same variant:  iso-area B re-run (10-18) vs the 10-16 isoB run
     (TM MPKI / TM right / GShare MPKI / TAGE MPKI).
  Q3 pollution gate:  instructions and GShare wrong must be identical per trace
     between the A and B runs (same traces, input-side predictor untouched).

Run from /data/tm_gha_sweep after `git pull`.
"""
import argparse
import csv
import glob
import os
import sys

CSV_FIELDS = ("TM MPKI", "TM accuracy", "TM right", "TM wrong",
              "GShare MPKI", "GShare accuracy")
LOG_FIELDS = CSV_FIELDS + ("instructions", "GShare wrong")
Q1_FIELDS = ("TM MPKI", "TM right", "GShare MPKI", "GShare wrong", "instructions")
Q2_FIELDS = ("TM MPKI", "TM right", "GShare MPKI", "TAGE MPKI")
Q3_FIELDS = ("instructions", "GShare wrong")


def read_csv(path):
    """Read an ALL.csv that is a concatenation of shard CSVs (repeated headers)."""
    out = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            tr = (r.get("trace") or "").strip()
            if not tr or tr == "trace":
                continue
            out[tr] = r
    return out


def scrape_lines(fh):
    out = {}
    for line in fh:
        for k in LOG_FIELDS:
            if k == "instructions":
                continue
            if line.startswith(k + ":"):
                out[k] = line.split(":", 1)[1].strip()
        if line.startswith("Measured # of instructions:"):
            out["instructions"] = line.split(":", 1)[1].strip()
        f = line.split()
        if len(f) >= 5 and f[0] == "CondDirect":
            out["TAGE MPKI"] = f[4]
    return out


def scrape_log(path):
    with open(path, errors="replace") as fh:
        return scrape_lines(fh)


def read_logs(globpat):
    out = {}
    for gz in sorted(glob.glob(globpat)):
        base = os.path.basename(gz)[:-3]          # strip .gz -> cfg__trace.log
        tr = base[:-4].split("__", 1)[1] if "__" in base else base[:-4]
        out[tr] = _scrape_gz(gz)
    return out


def _scrape_gz(path):
    import gzip
    with gzip.open(path, "rt", errors="replace") as fh:
        return scrape_lines(fh)


def cmp(name, left, right, fields, ok, bad):
    only_l = sorted(set(left) - set(right))
    only_r = sorted(set(right) - set(left))
    if only_l or only_r:
        print("  !! %s: trace sets differ  left-only=%s right-only=%s"
              % (name, only_l[:5], only_r[:5]))
        bad.append((name, "setdiff", only_l[:5], only_r[:5]))
    shared = sorted(set(left) & set(right))
    n = 0
    for tr in shared:
        diffs = [(f, left[tr].get(f, ""), right[tr].get(f, ""))
                 for f in fields
                 if left[tr].get(f, "") != right[tr].get(f, "")]
        if diffs:
            n += 1
            bad.append((name, tr, diffs))
            if n <= 10:
                print("  !! %-6s %-18s %s" % (name, tr, diffs))
        else:
            ok[0] += len(fields)
    print("  %-6s: %d trace(s) x %d field(s) compared, %d trace(s) mismatched"
          % (name, len(shared), len(fields), n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseA", default="baseA_results/ALL.csv")
    ap.add_argument("--isoB", default="isoB_results/ALL.csv")
    ap.add_argument("--oldB", default="/tmp/pipeline_verify/isoB_ALL_20261016.csv")
    ap.add_argument("--refdir", default="/data/cbp_trace_staging/trace_logs")
    ap.add_argument("--basecsv", default="/data/tm_cbp_sim/.dsh/logs/baseline/"
                                        "standalone_tm_6e6d30a_ku_20260929.csv")
    a = ap.parse_args()

    baseA = read_csv(a.baseA)
    isoB = read_csv(a.isoB)
    oldB = read_csv(a.oldB)
    ref = {}
    for p in sorted(glob.glob(os.path.join(a.refdir, "*.log"))):
        ref[os.path.basename(p)[:-4]] = scrape_log(p)
    newA_logs = read_logs("baseA_results/logs/*.log.gz")
    newB_logs = read_logs("isoB_results/logs/*.log.gz")

    print("rows: A=%d  B=%d  oldB=%d  ku-raw=%d  A-logs=%d  B-logs=%d"
          % (len(baseA), len(isoB), len(oldB), len(ref), len(newA_logs), len(newB_logs)))

    ok = [0]
    bad = []

    print("\n== Q0: CSV vs its own committed raw stdout ==")
    cmp("Q0-A", baseA, newA_logs, LOG_FIELDS, ok, bad)
    cmp("Q0-B", isoB, newB_logs, LOG_FIELDS, ok, bad)

    print("\n== Q1: GHA A-baseline vs ku baseline raw stdout (same variant) ==")
    cmp("Q1", baseA, ref, Q1_FIELDS, ok, bad)

    print("\n== Q2: GHA B re-run (10-18) vs GHA B first run (10-16) ==")
    cmp("Q2", isoB, oldB, Q2_FIELDS, ok, bad)

    print("\n== Q3: A vs B per-trace input-side columns (pollution gate) ==")
    cmp("Q3", baseA, isoB, Q3_FIELDS, ok, bad)

    print("\n== aggregates ==")
    try:
        with open(a.basecsv, newline="") as fh:
            rows = list(csv.DictReader(fh))
        tmcol = [k for k in rows[0] if "TM MPKI" in k][0]
        m = sum(float(r[tmcol]) for r in rows) / len(rows)
        print("  ku baseline CSV (AGENTS 10.1): %d traces, mean TM MPKI %.6f (doc says 13.4154)"
              % (len(rows), m))
        for tag, d, col in (("ku raw logs", ref, "TM MPKI"),
                            ("GHA A ctl   ", baseA, "TM MPKI"),
                            ("GHA B rerun ", isoB, "TM MPKI")):
            v = [float(d[t][col]) for t in d]
            print("  %s: %d traces, mean TM MPKI %.6f" % (tag, len(v), sum(v) / len(v)))
    except Exception as e:
        print("  skipped:", e)

    print("\n==== VERDICT ====")
    if bad:
        print("MISMATCH in %d group(s) - STOP, report to TM PM / Chief, do not analyse further"
              % len(bad))
        return 1
    print("ALL CHECKS BIT-IDENTICAL (%d field comparisons, 0 mismatch)" % ok[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
