"""Base agent class with dual-layer architecture (Intelligence + Execution)."""

import asyncio
import json
import os
import time
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

from .agent_communication import AgentCommunicator
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

        # Coordination: Inter-agent communication
        self.communicator = AgentCommunicator(
            agent_registry=config.agent_registry,
            timeout=30
        )

        # Task Queue: Single-threaded execution
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.is_executing: bool = False
        self.current_task_id: Optional[str] = None
        self._queue_processor_task: Optional[asyncio.Task] = None

        # State
        self._is_running = False

        self.logger.info(f"Initialized {config.role} agent on port {config.port}")
        if config.agent_registry:
            self.logger.debug(
                f"Agent registry configured with {len(config.agent_registry)} agents: "
                f"{list(config.agent_registry.keys())}"
            )

    async def start(self):
        """Start the agent (initialize connections and Claude terminal)."""
        if self._is_running:
            return

        self.logger.section(f"Starting {self.config.role} Agent")

        # Start agent communicator
        await self.communicator.start()

        # Start Claude Code terminal
        self.claude_terminal.start()

        # Start queue processor in background
        self._queue_processor_task = asyncio.create_task(self._process_task_queue())
        self.logger.debug("Started task queue processor")

        self._is_running = True
        self.logger.success(f"{self.config.role} agent started")

    async def stop(self):
        """Stop the agent (cleanup connections and Claude terminal)."""
        if not self._is_running:
            return

        self.logger.info(f"Stopping {self.config.role} agent")

        # Cancel queue processor
        if self._queue_processor_task:
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass
            self.logger.debug("Stopped task queue processor")

        # Stop Claude Code terminal
        self.claude_terminal.stop()

        # Stop agent communicator
        await self.communicator.stop()

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
        Execute a task - either immediately or queue if busy.

        This is the main entry point for A2A requests.

        Args:
            context: Request context with message and task info
            event_queue: Queue for sending status updates
        """
        # Convenience updater for status updates
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        # Check if Claude Code is currently executing
        if self.is_executing:
            # Queue the task
            queue_size = self.task_queue.qsize() + 1  # +1 for this task
            self.logger.info(
                f"Claude Code busy with task {self.current_task_id}, "
                f"queueing task {context.task_id} (queue position: {queue_size})"
            )

            # Update status to submitted (task is queued)
            await updater.update_status(TaskState.submitted)

            # Add to queue
            await self.task_queue.put((context, event_queue))
            return

        # Execute immediately
        await self._execute_task(context, event_queue)

    async def _process_task_queue(self):
        """Background processor for queued tasks."""
        self.logger.debug("Task queue processor started")

        while True:
            try:
                # Wait for next task
                context, event_queue = await self.task_queue.get()

                # Execute the task
                self.logger.info(f"Processing queued task {context.task_id}")
                await self._execute_task(context, event_queue)

                # Mark as done
                self.task_queue.task_done()

            except asyncio.CancelledError:
                self.logger.debug("Task queue processor cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error processing queued task: {e}")
                import traceback
                traceback.print_exc()

    async def _execute_task(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ):
        """
        Internal method that actually executes the task.

        This contains the core task execution logic.

        Args:
            context: Request context with message and task info
            event_queue: Queue for sending status updates
        """
        # Set execution flag
        self.is_executing = True
        self.current_task_id = context.task_id

        try:
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

            # Check task type
            task_type = analysis.get('task_type', 'execution')
            self.logger.info(f"Task type: {task_type}")

            if task_type == 'informational':
                # Informational query - answer directly without execution
                self.logger.info("Informational query detected - answering directly")

                # Get direct answer from analysis
                direct_answer = analysis.get('direct_answer', 'I can help with that.')

                # Ensure answer is a string (handle cases where Claude returns JSON/dict)
                if isinstance(direct_answer, dict):
                    # Convert dict to readable text
                    direct_answer = json.dumps(direct_answer, indent=2)
                elif not isinstance(direct_answer, str):
                    # Convert other types to string
                    direct_answer = str(direct_answer)

                # Send answer as artifact
                answer_parts = [TextPart(text=direct_answer)]
                await updater.add_artifact(answer_parts)

                # Status: Completed
                await updater.update_status(TaskState.completed, final=True)
                self.logger.success("Informational query answered successfully")

            else:
                # Execution task - full pipeline with Claude Code
                self.logger.info("Execution task detected - proceeding with full pipeline")

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
                self._send_to_claude(
                    analysis.get('execution_instruction', task_description),
                    context.task_id
                )

                # Phase 4.5: Monitor execution with streaming updates
                self.logger.info("Phase 4.5: Monitoring execution with streaming updates...")
                await self._monitor_claude_execution(
                    task_id=context.task_id,
                    task_manager=task_manager,
                    updater=updater,
                    max_duration=300,  # 5 minutes max
                    update_interval=5   # Update every 5 seconds
                )

                # Phase 5: Collection - Gather results and generate artifacts
                self.logger.info("Phase 5: Collecting results and generating artifacts...")
                await self._collect_and_send_artifacts(
                    task_manager=task_manager,
                    updater=updater,
                    task_id=context.task_id
                )

                # Status: Completed
                await updater.update_status(TaskState.completed, final=True)
                self.logger.success("Task completed successfully")

        except Exception as e:
            self.logger.error(f"Task execution failed: {e}")
            import traceback
            traceback.print_exc()
            await updater.add_artifact([TextPart(text=f"Error: {str(e)}")])
            await updater.update_status(TaskState.failed, final=True)

        finally:
            # Clear execution flag
            self.is_executing = False
            self.current_task_id = None
            self.logger.debug(f"Execution flag cleared for task {context.task_id}")

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
- task_type: "informational" | "execution"
  * "informational": Questions, explanations, capability queries (answer directly)
  * "execution": Building, coding, creating artifacts (needs Claude Code execution)
- needs_coordination: true/false (do you need input from other agents?)
- required_agents: list of agent names needed (options: {', '.join(self.config.related_agents)})
- execution_instruction: clear instruction for executing this task
- complexity: "simple", "moderate", or "complex"
- key_requirements: list of key requirements
- direct_answer: (if task_type="informational") provide a complete answer to the user's question

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
                    'task_type': 'execution',  # Default to execution if unsure
                    'needs_coordination': False,
                    'required_agents': [],
                    'execution_instruction': task,
                    'complexity': 'moderate',
                    'key_requirements': [],
                    'direct_answer': None
                }

            self.logger.debug(f"Analysis: {json.dumps(analysis, indent=2)}")
            return analysis

        except Exception as e:
            self.logger.error(f"Analysis failed: {e}")
            # Return basic analysis on error
            return {
                'task_type': 'execution',  # Default to execution on error
                'needs_coordination': False,
                'required_agents': [],
                'execution_instruction': task,
                'complexity': 'unknown',
                'key_requirements': [],
                'direct_answer': None
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

        Uses the AgentCommunicator to send a message and get a response.

        Args:
            agent_name: Name of the agent to ask
            question: Question/request to send
            context: Request context

        Returns:
            Response dictionary with 'response' key containing agent's answer
        """
        try:
            # Use communicator to ask the agent
            response_text = await self.communicator.ask_agent(
                agent_name=agent_name,
                question=question,
                context_id=context.context_id
            )

            return {"response": response_text}

        except Exception as e:
            self.logger.error(f"Failed to ask {agent_name}: {e}")
            return {"response": f"Error communicating with {agent_name}: {str(e)}"}

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

    def _send_to_claude(self, instruction: str, task_id: str):
        """
        Send instruction to Claude Code terminal with task-specific completion protocol.

        Args:
            instruction: Instruction to send
            task_id: Task ID for naming the summary file
        """
        # Ensure summaries directory exists
        summaries_dir = self.claude_terminal.workspace / "summaries"
        summaries_dir.mkdir(exist_ok=True)

        # Create instruction with task-specific completion file
        command = f"""{instruction}. Read CONTEXT.md and INSTRUCTIONS.md for full details.

CRITICAL: When you complete this task, create a file named summaries/{task_id}.md with:

# Task Completion Summary

## Objective
[What was the task?]

## Accomplishments
- [Bullet point 1]
- [Bullet point 2]

## Key Deliverables
- `path/to/file1.ext` - Description of file 1
- `path/to/file2.ext` - Description of file 2
[List ONLY the essential files that should be returned as artifacts]

## Test Results
✅ All X tests passed
[OR] ⏭️ No tests (explanation)
[OR] ❌ X tests failed

## Important Notes
- [Any caveats, issues, or recommendations]

## Status
✅ COMPLETED [OR] ⚠️ PARTIAL [OR] ❌ FAILED

Do not proceed to other tasks until summaries/{task_id}.md is created."""

        # Send command
        success = self.claude_terminal.send_command(command)

        if not success:
            raise RuntimeError("Failed to send command to Claude Code")

        self.logger.debug(f"Sent instruction to Claude Code with task-specific summary protocol")
        self.logger.warning("⚠️  User action required: Claude Code may require approval - check the terminal window")

    async def _monitor_claude_execution(
        self,
        task_id: str,
        task_manager: TaskManager,
        updater: TaskUpdater,
        max_duration: int = 300,
        update_interval: int = 5
    ):
        """
        Monitor Claude Code execution by checking for task-specific completion file.

        Double Enter pattern is handled in _send_to_claude() - both Enters sent sequentially.
        This method just monitors for the completion file and sends status updates.

        Args:
            task_id: Task ID for locating summary file
            task_manager: Task manager for this execution
            updater: TaskUpdater for sending status updates
            max_duration: Maximum duration in seconds (default: 5 minutes)
            update_interval: Seconds between checks (default: 5)
        """
        start_time = time.time()
        last_output = ""
        update_count = 0

        # Task-specific completion file
        complete_file = self.claude_terminal.workspace / "summaries" / f"{task_id}.md"

        self.logger.debug(f"Monitoring for completion file: {complete_file}")

        while True:
            elapsed = time.time() - start_time

            # Check timeout
            if elapsed > max_duration:
                self.logger.warning(
                    f"Max duration reached ({max_duration}s), stopping monitoring"
                )
                break

            # Check for completion marker file
            if complete_file.exists():
                self.logger.success(f"Task completion detected: {complete_file}")
                break

            # Capture latest output for status updates
            current_output = self.claude_terminal.capture_output(max_lines=50)

            # Send periodic status update if output changed
            if current_output and current_output != last_output:
                # Extract last few lines as summary
                lines = current_output.strip().split('\n')
                recent_lines = lines[-5:] if len(lines) > 5 else lines
                summary = '\n'.join(recent_lines)

                # Send status update (just state, no message)
                try:
                    await updater.update_status(TaskState.working)
                    update_count += 1
                    self.logger.debug(f"Sent status update #{update_count} [{int(elapsed)}s]")

                except Exception as e:
                    self.logger.error(f"Failed to send status update: {e}")

                last_output = current_output

            # Wait before next check
            await asyncio.sleep(update_interval)

        self.logger.info(
            f"Monitoring completed after {int(elapsed)}s with {update_count} updates"
        )

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

    async def _collect_and_send_artifacts(
        self,
        task_manager: TaskManager,
        updater: TaskUpdater,
        task_id: str
    ):
        """
        Collect results from workspace and send as artifacts.

        Implements the task-specific summary protocol:
        1. Primary artifact: summaries/{task_id}.md (always)
        2. Key deliverables: Only files listed in summary (max 4)
        3. Max 5 artifacts total

        Args:
            task_manager: Task manager for accessing task context
            updater: TaskUpdater for sending artifacts
            task_id: Task ID for locating summary file
        """
        workspace = self.claude_terminal.workspace

        # 1. Primary artifact: Task-specific summary
        summary_file = workspace / "summaries" / f"{task_id}.md"

        if summary_file.exists():
            summary_content = summary_file.read_text()
            await updater.add_artifact([TextPart(text=summary_content)])
            self.logger.success(f"Sent primary artifact: {summary_file.name}")
        else:
            # Fallback if no summary file
            self.logger.warning(f"Summary file not found: {summary_file}")
            fallback_summary = self._create_fallback_summary(task_id)
            summary_content = fallback_summary
            await updater.add_artifact([TextPart(text=fallback_summary)])
            self.logger.info("Sent fallback summary")

        # 2. Extract key deliverables from summary
        key_files = self._extract_key_deliverables_from_summary(summary_content)
        self.logger.info(f"Found {len(key_files)} key deliverables")

        # 3. Send only key deliverables (max 4)
        sent_count = 0
        for file_path_str in key_files[:4]:
            full_path = workspace / file_path_str
            if full_path.exists():
                try:
                    content = full_path.read_text()
                    await updater.add_artifact([TextPart(text=content)])
                    sent_count += 1
                    self.logger.debug(f"Sent deliverable: {file_path_str}")
                except Exception as e:
                    self.logger.error(f"Failed to read {file_path_str}: {e}")
            else:
                self.logger.warning(f"Deliverable not found: {file_path_str}")

        self.logger.info(f"Sent {sent_count + 1} artifacts total (1 summary + {sent_count} deliverables)")

    def _extract_key_deliverables_from_summary(self, summary: str) -> list[str]:
        """
        Extract file paths from the Key Deliverables section of summary.

        Args:
            summary: Summary file content

        Returns:
            List of relative file paths
        """
        import re

        # Look for Key Deliverables section
        match = re.search(
            r'## Key Deliverables\s*\n(.*?)(?:\n##|\Z)',
            summary,
            re.DOTALL | re.IGNORECASE
        )

        if not match:
            self.logger.debug("No Key Deliverables section found in summary")
            return []

        deliverables_section = match.group(1)

        # Extract file paths from markdown list items
        # Pattern: - `path/to/file.ext` - Description
        file_paths = re.findall(r'-\s*`([^`]+)`', deliverables_section)

        self.logger.debug(f"Extracted {len(file_paths)} deliverable paths from summary")
        return file_paths

    def _create_fallback_summary(self, task_id: str) -> str:
        """
        Create fallback summary if Claude Code didn't create one.

        Args:
            task_id: Task ID

        Returns:
            Fallback summary content
        """
        terminal_output = self.claude_terminal.capture_output(max_lines=100)
        workspace_files = self.claude_terminal.get_workspace_files()

        # Filter out context files and summaries
        context_files = {'CONTEXT.md', 'SPECS.md', 'INSTRUCTIONS.md'}
        generated_files = [
            f.relative_to(self.claude_terminal.workspace)
            for f in workspace_files
            if f.name not in context_files
            and 'summaries/' not in str(f.relative_to(self.claude_terminal.workspace))
        ]

        return f"""# Task Completion Summary

## Objective
Task {task_id}

## Accomplishments
Claude Code executed the task. See terminal output below.

## Key Deliverables
{chr(10).join(f'- `{f}` - Generated file' for f in generated_files[:4])}

## Test Results
⏭️ Status unknown (summary not created by Claude Code)

## Terminal Output
```
{terminal_output[-1000:] if terminal_output else 'No output captured'}
```

## Important Notes
- Summary file was not created by Claude Code
- This is an auto-generated fallback summary

## Status
⚠️ PARTIAL - Summary not created by Claude Code
"""

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

    def get_queue_status(self) -> dict:
        """
        Get current task queue status.

        Returns:
            Dictionary with queue status information
        """
        return {
            "agent_name": self.config.name,
            "is_executing": self.is_executing,
            "current_task_id": self.current_task_id,
            "queued_tasks": self.task_queue.qsize(),
            "agent_role": self.config.role
        }

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
