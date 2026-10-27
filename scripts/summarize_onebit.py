#!/usr/bin/env python3
"""Summarize the 2026-10-26 T6 1-bit / hybrid run.

Input : onebit_results/ALL.csv (11 arms x 6 T6 traces)
Output: SUMMARY.csv + a Markdown table on stdout

Invariants (the numbers mean nothing if these break):
  * per trace, GShare MPKI and instructions are identical across all arms
    (arms only touch the TM / 1-bit path, never the input-side predictors);
  * arms whose TM must stay untouched (mode 0/3, excluding tm_pc_only)
    reproduce the published per-trace T6 TM MPKI bit-for-bit (string equality).
"""
import argparse
import csv
import json
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="onebit_results/ALL.csv")
    ap.add_argument("--plan", default="t6_onebit.json")
    ap.add_argument("--out", default="onebit_results/SUMMARY.csv")
    a = ap.parse_args()

    rows = []
    with open(a.results, newline="") as fh:
        for r in csv.DictReader(fh):
            if not r.get("trace") or r["trace"] in ("trace", "variant"):
                continue
            rows.append(r)
    if not rows:
        print("::error::no rows in", a.results)
        return 1
    plan = json.load(open(a.plan))
    anchors = {s["trace"]: s["expect_baseline"] for s in plan["shards"].values()}
    untouched = {v["name"] for v in plan["variants"]
                 if v.get("mode") in (0, 3) and v["name"] != "tm_pc_only"}

    traces = sorted({r["trace"] for r in rows})
    arms = sorted({r["variant"] for r in rows})
    by = {(r["variant"], r["trace"]): r for r in rows}

    problems = []
    for t in traces:
        gs = {by[(v, t)]["GShare MPKI"] for v in arms if (v, t) in by}
        ins = {by[(v, t)]["instructions"] for v in arms if (v, t) in by}
        if len(gs) != 1:
            problems.append("%s: GShare MPKI varies across arms: %s" % (t, sorted(gs)))
        if len(ins) != 1:
            problems.append("%s: instructions vary across arms: %s" % (t, sorted(ins)))
    for v in arms:
        if v in untouched:
            for t in traces:
                got = by.get((v, t), {}).get("TM MPKI")
                want = anchors.get(t)
                if want is not None and got != str(want):
                    problems.append("%s/%s: TM MPKI %r != published %r" % (v, t, got, want))

    def num(r, k):
        try:
            return float(r.get(k))
        except (TypeError, ValueError):
            return None

    out = []
    for v in arms:
        rs = [by[(v, t)] for t in traces if (v, t) in by]

        def mean(k):
            vals = [num(r, k) for r in rs]
            vals = [x for x in vals if x is not None]
            return sum(vals) / len(vals) if vals else None

        out.append({
            "variant": v,
            "mode": rs[0].get("mode", ""),
            "traces": len(rs),
            "TM_MPKI_mean": "%.5f" % mean("TM MPKI") if mean("TM MPKI") is not None else "",
            "onebit_MPKI_mean": "%.5f" % mean("1bit MPKI") if mean("1bit MPKI") is not None else "",
            "HYB_MPKI_mean": "%.5f" % mean("HYB MPKI") if mean("HYB MPKI") is not None else "",
            "override_mean": "%.1f" % mean("override count") if mean("override count") is not None else "",
            "rescue_mean": "%.1f" % mean("rescue") if mean("rescue") is not None else "",
            "hurt_mean": "%.1f" % mean("hurt") if mean("hurt") is not None else "",
            "net_rescue_minus_hurt": "%.1f" % (mean("rescue") - mean("hurt"))
                if mean("rescue") is not None and mean("hurt") is not None else "",
            "GShare_MPKI_mean": "%.5f" % mean("GShare MPKI") if mean("GShare MPKI") is not None else "",
            "TAGE_MPKI_mean": "%.5f" % mean("TAGE MPKI") if mean("TAGE MPKI") is not None else "",
        })
    for r in out:
        r["_key"] = float(r["HYB_MPKI_mean"] or r["onebit_MPKI_mean"] or 1e9)
    out.sort(key=lambda r: r["_key"])
    fields = [k for k in out[0] if not k.startswith("_")]
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in out:
            w.writerow(r)
    print("wrote %s" % a.out)

    print("\n| arm | mode | T6 TM MPKI | 1-bit MPKI | hybrid MPKI | override | rescue | hurt | net | GShare | TAGE |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in out:
        print("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["variant"], r["mode"], r["TM_MPKI_mean"], r["onebit_MPKI_mean"],
            r["HYB_MPKI_mean"] or "-", r["override_mean"] or "-",
            r["rescue_mean"] or "-", r["hurt_mean"] or "-",
            r["net_rescue_minus_hurt"] or "-",
            r["GShare_MPKI_mean"], r["TAGE_MPKI_mean"]))
    print("\npublished T6 anchors (TM baseline): %s" % anchors)
    if problems:
        for p in problems:
            print("::error::" + p)
        return 1
    print("INVARIANTS OK: input-side columns identical across arms; untouched-TM arms bit-identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
