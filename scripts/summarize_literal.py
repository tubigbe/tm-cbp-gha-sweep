#!/usr/bin/env python3
"""Add a second churn metric to the literal summary.

  slot_churn_pct        : fraction of (clause, phase) slots whose included-literal
                          SET changed between two consecutive snapshots (strict)
  length_churn_pct      : fraction whose NUMBER of included literals changed
                          (this is the metric behind the 10-20 "21.8/32 clauses"
                          statement, so the two batches become directly comparable)

Run against the committed stats dir; regenerates SUMMARY.csv/.md.
"""
import csv
import glob
import gzip
import os
import sys

FIELDS_ORDER = ["variant", "trace", "group", "n_inputs",
                "duty_pre_pct_mean", "duty_post_pct_mean", "ever_included_pct",
                "mean_literals_per_clause", "empty_clause_pct",
                "slot_churn_pct", "length_churn_pct"]


def open_any(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", errors="replace")
    return open(path, errors="replace")


def snapshot_metrics(path):
    series = {}
    with open_any(path) as fh:
        for r in csv.DictReader(fh):
            series.setdefault((r["clause"], r["phase"]), []).append(
                (int(r["snapshot_id"]),
                 frozenset(r["names"].split(";")) if r["names"] else frozenset(),
                 int(r["n_literals"])))
    comps = sets = lens = 0
    lit_sum = rows = empty = 0
    for items in series.values():
        items.sort()
        for (_, sa, na), (_, sb, nb) in zip(items, items[1:]):
            comps += 1
            if sa != sb:
                sets += 1
            if na != nb:
                lens += 1
    with open_any(path) as fh:
        for r in csv.DictReader(fh):
            rows += 1
            n = int(r["n_literals"])
            lit_sum += n
            if n == 0:
                empty += 1
    return {
        "slot_churn_pct": (100.0 * sets / comps) if comps else 0.0,
        "length_churn_pct": (100.0 * lens / comps) if comps else 0.0,
        "mean_literals_per_clause": (lit_sum / rows) if rows else 0.0,
        "empty_clause_pct": (100.0 * empty / rows) if rows else 0.0,
    }


def main():
    stats_dir = sys.argv[1] if len(sys.argv) > 1 else "literal_switch_results/literal_stats"
    out = sys.argv[2] if len(sys.argv) > 2 else "literal_switch_results/SUMMARY.csv"
    duty_files = sorted(glob.glob(os.path.join(stats_dir, "*_literal_duty.csv*")))
    if not duty_files:
        print("::error::no duty CSVs under", stats_dir)
        return 1

    rows_out = []
    for duty_path in duty_files:
        key = os.path.basename(duty_path).split("_literal_duty")[0]
        variant, trace = key.split("__", 1)
        snap = snapshot_metrics(duty_path.replace("_literal_duty.csv", "_clause_snapshots.csv"))
        duty = list(csv.DictReader(open_any(duty_path)))
        groups = {}
        for r in duty:
            name = r["name"]
            g = ("pc" if name.startswith("pc") else
                 "global_history" if name.startswith("gh") else
                 "local_history" if name.startswith("lh") else
                 "path" if name.startswith("b") else "other")
            groups.setdefault(g, []).append(r)
        groups["ALL"] = duty
        for g, rs in groups.items():
            n = len(rs)
            rows_out.append({
                "variant": variant, "trace": trace, "group": g, "n_inputs": n,
                "duty_pre_pct_mean": "%.4f" % (sum(float(r["duty_pre_pct"]) for r in rs) / n),
                "duty_post_pct_mean": "%.4f" % (sum(float(r["duty_post_pct"]) for r in rs) / n),
                "ever_included_pct": "%.2f" % (100.0 * sum(1 for r in rs if r["ever_included"] == "1") / n),
                "mean_literals_per_clause": "%.4f" % snap["mean_literals_per_clause"],
                "empty_clause_pct": "%.4f" % snap["empty_clause_pct"],
                "slot_churn_pct": "%.4f" % snap["slot_churn_pct"],
                "length_churn_pct": "%.4f" % snap["length_churn_pct"],
            })

    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS_ORDER)
        w.writeheader()
        for r in rows_out:
            w.writerow(r)
    print("wrote %s (%d rows)" % (out, len(rows_out)))

    md = out.replace(".csv", ".md")
    with open(md, "w") as fh:
        fh.write("wrote %s (%d rows)\n\n" % (out, len(rows_out)))
        fh.write("| variant | trace | group | n | duty_pre% | duty_post% | ever% | lit/clause | empty% | slot_churn% | length_churn% |\n")
        fh.write("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for r in rows_out:
            fh.write("| {variant} | {trace} | {group} | {n_inputs} | {duty_pre_pct_mean} | "
                     "{duty_post_pct_mean} | {ever_included_pct} | {mean_literals_per_clause} | "
                     "{empty_clause_pct} | {slot_churn_pct} | {length_churn_pct} |\n".format(**r))
    print("wrote", md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
