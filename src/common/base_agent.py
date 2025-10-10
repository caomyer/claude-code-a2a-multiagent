"""Base agent class with dual-layer architecture (Intelligence + Execution)."""

import json
import os
import uuid
from pathlib import Path
from typing import Optional

import anthropic
import httpx
from a2a.client import A2AClient, A2ACardResolver
from a2a.server.agent_execution import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.server.tasks.task_manager import TaskManager
from a2a.types import (
    AgentCard,
    MessageSendParams,
    Part,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
    TaskState,
    TextPart,
)

from .agent_config import AgentConfig
from .claude_terminal import ClaudeCodeTerminal
from .task_store import ClaudeCodeTaskStore
from .terminal_utils import TerminalLogger


class BaseAgent(AgentExecutor):
    """
    Base agent with dual-layer architecture.

    Architecture:
    1. Intelligence Layer (Claude API) - Analyzes tasks, makes decisions
    2. Coordination Layer (A2A) - Communicates with other agents
    3. Context Packaging - Creates context files for execution
    4. Execution Layer (Claude Code in tmux) - Does the actual work
    5. Collection Layer - Gathers results and artifacts

    Each specialized agent (Frontend, Backend, PM, UX) inherits from this base.
    """

    def __init__(self, config: AgentConfig):
        """
        Initialize the base agent.

        Args:
            config: Agent configuration
        """
        self.config = config
        self.logger = TerminalLogger(
            config.name,
            log_file=Path(f"logs/{config.name}.log")
        )

        # Task Management: TaskStore for persistence
        self.task_store = ClaudeCodeTaskStore(
            workspace_dir=config.workspace,
            agent_name=config.name
        )

        # Intelligence Layer: Claude API
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment")

        self.claude_api = anthropic.Anthropic(api_key=api_key)

        # Execution Layer: Claude Code Terminal
        self.claude_terminal = ClaudeCodeTerminal(
            workspace=config.workspace,
            agent_name=config.name,
            auto_open_window=True,
            logger=self.logger
        )

        # Coordination: Remote agent connections (lazy-loaded)
        self._remote_agents: dict[str, A2AClient] = {}
        self._agent_cards: dict[str, AgentCard] = {}
        self._http_client: Optional[httpx.AsyncClient] = None

        # State
        self._is_running = False

        self.logger.info(f"Initialized {config.role} agent on port {config.port}")

    async def start(self):
        """Start the agent (initialize connections and Claude terminal)."""
        if self._is_running:
            return

        self.logger.section(f"Starting {self.config.role} Agent")

        # Start HTTP client for A2A calls
        self._http_client = httpx.AsyncClient(timeout=30)

        # Start Claude Code terminal
        self.claude_terminal.start()

        self._is_running = True
        self.logger.success(f"{self.config.role} agent started")

    async def stop(self):
        """Stop the agent (cleanup connections and Claude terminal)."""
        if not self._is_running:
            return

        self.logger.info(f"Stopping {self.config.role} agent")

        # Stop Claude Code terminal
        self.claude_terminal.stop()

        # Close HTTP client
        if self._http_client:
            await self._http_client.aclose()

        self._is_running = False
        self.logger.success(f"{self.config.role} agent stopped")

    # =========================================================================
    # A2A AgentExecutor Implementation
    # =========================================================================

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ):
        """
        Execute a task received via A2A.

        This is the main entry point for A2A requests.

        Args:
            context: Request context with message and task info
            event_queue: Queue for sending status updates
        """
        # Initialize task management
        task_manager = TaskManager(
            task_id=context.task_id,
            context_id=context.context_id,
            task_store=self.task_store,
            initial_message=context.message,
            context=context.server_context if hasattr(context, 'server_context') else None
        )

        # Convenience updater for status updates
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        try:
            # Extract task from message
            task_description = self._extract_task_from_message(context.message)

            self.logger.task_info(context.task_id, task_description)

            # Get or create task
            task = await task_manager.get_task()
            if not task:
                # Task doesn't exist yet - will be created by first status update
                # Status: Submitted
                await updater.update_status(TaskState.submitted)
                self.logger.debug(f"Created new task {context.task_id}")
            else:
                self.logger.debug(f"Continuing existing task {context.task_id}")

            # Status: Working
            await updater.update_status(TaskState.working)

            # Phase 1: Intelligence - Analyze the task
            self.logger.info("Phase 1: Analyzing task with Claude API...")
            analysis = await self._analyze_task(task_description, context)

            # Phase 2: Coordination - Ask other agents if needed
            specs = {}
            if analysis.get('needs_coordination'):
                self.logger.info("Phase 2: Coordinating with other agents...")
                specs = await self._coordinate_with_agents(analysis, context)

            # Phase 3: Context Packaging - Prepare for execution
            self.logger.info("Phase 3: Packaging context for execution...")
            self._build_context_package(
                task_description,
                analysis,
                specs,
                context
            )

            # Phase 4: Execution - Send to Claude Code
            self.logger.info("Phase 4: Executing task with Claude Code...")
            self._send_to_claude(analysis.get('execution_instruction', task_description))

            # Wait for Claude Code to complete (simplified for now)
            # TODO: Implement proper completion detection
            import asyncio
            await asyncio.sleep(10)

            # Phase 5: Collection - Gather results
            self.logger.info("Phase 5: Collecting results...")
            results = self._collect_results()

            # Return results via A2A
            result_parts = [TextPart(text=results)]
            await updater.add_artifact(result_parts)
            await updater.update_status(TaskState.completed, final=True)

            self.logger.success("Task completed successfully")

        except Exception as e:
            self.logger.error(f"Task execution failed: {e}")
            await updater.add_artifact([TextPart(text=f"Error: {str(e)}")])
            await updater.update_status(TaskState.failed, final=True)

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        """
        Cancel task execution.

        Args:
            context: Request context
            event_queue: Event queue for updates
        """
        self.logger.warning(f"Cancellation requested for task {context.task_id}")
        # For now, just log it
        # TODO: Implement proper cancellation

    # =========================================================================
    # Intelligence Layer (Claude API)
    # =========================================================================

    async def _analyze_task(self, task: str, context: RequestContext) -> dict:
        """
        Analyze the task using Claude API.

        This is the intelligence layer that decides:
        - What needs to be done
        - Which other agents to consult
        - How to execute the task

        Args:
            task: Task description
            context: Request context

        Returns:
            Analysis dictionary with:
            - needs_coordination: bool
            - required_agents: list[str]
            - execution_instruction: str
            - complexity: str
        """
        analysis_prompt = f"""Analyze this task and provide a JSON response:

Task: {task}

Your role: {self.config.role}
Your capabilities: {', '.join(self.config.capabilities)}

Provide analysis as JSON with these fields:
- needs_coordination: true/false (do you need input from other agents?)
- required_agents: list of agent names needed (options: {', '.join(self.config.related_agents)})
- execution_instruction: clear instruction for executing this task
- complexity: "simple", "moderate", or "complex"
- key_requirements: list of key requirements

Response (JSON only):"""

        try:
            response = self.claude_api.messages.create(
                model=self.config.model,
                max_tokens=2048,
                system=self.config.get_claude_system_prompt(),
                messages=[{
                    "role": "user",
                    "content": analysis_prompt
                }]
            )

            # Extract JSON from response
            content = response.content[0].text

            # Try to parse JSON
            try:
                # Look for JSON in the response
                start = content.find('{')
                end = content.rfind('}') + 1
                if start != -1 and end > start:
                    json_str = content[start:end]
                    analysis = json.loads(json_str)
                else:
                    raise ValueError("No JSON found in response")
            except (json.JSONDecodeError, ValueError):
                # If JSON parsing fails, create a basic analysis
                self.logger.warning("Failed to parse JSON analysis, using defaults")
                analysis = {
                    'needs_coordination': False,
                    'required_agents': [],
                    'execution_instruction': task,
                    'complexity': 'moderate',
                    'key_requirements': []
                }

            self.logger.debug(f"Analysis: {json.dumps(analysis, indent=2)}")
            return analysis

        except Exception as e:
            self.logger.error(f"Analysis failed: {e}")
            # Return basic analysis on error
            return {
                'needs_coordination': False,
                'required_agents': [],
                'execution_instruction': task,
                'complexity': 'unknown',
                'key_requirements': []
            }

    # =========================================================================
    # Coordination Layer (A2A)
    # =========================================================================

    async def _coordinate_with_agents(
        self,
        analysis: dict,
        context: RequestContext
    ) -> dict:
        """
        Coordinate with other agents as needed.

        Args:
            analysis: Task analysis from Claude API
            context: Request context

        Returns:
            Dictionary of specifications from other agents
        """
        specs = {}
        required_agents = analysis.get('required_agents', [])

        for agent_name in required_agents:
            if agent_name in self.config.related_agents:
                try:
                    self.logger.a2a_request(
                        self.config.name,
                        agent_name,
                        f"Requesting specifications for task"
                    )

                    response = await self._ask_agent(
                        agent_name,
                        f"Provide specifications for: {analysis.get('execution_instruction')}",
                        context
                    )

                    specs[agent_name] = response
                    self.logger.a2a_response(agent_name, "completed")

                except Exception as e:
                    self.logger.error(f"Failed to coordinate with {agent_name}: {e}")
                    specs[agent_name] = {"error": str(e)}

        return specs

    async def _ask_agent(
        self,
        agent_name: str,
        question: str,
        context: RequestContext
    ) -> dict:
        """
        Ask another agent for information via A2A.

        Args:
            agent_name: Name of the agent to ask
            question: Question/request to send
            context: Request context

        Returns:
            Response from the agent
        """
        # Get or create agent client
        if agent_name not in self._remote_agents:
            await self._connect_to_agent(agent_name)

        if agent_name not in self._remote_agents:
            raise ValueError(f"Agent {agent_name} not available")

        # Create A2A message request
        message_request = SendMessageRequest(
            id=str(uuid.uuid4()),
            params=MessageSendParams(
                message={
                    'role': 'user',
                    'parts': [{'type': 'text', 'text': question}],
                    'messageId': str(uuid.uuid4()),
                    'taskId': context.task_id,
                    'contextId': context.context_id
                }
            )
        )

        # Send message
        response: SendMessageResponse = await self._remote_agents[agent_name].send_message(
            message_request
        )

        # Extract result
        if isinstance(response.root, SendMessageSuccessResponse):
            if isinstance(response.root.result, Task):
                # Extract text from artifacts
                result_text = ""
                for artifact in response.root.result.artifacts:
                    for part in artifact.parts:
                        if hasattr(part, 'text'):
                            result_text += part.text

                return {"response": result_text}

        return {"response": "No response"}

    async def _connect_to_agent(self, agent_name: str):
        """
        Connect to a remote agent.

        Args:
            agent_name: Name of the agent to connect to
        """
        if not self._http_client:
            raise ValueError("HTTP client not initialized")

        # Get agent URL from environment
        agent_url = os.getenv(f"{agent_name.upper()}_AGENT_URL")
        if not agent_url:
            # Try default port mapping
            port_map = {
                'frontend': 8001,
                'backend': 8002,
                'pm': 8003,
                'ux': 8004
            }
            port = port_map.get(agent_name.lower())
            if port:
                agent_url = f"http://localhost:{port}"
            else:
                raise ValueError(f"No URL configured for agent: {agent_name}")

        try:
            # Fetch agent card
            card_resolver = A2ACardResolver(self._http_client, agent_url)
            card = await card_resolver.get_agent_card()

            # Create A2A client
            client = A2AClient(self._http_client, card, url=agent_url)

            # Store
            self._remote_agents[agent_name] = client
            self._agent_cards[agent_name] = card

            self.logger.debug(f"Connected to {agent_name} at {agent_url}")

        except Exception as e:
            self.logger.error(f"Failed to connect to {agent_name}: {e}")

    # =========================================================================
    # Context Packaging
    # =========================================================================

    def _build_context_package(
        self,
        task: str,
        analysis: dict,
        specs: dict,
        context: RequestContext
    ):
        """
        Build context files for Claude Code.

        Creates:
        - CONTEXT.md: Agent role, capabilities, task background
        - SPECS.md: Specifications from other agents
        - INSTRUCTIONS.md: Detailed execution instructions

        Args:
            task: Original task description
            analysis: Task analysis from Claude API
            specs: Specifications from other agents
            context: Request context
        """
        # CONTEXT.md
        context_content = f"""# Agent Context

## Role
{self.config.role}

## Task ID
{context.task_id}

## Task Description
{task}

## Capabilities
{chr(10).join(f'- {cap}' for cap in self.config.capabilities)}

## Analysis
- Complexity: {analysis.get('complexity', 'unknown')}
- Coordination needed: {analysis.get('needs_coordination', False)}

## Background
This task was delegated to you as the {self.config.role}. You have the necessary
capabilities and expertise to complete it.
"""
        self.claude_terminal.write_workspace_file("CONTEXT.md", context_content)

        # SPECS.md
        if specs:
            specs_content = "# Specifications from Other Agents\n\n"
            for agent_name, spec in specs.items():
                specs_content += f"## {agent_name.title()} Agent\n\n"
                specs_content += f"{spec.get('response', 'No specifications provided')}\n\n"

            self.claude_terminal.write_workspace_file("SPECS.md", specs_content)

        # INSTRUCTIONS.md
        instructions_content = f"""# Execution Instructions

## What to Build
{analysis.get('execution_instruction', task)}

## Key Requirements
{chr(10).join(f'- {req}' for req in analysis.get('key_requirements', []))}

## Deliverables
Please provide:
1. Clean, well-structured code
2. Tests (if applicable)
3. Documentation
4. Any necessary configuration files

## Notes
- Read CONTEXT.md for your role and capabilities
- Read SPECS.md for specifications from other agents (if present)
- Work autonomously and professionally
- Ask clarifying questions if needed
"""
        self.claude_terminal.write_workspace_file("INSTRUCTIONS.md", instructions_content)

        self.logger.debug("Context package created")

    # =========================================================================
    # Execution Layer (Claude Code)
    # =========================================================================

    def _send_to_claude(self, instruction: str):
        """
        Send instruction to Claude Code terminal.

        Args:
            instruction: Instruction to send
        """
        command = f"{instruction}. Read CONTEXT.md and INSTRUCTIONS.md for full details."
        success = self.claude_terminal.send_command(command)

        if not success:
            raise RuntimeError("Failed to send command to Claude Code")

        self.logger.debug(f"Sent instruction to Claude Code")

    # =========================================================================
    # Collection Layer
    # =========================================================================

    def _collect_results(self) -> str:
        """
        Collect results from Claude Code terminal.

        Returns:
            Results summary
        """
        # Capture terminal output
        output = self.claude_terminal.capture_output(max_lines=100)

        # Get workspace files
        files = self.claude_terminal.get_workspace_files()

        # Build results summary
        results = f"""# Task Results

## Terminal Output
```
{output}
```

## Generated Files
{chr(10).join(f'- {f.name}' for f in files if f.name not in ['CONTEXT.md', 'SPECS.md', 'INSTRUCTIONS.md'])}

## Workspace
All files are available in: {self.claude_terminal.workspace}
"""

        return results

    # =========================================================================
    # Task Management Helpers
    # =========================================================================

    async def get_task(self, task_id: str) -> Optional[Task]:
        """
        Get a task by ID.

        Args:
            task_id: Task ID

        Returns:
            Task if found, None otherwise
        """
        return await self.task_store.get(task_id)

    def get_task_stats(self) -> dict:
        """
        Get statistics about tasks.

        Returns:
            Dictionary with task statistics
        """
        return self.task_store.get_task_stats()

    async def cleanup_old_tasks(self, keep_recent: int = 10) -> int:
        """
        Clean up old completed tasks.

        Args:
            keep_recent: Number of recent tasks to keep

        Returns:
            Number of tasks cleaned up
        """
        return self.task_store.cleanup_completed_tasks(keep_recent)

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _extract_task_from_message(self, message) -> str:
        """Extract task description from A2A message."""
        task_parts = []
        for part in message.parts:
            part_root = part.root if hasattr(part, 'root') else part
            if hasattr(part_root, 'text'):
                task_parts.append(part_root.text)

        return '\n'.join(task_parts)

    def __enter__(self):
        """Context manager entry."""
        import asyncio
        asyncio.run(self.start())
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        import asyncio
        asyncio.run(self.stop())
