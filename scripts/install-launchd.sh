#!/usr/bin/env bash
# Instala el servicio como LaunchAgent: arranca al iniciar sesión y se reinicia si se cae.
#
#   scripts/install-launchd.sh              # modelo `active` de config.yaml
#   LAYA_ACTIVE_MODEL=laya-sentiment-v1 scripts/install-launchd.sh
#
# Ojo con el alcance: un LaunchAgent arranca cuando el usuario inicia sesión, no antes.
# Para que arranque en el boot sin login haría falta un LaunchDaemon (como root), que
# además tendría que poder leer la caché de modelos del usuario. Para una máquina
# personal, el agente es lo correcto.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.cesarmg.laya-decide"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
MODEL="${LAYA_ACTIVE_MODEL:-}"

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"

echo "=== 1/4 bajar cualquier instancia previa (launchd o nohup)"
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null && echo "  agente previo descargado" || true
if pkill -f "uvicorn service.server:app" 2>/dev/null; then
  echo "  instancia manual detenida"
  sleep 3
fi

echo "=== 2/4 escribir el plist"
if [ -n "$MODEL" ]; then
  MODEL_ENV="    <key>LAYA_ACTIVE_MODEL</key><string>$MODEL</string>"
else
  MODEL_ENV=""
fi
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT/scripts/service-run.sh</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HF_HUB_CACHE</key><string>$HOME/.cache/huggingface/hub</string>
    <key>HF_HUB_OFFLINE</key><string>0</string>
    <key>PATH</key><string>/usr/bin:/bin:/usr/sbin:/sbin</string>
$MODEL_ENV
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key><false/>
  </dict>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$ROOT/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/launchd.err.log</string>
</dict>
</plist>
EOF
echo "  $PLIST"

echo "=== 3/4 cargar el agente"
launchctl bootstrap "$DOMAIN" "$PLIST"

echo "=== 4/4 esperar a que responda"
PORT="$(cd "$ROOT" && .venv/bin/python -c "import yaml;print(yaml.safe_load(open('config.yaml'))['service']['port'])")"
for _ in $(seq 1 40); do
  curl -s -m 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
  sleep 3
done
if curl -s -m 10 "http://127.0.0.1:$PORT/health" | python3 -c "
import json,sys
d = json.load(sys.stdin)
w = d.get('weights') or {}
print(f\"  sirviendo: {d['model']} ({d['adapter']}) | smoke_ok={d['smoke_ok']} | hash_coincide={w.get('match')}\")
print(f\"  T: {d['calibration'].get('types_with_temperature') or 'ninguna'} | umbrales: {d['delegation']['per_type']}\")
"; then
  echo
  echo "listo. Comandos útiles:"
  echo "  launchctl print $DOMAIN/$LABEL | grep -E 'state|pid'"
  echo "  tail -f $ROOT/logs/launchd.err.log"
  echo "  scripts/uninstall-launchd.sh"
else
  echo "  el servicio no respondió; revisá $ROOT/logs/launchd.err.log" >&2
  exit 1
fi
