#!/usr/bin/env bash
# A10a texture features for every study area, one process per site (memory), resumable via texture.parquet.
cd "$(dirname "$0")/.."
for a in $(.venv/Scripts/python -c "from care_ew.config import AOIS;print(' '.join(a.key for a in AOIS))"); do
  [ -f "data/processed/$a/texture.parquet" ] && { echo "[$a] done"; continue; }
  .venv/Scripts/python -m care_ew.texture "$a" 2>&1 | grep -v Warning
done
echo TEXTURE_ALL_DONE
