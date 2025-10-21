"""Claude Agent SDK executor for A2A agents - new implementation with real-time streaming."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import override

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage, TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock

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


class ClaudeSDKExecutor(AgentExecutor):
    """Executes coding tasks using Claude Agent SDK with real-time streaming."""

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
        """Execute coding task with Claude Agent SDK, streaming updates in real-time."""

        logger.info(f"[{self.agent_role}] Starting execution (SDK mode)")
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
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ),
                final=False,
            )
        )

        try:
            # 4. Configure SDK options
            options = ClaudeAgentOptions(
                system_prompt=self.system_prompt,
                cwd=str(self.workspace),
                permission_mode='acceptEdits',
                allowed_tools=['Edit', 'Write', 'Bash', 'Read', 'Glob', 'Grep'],
            )

            logger.info(f"[{self.agent_role}] Starting Claude Agent SDK query")
            logger.debug(f"[{self.agent_role}] Options: permission_mode={options.permission_mode}, cwd={options.cwd}")

            # 5. Stream execution with real-time updates
            result_text = ""
            tool_uses = []
            turn_count = 0

            async for message in query(prompt=instruction, options=options):
                logger.debug(f"[{self.agent_role}] Received message type: {type(message).__name__}")

                if isinstance(message, AssistantMessage):
                    # Process assistant message content
                    logger.debug(f"[{self.agent_role}] Processing AssistantMessage with {len(message.content)} blocks")

                    for block in message.content:
                        if isinstance(block, TextBlock):
                            # Accumulate text output
                            logger.debug(f"[{self.agent_role}] TextBlock: {block.text[:100]}...")
                            result_text += block.text + "\n"

                            # Send intermediate progress update
                            await self._send_progress_update(
                                event_queue=event_queue,
                                task=task,
                                update_text=f"📝 {block.text[:100]}...",
                            )

                        elif isinstance(block, ThinkingBlock):
                            # Log thinking process (if available with extended thinking)
                            logger.info(f"[{self.agent_role}] Thinking: {block.thinking[:100]}...")

                        elif isinstance(block, ToolUseBlock):
                            # Log tool usage
                            tool_uses.append(block.name)
                            logger.info(f"[{self.agent_role}] Using tool: {block.name}")

                            # Send tool usage update
                            await self._send_progress_update(
                                event_queue=event_queue,
                                task=task,
                                update_text=f"🔧 Using tool: {block.name}",
                            )

                        elif isinstance(block, ToolResultBlock):
                            # Log tool result
                            logger.debug(f"[{self.agent_role}] Tool result received")

                elif isinstance(message, ResultMessage):
                    # Handle final result metadata
                    logger.info(f"[{self.agent_role}] ResultMessage received")
                    logger.info(f"[{self.agent_role}] Duration: {message.duration_ms}ms (API: {message.duration_api_ms}ms)")
                    logger.info(f"[{self.agent_role}] Turns: {message.num_turns}")
                    logger.info(f"[{self.agent_role}] Cost: ${message.total_cost_usd:.4f}")
                    logger.info(f"[{self.agent_role}] Is error: {message.is_error}")

                    turn_count = message.num_turns

                    if message.is_error:
                        error_msg = f"Task completed with error (see logs for details)"
                        logger.error(f"[{self.agent_role}] {error_msg}")
                        raise Exception(error_msg)

                else:
                    # Log unexpected message types
                    logger.warning(f"[{self.agent_role}] Unexpected message type: {type(message).__name__}")

            # 6. Send final artifact with result
            if not result_text.strip():
                result_text = "Task completed (no text output)"
                logger.warning(f"[{self.agent_role}] No text output from Claude, using default message")

            logger.info(f"[{self.agent_role}] Sending final artifact (length: {len(result_text)} chars)")
            logger.debug(f"[{self.agent_role}] Result preview: {result_text[:200]}...")

            # Add execution summary
            summary = f"\n\n---\n**Execution Summary:**\n"
            summary += f"- Turns: {turn_count}\n"
            summary += f"- Tools used: {', '.join(tool_uses) if tool_uses else 'None'}\n"
            result_text += summary

            await event_queue.enqueue_event(
                TaskArtifactUpdateEvent(
                    task_id=task.id,
                    context_id=task.context_id,
                    artifact=new_text_artifact(
                        name="result",
                        description=f"Result from {self.agent_role}",
                        text=result_text.strip(),
                    ),
                )
            )

            # 7. Send completion
            logger.info(f"[{self.agent_role}] Sending completion event")
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    task_id=task.id,
                    context_id=task.context_id,
                    status=TaskStatus(
                        state=TaskState.completed,
                        message=new_agent_text_message(
                            f"✅ {self.agent_role} completed",
                            task.context_id,
                            task.id,
                        ),
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ),
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
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    ),
                    final=True,
                )
            )

    async def _send_progress_update(
        self,
        event_queue: EventQueue,
        task,
        update_text: str,
    ) -> None:
        """Send intermediate progress update to event queue."""
        logger.debug(f"[{self.agent_role}] Sending progress update: {update_text[:50]}...")

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task.id,
                context_id=task.context_id,
                status=TaskStatus(
                    state=TaskState.working,
                    message=new_agent_text_message(
                        update_text,
                        task.context_id,
                        task.id,
                    ),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ),
                final=False,
            )
        )

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
            logger.debug(f"[{self.agent_role}] Context summary length: {len(context_summary)} chars")
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
        """Cancel not supported for Claude Agent SDK."""
        logger.warning(f"[{self.agent_role}] Cancel called but not supported")
        raise Exception("cancel not supported")
