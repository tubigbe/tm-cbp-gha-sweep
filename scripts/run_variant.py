#!/usr/bin/env python3
"""Run ONE variant (one configuration) across all 6 T6 traces, inside a GHA runner.

Each shard = one configuration.  The shard:
  1. copies variants/<name>/*.{h,cc} over the pristine tree,
  2. builds,
  3. runs the 6 T6 traces with `--parallel` concurrency,
  4. writes results/shard-<N>-<name>.csv.

Raw stdout per trace is kept under logs/ (project protocol).
"""
import argparse, csv, json, os, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

T6 = ["int_1", "fp_4", "web_11", "media_3", "compress_4", "infra_14"]
FIELDS = ["variant", "trace", "seconds", "rc",
          "TM MPKI", "TM accuracy", "TM right", "TM wrong",
          "GShare MPKI", "GShare accuracy", "TAGE MPKI"]


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
            f = line.split()
            if len(f) >= 5 and f[0] == "CondDirect":
                out["TAGE MPKI"] = f[4]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--out-dir", default="results")
    a = ap.parse_args()

    idx = json.load(open("variants/index.json"))
    name = idx.get(str(a.shard))
    if name is None:
        print(f"shard {a.shard}: no variant assigned - nothing to do")
        return 0

    print(f"===== shard {a.shard} = variant {name} =====")
    vdir = os.path.join("variants", name)
    applied = []
    for fn in sorted(os.listdir(vdir)):
        if fn.endswith((".h", ".cc")):
            shutil.copy(os.path.join(vdir, fn), fn)
            applied.append(fn)
    print("applied overrides:", applied if applied else "(none - baseline)")

    print("--- build ---")
    subprocess.check_call(["make", "clean"])
    subprocess.check_call(["make", "-j4"])

    os.makedirs(a.logs_dir, exist_ok=True)
    os.makedirs(a.out_dir, exist_ok=True)

    def run(tr):
        p = find_trace(a.traces_dir, tr)
        log = os.path.join(a.logs_dir, f"{name}__{tr}.log")
        if p is None:
            return {"variant": name, "trace": tr, "seconds": "", "rc": 1}
        t0 = time.time()
        with open(log, "wb") as fh:
            rc = subprocess.call(["./cbp", "-E", "1000000", p], stdout=fh,
                                 stderr=subprocess.STDOUT)
        row = {"variant": name, "trace": tr, "seconds": f"{time.time()-t0:.1f}", "rc": rc}
        row.update(scrape(log))
        return row

    rows, t0 = [], time.time()
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        futs = {pool.submit(run, tr): tr for tr in T6}
        for fut in as_completed(futs):
            r = fut.result()
            rows.append(r)
            print(f"  {r['trace']:<12} {r.get('seconds',''):>8}s rc={r['rc']} "
                  f"TM MPKI={r.get('TM MPKI','-')} acc={r.get('TM accuracy','-')}")
    wall = time.time() - t0

    rows.sort(key=lambda r: T6.index(r["trace"]))
    path = os.path.join(a.out_dir, f"shard-{a.shard:02d}-{name}.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

    ok = [r for r in rows if r["rc"] == 0 and r.get("TM MPKI")]
    print(f"--- shard {a.shard} ({name}) done: {len(ok)}/{len(T6)} ok, wall {wall:.0f}s ---")
    if len(ok) != len(T6):
        print("!! some traces failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
