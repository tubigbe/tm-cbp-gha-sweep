#!/usr/bin/env python3
"""Full-set shard runner with an explicit configuration list.

Identical execution model to run_fullset_shard.py (one shard = one workload category,
tarball streamed from Google Drive straight into `tar -xJ`, 4-way parallel trace runs,
per-trace raw stdout kept), but the configuration list and the output directory are
command-line arguments, so a single configuration can be run without editing the file.

Usage:
  python3 scripts/run_fullset_cfg.py --shard 0 --configs isoB_49in_53cl \
      --plan fullsets_isoB.json --parallel 4 --out-dir isoB_results
"""
import argparse, csv, json, os, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

FIELDS = ["variant", "trace", "seconds", "rc",
          "TM MPKI", "TM accuracy", "TM right", "TM wrong",
          "GShare MPKI", "GShare accuracy", "TAGE MPKI",
          # the two columns the old CSVs lacked, needed for the per-trace
          # bit-identity check (instructions must match the ku baseline; any
          # GShare wrong drift means the comparison is polluted)
          "instructions", "GShare wrong"]


def sh(cmd, **kw):
    print("+ " + (cmd if isinstance(cmd, str) else " ".join(cmd)), flush=True)
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=True, **kw)


def find_trace(root, name):
    cands = {f"{name}.gz", f"{name}_trace.gz"}
    for d, _s, files in os.walk(root):
        for c in cands:
            if c in files:
                return os.path.join(d, c)
    return None


def scrape(path):
    out = {}
    with open(path, errors="replace") as fh:
        for line in fh:
            for k in ("TM MPKI", "TM accuracy", "TM right", "TM wrong",
                      "GShare MPKI", "GShare accuracy"):
                if line.startswith(k + ":"):
                    out[k] = line.split(":", 1)[1].strip()
            if line.startswith("GShare wrong:"):
                out["GShare wrong"] = line.split(":", 1)[1].strip()
            # NOTE: this line appears twice (once under TM, once under GShare);
            # both are the same trace instruction count, last one wins.
            if line.startswith("Measured # of instructions:"):
                out["instructions"] = line.split(":", 1)[1].strip()
            f = line.split()
            if len(f) >= 5 and f[0] == "CondDirect":
                out["TAGE MPKI"] = f[4]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--configs", required=True,
                    help="comma-separated directory names under variants/")
    ap.add_argument("--plan", default="fullsets_isoB.json")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--out-dir", default="isoB_results")
    a = ap.parse_args()
    cfgs = [c for c in a.configs.split(",") if c]

    plan = json.load(open(a.plan))
    me = plan.get(str(a.shard))
    if me is None:
        print(f"shard {a.shard}: no plan entry, exiting"); return 0

    cat = me["category"]; traces = me["traces"]
    print(f"===== shard {a.shard}: category {cat}, {len(traces)} traces =====")
    print(f"      configs: {cfgs}")
    print(f"      {', '.join(traces)}")
    sh("df -h . | tail -2")
    sh("nproc; free -g | head -2")

    os.makedirs(a.traces_dir, exist_ok=True)

    # ---- stream the category tarball from Google Drive and extract it in one pipe ----
    url = ("https://drive.usercontent.google.com/download?id=%s&export=download&confirm=t"
           % me["gdrive_id"])
    t0 = time.time()
    cmd = ('set -o pipefail; curl -sSL --retry 3 --retry-delay 5 "%s" | tar -xJ -C %s'
           % (url, a.traces_dir))
    print("+ " + cmd, flush=True)
    subprocess.run(cmd, shell=True, check=True, executable="/bin/bash")
    print(f"drive download+extract: {time.time()-t0:.0f}s")
    sh("df -h . | tail -1")
    found = sum(1 for t in traces if find_trace(a.traces_dir, t))
    print(f"found {found}/{len(traces)} traces after extraction")
    if found != len(traces):
        print("!! missing traces, listing traces dir:")
        subprocess.run(f"find {a.traces_dir} -name '*.gz' | head -50", shell=True)

    os.makedirs(a.logs_dir, exist_ok=True)
    os.makedirs(a.out_dir, exist_ok=True)
    rows = []

    for cfg in cfgs:
        print(f"\n--- config {cfg} ---")
        vdir = os.path.join("variants", cfg)
        if not os.path.isdir(vdir):
            print(f"!! no such variant dir: {vdir}"); return 2
        for fn in sorted(os.listdir(vdir)):
            if fn.endswith((".h", ".cc")):
                shutil.copy(os.path.join(vdir, fn), fn)
        sh("make clean >/dev/null")
        sh("make -j4")
        # echo back the knobs actually compiled, so the CSV is self-describing
        subprocess.run("grep -E '^#define (NUM_INPUTS|NUM_CLAUSES|THRESHOLD|TM_PATH_BRANCHES)' tm.h",
                       shell=True)

        def run(tr):
            p = find_trace(a.traces_dir, tr)
            log = os.path.join(a.logs_dir, f"{cfg}__{tr}.log")
            if p is None:
                return {"variant": cfg, "trace": tr, "seconds": "", "rc": 1}
            t0 = time.time()
            with open(log, "wb") as fh:
                rc = subprocess.call(["./cbp", "-E", "1000000", p], stdout=fh,
                                     stderr=subprocess.STDOUT)
            r = {"variant": cfg, "trace": tr, "seconds": f"{time.time()-t0:.1f}", "rc": rc}
            r.update(scrape(log))
            return r

        t0 = time.time()
        with ThreadPoolExecutor(max_workers=a.parallel) as pool:
            futs = {pool.submit(run, tr): tr for tr in traces}
            for fut in as_completed(futs):
                r = fut.result(); rows.append(r)
                print(f"    {r['trace']:<22} {r.get('seconds',''):>8}s rc={r['rc']} "
                      f"MPKI={r.get('TM MPKI','-')} acc={r.get('TM accuracy','-')}", flush=True)
        print(f"  config {cfg} took {time.time()-t0:.0f}s")

    path = os.path.join(a.out_dir, f"shard-{a.shard:02d}-{cat}.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["variant"], r["trace"])):
            w.writerow(r)
    bad = [r for r in rows if r["rc"] != 0 or not r.get("TM MPKI")]
    print(f"\n--- shard {a.shard} done: {len(rows)-len(bad)}/{len(rows)} ok ---")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
