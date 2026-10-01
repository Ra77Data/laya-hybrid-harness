#!/bin/bash
# Brings up DSH web with the Laya plugin pointing at this service.
#
# The decision service is NOT started here: launchd keeps it running (see the README,
# "Startup and persistence"). This script only brings up the DSH interface and registers the tool.
#
# DSH lives in a deepseek-harness checkout, which is not part of this repository: point DSH_DIR at
# yours, e.g. in the project's .envrc (it is machine-specific, so it does not belong in the repo).
set -euo pipefail

# The repo root comes from this script's own location, so the repo can live anywhere — and it is
# computed BEFORE any cd, because a relative $0 would otherwise resolve against the new directory.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -z "${DSH_DIR:-}" ]; then
  # DSH_DIR is machine-specific and normally comes from the project's .envrc — but direnv blocks a
  # file it has not been asked to approve, and a blocked .envrc should not stop you from starting
  # DSH. So look in the obvious places first and say which one was picked.
  for candidate in "$REPO/vendor/deepseek-harness" "$HOME/Projects/ml"/*/vendor/deepseek-harness; do
    if [ -d "$candidate/apps/cli" ]; then
      DSH_DIR="$candidate"
      echo "start-dsh: DSH_DIR not set, using $DSH_DIR (export DSH_DIR to choose another)" >&2
      break
    fi
  done
fi
if [ -z "${DSH_DIR:-}" ]; then
  echo "start-dsh: DSH_DIR is not set and no deepseek-harness checkout was found." >&2
  echo "  export DSH_DIR=\$HOME/Projects/ml/Hybrid_Harness/vendor/deepseek-harness" >&2
  exit 2
fi
[ -d "$DSH_DIR/apps/cli" ] || { echo "start-dsh: DSH_DIR=$DSH_DIR does not look like a deepseek-harness checkout (no apps/cli)" >&2; exit 2; }

PLUGIN_YML="$REPO/dsh-laya-plugin/laya.cordis.yml"
[ -f "$PLUGIN_YML" ] || { echo "start-dsh: missing $PLUGIN_YML — generate it with 'make cordis'" >&2; exit 2; }

cd "$DSH_DIR"
exec pnpm dsh web --patch "$PLUGIN_YML"
