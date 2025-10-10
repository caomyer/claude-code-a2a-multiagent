#!/bin/bash
# Test script for all 4 agents running simultaneously

set -e

echo "======================================================================"
echo "Testing All 4 Agents Simultaneously"
echo "======================================================================"
echo ""

# Activate virtual environment
source venv/bin/activate

# Create temp directory for logs
mkdir -p /tmp/agent_tests

# Start all 4 agents
echo "Starting all agents..."
echo ""

echo "  [1/4] Starting Frontend Agent (port 8001)..."
python -m src.agents.frontend > /tmp/agent_tests/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "      PID: $FRONTEND_PID"

echo "  [2/4] Starting Backend Agent (port 8002)..."
python -m src.agents.backend > /tmp/agent_tests/backend.log 2>&1 &
BACKEND_PID=$!
echo "      PID: $BACKEND_PID"

echo "  [3/4] Starting PM Agent (port 8003)..."
python -m src.agents.pm > /tmp/agent_tests/pm.log 2>&1 &
PM_PID=$!
echo "      PID: $PM_PID"

echo "  [4/4] Starting UX Agent (port 8004)..."
python -m src.agents.ux > /tmp/agent_tests/ux.log 2>&1 &
UX_PID=$!
echo "      PID: $UX_PID"

# Save PIDs
echo "$FRONTEND_PID" > /tmp/agent_tests/pids.txt
echo "$BACKEND_PID" >> /tmp/agent_tests/pids.txt
echo "$PM_PID" >> /tmp/agent_tests/pids.txt
echo "$UX_PID" >> /tmp/agent_tests/pids.txt

echo ""
echo "All agents started. Waiting 10 seconds for initialization..."
sleep 10

echo ""
echo "======================================================================"
echo "Testing AgentCard Endpoints"
echo "======================================================================"
echo ""

# Test function
test_agent() {
    local name=$1
    local port=$2
    local url="http://localhost:$port/.well-known/agent.json"

    echo "Testing $name Agent (port $port)..."

    if curl -s -f "$url" > /tmp/agent_tests/${name}_card.json; then
        local agent_name=$(cat /tmp/agent_tests/${name}_card.json | python -c "import sys, json; print(json.load(sys.stdin)['name'])")
        local skills_count=$(cat /tmp/agent_tests/${name}_card.json | python -c "import sys, json; print(len(json.load(sys.stdin)['skills']))")
        echo "  ✓ $name AgentCard accessible"
        echo "    - Name: $agent_name"
        echo "    - Skills: $skills_count"
        echo ""
        return 0
    else
        echo "  ✗ $name AgentCard FAILED"
        echo ""
        return 1
    fi
}

# Test all agents
PASS_COUNT=0
test_agent "Frontend" 8001 && ((PASS_COUNT++)) || true
test_agent "Backend" 8002 && ((PASS_COUNT++)) || true
test_agent "PM" 8003 && ((PASS_COUNT++)) || true
test_agent "UX" 8004 && ((PASS_COUNT++)) || true

echo "======================================================================"
echo "Test Results"
echo "======================================================================"
echo ""
echo "Agents passed: $PASS_COUNT/4"
echo ""

# Show tmux sessions
echo "======================================================================"
echo "Active tmux Sessions"
echo "======================================================================"
echo ""
tmux list-sessions 2>/dev/null || echo "No tmux sessions found"
echo ""

# Cleanup
echo "======================================================================"
echo "Cleanup"
echo "======================================================================"
echo ""

echo "Stopping all agents..."
while read pid; do
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null && echo "  ✓ Stopped agent (PID: $pid)"
    fi
done < /tmp/agent_tests/pids.txt

sleep 2

echo ""
echo "Killing tmux sessions..."
tmux kill-session -t claude-frontend 2>/dev/null && echo "  ✓ Killed claude-frontend" || echo "  - claude-frontend already gone"
tmux kill-session -t claude-backend 2>/dev/null && echo "  ✓ Killed claude-backend" || echo "  - claude-backend already gone"
tmux kill-session -t claude-pm 2>/dev/null && echo "  ✓ Killed claude-pm" || echo "  - claude-pm already gone"
tmux kill-session -t claude-ux 2>/dev/null && echo "  ✓ Killed claude-ux" || echo "  - claude-ux already gone"

echo ""
echo "======================================================================"
echo "Test Complete"
echo "======================================================================"
echo ""

if [ "$PASS_COUNT" -eq 4 ]; then
    echo "✓ All 4 agents passed! 🎉"
    echo ""
    exit 0
else
    echo "✗ Some agents failed ($((4 - PASS_COUNT))/4 failed)"
    echo ""
    echo "Check logs in /tmp/agent_tests/"
    exit 1
fi
