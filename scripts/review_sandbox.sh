#!/bin/bash
#
# Review Sandbox Script
# 
# Inspects a sandbox container snapshot to analyze what the agent did
# to solve a benchmark task. Shows file changes, command history, resource usage, etc.
#
# Usage:
#   ./scripts/review_sandbox.sh <sandbox_id>
#
# The sandbox_id is typically the benchmark task ID or container name.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SANDBOX_ROOT="${JUNE_DATA_DIR:-/home/rlee/june_data}/benchmark_sandboxes"

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <sandbox_id>"
    echo ""
    echo "Available sandboxes:"
    ls -1 "$SANDBOX_ROOT" 2>/dev/null || echo "  No sandboxes found"
    exit 1
fi

SANDBOX_ID="$1"
SANDBOX_DIR="$SANDBOX_ROOT/$SANDBOX_ID"

if [[ ! -d "$SANDBOX_DIR" ]]; then
    echo "Error: Sandbox '$SANDBOX_ID' not found at $SANDBOX_DIR"
    exit 1
fi

echo "=========================================="
echo "Sandbox Review: $SANDBOX_ID"
echo "=========================================="
echo ""

# Show metadata
if [[ -f "$SANDBOX_DIR/metadata.json" ]]; then
    echo "=== Metadata ==="
    cat "$SANDBOX_DIR/metadata.json" | python3 -m json.tool 2>/dev/null || cat "$SANDBOX_DIR/metadata.json"
    echo ""
fi

# Show command execution log
if [[ -f "$SANDBOX_DIR/commands.log" ]]; then
    echo "=== Command Execution Timeline ==="
    cat "$SANDBOX_DIR/commands.log"
    echo ""
    echo "Total commands: $(wc -l < "$SANDBOX_DIR/commands.log")"
    echo ""
fi

# Show file system tree
if [[ -d "$SANDBOX_DIR/filesystem" ]]; then
    echo "=== File System Tree ==="
    tree -L 5 "$SANDBOX_DIR/filesystem" 2>/dev/null || find "$SANDBOX_DIR/filesystem" -type f | head -50
    echo ""
fi

# Show file changes (diffs)
if [[ -d "$SANDBOX_DIR/diffs" ]]; then
    echo "=== File Changes ==="
    for diff_file in "$SANDBOX_DIR/diffs"/*.diff; do
        if [[ -f "$diff_file" ]]; then
            filename=$(basename "$diff_file" .diff)
            echo "--- $filename ---"
            head -30 "$diff_file"
            echo ""
        fi
    done
fi

# Show resource usage
if [[ -f "$SANDBOX_DIR/resources.json" ]]; then
    echo "=== Resource Usage ==="
    cat "$SANDBOX_DIR/resources.json" | python3 -m json.tool 2>/dev/null || cat "$SANDBOX_DIR/resources.json"
    echo ""
fi

# Show process tree
if [[ -f "$SANDBOX_DIR/processes.txt" ]]; then
    echo "=== Process Tree ==="
    cat "$SANDBOX_DIR/processes.txt"
    echo ""
fi

# Show efficiency metrics
if [[ -f "$SANDBOX_DIR/efficiency.json" ]]; then
    echo "=== Efficiency Metrics ==="
    cat "$SANDBOX_DIR/efficiency.json" | python3 -m json.tool 2>/dev/null || cat "$SANDBOX_DIR/efficiency.json"
    echo ""
fi

echo "=========================================="
echo "Review complete. Sandbox data at: $SANDBOX_DIR"
echo "=========================================="

