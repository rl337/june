#!/bin/bash
#
# Review Sandbox Script
# 
# Inspects a sandbox container snapshot to analyze what the agent did
# to solve a benchmark task. Shows file changes, command history, resource usage, etc.
#
# Usage:
#   ./scripts/review_sandbox.sh <sandbox_snapshot_dir>
#   ./scripts/review_sandbox.sh <output_dir> <task_id>
#
# Examples:
#   ./scripts/review_sandbox.sh /tmp/benchmarks/results/sandboxes/humaneval_0_snapshot
#   ./scripts/review_sandbox.sh /tmp/benchmarks/results humaneval_0

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Use the command (preferred)
if command -v poetry &> /dev/null; then
    # Use command for better JSON parsing and formatting
    cd "$PROJECT_ROOT"
    exec poetry run python -m essence review-sandbox "$@"
fi

# Fallback to shell-based review
if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <sandbox_snapshot_dir>"
    echo "   or: $0 <output_dir> <task_id>"
    echo ""
    echo "Examples:"
    echo "  $0 /tmp/benchmarks/results/sandboxes/humaneval_0_snapshot"
    echo "  $0 /tmp/benchmarks/results humaneval_0"
    exit 1
fi

SANDBOX_DIR="$1"
TASK_ID="${2:-}"

# If task_id is provided, treat first arg as output directory
if [[ -n "$TASK_ID" ]]; then
    OUTPUT_DIR="$SANDBOX_DIR"
    # Try to find snapshot in sandboxes subdirectory
    SANDBOX_DIR="$OUTPUT_DIR/sandboxes/${TASK_ID}_snapshot"
    
    # If not found, try in dataset subdirectories
    if [[ ! -d "$SANDBOX_DIR" ]]; then
        for dataset_dir in "$OUTPUT_DIR"/*; do
            if [[ -d "$dataset_dir" ]]; then
                candidate="$dataset_dir/sandboxes/${TASK_ID}_snapshot"
                if [[ -d "$candidate" ]]; then
                    SANDBOX_DIR="$candidate"
                    break
                fi
            fi
        done
    fi
fi

if [[ ! -d "$SANDBOX_DIR" ]]; then
    echo "Error: Sandbox snapshot directory not found: $SANDBOX_DIR"
    exit 1
fi

echo "=========================================="
echo "Sandbox Review: $(basename "$SANDBOX_DIR")"
echo "=========================================="
echo ""

# Find metadata file
METADATA_FILE="$SANDBOX_DIR/sandbox_metadata.json"
if [[ ! -f "$METADATA_FILE" ]]; then
    # Try in parent directory
    METADATA_FILE="$(dirname "$SANDBOX_DIR")/sandbox_metadata.json"
fi

if [[ ! -f "$METADATA_FILE" ]]; then
    echo "Error: Metadata file not found in $SANDBOX_DIR"
    echo "Expected: sandbox_metadata.json"
    exit 1
fi

# Show metadata
echo "=== Metadata ==="
if command -v python3 &> /dev/null; then
    python3 -m json.tool "$METADATA_FILE" 2>/dev/null || cat "$METADATA_FILE"
else
    cat "$METADATA_FILE"
fi
echo ""

# Extract and show command logs from metadata
echo "=== Command Execution Timeline ==="
if command -v python3 &> /dev/null; then
    python3 << 'PYTHON_SCRIPT'
import json
import sys
from datetime import datetime

try:
    with open(sys.argv[1], 'r') as f:
        metadata = json.load(f)
    
    command_logs = metadata.get('command_logs', [])
    print(f"Total commands: {len(command_logs)}\n")
    
    for i, log in enumerate(command_logs, 1):
        timestamp = log.get('timestamp', 0)
        time_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{i}] {time_str}")
        print(f"    Command: {log.get('command', 'N/A')}")
        print(f"    Return Code: {log.get('returncode', 'N/A')}")
        print(f"    Duration: {log.get('duration_seconds', 0):.2f}s")
        stdout = log.get('stdout', '')
        if stdout:
            lines = stdout.split('\n')[:3]
            print(f"    Stdout: {lines[0]}")
            if len(stdout.split('\n')) > 3:
                print(f"      ... ({len(stdout.split('\n')) - 3} more lines)")
        stderr = log.get('stderr', '')
        if stderr:
            print(f"    Stderr: {stderr[:100]}...")
        print()
except Exception as e:
    print(f"Error parsing command logs: {e}")
PYTHON_SCRIPT
    "$METADATA_FILE"
else
    echo "Python3 not available for parsing command logs"
fi
echo ""

# Show file system tree
echo "=== File System Tree ==="
# Look for filesystem.tar
TAR_FILE="$SANDBOX_DIR/filesystem.tar"
if [[ ! -f "$TAR_FILE" ]]; then
    TAR_FILE="$SANDBOX_DIR/snapshots/final/filesystem.tar"
fi

if [[ -f "$TAR_FILE" ]]; then
    echo "Filesystem snapshot: $TAR_FILE"
    if command -v tar &> /dev/null; then
        echo "Files in archive:"
        tar -tzf "$TAR_FILE" 2>/dev/null | head -50
        total=$(tar -tzf "$TAR_FILE" 2>/dev/null | wc -l)
        if [[ $total -gt 50 ]]; then
            echo "... ($((total - 50)) more files)"
        fi
    fi
else
    # List files directly
    if [[ -d "$SANDBOX_DIR" ]]; then
        echo "Files in snapshot directory:"
        find "$SANDBOX_DIR" -type f -not -name "*.tar" | head -50 | while read -r file; do
            rel_path="${file#$SANDBOX_DIR/}"
            size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo "?")
            echo "  $rel_path ($size bytes)"
        done
    fi
fi
echo ""

# Show metrics summary
echo "=== Metrics Summary ==="
if command -v python3 &> /dev/null; then
    python3 << 'PYTHON_SCRIPT'
import json
import sys

try:
    with open(sys.argv[1], 'r') as f:
        metadata = json.load(f)
    
    metrics = metadata.get('metrics', {})
    if metrics:
        print(f"Commands Executed: {metrics.get('commands_executed', 0)}")
        print(f"Files Created: {metrics.get('files_created', 0)}")
        print(f"Files Modified: {metrics.get('files_modified', 0)}")
        if metrics.get('end_time') and metrics.get('start_time'):
            duration = metrics.get('end_time') - metrics.get('start_time')
            print(f"Duration: {duration:.2f}s")
        print(f"Peak Memory: {metrics.get('peak_memory_mb', 0):.2f} MB")
        print(f"Success: {metrics.get('success', False)}")
        if metrics.get('error_message'):
            print(f"Error: {metrics.get('error_message')}")
except Exception as e:
    print(f"Error parsing metrics: {e}")
PYTHON_SCRIPT
    "$METADATA_FILE"
else
    echo "Python3 not available for parsing metrics"
fi
echo ""

echo "=========================================="
echo "Review complete. Sandbox data at: $SANDBOX_DIR"
echo "=========================================="
echo ""
echo "For more detailed analysis, use:"
echo "  poetry run python -m essence review-sandbox \"$SANDBOX_DIR\""


