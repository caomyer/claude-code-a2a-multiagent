#!/bin/bash
# Stop all agents for the A2A multi-agent system

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Stopping A2A Multi-Agent System${NC}"
echo -e "${YELLOW}========================================${NC}"

# Function to stop an agent
stop_agent() {
    local agent_name=$1
    local pid_file="pids/${agent_name}.pid"

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        echo -e "\n${YELLOW}Stopping ${agent_name} agent (PID: ${pid})...${NC}"

        if kill -0 $pid 2>/dev/null; then
            kill $pid
            echo -e "${GREEN}✓ ${agent_name} agent stopped${NC}"
        else
            echo -e "${YELLOW}⚠ ${agent_name} agent not running${NC}"
        fi

        rm "$pid_file"
    else
        echo -e "${YELLOW}⚠ No PID file for ${agent_name}${NC}"
    fi
}

# Stop all specialist agents
stop_agent "frontend"
stop_agent "backend"
stop_agent "pm"
stop_agent "ux"

# Clean up PID directory if empty
if [ -d "pids" ] && [ -z "$(ls -A pids)" ]; then
    rmdir pids
    echo -e "\n${GREEN}✓ Cleaned up PID directory${NC}"
fi

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}All agents stopped!${NC}"
echo -e "${GREEN}========================================${NC}\n"
