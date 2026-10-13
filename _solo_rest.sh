#!/bin/bash
set -u
cd /data/tm_gha_sweep || exit 1
TRACES=/data/tm_cbp_sim/training_traces
OUT=/data/tm_gha_sweep/gha12_solo_rest.txt
: > "$OUT"
echo "solo timings, one at a time (restart of the run lost to rc=127)" >> "$OUT"
for t in web_18 fp_0 infra_0 compress_1 media_1; do
  f=$(find "$TRACES" -name "${t}_trace.gz" | head -1)
  if [ -z "$f" ]; then echo "$t MISSING 0" >> "$OUT"; continue; fi
  s=$(date +%s)
  ./cbp -E 1000000 "$f" > "/tmp/_solo_${t}.log" 2>&1
  rc=$?
  e=$(date +%s)
  mpki=$(grep -m1 '^TM MPKI:' "/tmp/_solo_${t}.log" | awk '{print $3}')
  echo "$t $((e-s)) ${mpki:-rc=$rc}" >> "$OUT"
done
echo "DONE" >> "$OUT"
