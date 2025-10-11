"""Claude Code executor for A2A agents."""

import asyncio
import json
from pathlib import Path
from typing import override

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    TaskStatus,
    TaskState,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
)
from a2a.utils import new_task, new_agent_text_message, new_text_artifact


class ClaudeCodeExecutor(AgentExecutor):
    """Executes coding tasks using Claude Code headless mode."""

    def __init__(self, workspace: Path, agent_role: str, system_prompt: str):
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

    @override
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
        task_history = task.history if task and task.history else []
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
                "-p",
                instruction,
                "--output-format",
                "json",
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
                        text=result.get("result", str(result)),
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
        context_summary = "\n".join(
            [
                f"{msg.role}: {self._extract_text(msg)}"
                for msg in history[-5:]  # Last 5 messages for context
            ]
        )

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
            if hasattr(part, "text"):
                texts.append(part.text)
        return " ".join(texts)

    @override
    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """Cancel not supported for Claude Code headless mode."""
        raise Exception("cancel not supported")
