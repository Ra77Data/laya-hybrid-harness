#!/usr/bin/env bash
# Demostración completa en un comando: `make demo`.
#
# Arranca el servicio con el registro mínimo (config.demo.yaml, sólo Cardiff: corre en cualquier
# sistema operativo), muestra los casos, imprime las métricas y apaga. Si ya hay un servicio
# escuchando en el puerto, usa ese y no arranca otro.
set -uo pipefail
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1
cd "$(dirname "$0")/.."
PORT="${LAYA_PORT:-8091}"
URL="http://127.0.0.1:$PORT"
PY=".venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "no environment yet. Run first:  make setup" >&2
  exit 2
fi

PROPIO=0
if curl -s -m 2 "$URL/health" >/dev/null 2>&1; then
  echo "(using the service already running on $PORT)"
else
  echo "=== starting the service on $PORT with config.demo.yaml"
  echo "    the first time it downloads Cardiff XLM-R (~1.1 GB) from Hugging Face"
  LAYA_PORT="$PORT" LAYA_CONFIG=config.demo.yaml "$PY" -m uvicorn service.server:app \
    --host 127.0.0.1 --port "$PORT" > /tmp/harness-demo.log 2>&1 &
  PID=$!
  PROPIO=1
  trap 'kill $PID 2>/dev/null' EXIT
  for _ in $(seq 1 180); do
    curl -s -m 2 "$URL/health" >/dev/null 2>&1 && break
    sleep 2
  done
  if ! curl -s -m 5 "$URL/health" >/dev/null 2>&1; then
    echo "the service did not start. Last lines of the log:" >&2
    tail -25 /tmp/harness-demo.log >&2
    exit 1
  fi
  echo
fi

"$PY" scripts/demo.py --url "$URL"

if [ "$PROPIO" = "1" ] && [ "$KEEP" = "0" ]; then
  kill $PID 2>/dev/null
  wait $PID 2>/dev/null
  echo
  echo "=== demo finished. To actually leave it running:  make serve"
  echo "    (or 'bash scripts/demo.sh --keep' so it is not shut down at the end)"
elif [ "$PROPIO" = "1" ]; then
  echo
  echo "=== the service is still up at $URL"
  wait $PID
fi
