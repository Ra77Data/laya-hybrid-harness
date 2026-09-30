#!/usr/bin/env bash
# Verificación del quickstart en condiciones de primer uso: clon nuevo, sin entorno, sin caché
# de uv y sin caché de modelos. Mide cada paso y falla si alguno se rompe.
#
# Es la prueba que decide si el repo se puede publicar: si esto no funciona, nadie de afuera
# va a poder probarlo.
#
# Uso:  bash tests/quickstart_clean.sh [directorio]
set -uo pipefail

AQUI="$(cd "$(dirname "$0")/.." && pwd)"
DESTINO="${1:-/tmp/quickstart-clean}"
LOG="$AQUI/results/quickstart_clean.log"
mkdir -p "$(dirname "$LOG")"

paso() {  # paso <nombre> <comando...>
  local nombre="$1"; shift
  local t0 t1 estado
  t0=$(date +%s)
  echo "--- $nombre"
  if "$@" >> "$LOG" 2>&1; then estado=OK; else estado="FALLA (ver $LOG)"; fi
  t1=$(date +%s)
  printf '%-28s %4d s   %s\n' "$nombre" "$((t1 - t0))" "$estado"
  [ "$estado" = "OK" ]
}

echo "=== quickstart en limpio: $DESTINO"
echo "    (cachés de uv y de modelos vacías: mide el primer uso real)"
rm -rf "$DESTINO"
mkdir -p "$DESTINO"
: > "$LOG"

export UV_CACHE_DIR="$DESTINO/.uvcache"
export UV_PYTHON_INSTALL_DIR="$DESTINO/.uvpython"
export HF_HUB_CACHE="$DESTINO/.hfcache"
export HF_HOME="$DESTINO/.hfhome"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

paso "clonar el repo"        git clone -q "$AQUI" "$DESTINO/harness"
cd "$DESTINO/harness" || exit 2
echo "    archivos que llegan con el clon: $(git ls-files | wc -l | tr -d ' ')"
echo "    ¿llegó algún venv o log? $(git ls-files | grep -cE '\.venv|^logs/' || true)"

paso "make setup"            make setup
paso "make demo"             make demo
paso "make test"             make test

echo
echo "=== resumen"
if grep -q "demo terminado" "$LOG"; then
  echo "  el demo llegó al final"
else
  echo "  EL DEMO NO TERMINÓ: revisar $LOG"
fi
echo "  tamaño del entorno: $(du -sh "$DESTINO/harness/.venv" 2>/dev/null | cut -f1)"
echo "  tamaño de la caché de modelos: $(du -sh "$DESTINO/.hfcache" 2>/dev/null | cut -f1)"
echo "  log completo: $LOG"
