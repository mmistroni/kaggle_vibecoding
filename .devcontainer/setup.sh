#!/usr/bin/env bash
set -e

echo "=== 1. Setting up Python Virtual Environment ==="
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

echo "=== 2. Downloading Google Antigravity CLI Platform ==="
# Pull the native headless Linux CLI installer directly into the container
curl -fsSL https://antigravity.google/cli/install.sh | bash

# Ensure the new ~/.local/bin path is immediately registered for the current session
export PATH="$HOME/.local/bin:$PATH"

echo "=== 3. Verifying Installation ==="
if command -v agy &> /dev/null; then
    echo "Success! Google Antigravity CLI (agy) is installed and ready."
else
    echo "Warning: Checking local bin fallback paths..."
fi