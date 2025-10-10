"""Task storage with in-memory and file-based persistence."""

import json
import logging
from pathlib import Path
from typing import Optional

from a2a.server.context import ServerCallContext
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import Task

logger = logging.getLogger(__name__)


class ClaudeCodeTaskStore(InMemoryTaskStore):
    """
    Task store with file-based persistence for resilience.

    Extends InMemoryTaskStore to add:
    1. File-based persistence for task state
    2. Task recovery on restart
    3. Task history tracking

    Tasks are stored both in-memory (for fast access) and on disk (for persistence).
    """

    def __init__(self, workspace_dir: Path, agent_name: str):
        """
        Initialize the task store.

        Args:
            workspace_dir: Base workspace directory for the agent
            agent_name: Name of the agent (for logging and organization)
        """
        super().__init__()
        self.workspace_dir = workspace_dir
        self.agent_name = agent_name
        self.tasks_dir = workspace_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Initialized ClaudeCodeTaskStore for {agent_name} at {workspace_dir}"
        )

        # Load any persisted tasks on initialization
        self._load_persisted_tasks()

    async def save(
        self, task: Task, context: Optional[ServerCallContext] = None
    ) -> None:
        """
        Save task to both in-memory store and disk.

        Args:
            task: Task to save
            context: Optional server call context
        """
        # Save to in-memory store (parent class)
        await super().save(task, context)

        # Persist to disk
        try:
            self._persist_task(task)
            logger.debug(f"Persisted task {task.id} to disk")
        except Exception as e:
            logger.error(f"Failed to persist task {task.id}: {e}")
            # Don't fail the save operation if disk persistence fails
            # In-memory save was successful

    async def get(
        self, task_id: str, context: Optional[ServerCallContext] = None
    ) -> Optional[Task]:
        """
        Retrieve task from in-memory store (with disk fallback).

        Args:
            task_id: ID of the task to retrieve
            context: Optional server call context

        Returns:
            Task if found, None otherwise
        """
        # Try in-memory first
        task = await super().get(task_id, context)

        if task:
            return task

        # Fallback to disk if not in memory
        try:
            task = self._load_task_from_disk(task_id)
            if task:
                logger.debug(f"Loaded task {task_id} from disk")
                # Restore to in-memory store
                await super().save(task, context)
                return task
        except Exception as e:
            logger.error(f"Failed to load task {task_id} from disk: {e}")

        return None

    async def delete(
        self, task_id: str, context: Optional[ServerCallContext] = None
    ) -> None:
        """
        Delete task from both in-memory store and disk.

        Args:
            task_id: ID of the task to delete
            context: Optional server call context
        """
        # Delete from in-memory store
        await super().delete(task_id, context)

        # Delete from disk
        try:
            task_file = self.tasks_dir / f"{task_id}.json"
            if task_file.exists():
                task_file.unlink()
                logger.debug(f"Deleted task {task_id} from disk")
        except Exception as e:
            logger.error(f"Failed to delete task {task_id} from disk: {e}")

    def _persist_task(self, task: Task) -> None:
        """
        Persist task to disk as JSON.

        Args:
            task: Task to persist
        """
        task_file = self.tasks_dir / f"{task.id}.json"

        # Convert task to JSON (using Pydantic's serialization)
        task_json = task.model_dump_json(indent=2, exclude_none=True)

        # Write to file
        task_file.write_text(task_json)

    def _load_task_from_disk(self, task_id: str) -> Optional[Task]:
        """
        Load task from disk.

        Args:
            task_id: ID of the task to load

        Returns:
            Task if found on disk, None otherwise
        """
        task_file = self.tasks_dir / f"{task_id}.json"

        if not task_file.exists():
            return None

        # Read JSON from file
        task_json = task_file.read_text()

        # Parse into Task object
        task = Task.model_validate_json(task_json)

        return task

    def _load_persisted_tasks(self) -> None:
        """
        Load all persisted tasks from disk into in-memory store.

        Called during initialization to recover tasks after restart.
        """
        try:
            task_files = list(self.tasks_dir.glob("*.json"))

            if not task_files:
                logger.debug(f"No persisted tasks found for {self.agent_name}")
                return

            loaded_count = 0
            for task_file in task_files:
                try:
                    task_json = task_file.read_text()
                    task = Task.model_validate_json(task_json)

                    # Add to in-memory store (synchronous access to parent's _tasks dict)
                    # Note: InMemoryTaskStore stores tasks in a dict _tasks
                    if hasattr(self, '_tasks'):
                        self._tasks[task.id] = task
                        loaded_count += 1

                except Exception as e:
                    logger.error(f"Failed to load task from {task_file}: {e}")

            if loaded_count > 0:
                logger.info(
                    f"Loaded {loaded_count} persisted tasks for {self.agent_name}"
                )

        except Exception as e:
            logger.error(f"Failed to load persisted tasks: {e}")

    def get_all_tasks(self) -> list[Task]:
        """
        Get all tasks in the store (in-memory).

        Returns:
            List of all tasks
        """
        if hasattr(self, '_tasks'):
            return list(self._tasks.values())
        return []

    def get_tasks_by_context(self, context_id: str) -> list[Task]:
        """
        Get all tasks for a specific context.

        Args:
            context_id: Context ID to filter by

        Returns:
            List of tasks with the given context_id
        """
        if hasattr(self, '_tasks'):
            return [
                task for task in self._tasks.values()
                if task.context_id == context_id
            ]
        return []

    def get_task_stats(self) -> dict:
        """
        Get statistics about tasks in the store.

        Returns:
            Dictionary with task statistics
        """
        tasks = self.get_all_tasks()

        stats = {
            'total_tasks': len(tasks),
            'by_state': {},
            'by_context': {},
        }

        for task in tasks:
            # Count by state
            state = task.status.state.value
            stats['by_state'][state] = stats['by_state'].get(state, 0) + 1

            # Count by context
            context_id = task.context_id
            stats['by_context'][context_id] = stats['by_context'].get(context_id, 0) + 1

        return stats

    def cleanup_completed_tasks(self, keep_recent: int = 10) -> int:
        """
        Clean up old completed tasks, keeping only recent ones.

        Args:
            keep_recent: Number of recent completed tasks to keep

        Returns:
            Number of tasks cleaned up
        """
        if not hasattr(self, '_tasks'):
            return 0

        completed_tasks = [
            task for task in self._tasks.values()
            if task.status.state.value in ['completed', 'canceled', 'failed']
        ]

        # Sort by timestamp (most recent first)
        completed_tasks.sort(
            key=lambda t: t.status.timestamp or '',
            reverse=True
        )

        # Delete old ones
        tasks_to_delete = completed_tasks[keep_recent:]

        deleted_count = 0
        for task in tasks_to_delete:
            try:
                # Delete from in-memory
                del self._tasks[task.id]

                # Delete from disk
                task_file = self.tasks_dir / f"{task.id}.json"
                if task_file.exists():
                    task_file.unlink()

                deleted_count += 1

            except Exception as e:
                logger.error(f"Failed to delete task {task.id}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old tasks for {self.agent_name}")

        return deleted_count
