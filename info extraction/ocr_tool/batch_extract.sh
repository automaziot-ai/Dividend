#!/usr/bin/env bash
set -u
DIR="/Users/tomerbenami/Downloads/טפסים שרון לוגסי"
cd "$(dirname "$0")"
for f in "$DIR"/*.pdf; do
  name=$(basename "$f")
  # skip any rasterized output
  if [[ "$name" == *_rasterized_* ]]; then
    continue
  fi
  echo "=== $name ==="
  .venv/bin/python extract_fields.py "$f" 2>/dev/null
  echo
done
