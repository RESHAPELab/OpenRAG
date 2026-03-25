#!/usr/bin/env bash
# Note: use LF line endings on Windows (CRLF breaks `set` options in bash).
set -eu

if [[ ! -f ".env.test" ]]; then
  echo ".env.test not found. Create it from .env.test.example first."
  exit 1
fi

# Export all variables from .env.test for this shell.
set -a
# shellcheck source=/dev/null
source .env.test
set +a

echo "Starting isolated test databases..."
docker compose -f docker-compose.test.yml up -d

echo "Running second (test) bot with .env.test configuration..."
if command -v uv >/dev/null 2>&1; then
  uv run python main.py
elif [[ -f ".venv/Scripts/python.exe" ]]; then
  # Git Bash / WSL: PATH often does not include Windows `uv`
  .venv/Scripts/python.exe main.py
elif [[ -x ".venv/bin/python" ]]; then
  .venv/bin/python main.py
else
  echo "Could not find 'uv' or .venv Python. From PowerShell run: .\\run-test-bot.ps1"
  echo "Or install uv and ensure it is on PATH, then run: uv sync"
  exit 1
fi
