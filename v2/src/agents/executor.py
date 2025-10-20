"""Claude Code executor for A2A agents."""

import asyncio
import json
import logging
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

# Configure logger
logger = logging.getLogger(__name__)


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

        logger.info(f"[{self.agent_role}] Starting execution")
        logger.debug(f"[{self.agent_role}] Context: {context}")
        logger.debug(f"[{self.agent_role}] Workspace: {self.workspace}")

        # 1. Get or create task
        task = context.current_task
        if not task:
            logger.info(f"[{self.agent_role}] Creating new task")
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
            logger.debug(f"[{self.agent_role}] Task created with ID: {task.id}")
        else:
            logger.info(f"[{self.agent_role}] Using existing task: {task.id}")

        # 2. Build instruction
        user_input = context.get_user_input()
        logger.debug(f"[{self.agent_role}] User input: {user_input[:100]}...")

        task_history = task.history if task and task.history else []
        logger.debug(f"[{self.agent_role}] Task history length: {len(task_history)}")

        instruction = self._build_instruction(user_input, task_history)
        logger.debug(f"[{self.agent_role}] Built instruction (length: {len(instruction)} chars)")
        logger.debug(f"[{self.agent_role}] Full instruction:\n{instruction}")

        # 3. Send "working" status
        logger.info(f"[{self.agent_role}] Sending 'working' status event")
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
        logger.debug(f"[{self.agent_role}] 'working' status event sent")

        try:
            # 4. Call Claude Code headless (runs in workspace directory)
            cmd = ["claude", "-p", instruction, "--allowedTools", "Edit", "Bash", "Write", "--output-format", "json"]
            logger.info(f"[{self.agent_role}] Executing Claude Code headless")
            logger.debug(f"[{self.agent_role}] Command: {' '.join(cmd[:2])} [instruction] {' '.join(cmd[3:])}")
            logger.debug(f"[{self.agent_role}] Working directory: {self.workspace}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace),  # Set working directory
            )

            logger.debug(f"[{self.agent_role}] Process started, PID: {process.pid}")
            logger.info(f"[{self.agent_role}] Waiting for Claude Code to complete...")

            stdout, stderr = await process.communicate()

            logger.debug(f"[{self.agent_role}] Process completed with return code: {process.returncode}")
            logger.debug(f"[{self.agent_role}] STDOUT length: {len(stdout)} bytes")
            logger.debug(f"[{self.agent_role}] STDERR length: {len(stderr)} bytes")

            if stderr:
                logger.warning(f"[{self.agent_role}] STDERR output:\n{stderr.decode()}")

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"[{self.agent_role}] Claude Code failed with code {process.returncode}")
                logger.error(f"[{self.agent_role}] Error: {error_msg}")
                raise Exception(f"Claude Code failed: {error_msg}")

            # 5. Parse JSON output
            stdout_str = stdout.decode()
            logger.debug(f"[{self.agent_role}] Raw STDOUT:\n{stdout_str}")

            logger.info(f"[{self.agent_role}] Parsing JSON output")
            try:
                result = json.loads(stdout_str)
                logger.debug(f"[{self.agent_role}] Parsed result keys: {list(result.keys())}")
                logger.debug(f"[{self.agent_role}] Result: {result}")
            except json.JSONDecodeError as e:
                logger.error(f"[{self.agent_role}] Failed to parse JSON: {e}")
                logger.error(f"[{self.agent_role}] Invalid JSON output:\n{stdout_str}")
                raise

            # 6. Send artifact with result
            result_text = result.get("result", str(result))
            logger.info(f"[{self.agent_role}] Sending artifact event (result length: {len(result_text)} chars)")
            logger.debug(f"[{self.agent_role}] Result text preview: {result_text[:200]}...")

            await event_queue.enqueue_event(
                TaskArtifactUpdateEvent(
                    task_id=task.id,
                    context_id=task.context_id,
                    artifact=new_text_artifact(
                        name="result",
                        description=f"Result from {self.agent_role}",
                        text=result_text,
                    ),
                )
            )
            logger.debug(f"[{self.agent_role}] Artifact event sent")

            # 7. Send completion
            logger.info(f"[{self.agent_role}] Sending completion event")
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    task_id=task.id,
                    context_id=task.context_id,
                    status=TaskStatus(state=TaskState.completed),
                    final=True,
                )
            )
            logger.info(f"[{self.agent_role}] Execution completed successfully")

        except Exception as e:
            # Send failure
            logger.error(f"[{self.agent_role}] Execution failed with exception: {type(e).__name__}")
            logger.error(f"[{self.agent_role}] Error message: {str(e)}")
            logger.exception(f"[{self.agent_role}] Full traceback:")

            logger.info(f"[{self.agent_role}] Sending failure event")
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
            logger.debug(f"[{self.agent_role}] Failure event sent")

    def _build_instruction(self, user_input: str, history: list) -> str:
        """Build instruction from user input and task history."""
        logger.debug(f"[{self.agent_role}] Building instruction from {len(history)} history messages")

        context_summary = "\n".join(
            [
                f"{msg.role}: {self._extract_text(msg)}"
                for msg in history[-5:]  # Last 5 messages for context
            ]
        )

        if context_summary:
            logger.debug(f"[{self.agent_role}] Context summary:\n{context_summary}")
        else:
            logger.debug(f"[{self.agent_role}] No context summary (empty history)")

        instruction = f"""You are a {self.agent_role}.

{self.system_prompt}

Previous context:
{context_summary}

Current request:
{user_input}
"""
        logger.debug(f"[{self.agent_role}] Instruction built successfully")
        return instruction

    def _extract_text(self, message) -> str:
        """Extract text from message parts."""
        texts = []
        for part in message.parts:
            if hasattr(part, "text"):
                texts.append(part.text)
                logger.debug(f"[{self.agent_role}] Extracted text part: {part.text[:50]}...")

        result = " ".join(texts)
        logger.debug(f"[{self.agent_role}] Total extracted text length: {len(result)} chars")
        return result

    @override
    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """Cancel not supported for Claude Code headless mode."""
        raise Exception("cancel not supported")
