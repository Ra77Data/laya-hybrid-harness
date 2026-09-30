#!/usr/bin/env bash
# Arranca el servicio de decisión local (V7).
#
#   scripts/start-service.sh                     # usa el modelo `active` de config.yaml
#   LAYA_ACTIVE_MODEL=cardiff-xlmr scripts/start-service.sh
#
# El modelo servido, el puerto y los umbrales salen de config.yaml. No hay nada cableado.
set -euo pipefail
cd "$(dirname "$0")/.."

export PYTHONDONTWRITEBYTECODE=1
export TOKENIZERS_PARALLELISM=false
export USE_TF=0
# Cardiff viene del Hub: se permite la descarga la primera vez (queda en la caché estándar).
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
