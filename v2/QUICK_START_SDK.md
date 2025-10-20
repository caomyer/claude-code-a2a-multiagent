# Quick Start: Frontend SDK Agent

## 🚀 Start the SDK Agent (1 command!)

```bash
cd /Users/mingyucao_1/Documents/projects/agents_v2/v2
python -m src.agents.frontend_sdk_agent
```

You should see:
```
🚀 Starting frontend agent (SDK mode) on port 8001
✨ Real-time streaming enabled!
```

---

## ✅ What You Get vs Old Version

| Feature | Old (subprocess) | New (SDK) |
|---------|------------------|-----------|
| Progress updates | ❌ Only start/end | ✅ Real-time |
| Tool visibility | ❌ Hidden | ✅ Shows "Using tool: X" |
| Cost tracking | ❌ No | ✅ Logs cost per task |
| Type safety | ❌ Manual JSON | ✅ Typed messages |
| User experience | 😐 Wait until done | 😊 See progress live |

---

## 📁 Files Created

1. **[src/agents/frontend_sdk_agent.py](src/agents/frontend_sdk_agent.py)** - New agent using SDK executor
2. **[src/agents/sdk_executor.py](src/agents/sdk_executor.py)** - SDK-based executor with streaming
3. **[FRONTEND_SDK_MIGRATION.md](FRONTEND_SDK_MIGRATION.md)** - Detailed migration guide

**Old files unchanged:**
- [src/agents/frontend_agent.py](src/agents/frontend_agent.py) - Still works!
- [src/agents/executor.py](src/agents/executor.py) - Still works!

---

## 🧪 Quick Test

### Start the Agent
```bash
python -m src.agents.frontend_sdk_agent
```

### Send a Test Request
```python
import asyncio
import httpx
from a2a.client import A2AClient
from a2a.types import SendMessageRequest, MessageSendParams, Message, TextPart

async def test():
    async with httpx.AsyncClient() as http_client:
        client = A2AClient(http_client, "http://localhost:8001")

        request = SendMessageRequest(
            id="test-1",
            params=MessageSendParams(
                message=Message(
                    role="user",
                    parts=[TextPart(text="Create a React button component")],
                    messageId="msg-1",
                )
            )
        )

        response = await client.send_message(request)
        print(f"✅ Task started: {response.result.task.id}")

asyncio.run(test())
```

### What You Should See
- 🔧 "Frontend Engineer is working..."
- 📝 Progress updates (SDK only!)
- 🔧 "Using tool: Write"
- ✅ "Frontend Engineer completed"

---

## 🔄 Switch Back to Old Version

```bash
# Stop SDK agent (Ctrl+C)

# Start old agent
python -m src.agents.frontend_agent
```

Both use port 8001, so switching is instant!

---

## 📊 Key Differences in Code

### Old Version (subprocess)
```python
from .executor import ClaudeCodeExecutor

executor = ClaudeCodeExecutor(...)  # Subprocess + JSON parsing

agent_card = AgentCard(
    streaming=False,  # ❌ No streaming
)
```

### New Version (SDK)
```python
from .sdk_executor import ClaudeSDKExecutor

executor = ClaudeSDKExecutor(...)  # Native SDK with streaming

agent_card = AgentCard(
    streaming=True,  # ✅ Streaming enabled!
)
```

That's it! Just 2 line changes in the agent file.

---

## 🎯 Next Steps

1. **Test it now:**
   ```bash
   python -m src.agents.frontend_sdk_agent
   ```

2. **Compare behavior** with old version

3. **If you like it,** create SDK versions for other agents:
   - `backend_sdk_agent.py`
   - `pm_sdk_agent.py`
   - `ux_sdk_agent.py`

4. **After testing,** switch permanently

---

## 📚 More Info

- [FRONTEND_SDK_MIGRATION.md](FRONTEND_SDK_MIGRATION.md) - Full migration guide
- [MIGRATION_PLAN.md](MIGRATION_PLAN.md) - Overall strategy
- [SDK_MIGRATION_SUMMARY.md](SDK_MIGRATION_SUMMARY.md) - Why migrate?

---

## 💡 Pro Tip

Run both versions side-by-side (different terminals):

```bash
# Terminal 1: Old version (port 8001)
python -m src.agents.frontend_agent

# Terminal 2: Test against 8001
# Send request, see behavior

# Stop Terminal 1 (Ctrl+C)

# Terminal 1: New version (port 8001)
python -m src.agents.frontend_sdk_agent

# Terminal 2: Same test
# Compare streaming behavior!
```

Happy testing! 🎉
