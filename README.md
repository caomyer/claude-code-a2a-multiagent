# Claude Code A2A Multi-Agent System

A terminal-based multi-agent system using the Agent-to-Agent (A2A) protocol where each agent combines intelligent coordination (Claude API) with autonomous execution (Claude Code CLI in visible tmux terminals).

## Project Status

**Current Phase:** Phase 1 - Foundation ✅ COMPLETED

**Progress:** 20% complete (Phase 1 of 8)

See [PROGRESS.md](PROGRESS.md) for detailed status and how to resume work.

## Core Innovation

Agents have a **dual-layer architecture**:
- **Intelligence Layer** (Claude API): Analyzes tasks, coordinates with other agents, makes decisions
- **Execution Layer** (Claude Code CLI): Does actual coding work in visible, controllable terminals

**Key Technology:** Using **tmux** to programmatically control Claude Code while keeping it visible in auto-opened terminal windows.

## Project Structure

```
agents_v2/
├── README.md                 # This file
├── CLAUDE.md                 # Complete design document (8 phases)
├── A2A_LEARNING.md          # A2A protocol implementation guide
├── PROGRESS.md              # Current status & how to resume
├── requirements.txt         # Python dependencies
├── .env.example             # Configuration template
│
├── src/
│   ├── common/              # Shared utilities
│   │   ├── terminal_utils.py      # Rich terminal logger
│   │   └── claude_terminal.py     # tmux controller for Claude Code
│   ├── agents/              # Specialized agents (frontend, backend, pm, ux)
│   └── host_agent/          # Orchestrator
│
├── scripts/
│   └── check_dependencies.sh      # Dependency validation
│
├── workspaces/              # Claude Code workspaces per agent
├── logs/                    # Agent logs
├── pids/                    # Process IDs
└── venv/                    # Python virtual environment
```

## Quick Start

### Prerequisites

- Python 3.9+
- tmux (`brew install tmux` on macOS)
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- Anthropic API key

### Setup

```bash
# Clone/navigate to project
cd /Users/mingyucao_1/Documents/projects/agents_v2

# Create virtual environment (if not exists)
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Check all dependencies
./scripts/check_dependencies.sh

# Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### Test the Foundation

```bash
# Test the terminal controller
python test_terminal_controller.py

# Should see:
# ✅ All tests passed
# Claude Code running in tmux session
```

## Architecture Overview

### System Components

```
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│ Frontend     │◄──────►│   Backend    │◄──────►│      PM      │
│ Agent :8001  │  A2A   │ Agent :8002  │  A2A   │ Agent :8003  │
│              │        │              │        │              │
│ Intelligence │        │ Intelligence │        │ Intelligence │
│      ↕       │        │      ↕       │        │      ↕       │
│   Claude     │        │   Claude     │        │   Claude     │
│   (tmux)     │        │   (tmux)     │        │   (tmux)     │
└──────────────┘        └──────────────┘        └──────────────┘
       ↕                                                ↑
       │ A2A                                           │ A2A
       ↓                                               │
┌──────────────┐                              ┌──────────────┐
│      UX      │                              │     Host     │
│ Agent :8004  │                              │ Agent :8000  │
│              │                              │ (Orchestr.)  │
│ Intelligence │                              │              │
│      ↕       │                              │ Interactive  │
│   Claude     │                              │     CLI      │
│   (tmux)     │                              └──────────────┘
└──────────────┘
```

### Agent Dual-Layer Design

Each specialist agent:
1. **Receives A2A request** from host or other agents
2. **Intelligence Layer** (Claude API) analyzes the task
3. **Coordinates** with other agents if needed (via A2A)
4. **Creates context files** (CONTEXT.md, SPECS.md, INSTRUCTIONS.md)
5. **Execution Layer** (Claude Code in tmux) does the work
6. **Collects results** and returns via A2A

## Key Features

✅ **Phase 1 Complete:**
- Programmatic tmux control for Claude Code
- Auto-opening terminal windows (macOS/Linux)
- Rich terminal logging and status displays
- Workspace file management
- Clean session lifecycle

🚧 **Phase 2-8 In Progress:**
- Base agent architecture with dual layers
- A2A protocol integration
- Four specialized agents (Frontend, Backend, PM, UX)
- Host agent orchestrator
- Context synchronization
- Management scripts
- End-to-end testing

## Documentation

- **[CLAUDE.md](CLAUDE.md)** - Complete design document with all 8 implementation phases
- **[A2A_LEARNING.md](A2A_LEARNING.md)** - A2A protocol learnings from reference implementation
- **[PROGRESS.md](PROGRESS.md)** - Current status, what's done, what's next, how to resume

## Reference Implementation

We're adapting the official Google A2A samples architecture:
```
~/Documents/projects/a2a-samples/samples/python/agents/airbnb_planner_multiagent
```

**Key Adaptations:**
- Replace Google ADK → Anthropic Claude API
- Replace MCP tools → Claude Code CLI (tmux)
- Keep A2A protocol layer identical

## Development Workflow

### Current Phase (Phase 1) - Complete ✅

```bash
# Test terminal controller
python test_terminal_controller.py

# View tmux sessions
tmux ls

# Manually attach to test session
tmux attach -t claude-test
```

### Next Phase (Phase 2) - Ready to Start

```bash
# Will implement:
# - src/common/agent_config.py
# - src/common/base_agent.py
# - src/agents/{frontend,backend,pm,ux}/config.py
# - A2A integration
```

See [PROGRESS.md](PROGRESS.md) for detailed Phase 2 tasks.

## Technology Stack

**Core:**
- Python 3.13
- Anthropic Claude API (claude-sonnet-4-5)
- Claude Code CLI v2.0.13
- tmux 3.5a

**Libraries:**
- `a2a-sdk>=0.3.0` - Official A2A protocol
- `anthropic>=0.39.0` - Claude API client
- `httpx>=0.27.0` - Async HTTP for A2A calls
- `rich>=13.7.0` - Terminal UI
- `uvicorn>=0.30.0` - ASGI server for A2A agents

**Platform:**
- macOS (Darwin 24.6.0) - primary development
- Linux - supported via terminal emulator detection

## Testing

```bash
# Run dependency checks
./scripts/check_dependencies.sh

# Test terminal controller
python test_terminal_controller.py

# (Phase 2+) Test individual agents
python -m src.agents.frontend

# (Phase 2+) Test full system
./scripts/start_all.sh
```

## Troubleshooting

### tmux session not found
```bash
# List sessions
tmux ls

# Kill all sessions
tmux kill-server

# Restart test
python test_terminal_controller.py
```

### Claude Code not in PATH
```bash
# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Or set custom path in .env
CLAUDE_CLI_PATH=/path/to/claude
```

### ANTHROPIC_API_KEY not set
```bash
# Edit .env file
cp .env.example .env
# Add: ANTHROPIC_API_KEY=sk-ant-...
```

### Python packages missing
```bash
# Activate venv
source venv/bin/activate

# Reinstall
pip install -r requirements.txt
```

## Contributing

This is currently a development project. See [PROGRESS.md](PROGRESS.md) for current status.

## Implementation Phases

1. ✅ **Phase 1: Foundation** - Terminal controller, utilities, dependencies
2. 🔲 **Phase 2: Base Agent Architecture** - AgentConfig, BaseAgent, A2A integration
3. 🔲 **Phase 3: Specialized Agents** - Frontend, Backend, PM, UX agents
4. 🔲 **Phase 4: Host Agent** - Orchestrator with interactive CLI
5. 🔲 **Phase 5: Context Synchronization** - Intelligence → Execution layer
6. 🔲 **Phase 6: Startup Scripts** - Management and deployment
7. 🔲 **Phase 7: End-to-End Testing** - Real multi-agent tasks
8. 🔲 **Phase 8: Polish & Documentation** - Production ready

**Current Progress:** 1/8 phases complete (~20%)

## License

[TBD]

## References

- [A2A Protocol](https://github.com/google/a2a-python)
- [Anthropic Claude API](https://docs.anthropic.com/)
- [Claude Code CLI](https://docs.claude.com/en/docs/claude-code)
- [A2A Codelab](https://codelabs.developers.google.com/intro-a2a-purchasing-concierge)

---

**Last Updated:** 2025-10-10
**Status:** Phase 1 Complete - Ready for Phase 2
