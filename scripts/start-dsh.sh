#!/bin/bash
# Levanta DSH web con el plugin de Laya apuntando al servicio de V7.
#
# El servicio de decisión NO se arranca acá: lo mantiene launchd (ver README, "Arranque y
# persistencia"). Este script sólo levanta la interfaz de DSH y registra la tool.
set -euo pipefail
DSH_DIR="${DSH_DIR:-$HOME/Projects/ml/Hybrid_Harness_V3/vendor/deepseek-harness}"
cd "$DSH_DIR"
exec pnpm dsh web --patch "$HOME/Projects/ml/Hybrid_Harness_V7/dsh-laya-plugin/laya.cordis.yml"
