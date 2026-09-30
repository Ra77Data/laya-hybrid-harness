#!/usr/bin/env bash
# Ejecuta el servicio en primer plano. Es el punto de entrada que usa launchd.
#
# No redirige logs ni hace tee: de eso se encarga quien lo invoque (launchd con
# StandardOutPath/StandardErrorPath, o start-service.sh con su log con marca de tiempo).
set -euo pipefail
cd "$(dirname "$0")/.."

export PYTHONDONTWRITEBYTECODE=1
export TOKENIZERS_PARALLELISM=false
export USE_TF=0
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HOME/.cache/huggingface/hub}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-0}"

PORT="$(.venv/bin/python -c "import yaml;print(yaml.safe_load(open('config.yaml'))['service']['port'])")"
HOST="$(.venv/bin/python -c "import yaml;print(yaml.safe_load(open('config.yaml'))['service']['host'])")"

# Si el puerto ya está ocupado, mejor fallar rápido y con un mensaje claro que dejar
# dos servicios peleando por el mismo socket.
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[service-run] el puerto $PORT ya está ocupado; hay otra instancia corriendo" >&2
  exit 2
fi

echo "[service-run] host=$HOST puerto=$PORT modelo=${LAYA_ACTIVE_MODEL:-<el de config.yaml>}"
exec .venv/bin/python -m uvicorn service.server:app --host "$HOST" --port "$PORT"
