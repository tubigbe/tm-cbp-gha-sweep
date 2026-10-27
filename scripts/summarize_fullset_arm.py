#!/usr/bin/env python3
"""Summarise one full-set arm and cross-check determinism against the 105-trace A baseline.

The full set only means something if the measurement is clean, so this script refuses to
write a PASS unless every matched trace reproduces, bit for bit, the input-side columns
the baseline run already established:

  * GShare MPKI / GShare wrong / instructions  must equal baseA_results/ALL.csv
  * for arms that do not touch the TM (onebit_* / tm_pc_only) also TM MPKI / TM right
  * optional --ref-results: the per-trace 1bit columns must equal another arm's (the
    1-bit predictor itself is byte-identical across the 2026-10-26 arms)

Outputs, in --results:
  SUMMARY.csv   long form: arm,scope,metric,n,value,base,delta_pct
  SUMMARY.md    the same, human readable, plus the gate verdict
  INVENTORY.txt file counts + VERDICT line

Usage:
  python3 scripts/summarize_fullset_arm.py --arm onebit_pc17 --results fullset_onebit
"""
import argparse
import csv
import json
import os
import sys

TM_UNTOUCHED = {"onebit_pc17", "onebit_pc14", "onebit_gshare17", "tm_pc_only"}
GATE_COLS = ("GShare MPKI", "GShare wrong", "instructions")
FULL_SET_ANCHORS = {"TM": 13.41542, "GShare": 22.0221, "TAGE": 4.6880}


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def load(path):
    with open(path, newline="") as fh:
        return {r["trace"]: r for r in csv.DictReader(fh)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--base", default="baseA_results/ALL.csv")
    ap.add_argument("--plan", default="fullsets_isoB.json")
    ap.add_argument("--expect-traces", type=int, default=105)
    ap.add_argument("--ref-results", default="", help="another arm's results dir")
    ap.add_argument("--ref-arm", default="", help="that arm's name (for the log)")
    a = ap.parse_args()

    base = load(a.base)
    arm_rows = load(os.path.join(a.results, "ALL.csv"))
    plan = json.load(open(a.plan))
    trace2cat = {}
    for _k, sh in plan.items():
        for tr in sh["traces"]:
            trace2cat[tr] = sh["category"]

    traces = sorted(arm_rows)
    missing = [t for t in traces if t not in base]
    short = a.expect_traces - len(traces)

    # ---------------- determinism gate ----------------
    gate_fail = []
    n_checked = 0
    for t in traces:
        if t not in base:
            continue
        n_checked += len(GATE_COLS)
        for col in GATE_COLS:
            if (arm_rows[t].get(col) or "").strip() != (base[t].get(col) or "").strip():
                gate_fail.append((t, col, arm_rows[t].get(col), base[t].get(col)))
    if a.arm in TM_UNTOUCHED:
        for t in traces:
            if t not in base:
                continue
            n_checked += 2
            for col in ("TM MPKI", "TM right"):
                if (arm_rows[t].get(col) or "").strip() != (base[t].get(col) or "").strip():
                    gate_fail.append((t, col, arm_rows[t].get(col), base[t].get(col)))

    ref_fail = []
    n_ref_checked = 0
    if a.ref_results:
        ref = load(os.path.join(a.ref_results, "ALL.csv"))
        for t in traces:
            if t not in ref:
                continue
            n_ref_checked += 3
            for col in ("1bit MPKI", "1bit wrong", "1bit right"):
                if (arm_rows[t].get(col) or "").strip() != (ref[t].get(col) or "").strip():
                    ref_fail.append((t, col, arm_rows[t].get(col), ref[t].get(col)))

    # ---------------- effect metric ----------------
    has_hyb = any((r.get("HYB MPKI") or "").strip() for r in arm_rows.values())
    if has_hyb:
        metric = "HYB MPKI"
    elif a.arm.startswith("onebit"):
        metric = "1bit MPKI"
    else:
        metric = "TM MPKI"

    def base_tm(t):
        return num(base[t].get("TM MPKI")) if t in base else None

    def arm_val(t):
        return num(arm_rows[t].get(metric))

    scopes = ["ALL"] + sorted({trace2cat.get(t, "?") for t in traces})
    rows = []
    n_scope_rows = 0
    for sc in scopes:
        ts = [t for t in traces if sc == "ALL" or trace2cat.get(t) == sc]
        if not ts:
            continue
        n_scope_rows += 1
        b = mean([base_tm(t) for t in ts])
        v = mean([arm_val(t) for t in ts])
        onebit = mean([num(arm_rows[t].get("1bit MPKI")) for t in ts])
        delta = (v / b - 1.0) * 100.0 if (b and v is not None) else None
        rows.append({"arm": a.arm, "scope": sc, "metric": metric, "n": len(ts),
                     "value": v, "base": b, "delta_pct": delta,
                     "onebit": onebit})
    rows.append({"arm": a.arm, "scope": "ALL", "metric": "GShare MPKI", "n": len(traces),
                 "value": mean([num(arm_rows[t].get("GShare MPKI")) for t in traces]),
                 "base": mean([num(base[t].get("GShare MPKI")) for t in traces if t in base]),
                 "delta_pct": None, "onebit": None})
    rows.append({"arm": a.arm, "scope": "ALL", "metric": "TAGE MPKI", "n": len(traces),
                 "value": mean([num(arm_rows[t].get("TAGE MPKI")) for t in traces]),
                 "base": mean([num(base[t].get("TAGE MPKI")) for t in base]),
                 "delta_pct": None, "onebit": None})

    # per-trace wins/losses against the baseline TM
    deltas = []
    for t in traces:
        b, v = base_tm(t), arm_val(t)
        if b and v is not None:
            deltas.append((t, (v / b - 1.0) * 100.0))
    better = [d for d in deltas if d[1] < 0]
    worse = [d for d in deltas if d[1] > 0]
    deltas.sort(key=lambda x: x[1])

    # correction counters (means are over all 105 traces; sums are what "how often" means)
    cnt = {}
    for c in ("override count", "rescue", "hurt"):
        vals = [num(arm_rows[t].get(c)) for t in traces]
        cnt[c] = (sum(v for v in vals if v is not None),
                  mean(vals))

    # A run with zero compared columns has no determinism evidence at all - call it
    # incomplete rather than passing vacuously (this is how a missing/renamed base CSV
    # would otherwise slip through).
    ok = (not gate_fail) and (not ref_fail) and short <= 0 and n_checked > 0
    verdict = "COMPLETE" if ok else "INCOMPLETE"

    # ---------------- write SUMMARY.csv ----------------
    out = os.path.join(a.results, "SUMMARY.csv")
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["arm", "scope", "metric", "n", "value",
                                           "base", "delta_pct", "onebit"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    def fmt(x, d=5):
        return "-" if x is None else f"{x:.{d}f}"

    lines = [f"# full-set arm summary - `{a.arm}`", "",
             f"- traces: **{len(traces)}** (expected {a.expect_traces}; missing {short})",
             f"- effect metric: `{metric}`",
             f"- determinism gate: **{'PASS' if not gate_fail else 'FAIL'}** "
             f"({n_checked} input-side checks vs `baseA_results/ALL.csv`, "
             f"{len(gate_fail)} mismatches)",
             f"- 1-bit identity vs `{a.ref_arm or '-'}`: "
             f"**{'n/a' if not a.ref_results else ('PASS' if not ref_fail else 'FAIL')}**"
             + (f" ({n_ref_checked} checks, {len(ref_fail)} mismatches)" if a.ref_results else ""),
             ""]
    if gate_fail:
        lines.append("```")
        for f in gate_fail[:10]:
            lines.append(f"GATE MISMATCH {f}")
        lines.append("```")
    if ref_fail:
        lines.append("```")
        for f in ref_fail[:10]:
            lines.append(f"REF MISMATCH {f}")
        lines.append("```")

    lines += ["| scope | n | base TM | " + metric + " | delta | 1-bit |", "|---|---:|---:|---:|---:|---:|"]
    for r in rows[:n_scope_rows]:
        lines.append(f"| {r['scope']} | {r['n']} | {fmt(r['base'])} | {fmt(r['value'])} | "
                     f"{'-' if r['delta_pct'] is None else format(r['delta_pct'], '+.2f') + '%'} | "
                     f"{fmt(r['onebit'])} |")
    lines += ["", f"- per-trace better/worse vs TM: **{len(better)} / {len(worse)}** "
                  f"(of {len(deltas)})", ""]
    if deltas:
        lines.append("best traces: " + ", ".join(f"{t} {d:+.1f}%" for t, d in deltas[:5]))
        lines.append("worst traces: " + ", ".join(f"{t} {d:+.1f}%" for t, d in deltas[-5:]))
        lines.append("")
    if has_hyb:
        lines += ["| counter | sum over traces | mean per trace |", "|---|---:|---:|"]
        for c, (s, m) in cnt.items():
            lines.append(f"| {c} | {int(s)} | {fmt(m, 1)} |")
        lines.append("")
    lines.append(f"VERDICT: {verdict}")
    with open(os.path.join(a.results, "SUMMARY.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")

    # ---------------- INVENTORY ----------------
    logs = []
    ld = os.path.join(a.results, "logs")
    if os.path.isdir(ld):
        logs = [f for f in os.listdir(ld) if f.endswith(".log.gz")]
    with open(os.path.join(a.results, "INVENTORY.txt"), "w") as fh:
        fh.write(f"arm: {a.arm}\n")
        fh.write(f"traces: {len(traces)}\n")
        fh.write(f"per-trace logs: {len(logs)}\n")
        fh.write(f"gate checks: {n_checked}\n")
        fh.write(f"gate mismatches: {len(gate_fail)}\n")
        fh.write(f"ref checks: {n_ref_checked}\n")
        fh.write(f"ref mismatches: {len(ref_fail)}\n")
        fh.write(f"VERDICT: {verdict}\n")

    print("\n".join(lines))
    print(f"\nwrote {out}, SUMMARY.md, INVENTORY.txt")
    # NOT an exit code: the collect job commits the data first and only then turns the
    # run red on an INCOMPLETE verdict, so a failed gate never throws the results away.
    return 0


if __name__ == "__main__":
    sys.exit(main())
