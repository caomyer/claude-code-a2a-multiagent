# A2A Protocol - Learning Document

## Overview

This document captures learnings from studying the official A2A (Agent-to-Agent) protocol implementation in the `a2a-samples` repository. It serves as a practical guide for implementing A2A in the Claude Code multi-agent system.

**Reference Implementation:** `~/Documents/projects/a2a-samples/samples/python/agents/airbnb_planner_multiagent`

## What is A2A?

Agent-to-Agent (A2A) is a protocol that enables agents to communicate and coordinate with each other. It's designed to allow:
- **Agent discovery** through AgentCards
- **Message passing** between agents
- **Task delegation** and coordination
- **Streaming responses** with real-time updates
- **Stateful conversations** with context management

## Core Components

### 1. AgentCard (Agent Identity & Capabilities)

The AgentCard is like a business card for agents - it describes what the agent does and how to reach it.

```python
from a2a.types import AgentCard, AgentCapabilities, AgentSkill

agent_card = AgentCard(
    name='Weather Agent',                    # Agent's display name
    description='Helps with weather',        # What the agent does
    url='http://localhost:10001',            # Where to reach it
    version='1.0.0',                         # Version for compatibility
    default_input_modes=['text'],            # Accepts text input
    default_output_modes=['text'],           # Returns text output
    capabilities=AgentCapabilities(
        streaming=True,                      # Supports streaming responses
        push_notifications=True              # (Optional) Can push updates
    ),
    skills=[                                 # What the agent can do
        AgentSkill(
            id='weather_search',
            name='Search weather',
            description='Helps with weather in city, or states',
            tags=['weather'],
            examples=['weather in LA, CA']
        )
    ]
)
```

**Key Fields:**
- **name**: Human-readable agent name
- **description**: What the agent does
- **url**: HTTP endpoint for the agent
- **skills**: List of specific capabilities with examples
- **capabilities**: Streaming, push notifications, etc.

### 2. A2A Server (Remote Agent)

Remote agents run as HTTP servers that expose the A2A protocol. They receive tasks and return results.

**Architecture Pattern:**
```
┌─────────────────────────────────────────┐
│           __main__.py                   │
│  ┌─────────────────────────────────┐   │
│  │ 1. Create AgentCard             │   │
│  │ 2. Create AgentExecutor         │   │
│  │ 3. Create RequestHandler        │   │
│  │ 4. Create A2AStarletteApp       │   │
│  │ 5. Run with uvicorn             │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

**Implementation Example (Weather Agent):**

```python
# weather_agent/__main__.py
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities, AgentSkill

# Step 1: Create the AgentCard
agent_card = AgentCard(
    name='Weather Agent',
    description='Helps with weather',
    url=f'http://localhost:10001',
    version='1.0.0',
    default_input_modes=['text'],
    default_output_modes=['text'],
    capabilities=AgentCapabilities(streaming=True),
    skills=[AgentSkill(...)]
)

# Step 2: Create the agent executor (custom business logic)
agent_executor = WeatherExecutor(runner, agent_card)

# Step 3: Create the request handler
request_handler = DefaultRequestHandler(
    agent_executor=agent_executor,
    task_store=InMemoryTaskStore()
)

# Step 4: Create the A2A application
a2a_app = A2AStarletteApplication(
    agent_card=agent_card,
    http_handler=request_handler
)

# Step 5: Run the server
uvicorn.run(a2a_app.build(), host='0.0.0.0', port=10001)
```

**Key Insights:**
- Uses **Starlette** (ASGI framework) under the hood
- **InMemoryTaskStore** tracks task state
- **DefaultRequestHandler** handles A2A protocol details
- Your custom logic goes in the **AgentExecutor**

### 3. AgentExecutor (Custom Business Logic)

The AgentExecutor is where you implement your agent's actual functionality. It must implement the `execute()` method.

```python
from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState

class WeatherExecutor(AgentExecutor):
    def __init__(self, runner, card: AgentCard):
        self.runner = runner  # ADK Runner or your own logic
        self._card = card
        self._active_sessions = set()

    async def execute(
        self,
        context: RequestContext,      # Request details
        event_queue: EventQueue,       # For sending updates
    ):
        # Create updater for sending status/results
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        # Notify task is submitted
        await updater.update_status(TaskState.submitted)

        # Notify task is working
        await updater.update_status(TaskState.working)

        # Do your actual work here
        result = await self._do_work(context.message)

        # Send results
        await updater.add_artifact([TextPart(text=result)])

        # Mark as completed
        await updater.update_status(TaskState.completed, final=True)

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        # Handle cancellation (optional)
        raise ServerError(error=UnsupportedOperationError())
```

**Key Concepts:**
- **RequestContext**: Contains the incoming message, task_id, context_id
- **EventQueue**: For sending updates back to caller
- **TaskUpdater**: Helper to update task status and send artifacts
- **TaskState**: submitted → working → completed (or failed)

**Task States:**
```python
TaskState.submitted    # Task received
TaskState.working      # Task in progress
TaskState.completed    # Task done successfully
TaskState.failed       # Task failed
```

### 4. A2A Client (Connecting to Remote Agents)

The client side fetches AgentCards and sends messages to remote agents.

```python
import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest

# Step 1: Get the AgentCard
async with httpx.AsyncClient(timeout=30) as http_client:
    card_resolver = A2ACardResolver(http_client, 'http://localhost:10001')
    agent_card = await card_resolver.get_agent_card()

    # Step 2: Create A2A client
    a2a_client = A2AClient(http_client, agent_card, url='http://localhost:10001')

    # Step 3: Send a message
    message_request = SendMessageRequest(
        id='unique-message-id',
        params=MessageSendParams(
            message={
                'role': 'user',
                'parts': [{'type': 'text', 'text': 'What is the weather?'}],
                'messageId': 'msg-123',
                'taskId': 'task-456',      # Optional: for multi-turn
                'contextId': 'ctx-789'     # Optional: for session
            }
        )
    )

    response = await a2a_client.send_message(message_request)
```

**Key Points:**
- **A2ACardResolver**: Fetches AgentCard from `/.well-known/agent.json`
- **A2AClient**: Sends messages and receives responses
- **taskId**: Links related messages together
- **contextId**: Maintains session/conversation context

### 5. Message Format

Messages in A2A follow this structure:

```python
{
    'message': {
        'role': 'user',                              # 'user' or 'agent'
        'parts': [                                   # Array of content parts
            {'type': 'text', 'text': 'Hello'},      # Text part
            {'type': 'file', 'file': {...}}         # File part (optional)
        ],
        'messageId': 'unique-id',                    # Required
        'taskId': 'task-id',                         # Optional: groups messages
        'contextId': 'context-id'                    # Optional: session context
    }
}
```

**Part Types:**
- **TextPart**: Plain text content
- **FilePart**: File with URI or bytes
  - **FileWithUri**: Reference to a file
  - **FileWithBytes**: Inline file data

## Integration with Google ADK

The reference implementation uses **Google Agent Development Kit (ADK)** for the intelligence layer. Here's how they work together:

### ADK Agent Creation

```python
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

def create_weather_agent() -> LlmAgent:
    return LlmAgent(
        model=LiteLlm(model='gemini-2.5-flash'),
        name='weather_agent',
        description='An agent that can help questions about weather',
        instruction="""You are a specialized weather forecast assistant...""",
        tools=[MCPToolset(...)]  # MCP tools for data access
    )
```

### ADK Runner + A2A Executor Pattern

```python
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService

# Create ADK agent
adk_agent = create_weather_agent()

# Create ADK runner
runner = Runner(
    app_name='weather_agent',
    agent=adk_agent,
    artifact_service=InMemoryArtifactService(),
    session_service=InMemorySessionService(),
)

# Wrap in A2A executor
agent_executor = WeatherExecutor(runner, agent_card)
```

**In the Executor:**
```python
async def execute(self, context: RequestContext, event_queue: EventQueue):
    updater = TaskUpdater(event_queue, context.task_id, context.context_id)

    # Convert A2A message to ADK format
    adk_message = types.UserContent(
        parts=[convert_a2a_part_to_genai(part) for part in context.message.parts]
    )

    # Run ADK agent
    async for event in self.runner.run_async(
        session_id=context.context_id,
        user_id='default_user',
        new_message=adk_message
    ):
        if event.is_final_response():
            # Convert ADK response to A2A format
            parts = [convert_genai_part_to_a2a(p) for p in event.content.parts]
            await updater.add_artifact(parts)
            await updater.update_status(TaskState.completed, final=True)
            break

        # Send intermediate updates
        await updater.update_status(TaskState.working, message=...)
```

## Host Agent Pattern (Orchestrator)

The host agent coordinates multiple remote agents. It doesn't run as an A2A server - instead it uses ADK with A2A clients.

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Host Agent                        │
│                                                     │
│  ┌───────────────────────────────────────────┐    │
│  │         ADK Routing Agent                 │    │
│  │  - Analyzes user request                  │    │
│  │  - Decides which agents to call           │    │
│  │  - Has send_message tool                  │    │
│  └───────────────────────────────────────────┘    │
│                      ↓                              │
│  ┌───────────────────────────────────────────┐    │
│  │     Remote Agent Connections              │    │
│  │  - Maintains A2AClient for each agent     │    │
│  │  - Fetches AgentCards                     │    │
│  │  - Sends messages via A2A                 │    │
│  └───────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
         ↓                              ↓
   [Weather Agent]              [Airbnb Agent]
```

### Implementation Pattern

**1. Remote Agent Connection Manager:**
```python
class RemoteAgentConnections:
    def __init__(self, agent_card: AgentCard, agent_url: str):
        self._httpx_client = httpx.AsyncClient(timeout=30)
        self.agent_client = A2AClient(
            self._httpx_client,
            agent_card,
            url=agent_url
        )
        self.card = agent_card

    async def send_message(
        self,
        message_request: SendMessageRequest
    ) -> SendMessageResponse:
        return await self.agent_client.send_message(message_request)
```

**2. Routing Agent with A2A Tools:**
```python
class RoutingAgent:
    def __init__(self):
        self.remote_agent_connections = {}
        self.cards = {}

    async def _async_init_components(self, remote_agent_addresses: list[str]):
        async with httpx.AsyncClient(timeout=30) as client:
            for address in remote_agent_addresses:
                # Fetch AgentCard
                card_resolver = A2ACardResolver(client, address)
                card = await card_resolver.get_agent_card()

                # Create connection
                remote_connection = RemoteAgentConnections(
                    agent_card=card,
                    agent_url=address
                )
                self.remote_agent_connections[card.name] = remote_connection
                self.cards[card.name] = card

    def create_agent(self) -> Agent:
        return Agent(
            model='gemini-2.5-flash-lite',
            name='Routing_agent',
            instruction=self.root_instruction,
            tools=[self.send_message]  # Tool to call remote agents
        )

    def root_instruction(self, context) -> str:
        return f"""
        You are a Routing Delegator.

        Available Agents: {self.agents}

        Use send_message tool to delegate tasks to remote agents.
        """

    async def send_message(
        self,
        agent_name: str,
        task: str,
        tool_context: ToolContext
    ):
        """Tool callable by ADK agent to send messages to remote agents."""
        client = self.remote_agent_connections[agent_name]

        # Create message request
        message_request = SendMessageRequest(
            id=str(uuid.uuid4()),
            params=MessageSendParams(
                message={
                    'role': 'user',
                    'parts': [{'type': 'text', 'text': task}],
                    'messageId': str(uuid.uuid4()),
                    'taskId': tool_context.state.get('task_id'),
                    'contextId': tool_context.state.get('context_id')
                }
            )
        )

        # Send to remote agent
        response = await client.send_message(message_request)
        return response.root.result
```

**3. Create and Run:**
```python
# Create routing agent
async def create_routing_agent():
    routing_agent_instance = await RoutingAgent.create(
        remote_agent_addresses=[
            'http://localhost:10001',  # Weather
            'http://localhost:10002'   # Airbnb
        ]
    )
    return routing_agent_instance.create_agent()

# Run with Gradio UI
routing_agent = asyncio.run(create_routing_agent())
runner = Runner(agent=routing_agent, ...)

async for event in runner.run_async(...):
    # Handle events, show in UI
```

## Key Patterns & Best Practices

### 1. Session & Context Management

```python
# Multi-turn conversations need consistent IDs
task_id = str(uuid.uuid4())      # Same for all messages in a task
context_id = str(uuid.uuid4())   # Same for entire conversation
message_id = str(uuid.uuid4())   # Unique per message

# In remote agent executor
async def _upsert_session(self, session_id: str):
    session = await self.runner.session_service.get_session(
        app_name=self.runner.app_name,
        user_id='default_user',
        session_id=session_id
    )
    if session is None:
        session = await self.runner.session_service.create_session(
            app_name=self.runner.app_name,
            user_id='default_user',
            session_id=session_id
        )
    return session
```

### 2. Type Conversion (A2A ↔ ADK)

```python
def convert_a2a_part_to_genai(part: Part) -> types.Part:
    """A2A → Google GenAI format"""
    part = part.root
    if isinstance(part, TextPart):
        return types.Part(text=part.text)
    elif isinstance(part, FilePart):
        if isinstance(part.file, FileWithUri):
            return types.Part(
                file_data=types.FileData(
                    file_uri=part.file.uri,
                    mime_type=part.file.mime_type
                )
            )
    # ... handle other types

def convert_genai_part_to_a2a(part: types.Part) -> Part:
    """Google GenAI → A2A format"""
    if part.text:
        return TextPart(text=part.text)
    elif part.file_data:
        return FilePart(
            file=FileWithUri(
                uri=part.file_data.file_uri,
                mime_type=part.file_data.mime_type
            )
        )
    # ... handle other types
```

### 3. Streaming Updates

```python
async def execute(self, context, event_queue):
    updater = TaskUpdater(event_queue, context.task_id, context.context_id)

    # Initial status
    await updater.update_status(TaskState.submitted)
    await updater.update_status(TaskState.working)

    # Stream intermediate updates
    async for event in self.runner.run_async(...):
        if event.is_final_response():
            # Final result
            await updater.add_artifact(parts)
            await updater.update_status(TaskState.completed, final=True)
            break
        else:
            # Intermediate update
            await updater.update_status(
                TaskState.working,
                message=updater.new_agent_message(parts)
            )
```

### 4. Tool Integration (ADK Agent as Tool)

The host agent uses `send_message` as a tool:

```python
# In ADK agent definition
Agent(
    tools=[self.send_message]  # Method that calls remote agents
)

# The tool signature
async def send_message(
    self,
    agent_name: str,      # Which remote agent
    task: str,            # What to ask it
    tool_context: ToolContext  # ADK provides this
):
    # Call remote agent via A2A
    # Return result to ADK
```

## Dependency Stack

From `pyproject.toml`:

```toml
[project]
dependencies = [
    "a2a-sdk>=0.3.0",              # Core A2A protocol
    "google-adk>=1.7.0",           # Google Agent Development Kit
    "langchain-google-genai>=2.1.5",
    "langgraph>=0.4.5",
    "mcp>=1.5.0",                  # Model Context Protocol
    "uvicorn",                     # ASGI server
    "click>=8.2.0",                # CLI
    "httpx>=0.27.0",               # Async HTTP client
    "gradio>=5.30.0",              # UI (optional)
]
```

**Key Libraries:**
- **a2a-sdk**: Official A2A protocol implementation
- **google-adk**: Agent framework with LLM integration
- **uvicorn**: Runs the A2A server (Starlette/ASGI)
- **httpx**: Async HTTP client for A2A calls
- **mcp**: Model Context Protocol for tool integration

## Adapting to Claude Code Architecture

### Differences from Reference Implementation

| Aspect | Reference (ADK) | Our Implementation (Claude Code) |
|--------|-----------------|-----------------------------------|
| **Intelligence Layer** | Google ADK + Gemini | Anthropic Claude API |
| **Execution Layer** | MCP tools | Claude Code CLI (via tmux) |
| **Agent Framework** | ADK Runner | BaseAgent (custom) |
| **Tools** | MCP Toolset | Claude Code commands |
| **UI** | Gradio | Terminal-based |

### Adaptation Strategy

**1. Keep A2A Protocol Layer (Identical):**
```python
# Remote agents still use:
- A2AStarletteApplication
- DefaultRequestHandler
- InMemoryTaskStore
- AgentCard / AgentSkill
```

**2. Replace ADK with Claude API (Intelligence Layer):**
```python
# Instead of ADK Runner
class BaseAgent(AgentExecutor):
    def __init__(self, config: AgentConfig):
        self.claude_api = anthropic.Anthropic(...)
        # No ADK runner

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        # Use Claude API for analysis
        analysis = await self._analyze_with_claude(context.message)

        # Coordinate with other agents if needed
        if analysis.needs_other_agents:
            specs = await self._ask_other_agents(analysis)

        # Package context for Claude Code
        await self._create_context_files(context, analysis, specs)

        # Send to Claude Code terminal
        await self._send_to_claude_terminal(context)

        # Collect results
        results = await self._collect_results()

        # Return via A2A
        await updater.add_artifact([TextPart(text=results)])
        await updater.update_status(TaskState.completed, final=True)
```

**3. Host Agent Pattern (Similar to Reference):**
```python
# Host agent structure stays similar
class HostAgent:
    def __init__(self):
        # Connect to remote agents via A2A
        self.remote_connections = {}

    async def delegate_task(self, task: str):
        # Analyze which agent(s) to use (with Claude API)
        plan = await self.claude_api.analyze(task)

        # Send to appropriate agents via A2A
        for agent_name in plan.required_agents:
            message_request = SendMessageRequest(...)
            response = await self.remote_connections[agent_name].send_message(
                message_request
            )
```

### Key Mappings

**A2A Message → Claude Code Context:**
```python
# When BaseAgent receives A2A message
context.message.parts → Extract task description
context.task_id → Task identifier
context.context_id → Session/conversation ID

# Write to workspace
CONTEXT.md ← Agent role, background
SPECS.md ← Info from other agents (via A2A)
INSTRUCTIONS.md ← Execution plan

# Send to Claude Code terminal
tmux send-keys "Build feature. See CONTEXT.md"
```

**Claude Code Output → A2A Response:**
```python
# After Claude Code completes
terminal_output = tmux capture-pane
generated_files = scan_workspace()

# Convert to A2A artifacts
await updater.add_artifact([
    TextPart(text=terminal_output),
    FilePart(file=generated_files)
])
```

## Complete Flow Example

### User Request: "Get weather in LA"

**1. Host Agent receives request (via CLI/API)**
```python
user_input = "Get weather in LA"
```

**2. Host Agent uses Claude API to analyze**
```python
# Claude API determines: needs Weather Agent
plan = await claude_api.analyze(user_input)
# plan = {'agent': 'Weather Agent', 'task': 'Get current weather in LA'}
```

**3. Host Agent sends A2A message to Weather Agent**
```python
message_request = SendMessageRequest(
    id='msg-123',
    params=MessageSendParams(
        message={
            'role': 'user',
            'parts': [{'type': 'text', 'text': 'Get current weather in LA'}],
            'messageId': 'msg-123',
            'taskId': 'task-456',
            'contextId': 'ctx-789'
        }
    )
)

response = await weather_agent_client.send_message(message_request)
```

**4. Weather Agent receives via A2A server**
```python
# DefaultRequestHandler routes to WeatherExecutor.execute()
async def execute(context: RequestContext, event_queue: EventQueue):
    updater = TaskUpdater(event_queue, context.task_id, context.context_id)
    await updater.update_status(TaskState.working)

    # Weather agent does work (ADK + MCP tools)
    result = await self._get_weather('LA')

    # Return results
    await updater.add_artifact([TextPart(text=result)])
    await updater.update_status(TaskState.completed, final=True)
```

**5. Response flows back**
```python
# Weather Agent → Host Agent (via A2A)
# Host Agent → User (via CLI/API)
```

## Security Considerations

From the reference implementation disclaimer:

**⚠️ Important Security Notes:**

1. **Treat external agents as untrusted:**
   - Validate all AgentCard data
   - Sanitize description, name, skills.description
   - Can be used for prompt injection attacks

2. **Input validation:**
   - Validate all message parts
   - Check file types and sizes
   - Sanitize before using in prompts

3. **Authentication/Authorization:**
   - Reference uses no auth (demo only)
   - Production needs proper auth

## References

- **A2A Protocol:** https://github.com/google/a2a-python
- **Google ADK:** https://google.github.io/adk-docs/
- **Reference Implementation:** `~/Documents/projects/a2a-samples/samples/python/agents/airbnb_planner_multiagent`
- **A2A Codelab:** https://codelabs.developers.google.com/intro-a2a-purchasing-concierge

## Next Steps for Implementation

1. **Phase 1:** Implement A2A server for remote agents (Frontend, Backend, PM, UX)
   - Use A2AStarletteApplication
   - Create custom AgentExecutor for each
   - Integrate with Claude API + Claude Code terminal

2. **Phase 2:** Implement Host Agent
   - Create RemoteAgentConnections manager
   - Use Claude API for routing decisions
   - Send tasks via A2A to remote agents

3. **Phase 3:** Context synchronization
   - A2A message → Context files
   - Claude Code output → A2A artifacts

4. **Phase 4:** Multi-agent coordination
   - Remote agents call other remote agents
   - Maintain session/context IDs
   - Stream updates back to host

---

**Last Updated:** 2025-10-10
**Version:** 1.0
