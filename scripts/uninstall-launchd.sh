#!/usr/bin/env bash
# Descarga el LaunchAgent y detiene el servicio. No borra nada del proyecto.
set -euo pipefail
LABEL="com.cesarmg.laya-decide"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null; then
  echo "agente descargado"
else
  echo "(el agente no estaba cargado)"
fi
if [ -f "$PLIST" ]; then
  rm -f "$PLIST" && echo "plist eliminado: $PLIST"
fi
pkill -f "uvicorn service.server:app" 2>/dev/null && echo "proceso restante detenido" || true
echo "el servicio ya no arrancará solo ni se reiniciará."
