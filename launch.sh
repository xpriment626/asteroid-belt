#!/usr/bin/env bash
# launch.sh — start the FastAPI backend + SvelteKit dev server side by side.
# Ctrl-C in the terminal where this runs kills both.
#
# Usage: ./launch.sh

set -euo pipefail

# Kill the whole process group (this script + uvicorn + pnpm + their children)
# when the script exits — including via Ctrl-C in the foreground.
trap 'kill 0' EXIT

# Backend — http://127.0.0.1:8000  (auto-reloads on file changes)
uv run uvicorn asteroid_belt.server.app:app --reload &

# Frontend — http://127.0.0.1:5173  (proxies /api → :8000 per vite.config.ts)
cd web && pnpm dev
