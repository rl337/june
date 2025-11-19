#!/bin/bash
#
# Agent Monitoring Script
# 
# Monitors the looping agent every 10 minutes to verify it's not stuck.
# If stuck, updates REFACTOR_PLAN.md or the agent prompt to help it get unstuck.
#
# Usage:
#   ./scripts/monitor_agent.sh
#   # Run in background: nohup ./scripts/monitor_agent.sh > /tmp/agent_monitor.log 2>&1 &
#

set -euo pipefail

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REFACTOR_PLAN="$PROJECT_ROOT/REFACTOR_PLAN.md"
AGENT_LOOP_SCRIPT="$PROJECT_ROOT/scripts/refactor_agent_loop.sh"
LOG_FILE="${PROJECT_ROOT}/refactor_agent_loop.log"
MONITOR_LOG="${PROJECT_ROOT}/agent_monitor.log"

# Change to project root
cd "$PROJECT_ROOT"

# Function to log with timestamp
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$MONITOR_LOG"
}

# Function to check if agent is stuck
check_agent_status() {
    local stuck=false
    local reason=""
    
    # Check if agent process is running
    if ! pgrep -f "refactor_agent_loop.sh" > /dev/null; then
        log "WARNING: Agent loop script is not running!"
        return 1
    fi
    
    # Check for recent commits (last 20 minutes)
    local recent_commits=$(git log --oneline --since="20 minutes ago" | wc -l)
    if [ "$recent_commits" -eq 0 ]; then
        stuck=true
        reason="No commits in last 20 minutes"
    fi
    
    # Check for recent log activity (last 10 minutes)
    if [ -f "$LOG_FILE" ]; then
        local recent_log_lines=$(tail -100 "$LOG_FILE" | grep -c "$(date -d '10 minutes ago' '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -v-10M '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "")" || echo "0")
        if [ "$recent_log_lines" -eq 0 ]; then
            # Check if there's any activity in the last 10 minutes by checking timestamps
            local last_log_time=$(tail -1 "$LOG_FILE" | grep -oP '"timestamp_ms":\K[0-9]+' | head -1 || echo "0")
            local current_time=$(date +%s)000
            local time_diff=$((current_time - last_log_time))
            if [ "$time_diff" -gt 600000 ]; then  # 10 minutes in milliseconds
                stuck=true
                reason="${reason:+$reason, }No log activity in last 10 minutes"
            fi
        fi
    else
        stuck=true
        reason="${reason:+$reason, }Log file not found"
    fi
    
    # Check for repeating errors (same error 5+ times in last 20 lines)
    if [ -f "$LOG_FILE" ]; then
        local error_pattern=$(tail -20 "$LOG_FILE" | grep -i "error\|failed\|exception" | sort | uniq -c | sort -rn | head -1 | awk '{print $1}')
        if [ -n "$error_pattern" ] && [ "$error_pattern" -gt 5 ]; then
            stuck=true
            reason="${reason:+$reason, }Repeating errors detected"
        fi
    fi
    
    # Check if agent is in a thinking loop (same pattern repeating)
    if [ -f "$LOG_FILE" ]; then
        local last_50_lines=$(tail -50 "$LOG_FILE")
        local unique_patterns=$(echo "$last_50_lines" | grep -oP '"text":"[^"]{0,50}' | sort | uniq | wc -l)
        if [ "$unique_patterns" -lt 5 ]; then
            stuck=true
            reason="${reason:+$reason, }Agent appears to be in a loop (low pattern diversity)"
        fi
    fi
    
    if [ "$stuck" = true ]; then
        log "AGENT STUCK DETECTED: $reason"
        return 1
    else
        log "Agent is progressing normally"
        return 0
    fi
}

# Function to get current agent activity
get_agent_activity() {
    log "=== Agent Status Check ==="
    
    # Check if agent process is running
    if pgrep -f "refactor_agent_loop.sh" > /dev/null; then
        local pid=$(pgrep -f "refactor_agent_loop.sh" | head -1)
        local runtime=$(ps -p "$pid" -o etime= 2>/dev/null | xargs || echo "unknown")
        log "Agent process running (PID: $pid, Runtime: $runtime)"
    else
        log "WARNING: Agent process not found!"
        return 1
    fi
    
    # Check recent commits
    local recent_commits=$(git log --oneline --since="20 minutes ago" | wc -l)
    log "Recent commits (last 20 min): $recent_commits"
    
    # Check log file size
    if [ -f "$LOG_FILE" ]; then
        local log_size=$(wc -l < "$LOG_FILE")
        log "Log file size: $log_size lines"
        
        # Get last few log entries
        log "Last log entries:"
        tail -3 "$LOG_FILE" | grep -E '"type":"(assistant|error)"' | tail -3 | while IFS= read -r line; do
            log "  $line"
        done || log "  (no recent entries)"
    else
        log "WARNING: Log file not found!"
    fi
    
    # Check what the agent is working on (from REFACTOR_PLAN.md)
    if [ -f "$REFACTOR_PLAN" ]; then
        log "Current focus (from REFACTOR_PLAN.md):"
        grep -A 5 "⏳ IN PROGRESS" "$REFACTOR_PLAN" | head -10 | while IFS= read -r line; do
            log "  $line"
        done || log "  (no in-progress tasks found)"
    fi
}

# Function to help agent get unstuck
help_agent_unstuck() {
    local reason="$1"
    log "Attempting to help agent get unstuck: $reason"
    
    # Read current REFACTOR_PLAN.md
    if [ ! -f "$REFACTOR_PLAN" ]; then
        log "ERROR: REFACTOR_PLAN.md not found!"
        return 1
    fi
    
    # Check what the agent is currently working on
    local current_task=$(grep -A 10 "⏳ IN PROGRESS" "$REFACTOR_PLAN" | head -5 | grep -oP "Task \d+" | head -1 || echo "")
    
    # Add a note to REFACTOR_PLAN.md to help the agent
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local help_note="
## Agent Monitor Alert - $timestamp

**Status:** Agent appears to be stuck: $reason

**Current Task:** $current_task

**Recommendations:**
- If stuck on a specific task, consider breaking it into smaller subtasks
- If encountering errors, check logs and fix the underlying issue
- If no progress is being made, consider moving to a different task
- If blocked by external dependencies, document the blocker and move on

**Action:** Agent should review this alert and either:
1. Continue with current task if progress is being made
2. Break down the task into smaller steps
3. Move to a different task if blocked
4. Ask for help if truly stuck

---
"
    
    # Append to REFACTOR_PLAN.md (before the last line)
    if [ -f "$REFACTOR_PLAN" ]; then
        # Create a backup
        cp "$REFACTOR_PLAN" "${REFACTOR_PLAN}.backup.$(date +%Y%m%d_%H%M%S)"
        
        # Append the help note
        echo "$help_note" >> "$REFACTOR_PLAN"
        log "Added help note to REFACTOR_PLAN.md"
    fi
}

# Main monitoring loop
main() {
    log "Starting agent monitoring (checking every 10 minutes)"
    
    while true; do
        get_agent_activity
        
        if ! check_agent_status; then
            local reason=$(check_agent_status 2>&1 | grep "AGENT STUCK DETECTED" | cut -d: -f2- | xargs || echo "Unknown reason")
            help_agent_unstuck "$reason"
        fi
        
        log "Sleeping for 10 minutes..."
        sleep 600  # 10 minutes
    done
}

# Run main function
main

