#!/usr/bin/env bash
set -e

echo "=== 1. Setting up Python Virtual Environment ==="
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/pip install --upgrade pip

echo "=== 2. Creating Agent Workspace Ignore Safeguards ==="
# Prevent agy from blowing token limits by indexing the virtual env
if [ ! -f "AGENTS.md" ]; then
    cat << 'EOF' > AGENTS.md
# Workspace Rules
ignore:
  - .venv/
  - __pycache__/
  - .git/
EOF
    echo "Created AGENTS.md with default ignore rules."
fi

echo "=== 3. Downloading Google Antigravity CLI Platform ==="
# Run the installation script natively
curl -fsSL https://antigravity.google/cli/install.sh | bash

echo "=== 4. Verifying Installation ==="
# Explicitly evaluate path for verification step
export PATH="$HOME/.local/bin:$PATH"

if command -v agy &> /dev/null; then
    echo "Success! Google Antigravity CLI (agy) is installed and ready."
    # Optional: run a clean check to verify auth tokens work
    # agy status
else
    echo "Error: agy binary not found in expected paths."
    exit 1
fi