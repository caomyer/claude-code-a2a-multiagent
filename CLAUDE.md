# Claude Code A2A Multi-Agent System - Design Document

## Executive Summary

This project creates a **terminal-based multi-agent system** using the official **Agent2Agent (A2A) protocol** where each agent is an intelligent coordinator that uses **Claude Code CLI** as its execution toolkit.

We're using the **official Google A2A samples architecture**. If you feel unclear about APIs and implementation details, here are some resources:
1. A2A Protocol Specification lives here on the web for your reference: `https://a2a-protocol.org/dev/specification/`
2. A copy of A2A python package lives here locally for your reference: `~/Documents/projects/a2a-python/src/a2a`
3. Some examples building on top of a2a in local directory at `~/Documents/projects/a2a-samples/samples/python/agents/airbnb_planner_multiagent` which contains one example.

**Core Innovation:** Agents are not just Claude Code wrappers - they are intelligent services with a dual-layer architecture:
- **Intelligence Layer** (Claude API): Analyzes tasks, makes decisions, coordinates with other agents
- **Execution Layer** (Claude Code CLI): Performs autonomous coding work in visible, controllable terminals

**Key Technology:** Using **tmux** to programmatically control interactive Claude Code sessions while keeping them visible in auto-opened terminal windows.

## High-Level Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Agent (Port-Based Service)               │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │      Intelligence Layer (Claude API - Fast)           │ │
│  │                                                        │ │
│  │  • Receives A2A requests                              │ │
│  │  • Analyzes task complexity                           │ │
│  │  • Consults other agents if needed                    │ │
│  │  • Makes execution strategy decisions                 │ │
│  │  • Packages context for execution                     │ │
│  └────────────────────┬──────────────────────────────────┘ │
│                       │                                     │
│                       │ Creates context files               │
│                       ↓                                     │
│  ┌───────────────────────────────────────────────────────┐ │
│  │         Workspace (Shared Knowledge)                  │ │
│  │                                                        │ │
│  │  CONTEXT.md      - Agent role & background            │ │
│  │  SPECS.md        - Requirements from other agents     │ │
│  │  INSTRUCTIONS.md - Detailed execution plan            │ │
│  └────────────────────┬──────────────────────────────────┘ │
│                       │                                     │
│                       │ Sends command via tmux              │
│                       ↓                                     │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  Execution Layer (Claude Code in tmux - Powerful)     │ │
│  │                                                        │ │
│  │  • Runs in visible terminal (auto-opened)             │ │
│  │  • Reads context files for full knowledge             │ │
│  │  • Executes autonomous coding work                    │ │
│  │  • Controlled via tmux send-keys                      │ │
│  │  • User can watch in real-time                        │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Multi-Agent Interaction

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

## Design Principles

### 1. Agents Are Intelligent Coordinators, Not Wrappers

**Problem:** If agents are just "run Claude Code on request," we miss the opportunity for:
- Quick decisions that don't need full Claude Code
- Inter-agent coordination before execution
- Strategic planning and task decomposition
- Cost optimization (API calls vs. full Claude Code sessions)

**Solution:** Dual-layer architecture where agents think before acting.

```python
# Conceptual agent logic
async def execute_task(self, task):
    # Intelligence Layer: Analyze and plan
    analysis = await self.claude_api.analyze(task)
    
    if analysis.needs_clarification:
        # Get info from other agents via A2A
        specs = await self.ask_other_agents(analysis.required_info)
        
    # Package everything for execution
    context = self.build_context_package(task, analysis, specs)
    
    # Execution Layer: Send to Claude Code
    await self.claude_terminal.execute(context)
```

### 2. Claude Code in Visible, Controllable Terminals

**Challenge:** How to programmatically control Claude Code while keeping it visible?

**Solution:** tmux sessions with auto-opened terminal windows

```bash
# Agent starts and creates tmux session
tmux new-session -d -s "claude-frontend" "claude"

# Auto-open terminal window showing the session
osascript -e 'tell app "Terminal" to do script "tmux attach -t claude-frontend"'

# Agent sends commands programmatically
tmux send-keys -t "claude-frontend" "Build login form" Enter

# Agent captures output
tmux capture-pane -t "claude-frontend" -p
```

**Benefits:**
- ✅ User sees Claude Code working in real-time
- ✅ Agent has programmatic control
- ✅ Can debug by watching the terminal
- ✅ Transparent AI behavior

### 3. Context Synchronization via Workspace Files

**Problem:** Intelligence layer (Claude API) gains knowledge that execution layer (Claude Code) doesn't have.

**Solution:** Write context files that Claude Code reads.

```
Workspace Structure:
task-123/
├── CONTEXT.md           # Agent role, background, capabilities
├── SPECS.md             # Requirements from other agents
├── INSTRUCTIONS.md      # What to build, how to build it
└── [generated files]    # Claude Code outputs here
```

**Example Context File:**
```markdown
# CONTEXT.md

## Agent Role
Frontend Engineer specializing in React/TypeScript

## Current Task
Build user authentication login form

## Background
This is part of a larger authentication system. The backend team 
has confirmed the API endpoint is ready at POST /api/auth/login.

## Related Agents
- Backend Agent confirmed JWT token format
- UX Agent provided design specifications (see SPECS.md)

## Capabilities
- React 18 with TypeScript
- Material-UI components
- Form validation with yup
- Jest/React Testing Library
```

### 4. Shared Agent Base with Configuration

**Key Insight:** All specialist agents (Frontend, Backend, PM, UX) have the same structure - only their **role, capabilities, and system prompts** differ.

**Solution:** Create a shared `BaseAgent` that all agents inherit from, with role-specific configuration:

```python
# Base agent (shared logic)
class BaseAgent(AgentExecutor):
    """Shared intelligence + execution logic for all agents"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.claude_api = anthropic.Anthropic(...)
        self.claude_terminal = ClaudeCodeTerminal(
            workspace=config.workspace,
            agent_name=config.name
        )
        self.claude_terminal.start(auto_open_window=True)
    
    async def execute(self, context, event_queue):
        # Same for all agents: analyze → coordinate → package → execute
        pass

# Specialized agents just provide configuration
class FrontendAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentConfig(
            name="frontend",
            role="Frontend Engineer",
            capabilities=["React", "TypeScript", "CSS"],
            system_prompt="You are a frontend specialist...",
            port=8001
        ))

class BackendAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentConfig(
            name="backend",
            role="Backend Engineer",
            capabilities=["Node.js", "Python", "APIs"],
            system_prompt="You are a backend specialist...",
            port=8002
        ))
```

### 5. Auto-Opening Terminal Windows

**User Experience Goal:** When agents start, their Claude Code terminals should open automatically - no manual tmux attach needed.

**Platform-Specific Implementation:**

**macOS:**
```python
# Use AppleScript to open Terminal.app
applescript = f"""
tell application "Terminal"
    activate
    do script "tmux attach -t {session_name}"
    set custom title of window 1 to "Claude Code - {agent_name}"
end tell
"""
subprocess.run(["osascript", "-e", applescript])
```

**Linux:**
```python
# Use gnome-terminal or xterm
subprocess.Popen([
    "gnome-terminal",
    "--title", f"Claude Code - {agent_name}",
    "--", "tmux", "attach", "-t", session_name
])
```

## Project Structure

```
claude-code-a2a/
├── README.md                          # User-facing documentation
├── CLAUDE.md                          # This design document
├── requirements.txt                   # Dependencies
├── .env.example                       # Configuration template
│
├── src/
│   ├── common/
│   │   ├── base_agent.py             # Shared BaseAgent class
│   │   ├── agent_config.py           # AgentConfig dataclass
│   │   ├── claude_terminal.py        # Claude Code controller (shared)
│   │   ├── agent_cards.py            # A2A AgentCard definitions
│   │   └── terminal_utils.py         # Rich terminal output helpers
│   │
│   ├── host_agent/                    # Orchestrator (different structure)
│   │   ├── __main__.py               # Interactive CLI
│   │   └── executor.py               # Delegation logic
│   │
│   └── agents/                        # Specialized agents
│       ├── frontend/
│       │   ├── __main__.py           # Start server with config
│       │   └── config.py             # Frontend-specific config
│       ├── backend/
│       │   ├── __main__.py           # Start server with config
│       │   └── config.py             # Backend-specific config
│       ├── pm/
│       │   ├── __main__.py           # Start server with config
│       │   └── config.py             # PM-specific config
│       └── ux/
│           ├── __main__.py           # Start server with config
│           └── config.py             # UX-specific config
│
├── scripts/
│   ├── start_all.sh                   # Launch all agents
│   ├── stop_all.sh                    # Stop everything
│   └── check_dependencies.sh          # Verify tmux, claude installed
│
├── workspaces/                        # Claude Code workspaces
│   ├── frontend/
│   ├── backend/
│   ├── pm/
│   └── ux/
│
├── logs/                              # Agent logs
└── pids/                              # Process IDs for management
```

## Agent Configuration Examples

```python
# Frontend Agent Config
FRONTEND_CONFIG = AgentConfig(
    name="frontend",
    role="Frontend Engineer",
    port=8001,
    capabilities=[
        "React 18 with TypeScript",
        "Next.js 14",
        "Tailwind CSS / Material-UI",
        "State management (Redux, Zustand)",
        "Form validation",
        "Testing (Jest, React Testing Library)"
    ],
    system_prompt="""You are a Frontend Engineer agent in a multi-agent system.
    
Your expertise:
- Modern React patterns and hooks
- TypeScript for type safety
- Responsive design and accessibility
- Performance optimization
- Component testing

When analyzing tasks:
1. Check if you need UX design specifications
2. Verify backend API contracts
3. Consider accessibility and performance
4. Plan component structure before implementing

Your deliverables should include:
- Clean, typed component code
- Unit tests for components
- README with usage examples
- Accessibility considerations""",
    related_agents=["ux", "backend"]
)

# Backend Agent Config
BACKEND_CONFIG = AgentConfig(
    name="backend",
    role="Backend Engineer",
    port=8002,
    capabilities=[
        "Node.js / Express",
        "Python / FastAPI",
        "REST APIs / GraphQL",
        "Database design (PostgreSQL, MongoDB)",
        "Authentication / Authorization",
        "API documentation"
    ],
    system_prompt="""You are a Backend Engineer agent in a multi-agent system.

Your expertise:
- RESTful API design
- Database schema design
- Authentication and security
- API documentation
- Error handling and validation

When analyzing tasks:
1. Check if you need PM requirements
2. Clarify frontend integration needs
3. Consider security implications
4. Plan database schema if needed

Your deliverables should include:
- Well-structured API endpoints
- Database migrations if needed
- API documentation
- Unit and integration tests
- Security considerations""",
    related_agents=["pm", "frontend"]
)

# PM Agent Config
PM_CONFIG = AgentConfig(
    name="pm",
    role="Product Manager",
    port=8003,
    capabilities=[
        "Requirements analysis",
        "User story creation",
        "Technical specification writing",
        "Scope definition",
        "Stakeholder communication"
    ],
    system_prompt="""You are a Product Manager agent in a multi-agent system.

Your expertise:
- Breaking down complex requests into clear requirements
- Writing user stories and acceptance criteria
- Defining project scope
- Creating technical specifications

When analyzing tasks:
1. Clarify ambiguous requirements
2. Break down into user stories
3. Define acceptance criteria
4. Consider edge cases

Your deliverables should include:
- Clear requirement documents
- User stories with acceptance criteria
- Project scope definition
- Edge cases and considerations""",
    related_agents=["ux", "frontend", "backend"]
)

# UX Agent Config
UX_CONFIG = AgentConfig(
    name="ux",
    role="UX Designer",
    port=8004,
    capabilities=[
        "User interface design",
        "Design systems",
        "Accessibility guidelines",
        "User flow design",
        "Design specifications"
    ],
    system_prompt="""You are a UX Designer agent in a multi-agent system.

Your expertise:
- User interface design principles
- Design system creation
- Accessibility (WCAG guidelines)
- User experience optimization
- Design specifications

When analyzing tasks:
1. Consider user needs and flows
2. Ensure accessibility
3. Define clear design specifications
4. Consider responsive design

Your deliverables should include:
- Design specifications
- Component guidelines
- Accessibility requirements
- User flow descriptions
- Design system recommendations""",
    related_agents=["pm", "frontend"]
)
```

## Implementation Phases

### Phase 1: Foundation (Start Here)

**Goal:** Get basic infrastructure working before adding intelligence.

**Tasks:**
1. **Project Setup**
   - Create project structure
   - Set up requirements.txt with all dependencies
   - Create .env.example with all configuration options
   - Add dependency check script (tmux, claude CLI)

2. **Terminal Utilities**
   - Implement `terminal_utils.py` with TerminalLogger
   - Test colored output and status displays

3. **Claude Terminal Controller**
   - Implement `claude_terminal.py`:
     - `start()` - Create tmux session, start claude
     - `send_command()` - Send via tmux send-keys
     - `capture_output()` - Get terminal output
     - `_open_terminal_window()` - Platform-specific auto-open
   - Test with a simple manual command

**Validation:**
- [ ] Can create tmux session with Claude Code
- [ ] Can send command to Claude via tmux
- [ ] Terminal window auto-opens on macOS/Linux
- [ ] Can capture Claude's output

### Phase 2: Base Agent Architecture

**Goal:** Create shared agent infrastructure that all specialized agents will use.

**Tasks:**
1. **Agent Configuration System**
   - Implement `agent_config.py`:
     - AgentConfig dataclass with name, role, capabilities, system_prompt, port
   - Create config files for each agent (frontend, backend, pm, ux)

2. **Base Agent Class**
   - Implement `base_agent.py`:
     - `__init__()` - Takes AgentConfig, sets up Claude API + Claude Terminal
     - `execute()` - Main execution flow (intelligence → coordination → execution)
     - `_analyze_task()` - Use Claude API with agent's system prompt
     - `_ask_agent()` - Call other agents via A2A
     - `_build_context_package()` - Create CONTEXT.md, SPECS.md, INSTRUCTIONS.md
     - `_send_to_claude()` - Send command to Claude terminal
     - `_collect_results()` - Gather artifacts from workspace

3. **A2A Integration**
   - Implement A2A server setup in each agent's `__main__.py`
   - Use a2a-sdk to create agent servers
   - Test inter-agent communication

**Validation:**
- [ ] BaseAgent can be instantiated with different configs
- [ ] BaseAgent can analyze tasks with Claude API
- [ ] BaseAgent can call other agents via A2A
- [ ] BaseAgent can control Claude terminal

### Phase 3: Specialized Agents

**Goal:** Create all four specialized agents using the base architecture.

**Tasks:**
1. **Implement Each Agent**
   - `frontend/__main__.py` - Start with FRONTEND_CONFIG
   - `backend/__main__.py` - Start with BACKEND_CONFIG
   - `pm/__main__.py` - Start with PM_CONFIG
   - `ux/__main__.py` - Start with UX_CONFIG
   - Each just instantiates BaseAgent with their config

2. **Agent Cards**
   - Implement `agent_cards.py` to generate A2A AgentCard for each agent
   - Include capabilities and contact info in cards

**Validation:**
- [ ] All 4 agents can start independently
- [ ] Each agent's Claude terminal opens automatically
- [ ] Each agent responds to A2A requests on their port
- [ ] Agent cards are accessible at /.well-known/agent.json

### Phase 4: Host Agent (Orchestrator)

**Goal:** Create the orchestrator with interactive CLI.

**Tasks:**
1. **Host Agent Implementation**
   - Implement `host_agent/executor.py`:
     - Receives user requests
     - Analyzes which agents to involve
     - Delegates to appropriate agents via A2A
     - Collects and synthesizes results
   
2. **Interactive CLI**
   - Implement `host_agent/__main__.py`:
     - Start A2A server in background thread
     - Run interactive CLI loop
     - Display results nicely with rich

**Validation:**
- [ ] Can start host agent with interactive CLI
- [ ] Can type requests and get responses
- [ ] Host delegates to correct agents
- [ ] Results are collected and displayed

### Phase 5: Context Synchronization

**Goal:** Ensure intelligence layer knowledge is passed to execution layer.

**Tasks:**
1. **Context File Generation**
   - Enhance `_build_context_package()` in BaseAgent
   - Generate comprehensive CONTEXT.md with:
     - Agent role and capabilities
     - Task background
     - Related agent information
   - Generate SPECS.md with info from other agents
   - Generate INSTRUCTIONS.md with execution plan

2. **Test Context Flow**
   - Verify Claude Code reads and uses context files
   - Adjust format if needed for better Claude understanding

**Validation:**
- [ ] Context files are created before execution
- [ ] Claude Code references context in its work
- [ ] Information from other agents appears in SPECS.md
- [ ] Results reflect understanding of full context

### Phase 6: Startup & Management Scripts

**Goal:** Easy system management.

**Tasks:**
1. **Startup Script**
   - Implement `start_all.sh`:
     - Check dependencies (tmux, claude)
     - Start all 4 specialized agents in background
     - Wait for them to initialize
     - Start host agent in foreground (interactive)

2. **Stop Script**
   - Implement `stop_all.sh`:
     - Kill all agent processes
     - Kill all tmux sessions
     - Clean up PID files

3. **Dependency Check**
   - Implement `check_dependencies.sh`:
     - Verify tmux installed
     - Verify claude CLI installed
     - Verify Python packages
     - Check ANTHROPIC_API_KEY set

**Validation:**
- [ ] `./scripts/start_all.sh` starts entire system
- [ ] All terminals auto-open
- [ ] `./scripts/stop_all.sh` cleans everything up
- [ ] Helpful error messages if dependencies missing

### Phase 7: End-to-End Testing

**Goal:** Verify complete system works with real tasks.

**Tasks:**
1. **Simple Task Test**
   - Task: "Create a hello world React component"
   - Expected: Host → Frontend → Claude creates component
   - Verify: File created, tests included

2. **Multi-Agent Task Test**
   - Task: "Build a login form"
   - Expected: Host → PM → UX → Frontend → Backend coordination
   - Verify: All agents involved, context shared, code generated

3. **Error Handling**
   - Test agent unreachable
   - Test Claude Code error
   - Test invalid request
   - Verify: Graceful error messages

**Validation:**
- [ ] Simple tasks complete successfully
- [ ] Multi-agent coordination works
- [ ] Can watch Claude working in all terminals
- [ ] Errors are handled gracefully
- [ ] Results are returned correctly

### Phase 8: Polish & Documentation

**Goal:** Production-ready system.

**Tasks:**
1. **Logging**
   - Add comprehensive logging to all components
   - Log files in `logs/` directory
   - Different log levels (DEBUG, INFO, ERROR)

2. **Documentation**
   - Complete README.md with:
     - Installation instructions
     - Quick start guide
     - Configuration options
     - Troubleshooting
   - Add inline code comments
   - Add docstrings to all functions

3. **Error Messages**
   - Improve all error messages
   - Add suggestions for common issues
   - Friendly user-facing messages

**Validation:**
- [ ] All code is well-documented
- [ ] README is clear and complete
- [ ] Logs are helpful for debugging
- [ ] Error messages guide users to solutions

## Implementation Guidelines for Each Phase

### Testing Strategy Per Phase

```bash
# Phase 1: Test terminal controller
python -c "
from src.common.claude_terminal import ClaudeCodeTerminal
from pathlib import Path
terminal = ClaudeCodeTerminal(Path('./test_workspace'), 'test')
terminal.start()
terminal.send_command('echo Hello from tmux')
print(terminal.capture_output())
"

# Phase 2: Test base agent
python -c "
from src.common.base_agent import BaseAgent
from src.common.agent_config import AgentConfig
config = AgentConfig(name='test', role='Test', port=9000, ...)
agent = BaseAgent(config)
# Test intelligence layer
# Test execution layer
"

# Phase 3: Test individual agents
python -m src.agents.frontend &
curl http://localhost:8001/.well-known/agent.json

# Phase 4: Test host agent
python -m src.host_agent
> test request

# Phases 5-7: Integration testing
./scripts/start_all.sh
# Run through test scenarios
./scripts/stop_all.sh
```

### Key Decision Points

**Phase 1:**
- Which terminal to auto-open? (Terminal.app on macOS is default, but support iTerm2 too)
- How long to wait for Claude initialization? (3 seconds works well)

**Phase 2:**
- How detailed should system prompts be? (Detailed enough to guide behavior, but not prescriptive)
- What should be in AgentConfig vs. hardcoded? (Anything that differs between agents goes in config)

**Phase 3:**
- Should agents share a single workspace or separate? (Separate for isolation)
- How to name tmux sessions? (claude-{agent_name} for easy identification)

**Phase 5:**
- What format for context files? (Markdown for readability)
- How much context to include? (Err on the side of more - Claude can handle it)

**Phase 7:**
- What constitutes success? (Task completed + artifacts generated + tests pass)
- When to fail vs. retry? (Fail fast on configuration issues, retry on transient errors)

## Complete Task Execution Flow (Reference)

```
User Request: "Build login form with email/password validation"

┌─────────────────────────────────────────────────────────┐
│ 1. HOST AGENT receives request                         │
│    - Analyzes: "Frontend task with validation"         │
│    - Delegates to Frontend Agent via A2A               │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 2. FRONTEND AGENT - Intelligence Phase                 │
│    Uses Claude API with system prompt:                  │
│    {                                                    │
│      "needs_ux_input": true,                           │
│      "needs_backend_api": true,                        │
│      "requirements": ["Email validation",...]          │
│    }                                                   │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 3. COORDINATION Phase                                   │
│    Frontend asks UX Agent via A2A                       │
│    Frontend asks Backend Agent via A2A                  │
│    Collects specifications                              │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 4. CONTEXT PACKAGING Phase                             │
│    Creates in workspace/frontend/task-123/:             │
│    - CONTEXT.md                                         │
│    - SPECS.md (with UX + Backend info)                 │
│    - INSTRUCTIONS.md                                    │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 5. EXECUTION Phase                                      │
│    tmux send-keys -t claude-frontend                    │
│    "Build login form. See CONTEXT.md" Enter             │
│                                                         │
│    [Claude Code in visible terminal]:                   │
│    - Reads context files                                │
│    - Creates components                                 │
│    - Writes tests                                       │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 6. COLLECTION Phase                                     │
│    - Capture terminal output                            │
│    - Collect generated files                            │
│    - Parse test results                                 │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 7. RESPONSE Phase                                       │
│    Return to Host via A2A with artifacts                │
└─────────────────────────────────────────────────────────┘
```

## Technical Requirements

### Dependencies

```txt
# Python packages
a2a-sdk[http-server]>=0.2.3    # Official A2A protocol
anthropic>=0.39.0               # Claude API for intelligence
httpx>=0.27.0                   # HTTP client for A2A calls
rich>=13.7.0                    # Terminal UI
python-dotenv>=1.0.0            # Environment config
pytest>=8.0.0                   # Testing
pytest-asyncio>=0.23.0          # Async testing
```

### System Requirements

```bash
# Required
- Python 3.9+
- tmux (brew install tmux on macOS / apt-get install tmux on Linux)
- Claude Code CLI (npm install -g @anthropic-ai/claude-code)
- ANTHROPIC_API_KEY environment variable

# Optional but recommended
- Terminal.app (macOS) or gnome-terminal (Linux) for auto-opening
```

## Key Design Decisions

### 1. Why tmux Instead of pty?

**Chose tmux because:**
- ✅ Can view terminals easily (`tmux attach`)
- ✅ Sessions persist if agent crashes
- ✅ Better terminal emulation
- ✅ Can manually intervene if needed
- ✅ Standard tool developers already know

### 2. Why Context Files Instead of API Parameters?

**Chose context files because:**
- ✅ No length limits
- ✅ Claude Code can re-read them
- ✅ Visible to user for debugging
- ✅ Can include complex structured data
- ✅ Persist for reference

### 3. Why Shared Base Agent?

**Chose shared base class because:**
- ✅ Reduces code duplication (4 agents share same logic)
- ✅ Easier to maintain and update
- ✅ Consistent behavior across agents
- ✅ Configuration-driven specialization
- ✅ Single point of truth for agent behavior

### 4. Why Auto-Open Terminals?

**Philosophy:** Transparency in AI systems

**Benefits:**
- Users see what Claude Code is doing
- Builds trust in the system
- Easy debugging
- Can manually override if needed
- Educational - watch AI work

## Success Criteria

### MVP Completion Checklist

✅ **Architecture:**
- [ ] BaseAgent class implemented with dual-layer design
- [ ] All 4 specialized agents use BaseAgent with configs
- [ ] Claude Code runs in tmux sessions
- [ ] Context synchronization via workspace files

✅ **Visibility:**
- [ ] Claude Code terminals auto-open on agent start
- [ ] User can watch Claude working in real-time
- [ ] Terminal output is captured for results

✅ **Coordination:**
- [ ] Agents communicate via A2A protocol
- [ ] Frontend can ask UX for design specs
- [ ] Frontend can ask Backend for API details
- [ ] PM can coordinate requirements

✅ **User Experience:**
- [ ] Single command starts entire system (`./scripts/start_all.sh`)
- [ ] Interactive CLI in Host Agent works
- [ ] Clear visual feedback in all terminals
- [ ] Graceful error handling

✅ **Testing:**
- [ ] Can execute simple single-agent tasks
- [ ] Can execute complex multi-agent tasks
- [ ] System recovers from errors gracefully
- [ ] All generated code works

### Example Task Flow

**Input:** User types "Build user authentication system"

**Expected Behavior:**
1. Host Agent receives request
2. Host delegates to PM, UX, Backend, Frontend
3. PM Agent analyzes requirements → Claude Code creates PRD
4. UX Agent designs interface → Claude Code creates specifications
5. Backend Agent builds API → Claude Code implements endpoints
6. Frontend Agent builds UI → Claude Code creates components
7. All work visible in separate terminal windows
8. Results collected and returned to user

**Success Metrics:**
- All agents activate and coordinate
- Context is properly shared
- Claude Code executes in visible terminals
- Working code is generated
- Tests pass
- Documentation is created

---

**Ready for Implementation:** Follow the phases in order. Each phase builds on the previous one. Test thoroughly before moving to the next phase.
