#!/usr/bin/env python3
"""Frontend agent server - SDK version with real-time streaming.

This is a migration from frontend_agent.py that uses the new ClaudeSDKExecutor
instead of the subprocess-based ClaudeCodeExecutor.

Key differences:
- Uses ClaudeSDKExecutor for real-time streaming
- Enables streaming capability in AgentCapabilities
- Better progress visibility for users
"""

import asyncio
import logging
import sys
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard, AgentCapabilities

from .sdk_executor import ClaudeSDKExecutor  # 🆕 Use SDK executor
from .config import FRONTEND_CONFIG


def setup_logging(level=logging.DEBUG):
    """Configure logging for the agent."""
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Set specific loggers
    logging.getLogger('src.agents.sdk_executor').setLevel(level)  # 🆕 SDK executor logger
    logging.getLogger('a2a').setLevel(logging.INFO)  # Less verbose for A2A internals
    logging.getLogger('uvicorn').setLevel(logging.INFO)
    logging.getLogger('claude_agent_sdk').setLevel(logging.INFO)  # 🆕 SDK logger


async def start_frontend_sdk_agent():
    """Start the frontend agent server with SDK executor."""

    # Setup logging first
    import os
    log_level = os.getenv('LOG_LEVEL', 'DEBUG').upper()
    level = getattr(logging, log_level, logging.DEBUG)
    setup_logging(level=level)

    config = FRONTEND_CONFIG

    # 1. Setup workspace
    config.workspace.mkdir(parents=True, exist_ok=True)

    # 2. Create executor (🆕 using SDK version)
    executor = ClaudeSDKExecutor(
        workspace=config.workspace,
        agent_role=config.role,
        system_prompt=config.system_prompt,
    )

    # 3. Create request handler
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )

    # 4. Create agent card (🆕 streaming enabled!)
    agent_card = AgentCard(
        name=f"{config.role} (SDK)",  # 🆕 Distinguish from subprocess version
        description=f"{config.description} - Real-time streaming enabled",
        url=f"http://localhost:{config.port}",
        version="2.0.0",  # 🆕 Version 2 for SDK
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(
            streaming=True,  # 🆕 Streaming is now supported!
            push_notifications=False
        ),
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

    print(f"🚀 Starting {config.name} agent (SDK mode) on port {config.port}")
    print(f"✨ Real-time streaming enabled!")
    server = uvicorn.Server(uvicorn_config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(start_frontend_sdk_agent())
