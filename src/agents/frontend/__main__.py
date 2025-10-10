#!/usr/bin/env python3
"""Frontend Agent - A2A Server Entry Point.

This agent specializes in frontend development using React, TypeScript, and modern web technologies.
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
from agents.frontend.config import FRONTEND_CONFIG


def main():
    """Start the Frontend Agent A2A server."""
    logger = TerminalLogger("frontend-agent")

    logger.section("Frontend Agent Starting")
    logger.info(f"Agent: {FRONTEND_CONFIG.name}")
    logger.info(f"Role: {FRONTEND_CONFIG.role}")
    logger.info(f"Port: {FRONTEND_CONFIG.port}")
    logger.info(f"URL: {FRONTEND_CONFIG.url}")
    logger.info(f"Workspace: {FRONTEND_CONFIG.workspace}")
    logger.print()

    # Create agent card
    logger.info("Creating AgentCard...")
    agent_card = create_agent_card(FRONTEND_CONFIG)
    logger.success(f"✓ AgentCard created: {agent_card.name}")

    # Create agent executor (BaseAgent)
    logger.info("Initializing BaseAgent...")
    agent_executor = BaseAgent(FRONTEND_CONFIG)
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
        f"Frontend Agent is ready!\n\n"
        f"AgentCard: {FRONTEND_CONFIG.url}/.well-known/agent.json\n"
        f"Workspace: {FRONTEND_CONFIG.workspace}\n\n"
        f"Capabilities:\n" + "\n".join(f"  • {cap}" for cap in FRONTEND_CONFIG.capabilities[:5]) + "\n  ...",
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

    logger.info(f"Starting A2A server on {FRONTEND_CONFIG.url}")
    logger.print()

    # Run server
    try:
        uvicorn.run(
            a2a_app.build(),
            host="0.0.0.0",
            port=FRONTEND_CONFIG.port,
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
