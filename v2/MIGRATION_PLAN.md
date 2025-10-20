# Claude Agent SDK Migration Plan

## Executive Summary

**Decision:** ✅ **MIGRATE** from subprocess-based `claude` CLI to Python Claude Agent SDK

**Timeline:** 1-2 days for implementation + testing

**Risk:** Low (run both implementations in parallel during transition)

---

## Why Migrate?

### Current Implementation (Subprocess)

```python
# Call Claude Code CLI as subprocess
process = await asyncio.create_subprocess_exec(
    "claude", "-p", instruction, "--output-format", "json",
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=str(self.workspace),
)
stdout, stderr = await process.communicate()  # ⚠️ Blocks until complete
result = json.loads(stdout.decode())  # ⚠️ Manual parsing
```

**Limitations:**
1. **No real-time updates** - Waits for entire process to complete
2. **Manual JSON parsing** - Error-prone, no type safety
3. **Limited control** - Can only use CLI flags
4. **No streaming** - Can't show progress to users
5. **Process overhead** - Spawning shell processes

### New Implementation (SDK)

```python
# Use native Python SDK
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

options = ClaudeAgentOptions(
    system_prompt=self.system_prompt,
    cwd=str(self.workspace),
    permission_mode='acceptEdits',
)

async for message in query(prompt=instruction, options=options):
    if isinstance(message, AssistantMessage):  # ✅ Typed messages
        for block in message.content:
            if isinstance(block, TextBlock):
                # ✅ Real-time streaming updates!
                await event_queue.enqueue_event(...)
```

**Advantages:**
1. ✅ **Real-time streaming** - Updates as Claude works
2. ✅ **Type-safe** - Typed message objects (AssistantMessage, TextBlock, etc.)
3. ✅ **Native Python** - No subprocess/JSON parsing overhead
4. ✅ **Advanced features** - Custom tools, hooks, session management
5. ✅ **Better errors** - Structured exceptions vs stderr parsing
6. ✅ **Cleaner code** - ~30% reduction in lines

---

## Migration Strategy

### Phase 1: Parallel Implementation (Week 1)

**Goal:** Create new `ClaudeSDKExecutor` without touching existing code

```
src/agents/
├── executor.py              # ✅ Keep existing (subprocess)
└── sdk_executor.py          # 🆕 New SDK-based executor
```

**Changes:**
- Add `claude-agent-sdk` to requirements
- Implement `ClaudeSDKExecutor` with streaming
- Add feature flag to agent config

### Phase 2: Testing & Validation (Week 1-2)

**Goal:** Validate SDK implementation works as expected

**Test cases:**
1. Simple tasks (verify output correctness)
2. Multi-turn conversations (context handling)
3. Error scenarios (error message quality)
4. Performance comparison (speed, resource usage)
5. File operations (Edit, Write, Bash tools)

**Success criteria:**
- ✅ All tests pass
- ✅ Output quality matches or exceeds subprocess
- ✅ Real-time streaming works
- ✅ No regressions

### Phase 3: Gradual Rollout (Week 2)

**Goal:** Switch agents one at a time

**Approach:**
1. Start with UX agent (least critical)
2. Monitor for issues
3. Roll out to PM agent
4. Roll out to Frontend agent
5. Finally Backend agent

**Rollback plan:** Feature flag can instantly switch back to subprocess

### Phase 4: Deprecation (Week 3+)

**Goal:** Remove subprocess implementation once SDK is proven

**Steps:**
1. Wait 1-2 weeks for stability confirmation
2. Remove `ClaudeCodeExecutor` (subprocess version)
3. Rename `ClaudeSDKExecutor` → `ClaudeCodeExecutor`
4. Update documentation

---

## Implementation Details

### New Dependencies

```txt
# requirements.txt
claude-agent-sdk>=1.0.0  # 🆕 Add this
a2a-python>=0.1.0        # ✅ Already have
anthropic>=0.40.0        # ✅ Already have
```

### New Executor Interface

```python
class ClaudeSDKExecutor(AgentExecutor):
    """Executes coding tasks using Claude Agent SDK with real-time streaming."""

    def __init__(self, workspace: Path, agent_role: str, system_prompt: str):
        self.workspace = workspace
        self.agent_role = agent_role
        self.system_prompt = system_prompt

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute with SDK, streaming updates in real-time."""

        # Build instruction (same as before)
        instruction = self._build_instruction(...)

        # Configure SDK options
        options = ClaudeAgentOptions(
            system_prompt=self.system_prompt,
            cwd=str(self.workspace),
            permission_mode='acceptEdits',
            allowed_tools=['Edit', 'Write', 'Bash'],
        )

        # Stream execution with real-time updates
        result_text = ""
        async for message in query(prompt=instruction, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text
                        # ✅ Stream intermediate updates!
                        await self._send_progress_update(event_queue, block.text)

            elif isinstance(message, ResultMessage):
                # ✅ Get structured completion info
                logger.info(f"Cost: ${message.total_cost_usd}")
                logger.info(f"Turns: {message.num_turns}")

        # Send final artifact
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=task.id,
                artifact=new_text_artifact(text=result_text),
            )
        )
```

### Key Differences

| Aspect | Subprocess (Old) | SDK (New) |
|--------|------------------|-----------|
| **Execution** | `asyncio.create_subprocess_exec()` | `async for message in query()` |
| **Output** | Single JSON blob at end | Streaming messages |
| **Updates** | Only "working" + "completed" | Real-time progress events |
| **Errors** | Parse stderr string | Typed exceptions |
| **Config** | CLI flags (`--allowedTools`) | Python objects (`ClaudeAgentOptions`) |
| **Type safety** | Manual JSON parsing | Typed message objects |

### Message Types to Handle

```python
from claude_agent_sdk import (
    AssistantMessage,    # Claude's responses
    ResultMessage,       # Final result with metadata
    TextBlock,           # Text content
    ThinkingBlock,       # Reasoning (if available)
    ToolUseBlock,        # Tool calls
    ToolResultBlock,     # Tool results
)

async for message in query(...):
    match message:
        case AssistantMessage():
            # Handle assistant responses
            for block in message.content:
                if isinstance(block, TextBlock):
                    # Send progress update
                    ...
                elif isinstance(block, ToolUseBlock):
                    # Log tool usage
                    ...

        case ResultMessage():
            # Handle completion metadata
            logger.info(f"Completed in {message.duration_ms}ms")
            logger.info(f"Cost: ${message.total_cost_usd}")
```

---

## Risk Assessment

### Low Risk ✅

**Why it's safe:**
1. **Parallel implementation** - Old code keeps working
2. **Feature flag** - Instant rollback
3. **Gradual rollout** - Test on one agent at a time
4. **Well-documented SDK** - Official Anthropic support
5. **Type safety** - Fewer runtime errors

### Potential Issues & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| SDK has bugs | Low | Medium | Keep subprocess version, report to Anthropic |
| Different output format | Low | Medium | Comprehensive testing, output comparison |
| Performance regression | Very Low | Low | Benchmark both versions |
| Breaking API changes | Low | High | Pin SDK version, monitor releases |

---

## Success Metrics

### Performance Metrics

- [ ] **Speed:** SDK execution time ≤ subprocess time
- [ ] **Memory:** Memory usage doesn't increase significantly
- [ ] **Reliability:** Error rate ≤ current implementation

### Feature Metrics

- [ ] **Streaming:** Real-time updates visible to users
- [ ] **Quality:** Output quality matches or exceeds subprocess
- [ ] **Errors:** Better error messages than stderr parsing
- [ ] **Code:** 20-30% reduction in executor code

### User Experience Metrics

- [ ] **Visibility:** Users can see progress in real-time
- [ ] **Responsiveness:** System feels more responsive
- [ ] **Transparency:** Better logging and diagnostics

---

## Decision: ✅ PROCEED WITH MIGRATION

**Recommendation:** Implement `ClaudeSDKExecutor` alongside existing executor, test thoroughly, then switch over.

**Timeline:**
- Week 1 Days 1-2: Implement SDK executor
- Week 1 Days 3-4: Testing & validation
- Week 2: Gradual rollout to all agents
- Week 3+: Deprecate subprocess version

**Confidence:** High (90%+)

**Next steps:**
1. Add `claude-agent-sdk` to requirements.txt
2. Create `src/agents/sdk_executor.py`
3. Add feature flag to agent configs
4. Implement streaming message handling
5. Test thoroughly before switching
