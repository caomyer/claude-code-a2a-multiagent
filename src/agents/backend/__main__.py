#!/usr/bin/env python3
"""Backend Agent - A2A Server Entry Point.

This agent specializes in backend development using Node.js, Python, APIs, and databases.
It implements the A2A protocol and uses Claude Code for execution.
"""

import asyncio
import sys
from pathlib import Path

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from common.agent_cards import create_agent_card
from common.base_agent import BaseAgent
from common.terminal_utils import TerminalLogger
from agents.backend.config import BACKEND_CONFIG


def main():
    """Start the Backend Agent A2A server."""
    logger = TerminalLogger("backend-agent")

    logger.section("Backend Agent Starting")
    logger.info(f"Agent: {BACKEND_CONFIG.name}")
    logger.info(f"Role: {BACKEND_CONFIG.role}")
    logger.info(f"Port: {BACKEND_CONFIG.port}")
    logger.info(f"URL: {BACKEND_CONFIG.url}")
    logger.info(f"Workspace: {BACKEND_CONFIG.workspace}")
    logger.print()

    # Create agent card
    logger.info("Creating AgentCard...")
    agent_card = create_agent_card(BACKEND_CONFIG)
    logger.success(f"✓ AgentCard created: {agent_card.name}")

    # Create agent executor (BaseAgent)
    logger.info("Initializing BaseAgent...")
    agent_executor = BaseAgent(BACKEND_CONFIG)
    logger.success("✓ BaseAgent initialized")

    # Create task store
    task_store = InMemoryTaskStore()

    # Create request handler
    logger.info("Creating request handler...")
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store
    )
    logger.success("✓ Request handler created")

    # Create A2A application
    logger.info("Building A2A application...")
    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler
    )
    logger.success("✓ A2A application built")

    logger.print()
    logger.panel(
        f"Backend Agent is ready!\n\n"
        f"AgentCard: {BACKEND_CONFIG.url}/.well-known/agent.json\n"
        f"Workspace: {BACKEND_CONFIG.workspace}\n\n"
        f"Capabilities:\n" + "\n".join(f"  • {cap}" for cap in BACKEND_CONFIG.capabilities[:5]) + "\n  ...",
        title="Agent Ready",
        style="green"
    )
    logger.print()

    # Start agent (initialize Claude terminal in background)
    async def startup():
        """Startup routine to initialize agent resources."""
        logger.info("Starting Claude Code terminal...")
        await agent_executor.start()
        logger.success("✓ Claude terminal ready")

    # Run startup
    asyncio.run(startup())

    logger.info(f"Starting A2A server on {BACKEND_CONFIG.url}")
    logger.print()

    # Run server
    try:
        uvicorn.run(
            a2a_app.build(),
            host="0.0.0.0",
            port=BACKEND_CONFIG.port,
            log_level="info"
        )
    except KeyboardInterrupt:
        logger.warning("\nShutdown requested by user")
        logger.info("Cleaning up...")
        # TODO: Add cleanup logic (close tmux sessions, etc.)
        logger.success("✓ Shutdown complete")
    except Exception as e:
        logger.error(f"Server error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
