#!/bin/bash
# E-006: retrain on 17 sites (9 original + 4 Nepal + 4 India). Memory-light: one process per AOI for datasets.
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
cp outputs/results/metrics.json outputs/results/metrics_E004_9sites.json
NEW="NPL_chure_dang NPL_chure_sarlahi NPL_kavre NPL_surkhet IND_banni IND_jharia IND_chambal IND_thar"
for a in $NEW; do $PY -u -m care_ew.dataset $a 2>&1 | grep -v Warn | tail -1; done
$PY -u -m care_ew.train > logs/train17.log 2>&1; echo "train exit $?"
grep -v "Warn\|warn" logs/train17.log | grep "^A[0-9]_\|^FINAL\|^LOCO" | cut -c1-200
for a in $NEW; do $PY -u -m care_ew.predict $a 2>&1 | tail -1; done
echo "== RETRAIN17 DONE $(date)"
