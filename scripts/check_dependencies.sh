#!/bin/bash
# Dependency check script for Claude Code A2A Multi-Agent System

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}Claude Code A2A - Dependency Check${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

# Track if all dependencies are met
ALL_DEPS_OK=true

# Function to check command availability
check_command() {
    local cmd=$1
    local name=$2
    local install_msg=$3

    echo -n "Checking $name... "
    if command -v "$cmd" &> /dev/null; then
        local version=$($cmd --version 2>&1 | head -n1 || echo "unknown")
        echo -e "${GREEN}✓${NC} Found: $version"
        return 0
    else
        echo -e "${RED}✗${NC} Not found"
        echo -e "  ${YELLOW}Install:${NC} $install_msg"
        ALL_DEPS_OK=false
        return 1
    fi
}

# Function to check Python package
check_python_package() {
    local package=$1
    echo -n "Checking Python package '$package'... "
    if python3 -c "import $package" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Installed"
        return 0
    else
        echo -e "${YELLOW}⚠${NC} Not installed (will be installed with pip install -r requirements.txt)"
        return 1
    fi
}

# 1. Check Python
echo -e "\n${BLUE}[1/6] Python${NC}"
check_command "python3" "Python 3" "apt-get install python3 (Linux) or brew install python (macOS)"

# Check Python version
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    REQUIRED_VERSION="3.9"
    if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" = "$REQUIRED_VERSION" ]; then
        echo -e "  ${GREEN}✓${NC} Version $PYTHON_VERSION meets requirement (>= $REQUIRED_VERSION)"
    else
        echo -e "  ${RED}✗${NC} Version $PYTHON_VERSION is too old (need >= $REQUIRED_VERSION)"
        ALL_DEPS_OK=false
    fi
fi

# 2. Check tmux
echo -e "\n${BLUE}[2/6] tmux${NC}"
check_command "tmux" "tmux" "brew install tmux (macOS) or apt-get install tmux (Linux)"

# 3. Check Claude CLI
echo -e "\n${BLUE}[3/6] Claude Code CLI${NC}"
check_command "claude" "Claude Code CLI" "npm install -g @anthropic-ai/claude-code"

# 4. Check Node.js (optional but recommended for npm)
echo -e "\n${BLUE}[4/6] Node.js (optional)${NC}"
check_command "node" "Node.js" "brew install node (macOS) or apt-get install nodejs (Linux)"

# 5. Check environment variables
echo -e "\n${BLUE}[5/6] Environment Variables${NC}"
echo -n "Checking ANTHROPIC_API_KEY... "
if [ -n "$ANTHROPIC_API_KEY" ]; then
    echo -e "${GREEN}✓${NC} Set"
else
    echo -e "${RED}✗${NC} Not set"
    echo -e "  ${YELLOW}Action required:${NC} Set ANTHROPIC_API_KEY in .env file or environment"
    ALL_DEPS_OK=false
fi

# Check if .env file exists
echo -n "Checking .env file... "
if [ -f ".env" ]; then
    echo -e "${GREEN}✓${NC} Found"
else
    echo -e "${YELLOW}⚠${NC} Not found"
    echo -e "  ${YELLOW}Tip:${NC} Copy .env.example to .env and configure it"
    if [ -f ".env.example" ]; then
        echo -e "  ${BLUE}Run:${NC} cp .env.example .env"
    fi
fi

# 6. Check Python packages
echo -e "\n${BLUE}[6/6] Python Packages${NC}"
if [ -f "requirements.txt" ]; then
    check_python_package "anthropic"
    check_python_package "a2a"
    check_python_package "httpx"
    check_python_package "rich"
    check_python_package "dotenv"
    check_python_package "uvicorn"

    echo ""
    echo -e "${BLUE}To install Python packages:${NC}"
    echo -e "  pip install -r requirements.txt"
else
    echo -e "${RED}✗${NC} requirements.txt not found"
    ALL_DEPS_OK=false
fi

# Summary
echo ""
echo -e "${BLUE}======================================${NC}"
if [ "$ALL_DEPS_OK" = true ]; then
    echo -e "${GREEN}✓ All critical dependencies are met!${NC}"
    echo ""
    echo -e "${BLUE}Next steps:${NC}"
    echo -e "  1. Configure .env file with your ANTHROPIC_API_KEY"
    echo -e "  2. Install Python packages: pip install -r requirements.txt"
    echo -e "  3. Start agents: ./scripts/start_all.sh"
    exit 0
else
    echo -e "${RED}✗ Some dependencies are missing${NC}"
    echo ""
    echo -e "${YELLOW}Please install missing dependencies and run this script again.${NC}"
    exit 1
fi
