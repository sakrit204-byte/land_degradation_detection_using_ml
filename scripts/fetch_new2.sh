#!/bin/bash
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
NEW="NPL_chure_dang NPL_chure_sarlahi NPL_kavre NPL_surkhet IND_banni IND_jharia IND_chambal IND_thar"
run_modis() { for a in "$@"; do for t in 1 2 3; do [ -f data/processed/$a/modis.nc ] && break; $PY -u -m care_ew.context modis $a 2>&1 | grep -v Warn | tail -1; done; done; }
run_modis NPL_chure_dang NPL_chure_sarlahi NPL_kavre NPL_surkhet & run_modis IND_banni IND_jharia IND_chambal IND_thar & wait
for a in $NEW; do for t in 1 2; do [ -f data/processed/$a/hydro_summary.json ] && break; $PY -u -m care_ew.hydro $a 2>&1 | grep -v Warn | tail -1; done; done
for k in modis.nc hydro_summary.json dist_river_km.npy; do n=0; for a in $NEW; do [ -f data/processed/$a/$k ] && n=$((n+1)); done; echo "$k: $n/8"; done
