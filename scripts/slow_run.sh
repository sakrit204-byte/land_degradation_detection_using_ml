#!/bin/bash
# Slow, resumable, memory-gated pipeline (D-022). Each piece runs in its own process; a marker file
# logs/slow/<piece>.done is written on success and the piece is skipped on re-runs. Before each piece the
# script waits until >= MIN_FREE_GB of RAM is free. Re-run this script any time to resume.
cd "$(dirname "$0")/.."
PY=.venv/Scripts/python
MIN_FREE_GB=${MIN_FREE_GB:-5}
ALL=$($PY -c "from care_ew.config import AOIS; print(' '.join(a.key for a in AOIS))")
free_gb() { powershell -NoProfile -c "[math]::Floor((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB)"; }
wait_mem() { while true; do f=$(free_gb | tr -d '\r'); [ "${f:-0}" -ge "$MIN_FREE_GB" ] && return; echo "   waiting for memory (free ${f} GB < ${MIN_FREE_GB} GB) $(date +%H:%M)"; sleep 120; done; }
piece() {   # piece <name> <command...>
  local name=$1; shift
  [ -f logs/slow/$name.done ] && { echo "skip $name (done)"; return 0; }
  wait_mem
  echo "== $name start $(date +%H:%M:%S)"
  local t0=$(date +%s)
  "$@" > logs/slow/$name.log 2>&1
  local rc=$?
  if [ $rc -eq 0 ]; then touch logs/slow/$name.done; echo "   $name ok ($(( ($(date +%s)-t0)/60 )) min)"
  else echo "   $name FAILED rc=$rc (see logs/slow/$name.log); retry once after 5 min"; sleep 300; wait_mem
       "$@" > logs/slow/$name.log 2>&1 && { touch logs/slow/$name.done; echo "   $name ok on retry"; } || { echo "   $name FAILED again - stopping"; exit 1; }
  fi
}
piece train_ablation_final $PY -u -m care_ew.train ablation final
piece train_vc    $PY -u -m care_ew.train vc
piece train_lc    $PY -u -m care_ew.train lc
piece train_wf    $PY -u -m care_ew.train wf
piece train_loco  $PY -u -m care_ew.train loco
piece train_sens  $PY -u -m care_ew.train sens
for a in $ALL; do piece predict_$a $PY -u -m care_ew.predict $a; done
piece corroborate $PY -u -m care_ew.corroborate
piece figures     $PY -u -m care_ew.figures
piece export      $PY -u -m care_ew.export
echo "== SLOW RUN COMPLETE $(date)"
