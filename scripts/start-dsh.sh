#!/bin/bash
# Brings up DSH web with the Laya plugin pointing at the V7 service.
#
# The decision service is NOT started here: launchd keeps it running (see the README,
# "Startup and persistence"). This script only brings up the DSH interface and registers the tool.
set -euo pipefail
DSH_DIR="${DSH_DIR:-$HOME/Projects/ml/Hybrid_Harness_V3/vendor/deepseek-harness}"
cd "$DSH_DIR"
exec pnpm dsh web --patch "$HOME/Projects/ml/Hybrid_Harness_V7/dsh-laya-plugin/laya.cordis.yml"
