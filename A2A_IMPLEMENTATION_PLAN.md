# A2A Task vs Message: Understanding & Implementation Plan

## Executive Summary

After studying the official A2A Python package and the Airbnb multi-agent example, I've identified critical architectural patterns for proper task and message lifecycle management in our Claude Code multi-agent system.

## Key Learnings from A2A Protocol

### 1. **Message vs Task: The Core Differentiation**

#### **Message** - Ephemeral Communication
- **Purpose**: Single unit of conversation between user and agent
- **Lifecycle**: Created → Sent → Processed → Can become part of Task history
- **Key Properties**:
  - `message_id`: Unique identifier (UUID)
  - `role`: 'user' or 'agent'
  - `parts`: Content (text, files, data)
  - `context_id`: Groups related messages/tasks
  - `task_id`: Optional, links to a task

**When to use Messages:**
- Sending a new request to an agent
- Asking for clarification or providing input
- Agent responding with intermediate updates
- Quick, stateless communication

#### **Task** - Persistent Workflow State
- **Purpose**: Stateful operation tracking the entire lifecycle of work
- **Lifecycle**: Created → Working → (Multiple states) → Completed/Failed/Canceled
- **Key Properties**:
  - `id`: Unique task identifier (UUID)
  - `context_id`: Groups related tasks
  - `status`: Current state + optional message
  - `history`: Array of all messages exchanged
  - `artifacts`: Generated outputs (files, data)
  - `metadata`: Extension-specific data

**When to use Tasks:**
- Tracking long-running operations
- Maintaining conversation history
- Storing generated artifacts
- Managing stateful workflows across multiple interactions

### 2. **Task States & Lifecycle**

```
TaskState enum (from a2a/types.py:989-1003):
- submitted     → Initial state when task created
- working       → Agent is actively processing
- input_required → Agent needs user input to continue
- completed     → Successfully finished
- canceled      → User/system canceled
- failed        → Error occurred
- rejected      → Agent refused to process
- auth_required → Authentication needed
- unknown       → Fallback state
```

### 3. **Critical Patterns from Airbnb Example**

#### Pattern 1: Task Creation & Initialization
```python
# From agent_executor.py:50-52
if not task:
    task = new_task(context.message)  # Create task from initial message
    await event_queue.enqueue_event(task)  # Persist immediately
```

#### Pattern 2: Status Updates During Work
```python
# From agent_executor.py:94-108
await event_queue.enqueue_event(
    TaskStatusUpdateEvent(
        status=TaskStatus(
            state=TaskState.working,
            message=new_agent_text_message(event['content'], ...),
        ),
        final=False,  # More updates coming
        context_id=task.context_id,
        task_id=task.id,
    )
)
```

#### Pattern 3: Artifact Generation
```python
# From agent_executor.py:57-67
await event_queue.enqueue_event(
    TaskArtifactUpdateEvent(
        append=False,
        artifact=new_text_artifact(
            name='current_result',
            description='Result of request to agent.',
            text=event['content'],
        ),
        context_id=task.context_id,
        task_id=task.id,
        last_chunk=True,
    )
)
```

#### Pattern 4: Completion
```python
# From agent_executor.py:69-76
await event_queue.enqueue_event(
    TaskStatusUpdateEvent(
        status=TaskStatus(state=TaskState.completed),
        final=True,  # No more updates
        context_id=task.context_id,
        task_id=task.id,
    )
)
```

#### Pattern 5: Inter-Agent Communication
```python
# From routing_agent.py:263-282
message_request = SendMessageRequest(
    id=message_id,
    params=MessageSendParams.model_validate({
        'message': {
            'role': 'user',
            'parts': [{'type': 'text', 'text': task_description}],
            'messageId': message_id,
            'taskId': task_id,        # Link to existing task
            'contextId': context_id,  # Maintain context
        }
    })
)
send_response = await client.send_message(message_request)
# Response contains Task object with updated state
```

### 4. **TaskManager Lifecycle (from a2a package)**

The `TaskManager` class handles task persistence and state management:

```python
# Key operations from task_manager.py:

1. Initialize with task_id, context_id, TaskStore
   - If task_id provided: Load existing task
   - If not: Will create new task on first event

2. save_task_event(event):
   - Accepts Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
   - Updates task state in memory
   - Persists to TaskStore
   - Maintains history

3. update_with_message(message, task):
   - Adds message to task history
   - Moves status.message to history first
   - Updates in-place

4. Task History Management:
   - status.message: Current status message
   - history: All previous messages
   - When new message arrives, status.message moves to history
```

### 5. **Context ID vs Task ID**

**context_id**:
- Server-generated UUID for grouping related interactions
- Persists across multiple tasks
- Example: Entire "build login system" project has one context_id
- Multiple tasks can share same context_id
- Used for maintaining long-term conversation context

**task_id**:
- Server-generated UUID for specific work unit
- Unique per task
- Example: "Frontend builds login form" is one task_id
- Changes when work completes and new work starts
- Used for tracking specific operation lifecycle

## Problems in Our Current Design

### Problem 1: **Missing Task Lifecycle Management**
Our CLAUDE.md focuses on execution but doesn't define:
- When to create new tasks vs. continue existing tasks
- How to track task state through Claude Code execution
- How to persist and retrieve task state
- How to handle task history

### Problem 2: **Unclear Message vs Task Usage**
Our design conflates:
- Sending instructions to Claude Code (should be task-level)
- Quick queries between agents (can be message-level)
- Long-running work tracking (definitely task-level)

### Problem 3: **No EventQueue Pattern**
We don't have:
- Event-driven status updates
- Streaming progress reporting
- Proper artifact attachment to tasks

### Problem 4: **Context Management Gaps**
We haven't defined:
- How context_id flows through multi-agent collaboration
- When to create new contexts
- How to reference previous work within a context

## Proposed Implementation for Our Project

### Phase 1: Add Task Infrastructure

#### 1.1 Create TaskStore Implementation
```python
# src/common/task_store.py
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import Task

class ClaudeCodeTaskStore(InMemoryTaskStore):
    """Task store with file-based persistence for resilience"""

    def __init__(self, workspace_dir: Path):
        super().__init__()
        self.workspace_dir = workspace_dir

    async def save(self, task: Task, context=None):
        await super().save(task, context)
        # Also persist to disk
        task_file = self.workspace_dir / f"tasks/{task.id}.json"
        task_file.parent.mkdir(parents=True, exist_ok=True)
        task_file.write_text(task.model_dump_json(indent=2))
```

#### 1.2 Integrate TaskManager into BaseAgent
```python
# src/common/base_agent.py
from a2a.server.tasks.task_manager import TaskManager
from a2a.server.events.event_queue import EventQueue

class BaseAgent(AgentExecutor):

    def __init__(self, config: AgentConfig):
        self.config = config
        self.task_store = ClaudeCodeTaskStore(config.workspace)
        self.claude_api = anthropic.Anthropic(...)
        self.claude_terminal = ClaudeCodeTerminal(...)

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        """Main execution entry point from A2A server"""

        # 1. Initialize task management
        task_manager = TaskManager(
            task_id=context.task_id,
            context_id=context.context_id,
            task_store=self.task_store,
            initial_message=context.message,
        )

        # 2. Get or create task
        task = await task_manager.get_task()
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        # 3. Update status: working
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.working),
                final=False,
                context_id=task.context_id,
                task_id=task.id,
            )
        )

        # 4. Intelligence layer: Analyze task
        analysis = await self._analyze_task_with_claude_api(
            task=task,
            user_input=context.get_user_input()
        )

        # 5. Coordination: Ask other agents if needed
        if analysis.needs_other_agents:
            for agent_name in analysis.required_agents:
                specs = await self._ask_agent(agent_name, analysis.questions)
                # Update task with new information
                await event_queue.enqueue_event(
                    TaskStatusUpdateEvent(
                        status=TaskStatus(
                            state=TaskState.working,
                            message=new_agent_text_message(
                                f"Received specs from {agent_name}",
                                task.context_id,
                                task.id,
                            ),
                        ),
                        final=False,
                        context_id=task.context_id,
                        task_id=task.id,
                    )
                )

        # 6. Build context package for execution
        context_package = await self._build_context_package(task, analysis, specs)

        # 7. Execute with Claude Code
        await self._execute_with_claude_code(
            task=task,
            context_package=context_package,
            event_queue=event_queue,
        )

        # 8. Collect results and create artifacts
        results = await self._collect_results(task)
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                artifact=new_text_artifact(
                    name="implementation",
                    description="Generated code and tests",
                    text=results.code,
                ),
                context_id=task.context_id,
                task_id=task.id,
                last_chunk=True,
            )
        )

        # 9. Mark complete
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                status=TaskStatus(state=TaskState.completed),
                final=True,
                context_id=task.context_id,
                task_id=task.id,
            )
        )
```

#### 1.3 Add Inter-Agent Communication Helper
```python
# src/common/agent_communication.py
class AgentCommunicator:
    """Helper for inter-agent A2A communication"""

    def __init__(self, agent_registry: dict[str, str]):
        """
        Args:
            agent_registry: Mapping of agent_name -> agent_url
        """
        self.agent_registry = agent_registry
        self.clients: dict[str, A2AClient] = {}

    async def send_message_to_agent(
        self,
        agent_name: str,
        message_text: str,
        task_id: str,
        context_id: str,
    ) -> Task:
        """Send message to another agent and get task back"""

        if agent_name not in self.clients:
            # Initialize client for this agent
            agent_url = self.agent_registry[agent_name]
            card_resolver = A2ACardResolver(httpx.AsyncClient(), agent_url)
            card = await card_resolver.get_agent_card()
            self.clients[agent_name] = A2AClient(
                httpx.AsyncClient(),
                card,
                url=agent_url
            )

        client = self.clients[agent_name]

        message_request = SendMessageRequest(
            id=str(uuid.uuid4()),
            params=MessageSendParams(
                message=Message(
                    message_id=str(uuid.uuid4()),
                    role=Role.user,
                    parts=[TextPart(text=message_text)],
                    task_id=task_id,
                    context_id=context_id,
                )
            )
        )

        response = await client.send_message(message_request)

        if isinstance(response.root, SendMessageSuccessResponse):
            if isinstance(response.root.result, Task):
                return response.root.result

        raise Exception(f"Failed to get task from {agent_name}")
```

### Phase 2: Update BaseAgent to Use Task-Aware Patterns

```python
# src/common/base_agent.py (additional methods)

class BaseAgent(AgentExecutor):

    async def _ask_agent(
        self,
        agent_name: str,
        question: str,
        current_task: Task,
    ) -> str:
        """Ask another agent a question within current task context"""

        # Use existing context_id but don't reuse task_id
        # (other agent will create its own task)
        remote_task = await self.communicator.send_message_to_agent(
            agent_name=agent_name,
            message_text=question,
            task_id=None,  # Let remote agent create new task
            context_id=current_task.context_id,  # Share context
        )

        # Wait for completion or get current status
        # (In real implementation, might use streaming or polling)

        # Extract answer from task artifacts or history
        if remote_task.artifacts:
            return remote_task.artifacts[-1].parts[0].text

        if remote_task.history:
            last_message = remote_task.history[-1]
            return last_message.parts[0].text

        return remote_task.status.message.parts[0].text

    async def _build_context_package(
        self,
        task: Task,
        analysis: dict,
        specs: dict,
    ) -> dict:
        """Build context files for Claude Code execution"""

        workspace = self.config.workspace / f"tasks/{task.id}"
        workspace.mkdir(parents=True, exist_ok=True)

        # CONTEXT.md - Agent identity and task background
        context_md = workspace / "CONTEXT.md"
        context_md.write_text(f"""# Task Context

## Agent Role
{self.config.role}

## Agent Capabilities
{', '.join(self.config.capabilities)}

## Task ID
{task.id}

## Context ID
{task.context_id}

## Task History
{self._format_task_history(task)}

## Analysis
{analysis}
""")

        # SPECS.md - Requirements from other agents
        if specs:
            specs_md = workspace / "SPECS.md"
            specs_md.write_text(f"""# Specifications from Other Agents

{self._format_specs(specs)}
""")

        # INSTRUCTIONS.md - What to build
        instructions_md = workspace / "INSTRUCTIONS.md"
        instructions_md.write_text(f"""# Implementation Instructions

{analysis.get('instructions', '')}

## Success Criteria
{analysis.get('success_criteria', '')}

## Implementation Approach
{analysis.get('approach', '')}
""")

        return {
            'workspace': workspace,
            'context_file': context_md,
            'specs_file': specs_md if specs else None,
            'instructions_file': instructions_md,
        }

    async def _execute_with_claude_code(
        self,
        task: Task,
        context_package: dict,
        event_queue: EventQueue,
    ):
        """Execute task using Claude Code in tmux"""

        # Send command to Claude terminal
        command = f"""
Please implement the task described in:
- {context_package['context_file']}
- {context_package['instructions_file']}
{f"- {context_package['specs_file']}" if context_package['specs_file'] else ""}

Work in the directory: {context_package['workspace']}
"""

        await self.claude_terminal.send_command(command)

        # Monitor output and send status updates
        # (Simplified - real implementation would parse output)
        while not self.claude_terminal.is_complete():
            output = await self.claude_terminal.capture_output()

            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    status=TaskStatus(
                        state=TaskState.working,
                        message=new_agent_text_message(
                            output[-200:],  # Last 200 chars
                            task.context_id,
                            task.id,
                        ),
                    ),
                    final=False,
                    context_id=task.context_id,
                    task_id=task.id,
                )
            )

            await asyncio.sleep(2)  # Poll every 2 seconds
```

### Phase 3: Update Host Agent for Task Coordination

```python
# src/host_agent/executor.py

class HostAgentExecutor:
    """Orchestrator that manages task delegation"""

    def __init__(self):
        self.agent_communicator = AgentCommunicator({
            'frontend': 'http://localhost:8001',
            'backend': 'http://localhost:8002',
            'pm': 'http://localhost:8003',
            'ux': 'http://localhost:8004',
        })
        self.context_id = str(uuid.uuid4())  # Session context

    async def handle_user_request(self, user_input: str):
        """Process user request and coordinate agents"""

        # 1. Analyze which agents are needed
        plan = await self._analyze_request(user_input)

        # 2. Execute plan with task delegation
        tasks = []
        for step in plan.steps:
            task = await self.agent_communicator.send_message_to_agent(
                agent_name=step.agent,
                message_text=step.instructions,
                task_id=None,  # New task per agent
                context_id=self.context_id,  # Shared context
            )
            tasks.append(task)

        # 3. Wait for all tasks to complete
        # (In real impl, would use streaming/polling)

        # 4. Synthesize results
        return self._synthesize_results(tasks)
```

## Migration Path

### Immediate Actions (Week 1)
1. ✅ Understand Task vs Message distinction
2. ⬜ Add `task_store.py` with InMemoryTaskStore
3. ⬜ Update `base_agent.py` to accept RequestContext and EventQueue
4. ⬜ Implement basic task lifecycle (create → working → completed)

### Short Term (Week 2-3)
5. ⬜ Add `agent_communication.py` for inter-agent messaging
6. ⬜ Update all agent configs to include agent_registry
7. ⬜ Implement streaming status updates during Claude Code execution
8. ⬜ Add artifact generation for Claude Code outputs

### Medium Term (Week 4-5)
9. ⬜ Add file-based task persistence
10. ⬜ Implement task history management
11. ⬜ Add task cancellation support
12. ⬜ Implement error handling and failed state

### Long Term (Week 6+)
13. ⬜ Add task resubscription for long-running work
14. ⬜ Implement push notifications for async updates
15. ⬜ Add authenticated extended card support
16. ⬜ Performance optimization and monitoring

## Key Architectural Decisions

### Decision 1: Task per Agent Work Unit
**Rule**: Each agent creates its own task for work it performs.
**Rationale**: Allows independent tracking of each agent's work.
**Example**: Frontend building login form = 1 task. Backend building API = different task. Both share same context_id.

### Decision 2: Shared Context Across Collaboration
**Rule**: All agents working on the same user request share a context_id.
**Rationale**: Maintains conversation history and allows referencing previous work.
**Example**: "Build authentication system" gets one context_id used by PM, UX, Frontend, and Backend.

### Decision 3: Claude Code Execution is Part of Task
**Rule**: Claude Code execution is not a separate task, it's part of the agent's task.
**Rationale**: The agent (Intelligence Layer) is responsible for the task. Claude Code (Execution Layer) is just the tool it uses.
**Example**: Frontend Agent's task includes analysis + coordination + Claude Code execution + result collection.

### Decision 4: Messages for Quick Questions, Tasks for Work
**Rule**: Use Messages for clarification/info gathering. Use Tasks for actual work.
**Rationale**: Tasks are heavyweight (state, history, artifacts). Messages are lightweight.
**Example**:
- Message: "What's the API endpoint format?" (answer in seconds)
- Task: "Build the login API" (work for minutes/hours)

### Decision 5: EventQueue for Streaming Updates
**Rule**: All task updates go through EventQueue, not direct responses.
**Rationale**: Enables streaming, persistence, and async notifications.
**Example**: During Claude Code execution, send periodic TaskStatusUpdateEvent to show progress.

## Testing Strategy

### Unit Tests
- TaskStore save/retrieve
- TaskManager state transitions
- Message creation and validation
- Task lifecycle state machine

### Integration Tests
- Agent-to-agent communication via A2A
- Task context sharing across agents
- EventQueue event processing
- Claude Code execution with task updates

### End-to-End Tests
- User request → Multi-agent coordination → Task completion
- Task history accumulation across interactions
- Artifact generation and retrieval
- Error handling and task failure

## Success Metrics

1. **Task Traceability**: Every piece of work has a trackable task_id
2. **Context Continuity**: Can reference previous work via context_id
3. **Status Visibility**: Real-time task state updates during execution
4. **Artifact Persistence**: All generated code/files attached to tasks
5. **Agent Coordination**: Agents can delegate work and receive results via A2A

## Conclusion

The key insight is that **Tasks are the unit of persistent work**, while **Messages are ephemeral communication**. Our multi-agent system needs to:

1. Create tasks for each agent's work unit
2. Share context_id across collaborative work
3. Use EventQueue for streaming updates
4. Attach artifacts to completed tasks
5. Maintain task history for context

This aligns perfectly with A2A protocol patterns and provides the infrastructure needed for robust multi-agent coordination with Claude Code execution.
