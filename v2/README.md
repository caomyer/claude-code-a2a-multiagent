# Claude Code A2A Multi-Agent System (V2)

A **minimal** multi-agent system where specialist agents use Claude Code headless mode to collaborate on software development tasks via the A2A protocol.

## Key Features

- **76% less code than V1** (~470 lines vs 2000+)
- **Uses A2A protocol** for agent communication (no reinventing the wheel)
- **Claude Code headless mode** for autonomous execution
- **4 specialist agents**: Frontend, Backend, PM, UX
- **Interactive CLI** for natural language task delegation

## Architecture

```
User → Host Agent → [Frontend | Backend | PM | UX] → Claude Code Headless
                            ↓
                     A2A Protocol (TaskManager, EventQueue, A2AClient)
```

### What We Build (~470 lines)

1. **ClaudeCodeExecutor** (50 lines) - Translates A2A events ↔ Claude Code JSON
2. **AgentConfig** (150 lines) - Agent definitions and system prompts
3. **Agent Servers** (120 lines) - 4 agents × 30 lines each
4. **HostAgent** (150 lines) - Orchestrator with Claude API for task analysis

### What A2A Provides (We Don't Rebuild)

- TaskManager - Task lifecycle management
- EventQueue - Event streaming
- A2AClient - Agent-to-agent communication
- A2AServer - HTTP server for A2A protocol
- Task/Message data structures

## Prerequisites

### Required

- **Python 3.9+**
- **Claude Code CLI**: `npm install -g @anthropic-ai/claude-code`
- **ANTHROPIC_API_KEY**: Set as environment variable

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Quick Start

### 1. Set API Key

```bash
export ANTHROPIC_API_KEY="your-api-key"
```

### 2. Start All Agents

```bash
./scripts/start_all.sh
```

This will:
- Start 4 specialist agents on ports 8001-8004
- Launch the interactive host agent CLI

### 3. Try a Request

```
You: Build a React login form with email validation

🤔 Analyzing request...
✓ Analysis: frontend (primary)
  + Supporting: ux

📤 Delegating to frontend...
🔧 Frontend Engineer is working...
✓ frontend completed

📤 Consulting ux...
🔧 UX Designer is working...
✓ ux completed

============================================================
MULTI-AGENT COLLABORATION RESULTS
============================================================

FRONTEND AGENT:
----------------------------------------
[Login form implementation with validation]

UX AGENT:
----------------------------------------
[Design specifications and accessibility guidelines]

============================================================
```

### 4. Stop All Agents

```bash
./scripts/stop_all.sh
```

Or press `Ctrl+C` in the host agent terminal, then run stop script.

## Project Structure

```
v2/
├── src/
│   ├── agents/
│   │   ├── config.py              # Agent configurations
│   │   ├── executor.py            # ClaudeCodeExecutor
│   │   ├── frontend_agent.py      # Frontend agent server
│   │   ├── backend_agent.py       # Backend agent server
│   │   ├── pm_agent.py            # PM agent server
│   │   └── ux_agent.py            # UX agent server
│   │
│   └── host_agent/
│       └── host.py                # Orchestrator + CLI
│
├── scripts/
│   ├── start_all.sh               # Start all agents
│   └── stop_all.sh                # Stop all agents
│
├── workspaces/                    # Claude Code working directories
│   ├── frontend/
│   ├── backend/
│   ├── pm/
│   └── ux/
│
├── logs/                          # Agent logs
├── pids/                          # Process IDs
├── requirements.txt
└── README.md
```

## Agent Capabilities

### Frontend Agent (Port 8001)
- React 18 with TypeScript
- Next.js 14
- Tailwind CSS
- Component testing
- Responsive design

### Backend Agent (Port 8002)
- REST APIs (FastAPI/Express)
- Database design (PostgreSQL)
- Authentication & authorization
- API documentation
- Testing

### PM Agent (Port 8003)
- Requirements analysis
- User story creation
- Technical specifications
- Scope definition

### UX Agent (Port 8004)
- UI/UX design
- Design systems
- Accessibility (WCAG)
- User flows

## How It Works

### 1. Request Analysis

The host agent uses Claude API to analyze your request and determine which agents should be involved:

```python
{
  "primary_agent": "frontend",
  "supporting_agents": ["ux", "backend"],
  "coordination_needed": true
}
```

### 2. Task Delegation

Host delegates to each agent via A2A protocol:

```python
await client.send_message(
    SendMessageRequest(
        message=Message(role="user", parts=[TextPart(text=task)]),
        contextId=shared_context_id,
    )
)
```

### 3. Claude Code Execution

Each agent's executor calls Claude Code headless mode:

```bash
cd ./workspaces/frontend
claude -p "You are a Frontend Engineer... [task details]" \
  --output-format json
```

### 4. Result Collection

Results flow back through A2A events:

```python
TaskArtifactUpdateEvent(artifact=result)
TaskStatusUpdateEvent(state=completed, final=True)
```

### 5. Response Synthesis

Host collects all results and formats them for the user.

## Development

### Adding a New Agent

1. **Create config** in `src/agents/config.py`:

```python
NEW_AGENT_CONFIG = AgentConfig(
    name="new_agent",
    role="New Agent Role",
    port=8005,
    description="What this agent does",
    capabilities=["capability1", "capability2"],
    system_prompt="Detailed instructions...",
    workspace=Path("./workspaces/new_agent"),
)
```

2. **Create agent server** in `src/agents/new_agent.py`:

```python
from .config import NEW_AGENT_CONFIG
# ... (follow pattern from other agents)
```

3. **Update host agent** in `src/host_agent/host.py`:

```python
agent_registry = {
    # ... existing agents
    'new_agent': 'http://localhost:8005',
}
```

4. **Update start/stop scripts** to include the new agent.

### Running Individual Agents

```bash
# Start just the frontend agent
python3 -m src.agents.frontend_agent

# Check agent card
curl http://localhost:8001/.well-known/agent.json
```

## Troubleshooting

### Agents Not Starting

Check logs:
```bash
tail -f logs/frontend.log
```

### Claude Code Issues

Verify installation:
```bash
claude --version
```

### Port Already in Use

Check what's using the port:
```bash
lsof -i :8001
```

Kill the process:
```bash
kill $(lsof -ti:8001)
```

### API Key Issues

Verify it's set:
```bash
echo $ANTHROPIC_API_KEY
```

## Comparison with V1

| Aspect | V1 | V2 |
|--------|----|----|
| **Code Size** | 2000+ lines | ~470 lines (76% reduction) |
| **Task Management** | Custom implementation | A2A TaskManager |
| **Agent Communication** | Custom AgentCommunicator | A2A Client/Server |
| **Event Streaming** | File-based coordination | A2A EventQueue |
| **Claude Integration** | tmux + MCP | Headless mode |
| **Complexity** | High | Minimal |

## License

MIT

## Contributing

This is a demo/reference implementation. Feel free to fork and adapt!

## Resources

- [A2A Protocol Specification](https://a2a-protocol.org/dev/specification/)
- [A2A Python SDK](https://github.com/google/a2a-python)
- [Claude Code Documentation](https://docs.claude.com/en/docs/claude-code/headless)
