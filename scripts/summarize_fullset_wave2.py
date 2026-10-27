#!/usr/bin/env python3
"""Wave-2 wrapper around scripts/summarize_fullset_arm.py.

Two arms need a different notion of "the TM must not move":

  hybC_t2    TM_MODE 3 only gates the OUTPUT (use the TM when |vote| >= 2, else keep the
             1-bit prediction); the TM itself is untouched, so its TM MPKI / TM right must
             still equal the 105-trace baseline -> add it to the untouched set.

  tm_pc_only this arm's "TM" is a DIFFERENT TM (only the 21 PC bits, 1,344 B), so its TM
             numbers legitimately differ from the baseline -> remove it from the untouched
             set that the wave-1 script carries.

Why a wrapper instead of an edit: scripts/summarize_fullset_arm.py is in the wave-1
workflow's push paths, so committing a change to it would re-trigger 14 finished jobs.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import summarize_fullset_arm as base  # noqa: E402

arm = None
for i, a in enumerate(sys.argv):
    if a == "--arm" and i + 1 < len(sys.argv):
        arm = sys.argv[i + 1]

untouched = set(base.TM_UNTOUCHED)
if arm == "hybC_t2":
    untouched.add(arm)
elif arm == "tm_pc_only":
    untouched.discard(arm)
print("wave2 wrapper: TM-identity gate set = %s" % sorted(untouched))
base.TM_UNTOUCHED = untouched

sys.exit(base.main())
