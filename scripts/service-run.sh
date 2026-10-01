#!/usr/bin/env bash
# Runs the service in the foreground. It is the entry point launchd uses.
#
# It does not redirect logs or tee: whoever invokes it takes care of that (launchd with
# StandardOutPath/StandardErrorPath, or start-service.sh with its timestamped log).
set -euo pipefail
cd "$(dirname "$0")/.."

export PYTHONDONTWRITEBYTECODE=1
export TOKENIZERS_PARALLELISM=false
export USE_TF=0
export HF_HUB_CACHE="${HF_HUB_CACHE:-$HOME/.cache/huggingface/hub}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-0}"

PORT="$(.venv/bin/python -c "import yaml;print(yaml.safe_load(open('config.yaml'))['service']['port'])")"
HOST="$(.venv/bin/python -c "import yaml;print(yaml.safe_load(open('config.yaml'))['service']['host'])")"

# If the port is already taken, better to fail fast with a clear message than to leave
# two services fighting over the same socket.
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[service-run] el puerto $PORT ya está ocupado; hay otra instancia corriendo" >&2
  exit 2
fi

echo "[service-run] host=$HOST puerto=$PORT modelo=${LAYA_ACTIVE_MODEL:-<el de config.yaml>}"
exec .venv/bin/python -m uvicorn service.server:app --host "$HOST" --port "$PORT"
