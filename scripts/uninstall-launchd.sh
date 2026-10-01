#!/usr/bin/env bash
# Descarga el LaunchAgent y detiene el servicio. No borra nada del proyecto.
set -euo pipefail
LABEL="com.cesarmg.laya-decide"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null; then
  echo "agent unloaded"
else
  echo "(the agent was not loaded)"
fi
if [ -f "$PLIST" ]; then
  rm -f "$PLIST" && echo "plist removed: $PLIST"
fi
pkill -f "uvicorn service.server:app" 2>/dev/null && echo "remaining process stopped" || true
echo "the service will no longer start on its own or restart."
