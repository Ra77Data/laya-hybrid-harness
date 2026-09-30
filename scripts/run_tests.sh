#!/usr/bin/env bash
# Self-test del servicio + sondas, contra una instancia temporal en un puerto libre.
# Es lo que corre `make test`. No toca la instancia desplegada.
set -uo pipefail
cd "$(dirname "$0")/.."
PORT="${LAYA_TEST_PORT:-8099}"
URL="http://127.0.0.1:$PORT"
PY=".venv/bin/python"
FAIL=0

if [ ! -x "$PY" ]; then
  echo "no hay entorno: corré 'make setup' primero" >&2
  exit 2
fi

echo "=== arrancando una instancia de prueba en $PORT"
LAYA_PORT="$PORT" "$PY" -m uvicorn service.server:app --host 127.0.0.1 --port "$PORT" \
  > /tmp/harness-test.log 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null' EXIT

for _ in $(seq 1 60); do
  curl -s -m 2 "$URL/health" >/dev/null 2>&1 && break
  sleep 2
done
if ! curl -s -m 5 "$URL/health" >/dev/null 2>&1; then
  echo "FALLA: el servicio no arrancó (ver /tmp/harness-test.log)" >&2
  tail -20 /tmp/harness-test.log >&2
  exit 1
fi

echo
echo "=== self-test de los modelos declarados"
"$PY" - "$URL" <<'PYEOF' || FAIL=1
import json, sys, urllib.request
url = sys.argv[1]
req = urllib.request.Request(url + "/selftest", data=b"{}", headers={"Content-Type": "application/json"})
d = json.load(urllib.request.urlopen(req, timeout=600))
print(f"  passed: {d['passed']}")
for mid, recs in d["results"].items():
    for r in recs:
        print(f"   {'OK ' if r['ok'] else 'FALLA'} [{mid}] esperado={r['expected']} obtenido={r.get('got')}")
sys.exit(0 if d["passed"] else 1)
PYEOF

echo
echo "=== casos límite"
"$PY" scripts/probe_harness.py --url "$URL" --out /tmp/probe.json | tail -4 || FAIL=1

echo
echo "=== concurrencia (es lo que tumbaba el servicio antes del candado de inferencia)"
"$PY" scripts/probe_concurrency.py --url "$URL" --counts 2,4,8 --out /tmp/conc.json | grep -E "concurrentes|agente" || FAIL=1

echo
if [ "$FAIL" = "0" ]; then echo "TODO OK"; else echo "HUBO FALLAS"; fi
exit $FAIL
