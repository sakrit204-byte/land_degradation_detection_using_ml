#!/bin/bash
# E-004 heat experiment, memory-light: one process per AOI for the dataset build, then ablation + final.
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
for a in NPL_chure IND_bundelkhand ETH_tigray KEN_baringo SEN_ferlo ESP_murcia BRA_matopiba MNG_steppe AUS_murraydarling; do
  $PY -u -m care_ew.dataset $a 2>&1 | grep -v Warn | tail -1
done
$PY -u -m care_ew.train ablation final > logs/train_heat.log 2>&1
echo "train exit $?"
grep -v "Warn\|warn" logs/train_heat.log | grep "^A[0-9]_\|^FINAL" | cut -c1-230
