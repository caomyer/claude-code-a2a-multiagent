# A2A Inspector Enhancement Project

## Overview

This directory contains planning documents for enhancing the a2a-inspector tool with task management capabilities.

## Documents

### [task-dashboard-plan.md](./task-dashboard-plan.md)
**Comprehensive implementation plan** for adding a task management dashboard to the a2a-inspector.

**Key Sections:**
- Current state analysis of A2A protocol and inspector
- Architecture design (backend + frontend)
- Phased implementation plan (6 phases, 4-5 days)
- Technical decisions and rationale
- Success criteria and risk assessment
- Future enhancement roadmap

**Summary:**
- **Goal:** Add comprehensive task viewing, filtering, and monitoring to a2a-inspector
- **Approach:** Tab-based UI with real-time WebSocket updates
- **LOC Estimate:** ~1,740 lines (backend + frontend)
- **Timeline:** 4-5 working days

## Key Findings

### A2A Protocol Task Listing

The A2A protocol specification defines a `tasks/list` endpoint at:
- Location: `a2a.server.request_handlers.rest_handler.RESTHandler.list_tasks()`
- **Status:** Defined but NOT IMPLEMENTED (raises `NotImplementedError`)
- Current SDK version does not provide task listing capabilities

### Workaround Strategy

Since the SDK doesn't implement task listing, our plan uses:
1. **Task Tracker Service** - Inspector tracks tasks it sees through message exchanges
2. **Direct A2A Client Queries** - Attempt to call agent's `/v1/tasks` endpoint
3. **Fallback Storage** - Store task metadata in inspector's own storage

This allows us to build the dashboard without waiting for SDK implementation.

## Implementation Status

- [ ] Phase 1: Backend Foundation
- [ ] Phase 2: Frontend Dashboard UI
- [ ] Phase 3: Task Detail View
- [ ] Phase 4: Real-Time Updates
- [ ] Phase 5: Context Grouping & Filters
- [ ] Phase 6: Polish & Testing

## Next Steps

1. **Review Plan** - Get feedback on the proposed architecture
2. **Approve Approach** - Confirm the workaround strategy makes sense
3. **Begin Implementation** - Start with Phase 1 (backend foundation)
4. **Iterate** - Build and test each phase incrementally

## Related Files

- **Inspector Codebase:** `/a2a-inspector/`
- **Backend Entry Point:** `/a2a-inspector/backend/app.py`
- **Frontend Entry Point:** `/a2a-inspector/frontend/src/script.ts`

## Questions?

See the "Open Questions" section in [task-dashboard-plan.md](./task-dashboard-plan.md) for discussion points.
