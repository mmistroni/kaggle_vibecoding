#!/usr/bin/env bash
set -e

echo "=== 1. Setting up Python Virtual Environment ==="
python3 -m venv .venv
source .venv/bin/activate
# Ensure we stay inside virtualenv context for pip
.venv/bin/pip install --upgrade pip

echo "=== 2. Downloading Google Antigravity CLI Platform ==="
# Added -s flag if the installer supports non-interactive silent flags, otherwise standard curl pipeline
curl -fsSL https://antigravity.google/cli/install.sh | bash

echo "=== 3. Verifying Installation ==="
# Verify via absolute path since export PATH won't persist past this script execution lifecycle
if [ -f "$HOME/.local/bin/agy" ] || command -v agy &> /dev/null; then
    echo "Success! Google Antigravity CLI (agy) is installed and ready."
else
    echo "Error: agy binary not found in expected paths."
    exit 1
fi