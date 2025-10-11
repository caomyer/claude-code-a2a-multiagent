#!/usr/bin/env python3
"""Backend agent server."""

import asyncio
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities

from .executor import ClaudeCodeExecutor
from .config import BACKEND_CONFIG


async def start_backend_agent():
    """Start the backend agent server."""

    config = BACKEND_CONFIG

    # 1. Setup workspace
    config.workspace.mkdir(parents=True, exist_ok=True)

    # 2. Create executor
    executor = ClaudeCodeExecutor(
        workspace=config.workspace,
        agent_role=config.role,
        system_prompt=config.system_prompt,
    )

    # 3. Create request handler
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )

    # 4. Create agent card
    agent_card = AgentCard(
        name=config.role,
        description=config.description,
        url=f"http://localhost:{config.port}",
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        skills=[],
    )

    # 5. Create A2A server
    a2a_server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    # 6. Build ASGI app
    asgi_app = a2a_server.build()

    # 7. Start HTTP server
    uvicorn_config = uvicorn.Config(
        app=asgi_app,
        host="0.0.0.0",
        port=config.port,
        log_level="info",
    )

    print(f"🚀 Starting {config.name} agent on port {config.port}")
    server = uvicorn.Server(uvicorn_config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(start_backend_agent())
