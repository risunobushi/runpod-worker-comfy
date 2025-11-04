#!/usr/bin/env bash

set -e

SNAPSHOT_FILE=$(ls /*snapshot*.json 2>/dev/null | head -n 1)

if [ -z "$SNAPSHOT_FILE" ]; then
    echo "runpod-worker-comfy: No snapshot file found. Exiting..."
    exit 0
fi

echo "runpod-worker-comfy: restoring snapshot: $SNAPSHOT_FILE"

# Disable tracking and skip prompts to avoid interactive prompts in Docker builds
comfy --skip-prompt --no-enable-telemetry node restore-snapshot "$SNAPSHOT_FILE" --workspace /comfyui --pip-non-url

echo "runpod-worker-comfy: restored snapshot file: $SNAPSHOT_FILE"