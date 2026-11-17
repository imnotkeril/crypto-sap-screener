#!/usr/bin/env bash
# Publish the backend as a Docker Space. Needs a Hugging Face token with Write access
# (`hf auth login`). Usage: bash deploy/huggingface/deploy.sh [space-name]
set -euo pipefail
SPACE="${1:-crypto-sap-screener-api}"
USER_NAME="$(hf auth whoami | sed -n 's/^user=//p')"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
hf repos create "$USER_NAME/$SPACE" --type space --space-sdk docker --exist-ok
git clone "https://huggingface.co/spaces/$USER_NAME/$SPACE" "$TMP/space"
cp "$ROOT/deploy/huggingface/Dockerfile" "$ROOT/deploy/huggingface/README.md" "$ROOT/requirements.txt" "$TMP/space/"
rm -rf "$TMP/space/backend" && cp -r "$ROOT/backend" "$TMP/space/backend"
rm -rf "$TMP/space/backend/cache" "$TMP/space/backend/data" "$TMP/space/backend/.env" "$TMP/space/backend/tests"
find "$TMP/space" -name __pycache__ -type d -prune -exec rm -rf {} +
cd "$TMP/space" && git add -A && git commit -m "Deploy API" && git push
echo "Set Space variables: CORS_ORIGINS=<your frontend origin>. Then VITE_API_URL=https://$USER_NAME-$SPACE.hf.space in the frontend build."
