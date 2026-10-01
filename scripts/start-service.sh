#!/usr/bin/env bash
# Starts the local decision service (V7).
#
#   scripts/start-service.sh                     # uses the `active` model of config.yaml
#   LAYA_ACTIVE_MODEL=cardiff-xlmr scripts/start-service.sh
#
# The served model, the port and the thresholds come from config.yaml. Nothing is hardcoded.
set -euo pipefail
cd "$(dirname "$0")/.."

export PYTHONDONTWRITEBYTECODE=1
export TOKENIZERS_PARALLELISM=false
export USE_TF=0
# Cardiff comes from the Hub: the download is allowed the first time (it stays in the standard cache).
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HOME/.cache/huggingface/hub}"   # la ruta estándar de HF
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-0}"

read -r PORT DEFAULT_MODEL < <(.venv/bin/python -c "
import yaml; c = yaml.safe_load(open('config.yaml'))
print(c['service']['port'], c['active'])")

MODEL="${LAYA_ACTIVE_MODEL:-$DEFAULT_MODEL}"
mkdir -p logs
STAMP="$(date '+%Y%m%d-%H%M%S')"
LOG="logs/service_${MODEL}_${STAMP}.log"

echo "[start-service] modelo=$MODEL puerto=$PORT log=$LOG"
echo "[start-service] pesos y calibración se verifican al arrancar; si el hash no coincide, no levanta"

LAYA_ACTIVE_MODEL="$MODEL" exec .venv/bin/python -m uvicorn service.server:app \
    --host 127.0.0.1 --port "$PORT" 2>&1 | tee -a "$LOG"
