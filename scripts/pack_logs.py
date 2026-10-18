#!/usr/bin/env python3
"""Pack the per-trace RAW STDOUT collected from shard artifacts into the results
directory, so the collect job can commit it back to the repo.

Why: artifacts expire (14 days) and need credentials to download; the repo does
not.  Raw stdout is the only place where `Measured # of instructions` and
`GShare wrong` live, i.e. the columns the CSV does not carry, so losing it
blocks per-trace bit-identity checks.  GHA-first therefore requires this step.

Layout:  collected/logs/<name>.log  ->  <out>/<name>.log.gz
A `SHA256SUMS` manifest is written next to the .gz files; it hashes the
UNCOMPRESSED content (gzip output can vary between zlib versions).

Usage:
  python3 scripts/pack_logs.py --src collected --out isoB_results/logs --expect 105
Exit codes: 0 ok, 1 no logs / count mismatch (loud failure on purpose: a collect
that silently drops raw stdout is exactly the bug this script exists to prevent).
"""
import argparse
import gzip
import hashlib
import os
import sys


def count_csv_rows(patterns):
    """Number of data rows (one per run) across the given shard CSV globs."""
    import csv
    import glob
    total = 0
    for pat in patterns:
        for f in sorted(glob.glob(pat)):
            with open(f, newline="") as fh:
                rows = list(csv.reader(fh))
            total += max(0, len(rows) - 1)  # minus the header
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="collected", help="download-artifact root")
    ap.add_argument("--out", required=True, help="destination dir, e.g. isoB_results/logs")
    ap.add_argument("--suffix", default=".log", help="artifact file suffix to pack")
    ap.add_argument("--expect", type=int, default=0,
                    help="required number of logs; 0 = only require >=1")
    ap.add_argument("--expect-csv", default="",
                    help="comma-separated glob(s) of shard CSVs; one data row per run, "
                         "so the total row count must equal the number of logs")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    manifest = []
    raw_total = comp_total = 0

    for root, _dirs, files in os.walk(a.src):
        for fn in sorted(files):
            if not fn.endswith(a.suffix):
                continue
            src = os.path.join(root, fn)
            rel = os.path.relpath(src, a.src).split(os.sep)
            if rel and rel[0] == "logs":
                rel = rel[1:]
            dst = os.path.join(a.out, *rel) + ".gz"
            # collision guard: same basename from different shards => keep the path
            if os.path.exists(dst) and os.path.getsize(dst) > 0:
                dst = os.path.join(a.out, *rel[:-1], rel[-1] + ".gz") if len(rel) > 1 else dst
            with open(src, "rb") as fh:
                data = fh.read()
            h = hashlib.sha256(data).hexdigest()
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            with gzip.open(dst, "wb", compresslevel=9) as fh:
                fh.write(data)
            raw_total += len(data)
            comp_total += os.path.getsize(dst)
            manifest.append("%s  %d  %s" % (h, len(data), os.path.basename(dst)))
            print("  packed %-58s %7d -> %6d B" % (os.path.basename(dst), len(data),
                                                   os.path.getsize(dst)))

    if manifest:
        with open(os.path.join(a.out, "SHA256SUMS"), "w") as fh:
            fh.write("\n".join(manifest) + "\n")

    print("pack_logs: %d log(s), %d -> %d bytes, out=%s"
          % (len(manifest), raw_total, comp_total, a.out))
    if not manifest:
        print("::error::pack_logs: no %s files under %s - shard artifacts did not carry raw stdout"
              % (a.suffix, a.src))
        return 1
    if a.expect and len(manifest) != a.expect:
        print("::error::pack_logs: expected %d log(s), got %d - incomplete collect"
              % (a.expect, len(manifest)))
        return 1
    if a.expect_csv:
        runs = count_csv_rows(a.expect_csv.split(","))
        if runs != len(manifest):
            print("::error::pack_logs: %d CSV run row(s) vs %d log(s) - "
                  "some raw stdout did not make it back" % (runs, len(manifest)))
            return 1
        print("pack_logs: %d log(s) == %d run row(s) in %s"
              % (len(manifest), runs, a.expect_csv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
