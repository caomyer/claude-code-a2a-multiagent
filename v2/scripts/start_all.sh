#!/bin/bash
# Start all agents for the A2A multi-agent system

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Starting A2A Multi-Agent System${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 not found${NC}"
    exit 1
fi

# Check if required environment variables are set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}Error: ANTHROPIC_API_KEY environment variable not set${NC}"
    exit 1
fi

# Check if claude CLI is available
if ! command -v claude &> /dev/null; then
    echo -e "${YELLOW}Warning: claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code${NC}"
fi

# Create PID directory
mkdir -p pids

# Function to start an agent
start_agent() {
    local agent_name=$1
    local agent_script=$2
    local port=$3

    echo -e "\n${YELLOW}Starting ${agent_name} agent on port ${port}...${NC}"

    # Start agent in background and save PID
    python3 -m "src.agents.${agent_script}" > "logs/${agent_name}.log" 2>&1 &
    local pid=$!
    echo $pid > "pids/${agent_name}.pid"

    echo -e "${GREEN}✓ ${agent_name} agent started (PID: ${pid})${NC}"
}

# Create log directory
mkdir -p logs

# Start specialist agents in background
start_agent "frontend" "frontend_agent" "8001"
start_agent "backend" "backend_agent" "8002"
start_agent "pm" "pm_agent" "8003"
start_agent "ux" "ux_agent" "8004"

# Wait for agents to initialize
echo -e "\n${YELLOW}Waiting for agents to initialize...${NC}"
sleep 3

# Check if agents are running
echo -e "\n${YELLOW}Checking agent health...${NC}"
for port in 8001 8002 8003 8004; do
    if curl -s "http://localhost:${port}/.well-known/agent.json" > /dev/null; then
        echo -e "${GREEN}✓ Agent on port ${port} is ready${NC}"
    else
        echo -e "${YELLOW}⚠ Agent on port ${port} not responding yet${NC}"
    fi
done

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}All specialist agents started!${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "\n${YELLOW}Starting host agent (interactive CLI)...${NC}\n"

# Start host agent in foreground (interactive)
python3 -m src.host_agent.host
