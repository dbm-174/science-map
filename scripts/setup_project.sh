#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)/app"
mkdir -p "$ROOT/backend/api" \
  "$ROOT/backend/pipeline" \
  "$ROOT/backend/data/raw" \
  "$ROOT/backend/data/interim" \
  "$ROOT/backend/data/processed" \
  "$ROOT/backend/data/cache" \
  "$ROOT/frontend"

# .env example
cat >"$ROOT/.env.example" <<'EOF'
NOMINATIM_EMAIL=you@example.org
HOST=127.0.0.1
PORT=8000
EOF

# README placeholder
cat >"$ROOT/README.md" <<'EOF'
Siehe Projekt-Root README.md
EOF

echo "Projektstruktur erstellt unter $ROOT"
echo "Lege deine gepris_persons.json in app/backend/data/raw/ ab."
