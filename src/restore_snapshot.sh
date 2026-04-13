#!/usr/bin/env bash

SNAPSHOT_FILE=$(ls /*snapshot*.json 2>/dev/null | head -n 1)

if [ -z "$SNAPSHOT_FILE" ]; then
    echo "runpod-worker-comfy: No snapshot file found. Exiting..."
    exit 0
fi

echo "runpod-worker-comfy: restoring snapshot: $SNAPSHOT_FILE"

MANAGER_DIR="/comfyui/custom_nodes/ComfyUI-Manager"

# Bootstrap ComfyUI-Manager if not already installed — required for cm-cli to work
if [ ! -d "$MANAGER_DIR" ]; then
    echo "runpod-worker-comfy: Bootstrapping ComfyUI-Manager..."
    git clone https://github.com/ltdrdata/ComfyUI-Manager.git "$MANAGER_DIR"

    # Checkout the exact hash from the snapshot if available
    MANAGER_HASH=$(python3 -c "
import json, sys
try:
    d = json.load(open('$SNAPSHOT_FILE'))
    print(d.get('git_custom_nodes', {}).get('https://github.com/ltdrdata/ComfyUI-Manager.git', {}).get('hash', ''))
except: pass
" 2>/dev/null)

    if [ -n "$MANAGER_HASH" ]; then
        echo "runpod-worker-comfy: Checking out ComfyUI-Manager at $MANAGER_HASH"
        git -C "$MANAGER_DIR" checkout "$MANAGER_HASH" || \
            echo "runpod-worker-comfy: WARNING - Could not checkout $MANAGER_HASH, using latest"
    fi
fi

CM_CLI="$MANAGER_DIR/cm-cli.py"
if [ ! -f "$CM_CLI" ]; then
    echo "runpod-worker-comfy: WARNING - cm-cli.py not found, skipping snapshot restoration"
    exit 0
fi

# Restore custom nodes only — no --pip-* flags to avoid downgrading torch (cu130 required for Blackwell)
echo "runpod-worker-comfy: Restoring custom nodes via cm-cli (pip skipped to preserve torch==2.10.0+cu130)..."
if python3 "$CM_CLI" restore-snapshot "$SNAPSHOT_FILE" 2>&1; then
    echo "runpod-worker-comfy: successfully restored snapshot: $SNAPSHOT_FILE"
else
    EXIT_CODE=$?
    echo "runpod-worker-comfy: WARNING - snapshot restoration failed with exit code $EXIT_CODE"
    echo "runpod-worker-comfy: Continuing with base ComfyUI installation..."
fi
