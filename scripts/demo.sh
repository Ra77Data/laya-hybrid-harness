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
  echo "no hay entorno todavía. Corré primero:  make setup" >&2
  exit 2
fi

PROPIO=0
if curl -s -m 2 "$URL/health" >/dev/null 2>&1; then
  echo "(uso el servicio que ya está corriendo en $PORT)"
else
  echo "=== arrancando el servicio en $PORT con config.demo.yaml"
  echo "    la primera vez descarga Cardiff XLM-R (~1,1 GB) desde Hugging Face"
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
    echo "el servicio no arrancó. Últimas líneas del log:" >&2
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
  echo "=== demo terminado. Para dejarlo corriendo de verdad:  make serve"
  echo "    (o 'bash scripts/demo.sh --keep' para que no lo apague al terminar)"
elif [ "$PROPIO" = "1" ]; then
  echo
  echo "=== el servicio sigue arriba en $URL"
  wait $PID
fi
