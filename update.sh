#!/usr/bin/env bash
# One-command redeploy: pull the latest code, rebuild, and restart the stack.
# Run from anywhere: ./update.sh
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Pulling latest code..."
git pull --ff-only

echo "==> Rebuilding and restarting containers..."
cd backend
docker compose up -d --build

echo "==> Pruning dangling images..."
docker image prune -f >/dev/null

echo "==> Done. Current status:"
docker compose ps
