#!/bin/bash
set -euo pipefail

# Only run in remote (Claude Code on the web) environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Update uv and install dependencies
cd "$CLAUDE_PROJECT_DIR"
uv self update --quiet
uv sync --quiet

# Install pre-commit hooks
bash scripts/install-hooks.sh
