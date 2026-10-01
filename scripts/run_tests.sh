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
  echo "no environment: run 'make setup' first" >&2
  exit 2
fi

# Si quedó una instancia de prueba anterior, esperar a que libere el puerto: correr `make test`
# dos veces seguidas fallaba de forma confusa (el servicio nuevo no podía enlazar).
for _ in $(seq 1 15); do
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 || break
  sleep 1
done
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "port $PORT is still in use; stop whatever is listening there and retry" >&2
  exit 2
fi

echo "=== starting a test instance on $PORT"
LAYA_PORT="$PORT" "$PY" -m uvicorn service.server:app --host 127.0.0.1 --port "$PORT" \
  > /tmp/harness-test.log 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null' EXIT

for _ in $(seq 1 60); do
  curl -s -m 2 "$URL/health" >/dev/null 2>&1 && break
  sleep 2
done
if ! curl -s -m 5 "$URL/health" >/dev/null 2>&1; then
  echo "FAILED: the service did not start (see /tmp/harness-test.log)" >&2
  tail -20 /tmp/harness-test.log >&2
  exit 1
fi

echo
echo "=== self-test of the declared models"
"$PY" - "$URL" <<'PYEOF' || FAIL=1
import json, sys, urllib.request
url = sys.argv[1]
req = urllib.request.Request(url + "/selftest", data=b"{}", headers={"Content-Type": "application/json"})
d = json.load(urllib.request.urlopen(req, timeout=600))
print(f"  passed: {d['passed']} | cases evaluated: {d.get('tested')} | "
      f"skipped models (not on this machine): {d.get('skipped_models') or 'none'}")
for mid, recs in d["results"].items():
    for r in recs:
        if r.get("skipped"):
            print(f"   SKIPPED [{mid}] {r.get('reason')}")
        else:
            print(f"   {'OK ' if r.get('ok') else 'FAILED'} [{mid}] expected={r.get('expected')} "
                  f"got={r.get('got')} {r.get('error') or ''}")
sys.exit(0 if d["passed"] else 1)
PYEOF

echo
echo "=== edge cases"
"$PY" scripts/probe_harness.py --url "$URL" --out /tmp/probe.json | tail -4 || FAIL=1

echo
echo "=== concurrency (what used to take the service down before the inference lock)"
"$PY" scripts/probe_concurrency.py --url "$URL" --counts 2,4,8 --out /tmp/conc.json | grep -E "concurrent|agent" || FAIL=1

echo
if [ "$FAIL" = "0" ]; then echo "ALL OK"; else echo "THERE WERE FAILURES"; fi
exit $FAIL
