#!/bin/bash
# Start all specialist agents in background

set -e

echo "======================================================================"
echo "Starting All Specialist Agents"
echo "======================================================================"
echo ""

# Activate virtual environment
source venv/bin/activate

# Create temp directory for logs and PIDs
mkdir -p /tmp/agent_system
rm -f /tmp/agent_system/*.pid

# Start all 4 specialist agents
echo "Starting agents..."
echo ""

echo "  [1/4] Starting Frontend Agent (port 8001)..."
python -m src.agents.frontend > /tmp/agent_system/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > /tmp/agent_system/frontend.pid
echo "      PID: $FRONTEND_PID"

echo "  [2/4] Starting Backend Agent (port 8002)..."
python -m src.agents.backend > /tmp/agent_system/backend.log 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > /tmp/agent_system/backend.pid
echo "      PID: $BACKEND_PID"

echo "  [3/4] Starting PM Agent (port 8003)..."
python -m src.agents.pm > /tmp/agent_system/pm.log 2>&1 &
PM_PID=$!
echo "$PM_PID" > /tmp/agent_system/pm.pid
echo "      PID: $PM_PID"

echo "  [4/4] Starting UX Agent (port 8004)..."
python -m src.agents.ux > /tmp/agent_system/ux.log 2>&1 &
UX_PID=$!
echo "$UX_PID" > /tmp/agent_system/ux.pid
echo "      PID: $UX_PID"

echo ""
echo "All specialist agents started. Waiting 10 seconds for initialization..."
sleep 10

echo ""
echo "======================================================================"
echo "Verifying Agent Status"
echo "======================================================================"
echo ""

# Check each agent
ALL_OK=true

for agent in frontend backend pm ux; do
    case $agent in
        frontend) port=8001 ;;
        backend) port=8002 ;;
        pm) port=8003 ;;
        ux) port=8004 ;;
    esac

    if curl -s -f "http://localhost:$port/.well-known/agent.json" > /dev/null; then
        echo "  ✓ $agent agent (port $port) - Online"
    else
        echo "  ✗ $agent agent (port $port) - FAILED"
        ALL_OK=false
    fi
done

echo ""

if [ "$ALL_OK" = true ]; then
    echo "======================================================================"
    echo "All Agents Ready!"
    echo "======================================================================"
    echo ""
    echo "Specialist agents are running on ports 8001-8004."
    echo "Logs are in /tmp/agent_system/*.log"
    echo "PIDs are in /tmp/agent_system/*.pid"
    echo ""
    echo "To start the Host Agent:"
    echo "  python -m src.host_agent"
    echo ""
    echo "To stop all agents:"
    echo "  ./scripts/stop_all_agents.sh"
    echo ""
    exit 0
else
    echo "======================================================================"
    echo "Some Agents Failed to Start"
    echo "======================================================================"
    echo ""
    echo "Check logs in /tmp/agent_system/*.log"
    echo ""
    echo "To stop running agents:"
    echo "  ./scripts/stop_all_agents.sh"
    echo ""
    exit 1
fi
