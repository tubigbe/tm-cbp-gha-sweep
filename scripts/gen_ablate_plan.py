#!/usr/bin/env python3
"""Generate ablatesets.json - the shard plan for the V13 input-ablation experiment.

18 shards = 6 trace groups x 3 configurations; inside a shard all 4 ablation
modes (NONE + P/L/B) of every trace in the group are run with 4-way parallelism.

Also embeds the *expected* NONE results (measured earlier: baseline from the
2026-09-29 ku full sweep, both FPTM configs from the 2026-10-13 GHA full-set run)
so that every shard self-checks that its NONE rows reproduce them exactly.

Run on ku:  python3 /tmp/gen_ablate_plan.py  ->  /data/tm_gha_sweep/ablatesets.json
"""
import json
import os

OUT = "/data/tm_gha_sweep/ablatesets.json"

DRIVE = {
    "int":      ("1R9eJg5pUaE4FNq1k1Xv3DfnE93CzYROi", "int.tar.xz", 4.73),
    "web":      ("18P3ndXZKSwpxNVjoUB7TWUIq0PJfSljf", "web.tar.xz", 1.89),
    "infra":    ("15lDyv-PH_bfnPXweIHwS97ZATX_T94hj", "infra.tar.xz", 1.49),
    "fp":       ("1TA1n-6U2aoBUoPpCEGyberAKYIYhi3I3", "fp.tar.xz", 1.82),
    "compress": ("1YDfitnG4bRX2nOFh5X4o0QePAF8vZCg_", "compress.tar.xz", 1.37),
    "media":    ("1c0914RMqTpKwtKG2vU3fCgiaNXQ5xx6n", "media.tar.xz", 0.38),
}

CONFIGS = [
    {"id": "00_baseline",       "label": "baseline (S=5, T=6)"},
    {"id": "02_fuzzy_LF4_T18",  "label": "FPTM LF=4 T=18"},
    {"id": "04_fuzzy_LF8_T24",  "label": "FPTM LF=8 T=24"},
]

# trace group -> (domains, traces, single-run seconds, why this shape)
GROUPS = [
    ("intA",     ["int"],              ["int_32_trace"],                              768, "int_32 is the V13 long pole (110M instr); alone in a shard"),
    ("intB",     ["int"],              ["int_34_trace", "int_36_trace", "int_13_trace"], 934, "the three shorter int traces"),
    ("web",      ["web"],              ["web_6_trace", "web_13_trace", "web_18_trace"],  663, "all three web traces"),
    ("infra",    ["infra"],            ["infra_0_trace", "infra_12_trace"],              628, "both infra traces"),
    ("fpmedia",  ["fp", "media"],      ["fp_0_trace", "fp_8_trace", "media_1_trace"],    628, "fp pair + the single media trace (media alone is too small to justify a shard)"),
    ("compress", ["compress"],         ["compress_1_trace"],                             215, "the single compress trace"),
]

# expected NONE values, (mpki, accuracy%) -- the control these shards must reproduce
EXPECT = {
    "00_baseline": {
        "int_32_trace": [17.6676, 84.6199], "int_34_trace": [8.03206, 94.9644],
        "int_36_trace": [18.6284, 87.086],  "int_13_trace": [3.11935, 97.06],
        "web_6_trace": [18.6708, 87.5583],  "web_13_trace": [14.9833, 87.5491],
        "web_18_trace": [11.2554, 90.8925], "infra_0_trace": [8.14942, 93.659],
        "infra_12_trace": [21.5098, 86.3206], "fp_0_trace": [3.73496, 93.0827],
        "fp_8_trace": [12.3475, 78.7306],   "compress_1_trace": [3.50769, 96.7429],
        "media_1_trace": [7.37598, 85.9794],
    },
    "02_fuzzy_LF4_T18": {
        "int_32_trace": [17.612, 84.6683],  "int_34_trace": [9.10074, 94.2944],
        "int_36_trace": [17.5305, 87.8471], "int_13_trace": [3.67157, 96.5395],
        "web_6_trace": [18.054, 87.9693],   "web_13_trace": [13.7794, 88.5495],
        "web_18_trace": [10.351, 91.6243],  "infra_0_trace": [9.4726, 92.6294],
        "infra_12_trace": [19.4835, 87.6092], "fp_0_trace": [3.53699, 93.4494],
        "fp_8_trace": [12.0917, 79.1712],   "compress_1_trace": [3.39547, 96.8471],
        "media_1_trace": [7.45003, 85.8387],
    },
    "04_fuzzy_LF8_T24": {
        "int_32_trace": [17.6358, 84.6476], "int_34_trace": [8.77929, 94.496],
        "int_36_trace": [17.2993, 88.0074], "int_13_trace": [3.7488, 96.4667],
        "web_6_trace": [17.9747, 88.0222],  "web_13_trace": [13.7484, 88.5753],
        "web_18_trace": [10.3059, 91.6609], "infra_0_trace": [9.48557, 92.6193],
        "infra_12_trace": [19.501, 87.5981], "fp_0_trace": [3.88616, 92.8027],
        "fp_8_trace": [12.1075, 79.144],    "compress_1_trace": [3.39433, 96.8481],
        "media_1_trace": [7.56843, 85.6136],
    },
}

MODES = ["NONE", "P", "L", "B"]

shards = {}
idx = 0
order = []
for gname, domains, traces, est, why in GROUPS:
    for cfg in CONFIGS:
        cats = {}
        for d in domains:
            gid, tb, gb = DRIVE[d]
            cats[d] = {"gdrive_id": gid, "tarball": tb, "size_gb": gb}
        shards[str(idx)] = {
            "group": gname,
            "why": why,
            "domains": domains,
            "categories": cats,
            "cfg": cfg["id"],
            "cfg_label": cfg["label"],
            "traces": traces,
            # one trace x one mode = one cbp run; 4 run at a time
            "est_shard_sec": round(est * len(MODES) / 3.5),
            "expect": {t: EXPECT[cfg["id"]][t] for t in traces},
        }
        order.append((idx, gname, cfg["id"], len(traces) * len(MODES), shards[str(idx)]["est_shard_sec"]))
        idx += 1

plan = {
    "experiment": "V13 input-group ablation x 3 configurations",
    "generated_by": "gen_ablate_plan.py",
    "trace_set": "runlist_validate.txt (V13, 13 traces)",
    "configs": CONFIGS,
    "modes": {
        "NONE": "no ablation (control; must reproduce the published per-trace values)",
        "P": "zero current-branch PC  bits [0,20]",
        "L": "zero local history     bits [45,48]",
        "B": "zero preceding-branch path history bits [49,80]",
    },
    "hook": "TM_ABLATE env var in tm_predictor.cc::assemble_input (see tm_bp_diagnosis.md 2.2)",
    "shards": shards,
}

with open(OUT, "w") as fh:
    json.dump(plan, fh, indent=1, sort_keys=False)
    fh.write("\n")

print("wrote %s (%d shards, %.1f KB)" % (OUT, len(shards), os.path.getsize(OUT) / 1024.0))
print("%-4s %-9s %-18s %5s %8s" % ("shd", "group", "cfg", "runs", "est_s"))
for i, g, c, runs, est in order:
    print("%-4d %-9s %-18s %5d %8d" % (i, g, c, runs, est))
print("total runs = %d, sum(est) = %d s, longest shard = %d s (%.1f min)" % (
    sum(r for _, _, _, r, _ in order), sum(e for *_, e in order), max(e for *_, e in order),
    max(e for *_, e in order) / 60.0))
