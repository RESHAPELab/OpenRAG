#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f ".env.test" ]]; then
  echo ".env.test not found. Create it from .env.test.example first."
  exit 1
fi

# Export all variables from .env.test for this shell.
set -a
source .env.test
set +a

echo "Starting isolated test databases..."
docker compose -f docker-compose.test.yml up -d

echo "Running second (test) bot with .env.test configuration..."
uv run python main.py
