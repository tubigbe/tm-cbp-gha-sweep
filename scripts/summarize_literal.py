#!/usr/bin/env python3
"""Summarize the literal-dynamics statistics into one table (task 3 deliverable).

Inputs: the per-trace `<variant>__<trace>_literal_duty.csv(.gz)` and
`<variant>__<trace>_clause_snapshots.csv(.gz)` produced by the TM_LITERAL_STATS
build, from the 2026-10-26 switch variants.

Outputs: <out>.csv with one row per (variant, trace, input-group) plus one
"ALL" group row, and a Markdown table on stdout.

Input groups are inferred from the literal names in tm.cc's TM_INPUT_NAMES:
  pc2..pcN   -> PC bits
  gh0..ghN   -> global history bits
  lh/bN_pcN  -> local history / preceding-branch path bits
"""
import argparse
import csv
import glob
import gzip
import os
import re
import sys

GROUP_RE = [
    (re.compile(r"^pc\d+$"), "pc"),
    (re.compile(r"^gh\d+$"), "global_history"),
    (re.compile(r"^lh\d+$"), "local_history"),
    (re.compile(r"^b\d+_pc\d+$"), "path"),
    (re.compile(r"^b\d+_dir$"), "path"),
]


def group_of(name):
    for rx, g in GROUP_RE:
        if rx.match(name):
            return g
    return "other"


def open_any(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", errors="replace")
    return open(path, errors="replace")


def load_duty(path):
    rows = []
    with open_any(path) as fh:
        for r in csv.DictReader(fh):
            r["group"] = group_of(r["name"])
            rows.append(r)
    return rows


def load_snapshot_stats(path):
    """Clause occupancy + churn from the per-100k-update snapshots."""
    n_rows = 0
    empty = 0
    lit_sum = 0
    prev = {}
    changes = 0
    comps = 0
    with open_any(path) as fh:
        for r in csv.DictReader(fh):
            n_rows += 1
            n = int(r["n_literals"])
            lit_sum += n
            if n == 0:
                empty += 1
            key = (r["snapshot_id"], r["phase"], r["clause"])
            names = frozenset(r["names"].split(";")) if r["names"] else frozenset()
            if key in prev:
                comps += 1
                if prev[key] != names:
                    changes += 1
            prev[key] = names
    return {
        "snapshot_rows": n_rows,
        "mean_literals_per_clause": (lit_sum / n_rows) if n_rows else 0.0,
        "empty_clause_pct": (100.0 * empty / n_rows) if n_rows else 0.0,
        "slot_churn_pct": (100.0 * changes / comps) if comps else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats-dir", default="literal_switch_results/literal_stats")
    ap.add_argument("--out", default="literal_switch_results/SUMMARY.csv")
    a = ap.parse_args()

    duty_files = sorted(glob.glob(os.path.join(a.stats_dir, "*_literal_duty.csv*")))
    if not duty_files:
        print("::error::no duty CSVs under", a.stats_dir)
        return 1

    out_rows = []
    for duty_path in duty_files:
        key = os.path.basename(duty_path).split("_literal_duty")[0]
        variant, trace = key.split("__", 1)
        duty = load_duty(duty_path)
        snap_path = duty_path.replace("_literal_duty.csv", "_clause_snapshots.csv")
        snap = load_snapshot_stats(snap_path) if os.path.exists(snap_path) else {}

        by_group = {}
        for r in duty:
            by_group.setdefault(r["group"], []).append(r)
        for group, rows in sorted(by_group.items()) + ([("ALL", duty)] if len(by_group) > 1 else []):
            n = len(rows)
            pre = sum(float(r["duty_pre_pct"]) for r in rows) / n
            post = sum(float(r["duty_post_pct"]) for r in rows) / n
            ever = 100.0 * sum(1 for r in rows if r["ever_included"] == "1") / n
            out_rows.append({
                "variant": variant, "trace": trace, "group": group, "n_inputs": n,
                "duty_pre_pct_mean": "%.4f" % pre,
                "duty_post_pct_mean": "%.4f" % post,
                "ever_included_pct": "%.2f" % ever,
                "mean_literals_per_clause": "%.4f" % snap.get("mean_literals_per_clause", 0.0),
                "empty_clause_pct": "%.4f" % snap.get("empty_clause_pct", 0.0),
                "slot_churn_pct": "%.4f" % snap.get("slot_churn_pct", 0.0),
            })

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    fields = list(out_rows[0])
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print("wrote %s (%d rows)" % (a.out, len(out_rows)))

    # compact markdown table: variant x group
    print("\n| variant | trace | group | n | duty_pre% | duty_post% | ever% | lit/clause | empty_clause% | churn% |")
    print("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in out_rows:
        print("| {variant} | {trace} | {group} | {n_inputs} | {duty_pre_pct_mean} | {duty_post_pct_mean} | "
              "{ever_included_pct} | {mean_literals_per_clause} | {empty_clause_pct} | {slot_churn_pct} |".format(**r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
