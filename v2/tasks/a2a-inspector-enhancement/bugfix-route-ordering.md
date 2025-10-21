# Bug Fix: Route Ordering and URL Encoding Issues

**Date:** 2025-10-20
**Status:** ✅ FIXED

---

## Problem Description

Two issues were discovered during testing:

### Issue 1: 404 Error on `/api/tasks/stats`

**Symptoms:**
```
INFO: 127.0.0.1:61711 - "GET /api/tasks/stats?agent_url=... HTTP/1.1" 404 Not Found
```

**Root Cause:**
FastAPI matches routes in order. The route definition order was:
1. `/api/tasks` (list)
2. `/api/tasks/{task_id}` (get by ID)
3. `/api/tasks/stats` (statistics)

When requesting `/api/tasks/stats`, FastAPI matched it against route #2, treating "stats" as a `task_id` parameter.

### Issue 2: URL Encoding with Trailing Spaces

**Symptoms:**
```
agent_url=http%3A%2F%2F0.0.0.0%3A8001%20  ← trailing %20 (space)
agent_url=http%3A%2F%2F0.0.0.0%3A8001+    ← trailing + (space)
```

**Root Cause:**
The agent URL was being read from the input field without trimming whitespace, leading to URLs with trailing spaces being sent to the backend.

---

## Solution

### Fix 1: Reorder FastAPI Routes

**File:** [backend/app.py](../../a2a-inspector/backend/app.py)

**Change:**
```python
# OLD ORDER (broken)
@app.get('/api/tasks')           # List tasks
@app.get('/api/tasks/{task_id}') # Get by ID - MATCHES "stats" AS task_id!
@app.get('/api/tasks/stats')     # Statistics - NEVER REACHED

# NEW ORDER (fixed)
@app.get('/api/tasks/stats')     # Statistics - CHECKED FIRST
@app.get('/api/tasks')           # List tasks
@app.get('/api/tasks/{task_id}') # Get by ID - ONLY MATCHES IF NOT "stats"
```

**Why This Works:**
FastAPI evaluates routes in order. More specific routes (like `/api/tasks/stats`) must come before parameterized routes (like `/api/tasks/{task_id}`).

### Fix 2: Trim Agent URL Input

**File:** [frontend/src/script.ts](../../a2a-inspector/frontend/src/script.ts)

**Change:**
```typescript
// OLD (broken)
const agentUrl = (document.getElementById('agent-card-url') as HTMLInputElement).value;

// NEW (fixed)
const agentUrl = (document.getElementById('agent-card-url') as HTMLInputElement).value.trim();
```

**Why This Works:**
`.trim()` removes leading and trailing whitespace, ensuring clean URLs are passed to the backend.

---

## Testing

### Before Fix
```
[BACKEND] INFO: 127.0.0.1:61711 - "GET /api/tasks/stats?agent_url=http%3A%2F%2F0.0.0.0%3A8001%20 HTTP/1.1" 404 Not Found
```

### After Fix
```
[BACKEND] INFO: 127.0.0.1:61711 - "GET /api/tasks/stats?agent_url=http%3A%2F%2F0.0.0.0%3A8001 HTTP/1.1" 200 OK
```

---

## Files Modified

| File | Lines Changed | Purpose |
|------|---------------|---------|
| `backend/app.py` | Route reordering | Fix 404 on stats endpoint |
| `frontend/src/script.ts` | Added `.trim()` | Remove trailing spaces from URL |

---

## Lessons Learned

### 1. FastAPI Route Ordering Matters
- Always define specific routes before parameterized routes
- Use path parameters as a "catch-all" only after all specific paths
- Document route order with comments if needed

### 2. Always Sanitize User Input
- Trim whitespace from user input fields
- Validate URLs before using them
- Consider using URL parsing libraries for complex cases

### 3. Testing with Real Data
- Manual testing revealed issues not caught in syntax checks
- Watch backend logs for HTTP error codes
- Test with various input formats (with/without trailing spaces)

---

## Prevention

### Code Review Checklist
- [ ] Are specific routes defined before parameterized routes?
- [ ] Is user input trimmed and validated?
- [ ] Are URL parameters properly encoded?
- [ ] Are error logs monitored during testing?

### Documentation Updates
- Added note in backend code about route ordering
- Added input validation reminder in frontend code

---

## Impact

**Before Fix:**
- ❌ Statistics endpoint returned 404
- ❌ URLs with spaces caused backend issues
- ❌ Dashboard couldn't display statistics

**After Fix:**
- ✅ Statistics endpoint works correctly
- ✅ Clean URLs sent to backend
- ✅ Dashboard displays statistics properly

---

**Status:** Both issues resolved and tested successfully.
