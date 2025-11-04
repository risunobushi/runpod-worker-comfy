#!/usr/bin/env bash

SNAPSHOT_FILE=$(ls /*snapshot*.json 2>/dev/null | head -n 1)

if [ -z "$SNAPSHOT_FILE" ]; then
    echo "runpod-worker-comfy: No snapshot file found. Exiting..."
    exit 0
fi

echo "runpod-worker-comfy: restoring snapshot: $SNAPSHOT_FILE"

# Use --skip-prompt to avoid interactive tracking prompt in Docker builds
# If restoration fails, log the error but don't fail the build
if comfy --skip-prompt --no-enable-telemetry node restore-snapshot "$SNAPSHOT_FILE" --pip-non-url 2>&1; then
    echo "runpod-worker-comfy: successfully restored snapshot file: $SNAPSHOT_FILE"
else
    EXIT_CODE=$?
    echo "runpod-worker-comfy: WARNING - snapshot restoration failed with exit code $EXIT_CODE"
    echo "runpod-worker-comfy: This may indicate the snapshot is incompatible with the current installation path"
    echo "runpod-worker-comfy: Continuing with base ComfyUI installation..."
    exit 0
fi