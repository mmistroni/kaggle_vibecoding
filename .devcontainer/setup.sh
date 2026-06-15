#!/usr/bin/env bash

# 1. Create the virtual environment in the workspace
python3 -m venv .venv

# 2. Activate it
source .venv/bin/activate

# 3. Upgrade pip
pip install --upgrade pip

# 4. "Install" antigravity by forcing a pre-import script or adding a reminder
# Since antigravity is built-in, we can create a startup script that triggers it
echo "import antigravity" > workspace_init.py

echo "Environment setup complete! Virtual environment created at .venv"