#!/usr/bin/env python3
"""One shard of the direction-B 2D sweep: (S, S_RELAX) grid on a single trace.

What is decoupled
  branch (1) recruitment : clause fires, literal true   -> +1 with p_inc   = (S-1)/S
  branch (2) push-out    : clause fires, literal false  -> -1 with p_dec   = 1/S
  branch (3) relax       : clause did NOT fire          -> -1 with p_relax = 1/S_RELAX
Before this experiment branch (3) also used p_dec, so one S set both the
specificity set point q* = p_dec/(p_inc+p_dec) and the forgetting inertia.
S_RELAX == S reproduces the original TM bit-for-bit (the (5,5) anchor).

Builds run sequentially in one tree (no two workers ever touch tm.h at the same
time); only the cbp runs are parallel.
"""
import argparse, csv, json, os, re, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

FIELDS = ["shard", "S", "S_RELAX", "seconds", "rc", "TM MPKI", "TM accuracy",
          "TM right", "TM wrong", "GShare MPKI", "TAGE MPKI"]


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
            f = line.split()
            if len(f) >= 5 and f[0] == "CondDirect":
                out["TAGE MPKI"] = f[4]
    return out


def set_macros(s, r):
    txt = open("tm.h").read()
    txt, n1 = re.subn(r"(?m)^#define S[ \t]+\d+", "#define S %d" % s, txt, count=1)
    txt, n2 = re.subn(r"(?m)^#define S_RELAX[ \t]+\d+", "#define S_RELAX %d" % r, txt, count=1)
    if n1 != 1 or n2 != 1:
        raise RuntimeError("macro substitution failed (%d, %d)" % (n1, n2))
    open("tm.h", "w").write(txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--parallel", type=int, default=5)
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--out-dir", default="twodim_results")
    ap.add_argument("--plan", default="twodimsets.json")
    a = ap.parse_args()

    plan = json.load(open(a.plan))
    me = plan["shards"].get(str(a.shard))
    if me is None:
        print("shard %d: no plan entry - nothing to do" % a.shard)
        return 0
    configs = [tuple(c) for c in me["configs"]]
    trace = plan["trace"]
    cat = plan["category"]
    vdir = os.path.join("variants", plan["variant"])

    print("===== shard %d: %d configs x %s =====" % (a.shard, len(configs), trace))
    print("      configs: %s" % (configs,))
    print("      estimated shard time: %ss" % me["est_shard_sec"])
    sh("nproc; free -g | head -2; df -h . | tail -2")

    # ---- 1) stream the category tarball straight from Google Drive -----------
    os.makedirs(a.traces_dir, exist_ok=True)
    url = ("https://drive.usercontent.google.com/download?id=%s&export=download&confirm=t"
           % cat["gdrive_id"])
    t0 = time.time()
    cmd = ('set -o pipefail; curl -sSL --retry 3 --retry-delay 5 "%s" | tar -xJ -C %s'
           % (url, a.traces_dir))
    print("+ drive %s %s (%s GB)" % (cat["dom"], cat["tarball"], cat["size_gb"]), flush=True)
    subprocess.run(cmd, shell=True, check=True, executable="/bin/bash")
    print("  download+extract %.0fs" % (time.time() - t0))
    tp = find_trace(a.traces_dir, trace)
    if tp is None:
        print("::error::trace %s missing after extraction" % trace)
        return 1
    tp = os.path.abspath(tp)
    sh("df -h . | tail -1")

    # ---- 2) build one binary per config, sequentially -----------------------
    os.makedirs("bins", exist_ok=True)
    os.makedirs(a.logs_dir, exist_ok=True)
    os.makedirs(a.out_dir, exist_ok=True)
    subprocess.run("make clean >/dev/null", shell=True, check=True)

    built = []
    for (s, r) in configs:
        t0 = time.time()
        subprocess.check_call(["git", "checkout", "--", "tm.cc", "tm.h", "tm_predictor.cc"])
        applied = []
        for fn in sorted(os.listdir(vdir)):
            if fn.endswith((".h", ".cc")):
                shutil.copy(os.path.join(vdir, fn), fn)
                applied.append(fn)
        set_macros(s, r)
        subprocess.run("rm -f tm.o cbp && make -j4", shell=True, check=True,
                       stdout=subprocess.DEVNULL)
        dst = "bins/cbp_S%d_R%d" % (s, r)
        shutil.copy("cbp", dst)
        built.append((s, r, dst))
        print("    built S=%-2d S_RELAX=%-2d in %.0fs  overlay=%s" % (s, r, time.time() - t0, applied),
              flush=True)
    subprocess.check_call(["git", "checkout", "--", "tm.cc", "tm.h", "tm_predictor.cc"])

    # ---- 3) run them, all at once -------------------------------------------
    def run(s, r, binary):
        log = os.path.join(a.logs_dir, "shard%02d__S%d_R%d.log" % (a.shard, s, r))
        t0 = time.time()
        with open(log, "wb") as fh:
            rc = subprocess.call([binary, "-E", "1000000", tp], stdout=fh,
                                 stderr=subprocess.STDOUT)
        row = {"shard": a.shard, "S": s, "S_RELAX": r,
               "seconds": "%.1f" % (time.time() - t0), "rc": rc}
        row.update(scrape(log))
        return row

    t0 = time.time()
    rows = []
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        futs = [pool.submit(run, s, r, b) for (s, r, b) in built]
        for fut in as_completed(futs):
            row = fut.result()
            rows.append(row)
            print("    S=%-2s R=%-2s %8ss rc=%s MPKI=%s acc=%s" % (
                row["S"], row["S_RELAX"], row["seconds"], row["rc"],
                row.get("TM MPKI", "-"), row.get("TM accuracy", "-")), flush=True)
    print("  shard wall %.0fs for %d runs" % (time.time() - t0, len(built)))

    path = os.path.join(a.out_dir, "shard-%02d.csv" % a.shard)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["S"], r["S_RELAX"])):
            w.writerow(r)

    # ---- 4) self-checks ------------------------------------------------------
    problems = []
    bad = [r for r in rows if r["rc"] != 0 or not r.get("TM MPKI")]
    if bad:
        problems.append("%d runs failed: %s" % (len(bad), [(r["S"], r["S_RELAX"]) for r in bad]))
    anchor = plan.get("anchor", {})
    key = (anchor.get("S"), anchor.get("S_RELAX"))
    if key in configs:
        got = [float(r["TM MPKI"]) for r in rows if (r["S"], r["S_RELAX"]) == key]
        exp = float(anchor["TM MPKI"])
        if not got or abs(got[0] - exp) > 0.001:
            problems.append("ANCHOR (5,5): got %s expected %s" % (got, exp))
        else:
            print("(5,5) anchor reproduced: %s" % exp)
    if len(rows) > 1:
        vals = {float(r["TM MPKI"]) for r in rows}
        if len(vals) == 1:
            problems.append("all %d configs gave the identical MPKI - S_RELAX is not wired" % len(rows))
    if problems:
        for p in problems:
            print("::error::shard %d: %s" % (a.shard, p))
        return 1
    print("--- shard %d OK: %d runs ---" % (a.shard, len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
