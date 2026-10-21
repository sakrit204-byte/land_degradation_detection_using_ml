#!/bin/bash
# E-005 + E-006: 17 sites, A8 ecosystem-function features. Memory-light: one process per AOI for datasets/predictions.
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
ALL=$($PY -c "from care_ew.config import AOIS; print(' '.join(a.key for a in AOIS))")
[ -f outputs/results/metrics_E004_9sites.json ] || cp outputs/results/metrics.json outputs/results/metrics_E004_9sites.json
echo "== datasets $(date)"; for a in $ALL; do $PY -u -m care_ew.dataset $a 2>&1 | grep -v Warn | tail -1; done
echo "== train $(date)"; $PY -u -m care_ew.train > logs/train17.log 2>&1; echo "train exit $?"
grep -v "Warn\|warn" logs/train17.log | grep "^A[0-9]_\|^FINAL\|^LOCO" | cut -c1-200
echo "== predict $(date)"; for a in $ALL; do $PY -u -m care_ew.predict $a 2>&1 | tail -1; done
echo "== corroborate/figures/export $(date)"
$PY -u -m care_ew.corroborate > logs/corroborate.log 2>&1
$PY -u -m care_ew.figures > logs/figures.log 2>&1
$PY -u -m care_ew.export > logs/export.log 2>&1; echo "export exit $?"
echo "== FULL17 DONE $(date)"
