#!/usr/bin/env bash
# A10b red-edge composites for every study area; resumable (monthly parts in s2re_parts/), retries on failure.
cd "$(dirname "$0")/.."
for a in $(.venv/Scripts/python -c "from care_ew.config import AOIS;print(' '.join(a.key for a in AOIS))"); do
  for try in 1 2 3; do
    [ -f "data/processed/$a/s2_rededge.nc" ] && break
    .venv/Scripts/python -m care_ew.rededge "$a" 2>&1 | grep -E "wrote|items=0|Error" ; sleep 30
  done
  echo "[$a] $( [ -f data/processed/$a/s2_rededge.nc ] && echo OK || echo FAILED ) $(date +%H:%M)"
done
echo REDEDGE_ALL_DONE
