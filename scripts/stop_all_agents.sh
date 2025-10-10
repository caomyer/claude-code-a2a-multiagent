#!/bin/bash
# Stop all agents and clean up

echo "======================================================================"
echo "Stopping All Agents"
echo "======================================================================"
echo ""

# Stop agents from PID files
if [ -d "/tmp/agent_system" ]; then
    echo "Stopping specialist agents..."

    for agent in frontend backend pm ux; do
        pid_file="/tmp/agent_system/${agent}.pid"
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null && echo "  ✓ Stopped $agent agent (PID: $pid)"
                sleep 1
                # Force kill if still running
                if kill -0 "$pid" 2>/dev/null; then
                    kill -9 "$pid" 2>/dev/null && echo "    (forced)"
                fi
            else
                echo "  - $agent agent already stopped"
            fi
        fi
    done
fi

echo ""
echo "Killing tmux sessions..."

for session in claude-frontend claude-backend claude-pm claude-ux; do
    if tmux has-session -t "$session" 2>/dev/null; then
        tmux kill-session -t "$session" 2>/dev/null && echo "  ✓ Killed $session" || echo "  - $session already gone"
    fi
done

echo ""
echo "Cleanup complete!"
echo ""
