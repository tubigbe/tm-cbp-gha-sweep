#!/usr/bin/env python3
"""Summarize the 2026-10-26 T6 1-bit / hybrid run.

Input : onebit_results/ALL.csv (11 arms x 6 T6 traces, from run_onebit_t6.py)
Output: onebit_results/SUMMARY.csv + a Markdown table on stdout

Also enforces the two invariants that must hold for the numbers to mean anything:
  * per trace, `GShare MPKI` and `instructions` are identical across all arms
    (the arms only touch the TM / 1-bit predictor, never the input-side ones);
  * every arm with `expect_tm` set reproduces the published T6 TM MPKI for its
    trace bit-for-bit (string equality) - that is the "original TM untouched"
    proof for the arms that must not move it.
"""
import argparse
import csv
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="onebit_results/ALL.csv")
    ap.add_argument("--plan", default="t6_onebit.json")
    ap.add_argument("--out", default="onebit_results/SUMMARY.csv")
    a = ap.parse_args()

    rows = [r for r in csv.DictReader(open(a.results)) if r.get("trace") not in (None, "", "trace")]
    if not rows:
        print("::error::no rows in", a.results)
        return 1
    plan = json.load(open(a.plan))
    expect_tm = {v["name"]: v.get("expect_tm") for v in plan["variants"]}
    anchors = {s["trace"]: s["expect_baseline"] for s in plan["shards"].values()}

    traces = sorted({r["trace"] for r in rows})
    arms = sorted({r["variant"] for r in rows})
    by = {(r["variant"], r["trace"]): r for r in rows}

    problems = []
    # invariant 1: input-side columns constant across arms
    for t in traces:
        gs = {by[(v, t)]["GShare MPKI"] for v in arms if (v, t) in by}
        ins = {by[(v, t)]["instructions"] for v in arms if (v, t) in by}
        if len(gs) != 1:
            problems.append("%s: GShare MPKI varies across arms: %s" % (t, sorted(gs)))
        if len(ins) != 1:
            problems.append("%s: instructions vary across arms: %s" % (t, sorted(ins)))
    # invariant 2: untouched-TM anchors
    for v in arms:
        exp = expect_tm.get(v)
        if exp:
            for t in traces:
                got = by.get((v, t), {}).get("TM MPKI")
                want = anchors.get(t)
                if got != want:
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
            "GShare_MPKI_mean": "%.5f" % mean("GShare MPKI") if mean("GShare MPKI") is not None else "",
            "TAGE_MPKI_mean": "%.5f" % mean("TAGE MPKI") if mean("TAGE MPKI") is not None else "",
        })
    # sort by the most relevant metric: HYB if present, else 1bit
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

    print("\n| arm | mode | T6 TM MPKI | 1-bit MPKI | hybrid MPKI | GShare | TAGE |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for r in out:
        print("| %s | %s | %s | %s | %s | %s | %s |" % (
            r["variant"], r["mode"], r["TM_MPKI_mean"], r["onebit_MPKI_mean"],
            r["HYB_MPKI_mean"] or "-", r["GShare_MPKI_mean"], r["TAGE_MPKI_mean"]))
    print("\npublished T6 anchors (TM baseline): %s" % anchors)
    if problems:
        for p in problems:
            print("::error::" + p)
        return 1
    print("INVARIANTS OK: input-side columns identical across arms; untouched-TM arms bit-identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
