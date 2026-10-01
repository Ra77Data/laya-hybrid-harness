#!/usr/bin/env bash
# Unloads the LaunchAgent and stops the service. It deletes nothing from the project.
set -euo pipefail
LABEL="${LAYA_LABEL:-com.cesarmg.laya-decide}"
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
