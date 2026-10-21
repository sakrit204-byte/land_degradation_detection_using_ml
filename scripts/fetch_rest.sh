#!/bin/bash
# Sequential, outage-tolerant data acquisition chain (memory-light). Each step resumes from saved files
# and is retried (up to 15x, 2 min apart) until all its outputs exist - survives internet drop-outs.
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
AOIS="NPL_chure IND_bundelkhand ETH_tigray KEN_baringo SEN_ferlo ESP_murcia BRA_matopiba MNG_steppe AUS_murraydarling"
missing() { local n=0; for a in $AOIS; do [ -f data/processed/$a/$1 ] || n=$((n+1)); done; echo $n; }
for i in $(seq 1 15); do
  [ "$(missing s2_monthly.nc)" = 0 ] && break
  echo "== S2 try $i $(date)"; $PY -u scripts/run_s2_all.py >> logs/s2_build.log 2>&1 || sleep 120
done
for i in $(seq 1 15); do
  [ "$(missing modis.nc)" = 0 ] && break
  echo "== MODIS try $i $(date)"
  for a in $AOIS; do [ -f data/processed/$a/modis.nc ] || $PY -u -m care_ew.context modis $a 2>&1 | grep -v Warn >> logs/modis.log; done
  [ "$(missing modis.nc)" = 0 ] || sleep 120
done
for i in $(seq 1 10); do
  [ "$(missing hydro_summary.json)" = 0 ] && break
  echo "== HYDRO try $i $(date)"
  for a in $AOIS; do [ -f data/processed/$a/hydro_summary.json ] || $PY -u -m care_ew.hydro $a 2>&1 | grep -v Warn >> logs/hydro.log; done
  [ "$(missing hydro_summary.json)" = 0 ] || sleep 300
done
echo "== CORE DONE $(date)"
for i in $(seq 1 10); do
  [ "$(missing landsat.nc)" = 0 ] && break
  echo "== LANDSAT try $i $(date)"
  for a in $AOIS; do [ -f data/processed/$a/landsat.nc ] || $PY -u -m care_ew.context landsat $a 2>&1 | grep -v Warn >> logs/landsat.log; done
  [ "$(missing landsat.nc)" = 0 ] || sleep 120
done
echo "== ALL DONE $(date)"
