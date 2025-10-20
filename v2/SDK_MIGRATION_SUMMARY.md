# Claude Agent SDK Migration - Summary

## Decision: ✅ YES - Migrate to Claude Agent SDK

After researching the Claude Agent SDK (Python), **I strongly recommend migrating** from the subprocess-based approach to the SDK-based approach.

---

## Key Benefits

### 1. **Real-Time Streaming** 🚀
- **Before:** Wait for entire `claude` process to complete, then parse JSON output
- **After:** Stream messages as Claude works, showing live progress to users
- **Impact:** Much better UX - users see what's happening in real-time

### 2. **Native Python Integration** 🐍
- **Before:** Spawn subprocess, parse stdout/stderr, handle JSON manually
- **After:** Native async Python API with typed message objects
- **Impact:** Cleaner code, better error handling, type safety

### 3. **Advanced Features** ⚡
- Custom tools (expose Python functions to Claude)
- Session continuity (multi-turn conversations)
- Hooks for intercepting tool calls
- Better context management

### 4. **Code Quality** ✨
- **Before:** ~238 lines with subprocess management
- **After:** ~280 lines with streaming (but more features!)
- Type-safe message handling
- Structured error handling

---

## What I've Created

### 1. **Migration Plan** ([MIGRATION_PLAN.md](./MIGRATION_PLAN.md))
Comprehensive 4-phase migration strategy:
- Phase 1: Parallel implementation (keep old code)
- Phase 2: Testing & validation
- Phase 3: Gradual rollout to agents
- Phase 4: Deprecate old implementation

### 2. **New SDK Executor** ([src/agents/sdk_executor.py](./src/agents/sdk_executor.py))
New `ClaudeSDKExecutor` class with:
- ✅ Real-time streaming updates
- ✅ Type-safe message handling
- ✅ Progress updates during execution
- ✅ Tool usage visibility
- ✅ Execution cost tracking
- ✅ Better error handling

### 3. **Current Executor** (UNCHANGED)
[src/agents/executor.py](./src/agents/executor.py) remains fully functional - no changes!

---

## Side-by-Side Comparison

### Subprocess Approach (Current)

```python
# Wait for entire process to complete
process = await asyncio.create_subprocess_exec(
    "claude", "-p", instruction,
    "--output-format", "json",
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await process.communicate()  # Blocks!

# Manually parse JSON
result = json.loads(stdout.decode())
result_text = result.get("result", str(result))

# Send single artifact at the end
await event_queue.enqueue_event(
    TaskArtifactUpdateEvent(artifact=...)
)
```

**Limitations:**
- ❌ No progress updates until completion
- ❌ Manual JSON parsing (error-prone)
- ❌ Limited to CLI flags
- ❌ No streaming
- ❌ Process management overhead

### SDK Approach (New)

```python
# Configure options
options = ClaudeAgentOptions(
    system_prompt=self.system_prompt,
    cwd=str(self.workspace),
    permission_mode='acceptEdits',
    allowed_tools=['Edit', 'Write', 'Bash'],
)

# Stream execution in real-time
async for message in query(prompt=instruction, options=options):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                # Send progress update IMMEDIATELY!
                await event_queue.enqueue_event(
                    TaskStatusUpdateEvent(...)
                )
            elif isinstance(block, ToolUseBlock):
                # Log tool usage in real-time
                logger.info(f"Using tool: {block.name}")

    elif isinstance(message, ResultMessage):
        # Get execution metadata
        logger.info(f"Cost: ${message.total_cost_usd}")
        logger.info(f"Turns: {message.num_turns}")
```

**Advantages:**
- ✅ Real-time progress updates
- ✅ Type-safe message objects
- ✅ Native Python async API
- ✅ Better visibility (tool usage, cost, etc.)
- ✅ Structured error handling

---

## Message Types Handled

The new executor handles these SDK message types:

| Message Type | Purpose | What We Do |
|-------------|---------|------------|
| `AssistantMessage` | Claude's responses | Extract text, send progress updates |
| `TextBlock` | Text content | Accumulate and stream to users |
| `ThinkingBlock` | Reasoning (extended thinking) | Log for debugging |
| `ToolUseBlock` | Tool calls (Edit, Write, etc.) | Show "Using tool: X" updates |
| `ToolResultBlock` | Tool execution results | Log outcomes |
| `ResultMessage` | Final metadata | Log cost, duration, turn count |

---

## Migration Strategy (Safe & Gradual)

### Phase 1: Parallel Implementation ✅ DONE
- [x] Keep existing `executor.py` untouched
- [x] Create new `sdk_executor.py`
- [x] Document migration plan

### Phase 2: Testing (Next Steps)
- [ ] Add `claude-agent-sdk` to requirements.txt
- [ ] Test SDK executor with simple tasks
- [ ] Compare outputs with subprocess version
- [ ] Validate streaming works correctly

### Phase 3: Gradual Rollout
- [ ] Add feature flag to agent config
- [ ] Switch UX agent to SDK (least critical)
- [ ] Monitor for issues
- [ ] Roll out to PM → Frontend → Backend

### Phase 4: Deprecation (After 1-2 weeks)
- [ ] Remove subprocess executor
- [ ] Update documentation
- [ ] Clean up code

---

## Risk Assessment

**Overall Risk: LOW** ✅

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| SDK bugs | Low | Medium | Keep subprocess version, gradual rollout |
| Output differences | Low | Medium | Comprehensive testing |
| Performance issues | Very Low | Low | Benchmark both |
| API breaking changes | Low | High | Pin SDK version |

**Safety measures:**
- ✅ Parallel implementation (old code keeps working)
- ✅ Feature flag (instant rollback)
- ✅ Gradual rollout (one agent at a time)
- ✅ Comprehensive logging

---

## Next Steps

### Immediate (You can do now):

1. **Review the code:**
   - Read [sdk_executor.py](./src/agents/sdk_executor.py)
   - Compare with [executor.py](./src/agents/executor.py)
   - Check the [migration plan](./MIGRATION_PLAN.md)

2. **Add dependency:**
   ```bash
   pip install claude-agent-sdk
   ```

3. **Test the new executor:**
   - Update one agent config to use `ClaudeSDKExecutor`
   - Run a simple task
   - Observe streaming behavior

### Testing Checklist:

```python
# In agent config (e.g., frontend_agent.py):

# Option 1: Use subprocess (current)
from agents.executor import ClaudeCodeExecutor
executor = ClaudeCodeExecutor(...)

# Option 2: Use SDK (new)
from agents.sdk_executor import ClaudeSDKExecutor
executor = ClaudeSDKExecutor(...)
```

Test both versions and compare:
- [ ] Output correctness
- [ ] Streaming behavior (SDK should show progress)
- [ ] Error handling
- [ ] Performance (speed, memory)
- [ ] Cost tracking (SDK provides this!)

---

## Recommendation

**Proceed with migration:** The benefits far outweigh the risks.

**Timeline:**
- Today: Review code, add dependency, initial testing
- Week 1: Thorough testing, validation
- Week 2: Gradual rollout to all agents
- Week 3+: Deprecate subprocess version

**Confidence Level:** 95% - This is the right move!

---

## Questions?

Feel free to ask about:
- Implementation details
- Testing strategies
- Rollout timing
- Specific features

The new executor is ready to use whenever you are! 🚀
