# Claude Code A2A Multi-Agent System - V2 Design Document

## Executive Summary

**Philosophy:** Build the minimal glue code needed to connect Claude Code with A2A protocol. Let A2A handle agent communication, task management, and event streaming. Our only job is to translate between A2A's event model and Claude Code's capabilities.

**Core Principle:** **DON'T REINVENT THE WHEEL**
- ✅ Use A2A's built-in `TaskManager`, `EventQueue`, `TaskStore`
- ✅ Use A2A's `A2AClient` for agent-to-agent communication
- ✅ Use A2A's event types: `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`
- ✅ Use Claude Code headless mode for code execution (`claude -p '...' --output-format json`)
- ❌ Don't build custom task queues, agent communicators, or file-based coordination

**Code Budget:** ~470 lines total (vs. 2000+ in V1) - **76% reduction**

---

## What A2A Provides (DON'T REBUILD THESE)

### 1. TaskManager
**What it does:** Manages task lifecycle, persistence, and retrieval

**Interface (from a2a-python):**
```python
class TaskManager:
    def __init__(self, task_store: TaskStore):
        """Initializes with a task store (memory or disk-based)."""

    async def create_task(
        self,
        message: Message,
        context_id: str | None = None,
    ) -> Task:
        """Creates a new task from a message."""

    async def get_task(self, task_id: str) -> Task | None:
        """Retrieves a task by ID."""

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
    ) -> Task:
        """Updates task status."""

    async def add_artifact(
        self,
        task_id: str,
        artifact: Artifact,
    ) -> Task:
        """Adds an artifact to a task."""
```

**Data Structures:**
```python
@dataclass
class Task:
    id: str                          # Unique task ID
    context_id: str                  # Shared context across related tasks
    status: TaskStatus               # Current state
    artifacts: list[Artifact]        # Results produced
    history: list[Message]           # Full conversation history
    created_at: datetime
    updated_at: datetime

@dataclass
class TaskStatus:
    state: TaskState                 # working | completed | failed | cancelled
    message: Message | None          # Optional status message

class TaskState(str, Enum):
    working = "working"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
```

**V2 Decision:** ✅ **Use as-is. Never touch task persistence or lifecycle management.**

---

### 2. EventQueue
**What it does:** Streams task updates to clients in real-time

**Interface:**
```python
class EventQueue:
    async def enqueue_event(self, event: Event) -> None:
        """Send an event to all listeners."""

    async def subscribe(self, filter: EventFilter | None = None) -> AsyncIterator[Event]:
        """Subscribe to events matching filter."""
```

**Event Types We'll Use:**
```python
@dataclass
class TaskStatusUpdateEvent:
    """Sent when task status changes (thinking, working, completed)."""
    task_id: str
    context_id: str
    status: TaskStatus
    final: bool                      # True if this is the final update

@dataclass
class TaskArtifactUpdateEvent:
    """Sent when task produces an artifact (code, result, etc.)."""
    task_id: str
    context_id: str
    artifact: Artifact               # The produced artifact
```

**V2 Decision:** ✅ **Use as-is. Just call `enqueue_event()` to stream updates.**

---

### 3. A2AClient
**What it does:** Handles agent-to-agent communication

**Interface:**
```python
class A2AClient:
    def __init__(self, http_client: httpx.AsyncClient, agent_url: str):
        """Initialize client for a specific agent."""

    async def get_agent_card(self) -> AgentCard:
        """Fetch agent capabilities and metadata."""

    async def send_message(
        self,
        message_request: SendMessageRequest,
    ) -> SendMessageResponse:
        """Send a message to the agent and get task response."""
```

**Request/Response Types:**
```python
@dataclass
class SendMessageRequest:
    id: str                          # Request ID
    params: MessageSendParams        # Contains the actual message

@dataclass
class MessageSendParams:
    message: Message                 # The message to send

@dataclass
class Message:
    role: str                        # "user" | "agent"
    parts: list[Part]                # Message content (text, code, etc.)
    messageId: str                   # Unique message ID
    taskId: str | None = None        # If part of an existing task
    contextId: str | None = None     # If part of a shared context

@dataclass
class SendMessageResponse:
    result: MessageSendResult

@dataclass
class MessageSendResult:
    task: Task                       # The created/updated task
```

**V2 Decision:** ✅ **Use A2AClient directly. No custom AgentCommunicator.**

---

### 4. AgentExecutor (Provided by A2A - We Extend It)
**What it does:** Abstract base class from A2A that we extend with our custom executor

**Interface (from a2a-python):**
```python
from a2a.server import AgentExecutor  # ← Imported from A2A

class AgentExecutor(ABC):
    """Base class for executing agent tasks - PROVIDED BY A2A."""

    @abstractmethod
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Execute a task and stream events.

        Args:
            context: Contains message, task, and history
            event_queue: Where to send status/artifact events
        """
        pass
```

**RequestContext Data Structure (from A2A):**
```python
@dataclass
class RequestContext:
    message: Message                 # The incoming message
    current_task: Task | None        # Existing task (if continuing)

    def get_user_input(self) -> str:
        """Extract text from message parts."""

    def get_task_history(self) -> list[Message]:
        """Get full conversation history."""
```

**V2 Decision:** ✅ **AgentExecutor is from A2A. We just EXTEND it with our ClaudeCodeExecutor implementation.**

---

## What We Need to Build (V2 Components)

### Component 1: ClaudeCodeExecutor (per agent type)

**Purpose:** Thin wrapper that invokes Claude Code headless mode and converts JSON output to A2A events.

**File:** `src/agents/executor.py` (shared by all agent types)

**Interface:**
```python
class ClaudeCodeExecutor(AgentExecutor):
    """Executes coding tasks using Claude Code headless mode."""

    def __init__(
        self,
        workspace: Path,
        agent_role: str,
        system_prompt: str,
    ):
        """
        Initialize executor.

        Args:
            workspace: Working directory for Claude Code
            agent_role: "Frontend Engineer" | "Backend Engineer" | etc.
            system_prompt: Role-specific instructions for Claude Code
        """
        self.workspace = workspace
        self.agent_role = agent_role
        self.system_prompt = system_prompt

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Execute coding task and stream events.

        Implementation:
        1. Get task or create new one
        2. Build instruction for Claude Code
        3. Call Claude Code headless: `claude -p 'instruction' --output-format json`
        4. Parse JSON output
        5. Send artifact/completion events
        """
```

**Implementation (~50 lines):**
```python
import asyncio
import json
from pathlib import Path
from a2a.server import AgentExecutor, RequestContext, EventQueue
from a2a.types import (
    Task, TaskStatus, TaskState, TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent, new_task, new_agent_text_message,
    new_text_artifact,
)


class ClaudeCodeExecutor(AgentExecutor):
    """Executes coding tasks using Claude Code headless mode."""

    def __init__(self, workspace: Path, agent_role: str, system_prompt: str):
        self.workspace = workspace
        self.agent_role = agent_role
        self.system_prompt = system_prompt

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute coding task with Claude Code headless mode."""

        # 1. Get or create task
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        # 2. Build instruction
        user_input = context.get_user_input()
        task_history = context.get_task_history()
        instruction = self._build_instruction(user_input, task_history)

        # 3. Send "working" status
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                status=TaskStatus(
                    state=TaskState.working,
                    message=new_agent_text_message(
                        f"🔧 {self.agent_role} is working...",
                        task.context_id,
                        task.id,
                    ),
                ),
                final=False,
            )
        )

        try:
            # 4. Call Claude Code headless (runs in workspace directory)
            process = await asyncio.create_subprocess_exec(
                "claude",
                "-p", instruction,
                "--output-format", "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),  # Set working directory
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise Exception(f"Claude Code failed: {stderr.decode()}")

            # 5. Parse JSON output
            result = json.loads(stdout.decode())

            # 6. Send artifact with result
            await event_queue.enqueue_event(
                TaskArtifactUpdateEvent(
                    task_id=task.id,
                    context_id=task.context_id,
                    artifact=new_text_artifact(
                        name="result",
                        description=f"Result from {self.agent_role}",
                        text=result.get("response", str(result)),
                    ),
                )
            )

            # 7. Send completion
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    task_id=task.id,
                    context_id=task.context_id,
                    status=TaskStatus(state=TaskState.completed),
                    final=True,
                )
            )

        except Exception as e:
            # Send failure
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    task_id=task.id,
                    context_id=task.context_id,
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=new_agent_text_message(
                            f"❌ Error: {str(e)}",
                            task.context_id,
                            task.id,
                        ),
                    ),
                    final=True,
                )
            )

    def _build_instruction(self, user_input: str, history: list) -> str:
        """Build instruction from user input and task history."""
        context_summary = "\n".join([
            f"{msg.role}: {self._extract_text(msg)}"
            for msg in history[-5:]  # Last 5 messages for context
        ])

        return f"""You are a {self.agent_role}.

{self.system_prompt}

Previous context:
{context_summary}

Current request:
{user_input}
"""

    def _extract_text(self, message) -> str:
        """Extract text from message parts."""
        texts = []
        for part in message.parts:
            if hasattr(part, 'text'):
                texts.append(part.text)
        return " ".join(texts)
```

**Data Structures Needed:**
```python
# None! Uses A2A's built-in Task, Message, Artifact, etc.
```

**Claude Code Headless Output Format:**
```json
{
  "response": "Text response from Claude Code",
  "files_modified": ["path/to/file1.py", "path/to/file2.ts"],
  "session_id": "session-uuid"
}
```

**Available Claude CLI Flags (from docs):**
- `--print`, `-p`: Run in non-interactive mode
- `--output-format`: Specify output (`text`, `json`, `stream-json`)
- `--append-system-prompt`: Append to system prompt (only with `--print`)
- `--allowedTools`: List of tools allowed without permission
- `--disallowedTools`: List of tools disallowed without permission
- `--permission-mode`: Begin in specified permission mode (e.g., `acceptEdits`)
- `--max-turns`: Limit number of agentic turns
- `--resume`, `-r`: Resume specific session by ID
- `--continue`, `-c`: Load most recent conversation
- `--add-dir`: Add additional working directories

**Note:** Claude Code uses the current working directory (set via `cwd` in subprocess), NOT a `--workspace` flag.

---

### Component 2: Agent Configuration

**Purpose:** Define agent-specific behavior (role, system prompt, capabilities)

**File:** `src/agents/config.py`

**Data Structure:**
```python
@dataclass
class AgentConfig:
    """Configuration for a specialist agent."""

    # Identity
    name: str                        # "frontend" | "backend" | "pm" | "ux"
    role: str                        # "Frontend Engineer" | etc.
    port: int                        # A2A server port

    # Capabilities
    description: str                 # Short agent description
    capabilities: list[str]          # What this agent can do

    # Behavior
    system_prompt: str               # Instructions for Claude Code

    # Infrastructure
    workspace: Path                  # Working directory

# Predefined configs
FRONTEND_CONFIG = AgentConfig(
    name="frontend",
    role="Frontend Engineer",
    port=8001,
    description="Builds user interfaces with React/TypeScript",
    capabilities=[
        "React 18 with TypeScript",
        "Next.js 14",
        "Tailwind CSS",
        "Component testing",
        "Responsive design",
    ],
    system_prompt="""You are a Frontend Engineer specializing in:
- Modern React patterns and hooks
- TypeScript for type safety
- Accessible, responsive UIs
- Component-based architecture

When building:
1. Use TypeScript for all components
2. Follow React best practices
3. Include prop types and interfaces
4. Add basic tests
5. Consider accessibility (WCAG)
6. Use semantic HTML

Deliverables:
- Clean, typed component code
- Basic unit tests
- Usage documentation
""",
    workspace=Path("./workspaces/frontend"),
)

BACKEND_CONFIG = AgentConfig(
    name="backend",
    role="Backend Engineer",
    port=8002,
    description="Builds APIs and server-side logic",
    capabilities=[
        "REST APIs with FastAPI/Express",
        "Database design (PostgreSQL)",
        "Authentication & authorization",
        "API documentation",
        "Unit & integration testing",
    ],
    system_prompt="""You are a Backend Engineer specializing in:
- RESTful API design
- Database schema design
- Authentication and security
- Error handling and validation

When building:
1. Design clear API endpoints
2. Use proper HTTP methods and status codes
3. Validate all inputs
4. Handle errors gracefully
5. Document APIs (OpenAPI/Swagger)
6. Write tests

Deliverables:
- Well-structured API code
- Database migrations if needed
- API documentation
- Tests
""",
    workspace=Path("./workspaces/backend"),
)

PM_CONFIG = AgentConfig(
    name="pm",
    role="Product Manager",
    port=8003,
    description="Defines requirements and project scope",
    capabilities=[
        "Requirements analysis",
        "User story creation",
        "Technical specification writing",
        "Scope definition",
    ],
    system_prompt="""You are a Product Manager specializing in:
- Breaking down complex requests into clear requirements
- Writing detailed technical specifications
- Defining project scope and acceptance criteria

When analyzing:
1. Clarify ambiguous requirements
2. Break down into clear tasks
3. Define acceptance criteria
4. Consider edge cases
5. Think about user experience

Deliverables:
- Clear requirement documents
- User stories with acceptance criteria
- Technical specifications
- Edge case analysis
""",
    workspace=Path("./workspaces/pm"),
)

UX_CONFIG = AgentConfig(
    name="ux",
    role="UX Designer",
    port=8004,
    description="Designs user interfaces and experiences",
    capabilities=[
        "User interface design",
        "Design system specification",
        "Accessibility guidelines (WCAG)",
        "User flow design",
    ],
    system_prompt="""You are a UX Designer specializing in:
- User interface design principles
- Design system creation
- Accessibility (WCAG 2.1)
- User experience optimization

When designing:
1. Consider user needs and flows
2. Ensure accessibility
3. Define clear design specifications
4. Think mobile-first
5. Use design system principles

Deliverables:
- Design specifications
- Component guidelines
- Accessibility requirements
- User flow descriptions
""",
    workspace=Path("./workspaces/ux"),
)
```

**V2 Decision:** ✅ **Simple dataclass + configs (~150 lines total).**

---

### Component 3: Agent Server (per agent)

**Purpose:** Start A2A HTTP server with our executor

**File:** `src/agents/frontend_agent.py`, `backend_agent.py`, etc.

**Interface:**
```python
async def start_agent(config: AgentConfig) -> None:
    """
    Start an agent server.

    Args:
        config: Agent configuration

    This function:
    1. Creates workspace
    2. Creates executor
    3. Creates A2A server
    4. Starts HTTP server
    """
```

**Implementation (~30 lines per agent):**
```python
#!/usr/bin/env python3
"""Frontend agent server."""

import asyncio
from pathlib import Path

from a2a.server import A2AServer, TaskManager, MemoryTaskStore
from a2a.types import AgentCard

from agents.executor import ClaudeCodeExecutor
from agents.config import FRONTEND_CONFIG


async def start_frontend_agent():
    """Start the frontend agent server."""

    config = FRONTEND_CONFIG

    # 1. Setup workspace
    config.workspace.mkdir(parents=True, exist_ok=True)

    # 2. Create executor
    executor = ClaudeCodeExecutor(
        workspace=config.workspace,
        agent_role=config.role,
        system_prompt=config.system_prompt,
    )

    # 3. Create task manager
    task_store = MemoryTaskStore()
    task_manager = TaskManager(task_store)

    # 4. Create agent card
    agent_card = AgentCard(
        name=config.role,
        description=config.description,
        url=f"http://localhost:{config.port}",
        capabilities=config.capabilities,
    )

    # 5. Create A2A server
    server = A2AServer(
        agent_card=agent_card,
        task_manager=task_manager,
        executor=executor,
    )

    # 6. Start HTTP server
    print(f"🚀 Starting {config.name} agent on port {config.port}")
    await server.start(host="0.0.0.0", port=config.port)


if __name__ == "__main__":
    asyncio.run(start_frontend_agent())
```

**V2 Decision:** ✅ **~30 lines per agent = 120 lines for 4 agents.**

---

### Component 4: Host Agent (Orchestrator)

**Purpose:** Interactive CLI that delegates to specialist agents

**File:** `src/host_agent/host.py`

**Interface:**
```python
class HostAgent:
    """Orchestrator that delegates work to specialist agents."""

    def __init__(self, agent_registry: dict[str, str]):
        """
        Initialize host agent.

        Args:
            agent_registry: Mapping of agent names to URLs
                {'frontend': 'http://localhost:8001', ...}
        """
        self.agent_registry = agent_registry
        self.clients: dict[str, A2AClient] = {}
        self.http_client: httpx.AsyncClient = None

    async def start(self) -> None:
        """Initialize HTTP client and connect to agents."""

    async def stop(self) -> None:
        """Cleanup resources."""

    async def process_request(self, user_input: str) -> str:
        """
        Process user request and delegate to appropriate agents.

        Args:
            user_input: User's natural language request

        Returns:
            Final result as formatted string
        """

    async def _analyze_request(self, user_input: str) -> dict[str, Any]:
        """
        Use Claude API to analyze which agents to involve.

        Returns:
            {
                'primary_agent': str,
                'supporting_agents': list[str],
                'coordination_needed': bool,
            }
        """

    async def _delegate_to_agent(
        self,
        agent_name: str,
        message: str,
        context_id: str | None = None,
    ) -> Task:
        """
        Send message to an agent and wait for completion.

        Args:
            agent_name: Name of agent to delegate to
            message: Message to send
            context_id: Optional shared context ID

        Returns:
            Completed task with artifacts
        """
```

**Implementation (~150 lines):**
```python
import asyncio
import uuid
import httpx
import anthropic
from typing import Any

from a2a.client import A2AClient
from a2a.types import (
    SendMessageRequest, MessageSendParams, Message,
    TextPart, Task, TaskState,
)


class HostAgent:
    """Orchestrator that delegates work to specialist agents."""

    def __init__(self, agent_registry: dict[str, str]):
        self.agent_registry = agent_registry
        self.clients: dict[str, A2AClient] = {}
        self.http_client: httpx.AsyncClient = None
        self.claude_client = anthropic.Anthropic()

    async def start(self) -> None:
        """Initialize HTTP client."""
        self.http_client = httpx.AsyncClient(timeout=300.0)

    async def stop(self) -> None:
        """Cleanup resources."""
        if self.http_client:
            await self.http_client.aclose()

    async def process_request(self, user_input: str) -> str:
        """Process user request and delegate to agents."""

        # 1. Analyze request
        print(f"\n🤔 Analyzing request...")
        analysis = await self._analyze_request(user_input)
        print(f"✓ Analysis: {analysis['primary_agent']} (primary)")
        if analysis.get('supporting_agents'):
            print(f"  + Supporting: {', '.join(analysis['supporting_agents'])}")

        # 2. Generate shared context ID
        context_id = str(uuid.uuid4())

        # 3. Delegate to agents in order
        results = {}

        # Primary agent
        primary_agent = analysis['primary_agent']
        print(f"\n📤 Delegating to {primary_agent}...")

        primary_task = await self._delegate_to_agent(
            agent_name=primary_agent,
            message=user_input,
            context_id=context_id,
        )
        results[primary_agent] = primary_task
        print(f"✓ {primary_agent} completed")

        # Supporting agents (if needed)
        for agent_name in analysis.get('supporting_agents', []):
            print(f"\n📤 Consulting {agent_name}...")

            # Build message with context from primary
            supporting_message = self._build_supporting_message(
                user_input,
                primary_task,
                agent_name,
            )

            supporting_task = await self._delegate_to_agent(
                agent_name=agent_name,
                message=supporting_message,
                context_id=context_id,
            )
            results[agent_name] = supporting_task
            print(f"✓ {agent_name} completed")

        # 4. Synthesize results
        return self._format_results(results)

    async def _analyze_request(self, user_input: str) -> dict[str, Any]:
        """Analyze which agents should handle this request."""

        prompt = f"""Analyze this user request and determine which specialist agents should handle it.

Available agents:
- frontend: React/TypeScript UI development
- backend: API and server-side development
- pm: Requirements analysis and specifications
- ux: User interface/experience design

User request: {user_input}

Return a JSON object with:
- primary_agent: The main agent to handle this (string)
- supporting_agents: Other agents to consult (list of strings, can be empty)
- coordination_needed: Whether agents need to coordinate (boolean)

Example: {{"primary_agent": "frontend", "supporting_agents": ["ux", "backend"], "coordination_needed": true}}
"""

        response = self.claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        import json
        result_text = response.content[0].text
        # Extract JSON from response (handle markdown code blocks)
        if "```" in result_text:
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]

        return json.loads(result_text.strip())

    async def _delegate_to_agent(
        self,
        agent_name: str,
        message: str,
        context_id: str | None = None,
    ) -> Task:
        """Delegate to an agent and wait for completion."""

        # Get or create client
        if agent_name not in self.clients:
            agent_url = self.agent_registry.get(agent_name)
            if not agent_url:
                raise ValueError(f"Unknown agent: {agent_name}")

            self.clients[agent_name] = A2AClient(
                http_client=self.http_client,
                agent_url=agent_url,
            )

        client = self.clients[agent_name]

        # Build request
        message_id = str(uuid.uuid4())
        request = SendMessageRequest(
            id=message_id,
            params=MessageSendParams(
                message=Message(
                    role="user",
                    parts=[TextPart(text=message)],
                    messageId=message_id,
                    contextId=context_id,
                )
            )
        )

        # Send and get task
        response = await client.send_message(request)
        task = response.result.task

        # Wait for completion by polling
        while task.status.state == TaskState.working:
            await asyncio.sleep(2)
            task = await client.get_task(task.id)

        return task

    def _build_supporting_message(
        self,
        original_request: str,
        primary_task: Task,
        supporting_agent: str,
    ) -> str:
        """Build message for supporting agent with context."""

        # Extract primary agent's result
        primary_result = ""
        if primary_task.artifacts:
            for artifact in primary_task.artifacts:
                for part in artifact.parts:
                    if hasattr(part, 'text'):
                        primary_result = part.text
                        break

        return f"""Based on this user request: {original_request}

Context from primary agent:
{primary_result}

Please provide your specialist input as a {supporting_agent}."""

    def _format_results(self, results: dict[str, Task]) -> str:
        """Format results from all agents."""

        output = ["\n" + "="*60]
        output.append("MULTI-AGENT COLLABORATION RESULTS")
        output.append("="*60 + "\n")

        for agent_name, task in results.items():
            output.append(f"\n{agent_name.upper()} AGENT:")
            output.append("-" * 40)

            if task.artifacts:
                for artifact in task.artifacts:
                    for part in artifact.parts:
                        if hasattr(part, 'text'):
                            output.append(part.text)
            else:
                output.append("(No output)")

            output.append("")

        output.append("="*60)
        return "\n".join(output)


async def main():
    """Run interactive host agent CLI."""

    agent_registry = {
        'frontend': 'http://localhost:8001',
        'backend': 'http://localhost:8002',
        'pm': 'http://localhost:8003',
        'ux': 'http://localhost:8004',
    }

    host = HostAgent(agent_registry)
    await host.start()

    print("\n" + "="*60)
    print("CLAUDE CODE A2A MULTI-AGENT SYSTEM")
    print("="*60)
    print("\nAvailable agents:")
    for name in agent_registry.keys():
        print(f"  • {name}")
    print("\nType your request (or 'quit' to exit)\n")

    try:
        while True:
            user_input = input("You: ").strip()

            if user_input.lower() in ['quit', 'exit', 'q']:
                break

            if not user_input:
                continue

            try:
                result = await host.process_request(user_input)
                print(result)
            except Exception as e:
                print(f"\n❌ Error: {e}\n")

    finally:
        await host.stop()
        print("\n👋 Goodbye!\n")


if __name__ == "__main__":
    asyncio.run(main())
```

**Data Structures:**
```python
# Agent registry (configuration)
AgentRegistry = dict[str, str]  # {agent_name: agent_url}

# Analysis result
@dataclass
class RequestAnalysis:
    primary_agent: str               # Which agent handles this
    supporting_agents: list[str]     # Which agents to consult
    coordination_needed: bool        # Whether agents need to coordinate
```

**V2 Decision:** ✅ **~150 lines for orchestrator.**

---

## Complete Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      USER (CLI)                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────┐
│              HOST AGENT (Port 8000)                         │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  HostAgent                                            │  │
│  │  - Analyzes requests (Claude API)                     │  │
│  │  - Delegates to specialist agents                     │  │
│  │  - Uses A2AClient (no custom code)                    │  │
│  └───────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │ A2A Protocol
                     ↓
┌─────────────────────────────────────────────────────────────┐
│          SPECIALIST AGENTS (Ports 8001-8004)                │
│                                                             │
│  Each agent has identical structure:                        │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  A2AServer (from a2a-python)                          │ │
│  │  ✓ TaskManager - handles task lifecycle              │ │
│  │  ✓ EventQueue - streams updates                       │ │
│  │  ✓ HTTP endpoints - A2A protocol                      │ │
│  └────────────────────┬──────────────────────────────────┘ │
│                       │                                     │
│                       ↓                                     │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  ClaudeCodeExecutor (OUR CODE - 50 lines)             │ │
│  │  - Receives RequestContext + EventQueue               │ │
│  │  - Calls `claude -p '...' --output-format json`       │ │
│  │  - Parses JSON output                                 │ │
│  │  - Sends TaskArtifactUpdateEvent                      │ │
│  └────────────────────┬──────────────────────────────────┘ │
│                       │                                     │
│                       ↓                                     │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  CLAUDE CODE HEADLESS                                 │ │
│  │  `claude -p '...' --output-format json`               │ │
│  │  - Does the actual coding work                        │ │
│  │  - Returns JSON result when complete                  │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
agents_v2/
├── src/
│   ├── agents/
│   │   ├── config.py               # 150 lines - Agent configs
│   │   ├── executor.py             # 50 lines - ClaudeCodeExecutor
│   │   ├── frontend_agent.py       # 30 lines - Frontend server
│   │   ├── backend_agent.py        # 30 lines - Backend server
│   │   ├── pm_agent.py             # 30 lines - PM server
│   │   └── ux_agent.py             # 30 lines - UX server
│   │
│   └── host_agent/
│       └── host.py                 # 150 lines - Orchestrator
│
├── scripts/
│   ├── start_all.sh                # Start all agents
│   └── stop_all.sh                 # Stop all agents
│
├── workspaces/                     # Claude Code workspaces
│   ├── frontend/
│   ├── backend/
│   ├── pm/
│   └── ux/
│
└── requirements.txt

TOTAL: ~470 lines (vs 2000+ in V1)
```

---

## Key Interfaces Summary

### 1. What A2A Provides (Use As-Is)

| Component | What It Does | Interface |
|-----------|-------------|-----------|
| `TaskManager` | Task lifecycle | `create_task()`, `update_task_status()`, `add_artifact()` |
| `EventQueue` | Event streaming | `enqueue_event()`, `subscribe()` |
| `A2AClient` | Agent communication | `send_message()`, `get_agent_card()` |
| `A2AServer` | HTTP server | `start()` (with executor) |
| `Task` | Task data | `.id`, `.status`, `.artifacts`, `.history` |
| `Message` | Message data | `.role`, `.parts`, `.taskId`, `.contextId` |

### 2. What We Build

| Component | Lines | What It Does | Key Methods |
|-----------|-------|-------------|-------------|
| `ClaudeCodeExecutor` | 50 | Translate A2A ↔ Claude Code | `execute(context, event_queue)` |
| `AgentConfig` | 150 | Agent definitions | Dataclass + 4 configs |
| `Agent Servers` | 120 | Start A2A servers | `start_frontend_agent()`, etc. |
| `HostAgent` | 150 | Orchestrator | `process_request(user_input)` |

**Total:** ~470 lines

---

## Data Flow Example

**User Request:** "Build a login form"

```
1. USER → Host Agent
   HostAgent.process_request("Build a login form")

2. Host analyzes with Claude API
   analysis = {
     'primary_agent': 'frontend',
     'supporting_agents': ['ux', 'backend'],
   }

3. Host → UX Agent (via A2AClient)
   request = SendMessageRequest(
     message=Message(
       role="user",
       parts=[TextPart(text="Design specs for login form")],
       contextId="ctx-123",
     )
   )
   ux_task = await ux_client.send_message(request)

4. UX Agent → ClaudeCodeExecutor
   executor.execute(context, event_queue)

5. ClaudeCodeExecutor → Claude Code Headless
   $ cd ./workspaces/ux && \
     claude -p "You are a UX Designer...\nDesign specs for login form" \
     --output-format json

6. Claude Code returns JSON
   {
     "response": "# Login Form Design\n\n## Components:\n...",
     "files_modified": ["design.md"],
     "session_id": "sess-123"
   }

7. ClaudeCodeExecutor → EventQueue
   TaskArtifactUpdateEvent(artifact=design_spec)
   TaskStatusUpdateEvent(state=completed, final=True)

8. Events → A2AServer → A2AClient → Host

9. Host waits for ux_task.status.state == "completed"

10. Host → Backend Agent (with UX context)
    "Create login API endpoints based on: [UX design]"

11. Repeat flow for backend

12. Host → Frontend Agent (with UX + Backend context)
    "Build login form based on: [UX design] [Backend API]"

13. Frontend completes, Host returns final result
```

---

## Implementation Checklist

### Phase 1: Core Infrastructure (Day 1, 3 hours)
- [ ] `src/agents/config.py` - Agent configs (150 lines)
- [ ] `src/agents/executor.py` - ClaudeCodeExecutor (50 lines)
- [ ] Test: Single executor can call Claude Code headless and parse result

### Phase 2: Specialist Agents (Day 1, 2 hours)
- [ ] `src/agents/frontend_agent.py` (30 lines)
- [ ] `src/agents/backend_agent.py` (30 lines)
- [ ] `src/agents/pm_agent.py` (30 lines)
- [ ] `src/agents/ux_agent.py` (30 lines)
- [ ] Test: All 4 agents start and respond to A2A requests

### Phase 3: Host Agent (Day 2, 3 hours)
- [ ] `src/host_agent/host.py` - Orchestrator (150 lines)
- [ ] Interactive CLI
- [ ] Test: Can delegate to agents and collect results

### Phase 4: Integration & Polish (Day 2, 2 hours)
- [ ] Startup/shutdown scripts
- [ ] Error handling
- [ ] Logging
- [ ] End-to-end test: Multi-agent task
- [ ] Documentation

**Total Estimate:** 2 days, ~470 lines of code

---

## Critical Don'ts (What NOT to Build)

❌ **DON'T build:**
1. Custom `AgentCommunicator` - Use `A2AClient`
2. Custom `TaskQueue` - A2A has `TaskManager`
3. Custom `EventBus` - A2A has `EventQueue`
4. File-based coordination - Use `Task.history` and `context_id`
5. tmux control - Use Claude Code headless mode
6. MCP protocol layer - Use headless JSON output
7. Custom task persistence - Use `TaskStore`
8. Manual polling loops - Use A2A's event streaming
9. Context files (CONTEXT.md, etc.) - Use `Message.parts`

✅ **DO build:**
1. `ClaudeCodeExecutor` - Simple subprocess wrapper (50 lines)
2. `AgentConfig` - Configuration definitions (150 lines)
3. Agent server scripts - Start A2A servers (120 lines)
4. `HostAgent` - Orchestration logic (150 lines)

---

## Success Criteria

**V2 is successful if:**

1. **Minimal Code:**
   - Total < 500 lines (vs 2000+ in V1)
   - Each component under 150 lines
   - No duplicate functionality from A2A

2. **Correct Abstractions:**
   - Uses A2A's TaskManager, EventQueue, A2AClient
   - No custom task/event management
   - Claude Code headless mode (not MCP, not tmux)

3. **Clean Interfaces:**
   - ClaudeCodeExecutor: `execute(context, event_queue)`
   - HostAgent: `process_request(user_input)`
   - Simple subprocess calls to Claude Code

4. **Works End-to-End:**
   - Can delegate simple tasks
   - Can coordinate multi-agent tasks
   - Context sharing works
   - Clean JSON output parsing

5. **Maintainable:**
   - Easy to add new agent types
   - Clear separation of concerns
   - Minimal dependencies
   - Good error handling

---

## Next Steps

1. **Review this design** - Does it make sense?
2. **Approve or revise** - Any changes needed?
3. **Start Phase 1** - Build core infrastructure
4. **Iterate quickly** - Test each phase before next

**Total implementation time:** ~2 days for complete rebuild with **76% less code** than V1
