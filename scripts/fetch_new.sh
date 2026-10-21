#!/bin/bash
# Acquisition for the expansion sites (E-005). Outage-tolerant; resumes from saved files.
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
NEW="NPL_chure_dang NPL_chure_sarlahi NPL_kavre NPL_surkhet IND_banni IND_jharia IND_chambal IND_thar"
missing() { local n=0; for a in $NEW; do [ -f data/processed/$a/$1 ] || n=$((n+1)); done; echo $n; }
for a in $NEW; do $PY -u -m care_ew.climate $a 2>&1 | tail -1; done
# S2: 2 parallel processes
for i in $(seq 1 15); do
  [ "$(missing s2_monthly.nc)" = 0 ] && break
  echo "== S2 try $i $(date)"; $PY -u scripts/run_s2_all.py $NEW >> logs/s2_new.log 2>&1 || sleep 120
done
for kind in modis lst landsat; do
  for i in 1 2 3; do
    [ "$(missing $kind.nc)" = 0 ] && break
    echo "== $kind try $i $(date)"
    for a in $NEW; do [ -f data/processed/$a/$kind.nc ] || $PY -u -m care_ew.context $kind $a 2>&1 | grep -v Warn | tail -1; done
  done
done
for a in $NEW; do [ -f data/processed/$a/hydro_summary.json ] || $PY -u -m care_ew.hydro $a 2>&1 | grep -v Warn | tail -1; done
echo "== NEW SITES DONE $(date)"
