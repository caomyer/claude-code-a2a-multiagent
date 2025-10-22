"""Task tracking service for the A2A Inspector.

This module provides task management and tracking capabilities for debugging
and monitoring A2A agent tasks. Since the A2A SDK's task listing endpoint is
not yet implemented, this tracker maintains a local cache of tasks seen through
the inspector.
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from a2a.types import Task, TaskState


logger = logging.getLogger(__name__)


class TaskTracker:
    """Tracks tasks seen through the inspector for dashboard display.

    Maintains an in-memory cache of tasks organized by agent URL. Provides
    filtering, searching, and statistics capabilities for the task dashboard.

    Attributes:
        tasks: Mapping of task_id to Task objects
        task_by_agent: Mapping of agent_url to list of task_ids
        context_groups: Mapping of context_id to list of task_ids
        max_tasks: Maximum number of tasks to retain (LRU eviction)
    """

    def __init__(self, max_tasks: int = 1000):
        """Initialize the task tracker.

        Args:
            max_tasks: Maximum number of tasks to retain before evicting oldest
        """
        self.tasks: dict[str, Task] = {}
        self.task_by_agent: dict[str, list[str]] = defaultdict(list)
        self.context_groups: dict[str, list[str]] = defaultdict(list)
        self.max_tasks = max_tasks
        self._task_order: list[str] = []  # Track insertion order for LRU

    def add_task(self, task: Task, agent_url: str) -> None:
        """Add or update a task in the tracker.

        Args:
            task: The Task object to add or update
            agent_url: The URL of the agent that owns this task
        """
        task_id = task.id

        # Update or add task
        if task_id in self.tasks:
            logger.debug(f'Updating existing task: {task_id}')
            # Move to end of LRU order
            self._task_order.remove(task_id)
        else:
            logger.debug(f'Adding new task: {task_id}')
            # Add to agent mapping
            self.task_by_agent[agent_url].append(task_id)
            # Add to context grouping
            if task.context_id:
                self.context_groups[task.context_id].append(task_id)

        self.tasks[task_id] = task
        self._task_order.append(task_id)

        # Evict oldest tasks if we exceed max
        self._evict_if_needed()

    def get_task(self, task_id: str) -> Task | None:
        """Get a single task by ID.

        Args:
            task_id: The task ID to retrieve

        Returns:
            The Task object if found, None otherwise
        """
        return self.tasks.get(task_id)

    def get_tasks(
        self,
        agent_url: str | None = None,
        context_id: str | None = None,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Task], int]:
        """Get filtered task list with pagination.

        Args:
            agent_url: Filter by agent URL (optional)
            context_id: Filter by context ID (optional)
            state: Filter by task state (optional)
            limit: Maximum number of tasks to return
            offset: Number of tasks to skip (for pagination)

        Returns:
            Tuple of (task_list, total_count) where task_list contains
            the paginated tasks and total_count is the total matching tasks
        """
        # Start with all tasks or filter by agent
        if agent_url:
            task_ids = self.task_by_agent.get(agent_url, [])
            filtered_tasks = [
                self.tasks[tid] for tid in task_ids if tid in self.tasks
            ]
        else:
            filtered_tasks = list(self.tasks.values())

        # Apply context_id filter
        if context_id:
            filtered_tasks = [
                t for t in filtered_tasks if t.context_id == context_id
            ]

        # Apply state filter
        if state:
            try:
                task_state = TaskState(state)
                filtered_tasks = [
                    t for t in filtered_tasks if t.status.state == task_state
                ]
            except ValueError:
                logger.warning(f'Invalid task state filter: {state}')

        # Sort by status timestamp descending (most recent first)
        # Timestamp is ISO 8601 string, so lexicographic sort works correctly
        filtered_tasks.sort(
            key=lambda t: t.status.timestamp if t.status.timestamp else "",
            reverse=True,
        )

        # Get total count before pagination
        total_count = len(filtered_tasks)

        # Apply pagination
        paginated_tasks = filtered_tasks[offset : offset + limit]

        logger.debug(
            f'Retrieved {len(paginated_tasks)} tasks (total: {total_count}) '
            f'with filters: agent_url={agent_url}, context_id={context_id}, '
            f'state={state}'
        )

        return paginated_tasks, total_count

    def get_stats(self, agent_url: str | None = None) -> dict[str, Any]:
        """Get task statistics.

        Args:
            agent_url: Get stats for specific agent (optional)

        Returns:
            Dictionary containing task statistics including counts by state
        """
        # Filter tasks by agent if specified
        if agent_url:
            task_ids = self.task_by_agent.get(agent_url, [])
            tasks_to_analyze = [
                self.tasks[tid] for tid in task_ids if tid in self.tasks
            ]
        else:
            tasks_to_analyze = list(self.tasks.values())

        # Count tasks by state
        state_counts = {
            'submitted': 0,
            'working': 0,
            'completed': 0,
            'failed': 0,
            'cancelled': 0,
        }

        for task in tasks_to_analyze:
            state = task.status.state.value
            if state in state_counts:
                state_counts[state] += 1

        # Calculate additional metrics
        total_tasks = len(tasks_to_analyze)
        active_tasks = state_counts['submitted'] + state_counts['working']
        active_contexts = len(
            {
                task.context_id
                for task in tasks_to_analyze
                if task.context_id and task.status.state
                in [TaskState.submitted, TaskState.working]
            }
        )

        stats = {
            'total': total_tasks,
            'active': active_tasks,
            'submitted': state_counts['submitted'],
            'working': state_counts['working'],
            'completed': state_counts['completed'],
            'failed': state_counts['failed'],
            'cancelled': state_counts['cancelled'],
            'active_contexts': active_contexts,
        }

        logger.debug(f'Task statistics for {agent_url or "all agents"}: {stats}')
        return stats

    def get_context_tasks(self, context_id: str) -> list[Task]:
        """Get all tasks for a specific context.

        Args:
            context_id: The context ID to filter by

        Returns:
            List of Task objects in this context, sorted by status timestamp
        """
        task_ids = self.context_groups.get(context_id, [])
        tasks = [self.tasks[tid] for tid in task_ids if tid in self.tasks]

        # Sort by status timestamp
        tasks.sort(key=lambda t: t.status.timestamp if t.status.timestamp else datetime.min)

        return tasks

    def remove_task(self, task_id: str) -> bool:
        """Remove a task from the tracker.

        Args:
            task_id: The task ID to remove

        Returns:
            True if task was removed, False if not found
        """
        if task_id not in self.tasks:
            return False

        task = self.tasks[task_id]

        # Remove from tasks
        del self.tasks[task_id]

        # Remove from task order
        if task_id in self._task_order:
            self._task_order.remove(task_id)

        # Remove from agent mapping
        for agent_url, task_list in self.task_by_agent.items():
            if task_id in task_list:
                task_list.remove(task_id)
                break

        # Remove from context groups
        if task.context_id and task_id in self.context_groups[task.context_id]:
            self.context_groups[task.context_id].remove(task_id)

        logger.debug(f'Removed task: {task_id}')
        return True

    def clear_agent_tasks(self, agent_url: str) -> int:
        """Clear all tasks for a specific agent.

        Args:
            agent_url: The agent URL whose tasks to clear

        Returns:
            Number of tasks cleared
        """
        task_ids = self.task_by_agent.get(agent_url, []).copy()
        count = 0

        for task_id in task_ids:
            if self.remove_task(task_id):
                count += 1

        if agent_url in self.task_by_agent:
            del self.task_by_agent[agent_url]

        logger.info(f'Cleared {count} tasks for agent: {agent_url}')
        return count

    def clear_all(self) -> None:
        """Clear all tracked tasks."""
        count = len(self.tasks)
        self.tasks.clear()
        self.task_by_agent.clear()
        self.context_groups.clear()
        self._task_order.clear()
        logger.info(f'Cleared all {count} tracked tasks')

    def _evict_if_needed(self) -> None:
        """Evict oldest tasks if we exceed max_tasks limit."""
        while len(self.tasks) > self.max_tasks:
            # Remove oldest task (first in order)
            oldest_task_id = self._task_order[0]
            logger.debug(f'Evicting oldest task due to max limit: {oldest_task_id}')
            self.remove_task(oldest_task_id)
