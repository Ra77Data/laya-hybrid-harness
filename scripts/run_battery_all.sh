#!/usr/bin/env bash
# Runs the battery over every model in the registry, changing ONLY LAYA_ACTIVE_MODEL.
# It is the proof that the pipeline is model-agnostic: no code is touched between models.
set -u
cd "$(dirname "$0")/.."
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HOME/.cache/huggingface/hub}"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p results
URL=http://127.0.0.1:8091

for m in laya-sentiment-v1 laya-sentiment-v2 cardiff-xlmr; do
  echo "############ $m"
  pkill -f "uvicorn service.server:app" 2>/dev/null
  sleep 3
  LAYA_ACTIVE_MODEL="$m" .venv/bin/python -m uvicorn service.server:app \
      --host 127.0.0.1 --port 8091 > "results/service_$m.log" 2>&1 &
  PID=$!
  for _ in $(seq 1 90); do
    curl -s -m 2 "$URL/health" >/dev/null 2>&1 && break
    sleep 2
  done
  curl -s -m 10 "$URL/health" | .venv/bin/python -c "
import json,sys
d=json.load(sys.stdin)
w=d.get('weights') or {}
print(f\"  activo={d['model']} adaptador={d['adapter']} smoke_ok={d['smoke_ok']} hash_coincide={w.get('match')} T={d['calibration'].get('types_with_temperature')}\")"
  .venv/bin/python scripts/battery.py --url "$URL" --n 240 --out "results/battery_$m.json"
  kill $PID 2>/dev/null
  wait $PID 2>/dev/null
  sleep 2
done
echo "############ summary"
.venv/bin/python scripts/compare_batteries.py
