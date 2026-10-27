#!/bin/bash
# E-008 (D-025): acquisition + training tables for the six new sites. Resumable and outage-tolerant.
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
NEW="NPL_chure_udayapur NPL_chure_kailali NPL_sindhupalchok IND_marathwada IND_singrauli IND_shivalik"
missing() { local n=0; for a in $NEW; do [ -f data/processed/$a/$1 ] || n=$((n+1)); done; echo $n; }
for a in $NEW; do [ -f data/processed/$a/climate_monthly.csv ] || $PY -u -m care_ew.climate $a 2>&1 | tail -1; done
for a in $NEW; do [ -f data/processed/$a/static.nc ] || $PY -u -m care_ew.context static $a 2>&1 | grep -v Warn | tail -1; done
for i in $(seq 1 15); do
  [ "$(missing s2_monthly.nc)" = 0 ] && break
  echo "== S2 try $i $(date +%H:%M)"; $PY -u scripts/run_s2_all.py $NEW 2>&1 | grep -E "DONE|wrote|Error" || sleep 120
done
for i in 1 2 3; do
  [ "$(missing modis.nc)" = 0 ] && break
  for a in $NEW; do [ -f data/processed/$a/modis.nc ] || $PY -u -m care_ew.context modis $a 2>&1 | grep -v Warn | tail -1; done
done
for a in $NEW; do [ -f data/processed/$a/hydro_summary.json ] || $PY -u -m care_ew.hydro $a 2>&1 | grep -v Warn | tail -1; done
for a in $NEW; do [ -f data/processed/$a/table.parquet ] || $PY -u -m care_ew.dataset $a 2>&1 | grep -E "rows=|Error"; done
for k in climate_monthly.csv static.nc s2_monthly.nc modis.nc hydro_summary.json table.parquet; do echo "$k missing: $(missing $k)/6"; done
echo "== E008 DONE $(date +%H:%M)"
