#!/usr/bin/env python3
"""GHA 全集扫描：一个分片 = 一类 trace（int 拆两半）。
   每个分片自己从 Google Drive 拉它那一类的 tar.xz，解压，然后用**两个 FPTM 配置**
   各跑一遍本分片的 trace（4 路并行），结果写 results/shard-NN.csv。
"""
import argparse, csv, json, os, subprocess, sys, time, shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

CFGS = ["02_fuzzy_LF4_T18", "04_fuzzy_LF8_T24"]
FIELDS = ["variant", "trace", "seconds", "rc",
          "TM MPKI", "TM accuracy", "TM right", "TM wrong",
          "GShare MPKI", "GShare accuracy", "TAGE MPKI"]


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument("--out-dir", default="fullset_results")
    a = ap.parse_args()

    plan = json.load(open("fullsets.json"))
    me = plan.get(str(a.shard))
    if me is None:
        print(f"shard {a.shard}: 无计划，退出"); return 0

    cat = me["category"]; tarball = me["tarball"]; traces = me["traces"]
    print(f"===== shard {a.shard}: 类别 {cat}，{len(traces)} 条 trace =====")
    print(f"      {', '.join(traces)}")
    sh("df -h . | tail -2")
    sh("nproc; free -g | head -2")

    os.makedirs(a.traces_dir, exist_ok=True)

    # ---- 1) 从 Google Drive **流式**拉取并解压（不落盘 tar.xz，避免 14 GB 磁盘不够）----
    #      不用 gdown：Ubuntu 24.04 的 python 是 externally-managed，pip install 会被 PEP 668 拒绝。
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
    print(f"解压后找到 {found}/{len(traces)} 条")
    if found != len(traces):
        print("!! 缺 trace，列出 traces 目录：")
        subprocess.run(f"find {a.traces_dir} -name '*.gz' | head -50", shell=True)
    sh("df -h . | tail -1")

    os.makedirs(a.logs_dir, exist_ok=True)
    os.makedirs(a.out_dir, exist_ok=True)
    rows = []

    # ---- 3) 两个配置，各跑一遍本分片的 trace ----
    for cfg in CFGS:
        print(f"\n--- 配置 {cfg} ---")
        vdir = os.path.join("variants", cfg)
        for fn in sorted(os.listdir(vdir)):
            if fn.endswith((".h", ".cc")):
                shutil.copy(os.path.join(vdir, fn), fn)
        sh("make clean >/dev/null")
        sh("make -j4")

        def run(tr):
            p = find_trace(a.traces_dir, tr)
            log = os.path.join(a.logs_dir, f"{cfg}__{tr}.log")
            if p is None:
                return {"variant": cfg, "trace": tr, "seconds": "", "rc": 1, "err": "MISSING"}
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
        print(f"  配置 {cfg} 用时 {time.time()-t0:.0f}s")

    path = os.path.join(a.out_dir, f"shard-{a.shard:02d}-{cat}.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["variant"], r["trace"])):
            w.writerow(r)
    bad = [r for r in rows if r["rc"] != 0 or not r.get("TM MPKI")]
    print(f"\n--- shard {a.shard} 完成：{len(rows)-len(bad)}/{len(rows)} ok ---")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
