# Claude Code Execution Protocol

## Problem Statement

When agents delegate work to Claude Code (execution layer), we need:
1. **Reliable completion detection** - Know when Claude Code finishes
2. **Structured results** - Get distilled summaries, not raw terminal output
3. **Clean artifacts** - Send only meaningful deliverables, not noise
4. **Single-threaded execution** - Claude Code can only handle one task at a time per agent
5. **Automatic triggering** - No manual Enter key press required

## Design Principles

### Principle 1: File-Based Completion Protocol
Claude Code signals completion by creating a task-specific summary file, not by terminal output patterns.

### Principle 2: Task-Specific Summary Files
Each task gets its own summary file (`summaries/task_id.md`) for clear reference when multiple tasks have been executed.

### Principle 3: Selective Artifact Extraction
Only send artifacts explicitly marked as deliverables, not all workspace files.

### Principle 4: Task Queueing for Single-Threaded Execution
Claude Code can only handle one task at a time. New tasks are queued if execution is in progress.

### Principle 5: Automatic Command Execution
Tasks are automatically triggered without requiring manual user interaction.

## Implementation

### 1. Task-Specific Completion Detection

**Directory Structure:**
```
workspace/
├── summaries/
│   ├── task-abc-123.md      # Summary for task abc-123
│   ├── task-def-456.md      # Summary for task def-456
│   └── task-ghi-789.md      # Summary for task ghi-789
├── CONTEXT.md               # Current task context
├── SPECS.md                 # Current task specs
├── INSTRUCTIONS.md          # Current task instructions
└── [generated files]        # Task outputs
```

**When sending instruction to Claude Code:**
```python
def _send_to_claude(self, instruction: str, task_id: str):
    """Send instruction to Claude Code with completion protocol."""

    # Ensure summaries directory exists
    summaries_dir = self.claude_terminal.workspace / "summaries"
    summaries_dir.mkdir(exist_ok=True)

    # Create instruction with task-specific completion file
    command = f"""
{instruction}. Read CONTEXT.md and INSTRUCTIONS.md for full details.

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

Do not proceed to other tasks until summaries/{task_id}.md is created.
"""

    # Send to Claude Code with automatic Enter key trigger
    success = self.claude_terminal.send_command(command, auto_enter=True)

    if not success:
        raise RuntimeError("Failed to send command to Claude Code")
```

**Monitoring loop:**
```python
async def _monitor_claude_execution(
    self,
    task_id: str,
    max_duration: int = 300,
    update_interval: int = 5
):
    """Monitor Claude Code execution by checking for task-specific completion file."""

    # Task-specific completion file
    complete_file = self.claude_terminal.workspace / "summaries" / f"{task_id}.md"
    start_time = time.time()

    while time.time() - start_time < max_duration:
        # Check for completion marker
        if complete_file.exists():
            self.logger.success(f"Task completion detected: {complete_file}")
            return True

        # Optional: Send periodic status updates
        await self._send_status_update_if_output_changed()

        await asyncio.sleep(update_interval)  # Check every 5 seconds

    # Timeout
    self.logger.warning(f"Task monitoring timed out after {max_duration}s")
    return False
```

### 2. Task Queueing for Single-Threaded Execution

**Problem:** Claude Code can only handle one task at a time per agent. If a new task arrives while one is executing, it must be queued.

**Architecture:**
```python
class BaseAgent(AgentExecutor):
    def __init__(self, config: AgentConfig):
        # ... existing initialization ...

        # Task queue for single-threaded execution
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.is_executing: bool = False
        self.current_task_id: Optional[str] = None

        # Start queue processor
        self._queue_processor_task = None

    async def start(self):
        """Start the agent and queue processor."""
        # ... existing start logic ...

        # Start queue processor in background
        self._queue_processor_task = asyncio.create_task(self._process_task_queue())

    async def stop(self):
        """Stop the agent and queue processor."""
        # Cancel queue processor
        if self._queue_processor_task:
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass

        # ... existing stop logic ...

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        """
        Execute a task - either immediately or queue it if busy.
        """
        task_manager = TaskManager(...)
        updater = TaskUpdater(...)

        # Check if Claude Code is currently executing
        if self.is_executing:
            # Queue the task
            self.logger.info(f"Claude Code busy with task {self.current_task_id}, "
                           f"queueing task {context.task_id}")

            await updater.update_status(
                TaskState.submitted,
                message=f"Queued (waiting for task {self.current_task_id} to complete)"
            )

            # Add to queue
            await self.task_queue.put((context, event_queue))
            return

        # Execute immediately
        await self._execute_task(context, event_queue)

    async def _process_task_queue(self):
        """Background processor for queued tasks."""
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
                break
            except Exception as e:
                self.logger.error(f"Error processing queued task: {e}")

    async def _execute_task(self, context: RequestContext, event_queue: EventQueue):
        """
        Internal method that actually executes the task.

        This is the existing execute() logic, refactored into a separate method.
        """
        # Set execution flag
        self.is_executing = True
        self.current_task_id = context.task_id

        try:
            task_manager = TaskManager(...)
            updater = TaskUpdater(...)

            # ... existing task execution logic ...
            # Phase 1: Analysis
            # Phase 2: Coordination
            # Phase 3: Context packaging
            # Phase 4: Execution with monitoring
            # Phase 5: Artifact collection

        finally:
            # Clear execution flag
            self.is_executing = False
            self.current_task_id = None
```

**Queue Status Updates:**
```python
def get_queue_status(self) -> dict:
    """Get current queue status."""
    return {
        "is_executing": self.is_executing,
        "current_task_id": self.current_task_id,
        "queued_tasks": self.task_queue.qsize(),
        "agent_name": self.config.name
    }
```

### 3. Automatic Command Execution (No Manual Enter)

**Problem:** When sending commands via tmux, the Enter key must be explicitly triggered.

**Solution:** Ensure `send_command()` in `ClaudeCodeTerminal` always sends the Enter key.

**Implementation in `claude_terminal.py`:**
```python
def send_command(self, command: str, auto_enter: bool = True) -> bool:
    """
    Send a command to the Claude Code terminal.

    Args:
        command: Command to send
        auto_enter: Whether to automatically press Enter (default: True)

    Returns:
        True if successful, False otherwise
    """
    if not self.session_name:
        self.logger.error("Cannot send command: terminal not started")
        return False

    try:
        # Escape any special characters in the command
        # Note: tmux send-keys handles most escaping automatically

        # Build tmux command
        if auto_enter:
            # Send command with Enter key
            result = subprocess.run(
                ["tmux", "send-keys", "-t", self.session_name, command, "Enter"],
                capture_output=True,
                text=True,
                timeout=5
            )
        else:
            # Send command without Enter (for interactive input)
            result = subprocess.run(
                ["tmux", "send-keys", "-t", self.session_name, command],
                capture_output=True,
                text=True,
                timeout=5
            )

        if result.returncode == 0:
            self.logger.debug(f"Command sent to tmux session '{self.session_name}'")
            return True
        else:
            self.logger.error(f"Failed to send command: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        self.logger.error("Timeout sending command to tmux")
        return False
    except Exception as e:
        self.logger.error(f"Error sending command to tmux: {e}")
        return False
```

**Key Points:**
- By default, `auto_enter=True` automatically sends the Enter key
- The word "Enter" as a final argument to `tmux send-keys` triggers the key press
- No user interaction required - command executes immediately

### 4. Task Summary Format

**Standard structure for `summaries/{task_id}.md`:**
```markdown
# Task Completion Summary

## Objective
Create a login button component with email/password validation

## Accomplishments
- Created reusable Button component in React with TypeScript
- Implemented form validation using yup schema
- Added comprehensive unit tests with 95% coverage
- Created usage documentation with examples

## Key Deliverables
- `src/components/Button.tsx` - Main button component
- `src/components/Button.test.tsx` - Unit tests (8 tests)
- `src/components/README.md` - Component documentation
- `src/validation/loginSchema.ts` - Validation schema

## Test Results
✅ All 8 tests passed
- Button renders correctly ✓
- Click handler works ✓
- Disabled state works ✓
- Loading state works ✓
- Validation triggers ✓
- Email validation works ✓
- Password validation works ✓
- Form submission works ✓

## Important Notes
- Component uses Material-UI as peer dependency
- Email validation follows RFC 5322 standard
- Password requires minimum 8 characters
- Accessible with proper ARIA labels

## Status
✅ COMPLETED
```

### 5. Artifact Selection Strategy

**Don't send:**
- Configuration files (package.json, tsconfig.json, etc.) unless explicitly requested
- Build outputs (dist/, node_modules/)
- Context files (CONTEXT.md, SPECS.md, INSTRUCTIONS.md)
- Raw terminal output
- Summary files from other tasks

**Do send:**
1. **Primary Artifact**: Contents of `summaries/{task_id}.md` (always)
2. **Key Deliverables**: Only files listed in "Key Deliverables" section
3. **Limit**: Max 5 artifacts total (summary + 4 key files)

**Implementation:**
```python
async def _collect_and_send_artifacts(
    self,
    task_manager: TaskManager,
    updater: TaskUpdater,
    task_id: str
):
    """
    Collect results from workspace and send as artifacts.

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
        self.logger.success(f"Sent primary artifact: {summary_file}")
    else:
        # Fallback if no summary file
        self.logger.warning(f"Summary file not found: {summary_file}")
        fallback_summary = self._create_fallback_summary(task_id)
        await updater.add_artifact([TextPart(text=fallback_summary)])

    # 2. Extract key deliverables from summary
    key_files = self._extract_key_deliverables_from_summary(summary_content)
    self.logger.info(f"Found {len(key_files)} key deliverables")

    # 3. Send only key deliverables (max 4)
    for file_path in key_files[:4]:
        full_path = workspace / file_path
        if full_path.exists():
            try:
                content = full_path.read_text()
                await updater.add_artifact([TextPart(text=content)])
                self.logger.debug(f"Sent deliverable: {file_path}")
            except Exception as e:
                self.logger.error(f"Failed to read {file_path}: {e}")
        else:
            self.logger.warning(f"Deliverable not found: {file_path}")

def _extract_key_deliverables_from_summary(self, summary: str) -> list[str]:
    """
    Extract file paths from the Key Deliverables section of summary.

    Returns:
        List of relative file paths
    """
    import re

    # Look for Key Deliverables section
    match = re.search(
        r'## Key Deliverables\s*\n(.*?)\n##',
        summary,
        re.DOTALL | re.IGNORECASE
    )

    if not match:
        return []

    deliverables_section = match.group(1)

    # Extract file paths from markdown list items
    # Pattern: - `path/to/file.ext` - Description
    file_paths = re.findall(r'-\s*`([^`]+)`', deliverables_section)

    return file_paths

def _create_fallback_summary(self, task_id: str) -> str:
    """Create fallback summary if Claude Code didn't create one."""
    terminal_output = self.claude_terminal.capture_output(max_lines=100)
    workspace_files = self.claude_terminal.get_workspace_files()

    # Filter out context files
    generated_files = [
        f.relative_to(self.claude_terminal.workspace)
        for f in workspace_files
        if f.name not in ['CONTEXT.md', 'SPECS.md', 'INSTRUCTIONS.md']
        and 'summaries/' not in str(f)
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
{terminal_output[-1000:]}
```

## Status
⚠️ PARTIAL - Summary not created by Claude Code
"""
```

## Benefits

✅ **Reliable**: File-based protocol is deterministic, not heuristic
✅ **Structured**: Task-specific summaries are parseable and user-friendly
✅ **Clean**: Only meaningful artifacts, no noise
✅ **Traceable**: Each task has its own summary file for reference
✅ **Single-threaded**: Queue ensures one task at a time per agent
✅ **Automatic**: No manual intervention required
✅ **Scalable**: Works for both simple and complex tasks
✅ **Debuggable**: Summary files are human-readable for troubleshooting

## Complete Example Flow

```
User: "Create a login button component"
  ↓
Host Agent → Frontend Agent (A2A)
  ↓
Frontend Intelligence Layer analyzes → task_type: "execution"
  ↓
Frontend checks: Is Claude Code busy?
  ├─ YES → Queue task, return "Task queued (position 2)"
  └─ NO → Proceed immediately
  ↓
Agent sets is_executing = True, current_task_id = "abc-123"
  ↓
Agent sends to Claude Code:
  "Create login button. When done, create summaries/abc-123.md"
  + automatic Enter key press
  ↓
Claude Code starts working immediately (no manual Enter)
  ↓
Agent monitors: Check if summaries/abc-123.md exists every 5s
  ↓
Claude Code finishes, creates summaries/abc-123.md:
  """
  Accomplishments: Created Button.tsx, Button.test.tsx
  Key Deliverables:
    - `src/Button.tsx` - Main button component
    - `src/Button.test.tsx` - Unit tests
  Tests: 8/8 passed
  """
  ↓
Agent detects summaries/abc-123.md exists
  ↓
Agent sets is_executing = False, current_task_id = None
  ↓
Agent reads summary, extracts key files:
  - summaries/abc-123.md (summary itself)
  - src/Button.tsx (from deliverables list)
  - src/Button.test.tsx (from deliverables list)
  ↓
Agent sends 3 artifacts (clean, structured)
  ↓
Agent checks queue: Any tasks waiting?
  ├─ YES → Start next task from queue
  └─ NO → Idle, ready for new tasks
  ↓
User receives clean, structured results
```

## Migration Path

### Phase 1: Core Protocol (Critical - Fix Now)
- [x] Update `_send_to_claude()` to use task-specific summaries (`summaries/{task_id}.md`)
- [ ] Update `_send_to_claude()` to ensure automatic Enter key triggering
- [ ] Update `_monitor_claude_execution()` to check for task-specific completion file
- [ ] Update `_collect_and_send_artifacts()` to read from `summaries/{task_id}.md`
- [ ] Implement `_extract_key_deliverables_from_summary()` parser

### Phase 2: Task Queueing (Critical - Fix Now)
- [ ] Add task queue to BaseAgent (`self.task_queue`, `self.is_executing`)
- [ ] Refactor `execute()` to check if busy and queue if needed
- [ ] Implement `_process_task_queue()` background processor
- [ ] Implement `_execute_task()` (existing execute logic)
- [ ] Add queue status monitoring and logging

### Phase 3: Verification (This Week)
- [ ] Test single task execution
- [ ] Test multiple tasks with queueing
- [ ] Verify automatic Enter key triggering
- [ ] Verify artifact filtering (max 5)
- [ ] Test fallback summary creation

### Phase 4: Enhanced Features (Later)
- [ ] Structured `RESULTS.json` with machine-readable metadata
- [ ] Progress tracking via `STATUS.txt` for long-running tasks
- [ ] Error reporting via `ERRORS.md` for failed tasks
- [ ] Queue priority levels (urgent vs normal)
- [ ] Task cancellation support

## Implementation Checklist

**Critical (Immediate):**
- [ ] Task-specific summaries (`summaries/{task_id}.md`)
- [ ] Automatic Enter key in `send_command()`
- [ ] Task queueing for single-threaded execution
- [ ] Parse deliverables from summary
- [ ] Max 5 artifacts (summary + 4 files)

**Important (This Week):**
- [ ] Queue status monitoring
- [ ] Fallback summary creation
- [ ] Test with multiple queued tasks
- [ ] Verify completion detection reliability

**Nice to Have (Later):**
- [ ] `RESULTS.json` for machine parsing
- [ ] `STATUS.txt` for progress updates
- [ ] `ERRORS.md` for error details
- [ ] Queue priority system
- [ ] Task cancellation
