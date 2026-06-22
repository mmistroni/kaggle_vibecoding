#!/usr/bin/env bash
# -e: exit on error, -x: print commands as they run so you see exactly what fails
set -ex

echo "=== 1. Installing System Dependencies ==="
sudo apt-get update && sudo apt-get install -y sqlite3 libsqlite3-dev apt-transport-https ca-certificates gnupg curl

# Safely add the Google Cloud SDK distribution URI and public key
if [ ! -f "/usr/share/keyrings/cloud.google.gpg" ]; then
    curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
fi

# FIX: Changed sources.list.p to sources.list.d
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list

sudo apt-get update && sudo apt-get install -y google-cloud-cli

echo "=== 2. Setting up Python Virtual Environment ==="
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

echo "=== 3. Creating Agent Workspace Ignore Safeguards ==="
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

echo "=== 4. Downloading Google Antigravity CLI Platform ==="
# Note: If this URL is a placeholder/mock, it will fail under 'set -e'. 
# If it's a real URL, it will proceed.
curl -fsSL https://antigravity.google/cli/install.sh | bash

echo "=== 5. Installing Astral uv & Google Agents CLI ==="
curl -LsSf https://astral.sh/uv/install.sh | sh

# Explicitly add uv to the current script's path so it can be called immediately
export PATH="/home/vscode/.local/bin:$PATH"

echo "Running google-agents-cli setup..."
/home/vscode/.local/bin/uvx google-agents-cli setup

echo "=== 6. Verifying Installation ==="
if command -v gcloud &> /dev/null; then
    echo "Success! Google Cloud CLI (gcloud) is available."
    gcloud --version
else
    echo "Error: gcloud binary not found."
    exit 1
fi

echo "=== Setup Completed Successfully ==="