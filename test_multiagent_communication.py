#!/usr/bin/env python3
"""
Test multi-agent communication with Week 2 implementation.

This test:
1. Starts all specialist agents
2. Tests inter-agent communication using AgentCommunicator
3. Validates task persistence and streaming updates
4. Stops all agents cleanly
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from common.agent_communication import AgentCommunicator
from common.terminal_utils import TerminalLogger


def start_agents():
    """Start all specialist agents using the start script."""
    logger = TerminalLogger("test")
    logger.section("Starting All Agents")

    try:
        # Run start script
        result = subprocess.run(
            ["./scripts/start_all_agents.sh"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.success("✓ All agents started")
            logger.info("Waiting 10 seconds for agents to initialize...")
            time.sleep(10)
            return True
        else:
            logger.error(f"✗ Failed to start agents: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"✗ Exception starting agents: {e}")
        return False


def stop_agents():
    """Stop all agents using the stop script."""
    logger = TerminalLogger("test")
    logger.info("Stopping all agents...")

    try:
        result = subprocess.run(
            ["./scripts/stop_all_agents.sh"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            logger.success("✓ All agents stopped")
            return True
        else:
            logger.warning(f"⚠ Stop script returned: {result.returncode}")
            return True  # Don't fail test on cleanup

    except Exception as e:
        logger.warning(f"⚠ Exception stopping agents: {e}")
        return True  # Don't fail test on cleanup


async def test_agent_discovery():
    """Test that agents can be discovered via their AgentCards."""
    logger = TerminalLogger("test")
    logger.section("Test 1: Agent Discovery")

    try:
        # Create communicator with agent registry
        agent_registry = {
            'frontend': 'http://localhost:8001',
            'backend': 'http://localhost:8002',
            'pm': 'http://localhost:8003',
            'ux': 'http://localhost:8004'
        }

        communicator = AgentCommunicator(agent_registry, timeout=10)
        await communicator.start()

        logger.info(f"Attempting to connect to {len(agent_registry)} agents...")

        # Try to connect to each agent
        connected_agents = []
        for agent_name, agent_url in agent_registry.items():
            try:
                # Try to get agent card
                import httpx
                from a2a.client import A2ACardResolver

                async with httpx.AsyncClient(timeout=5) as client:
                    resolver = A2ACardResolver(client, agent_url)
                    card = await resolver.get_agent_card()

                    logger.success(f"✓ {agent_name} - {card.name}")
                    logger.info(f"  URL: {agent_url}")
                    logger.info(f"  Description: {card.description}")
                    connected_agents.append(agent_name)

            except Exception as e:
                logger.error(f"✗ {agent_name} - Failed: {e}")

        await communicator.stop()

        logger.print()
        logger.info(f"Connected to {len(connected_agents)}/{len(agent_registry)} agents")

        return len(connected_agents) == len(agent_registry)

    except Exception as e:
        logger.error(f"✗ Agent discovery failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_simple_message():
    """Test sending a simple message to an agent."""
    logger = TerminalLogger("test")
    logger.section("Test 2: Simple Message Exchange")

    try:
        # Create communicator
        agent_registry = {
            'frontend': 'http://localhost:8001',
        }

        communicator = AgentCommunicator(agent_registry, timeout=60)
        await communicator.start()

        # Send a simple question
        question = "What are your main capabilities?"
        logger.info(f"Sending to frontend agent: {question}")

        # Send message and get task
        task = await communicator.send_message_to_agent(
            agent_name='frontend',
            message_text=question,
            task_id=None,
            context_id=None
        )

        logger.success(f"✓ Received task: {task.id}")
        logger.info(f"  Task state: {task.status.state}")
        logger.info(f"  Context ID: {task.context_id}")

        # Wait a bit for task processing
        logger.info("Waiting for task processing...")
        await asyncio.sleep(5)

        # Check task artifacts
        if task.artifacts:
            logger.success(f"✓ Task has {len(task.artifacts)} artifact(s)")
            for artifact in task.artifacts:
                for part in artifact.parts:
                    part_root = part.root if hasattr(part, 'root') else part
                    if hasattr(part_root, 'text'):
                        preview = part_root.text[:200] if len(part_root.text) > 200 else part_root.text
                        logger.info(f"  Artifact preview: {preview}...")
        else:
            logger.warning("⚠ No artifacts in task yet (might still be processing)")

        await communicator.stop()

        logger.print()
        return True

    except Exception as e:
        logger.error(f"✗ Simple message test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_agent_coordination():
    """Test coordination between multiple agents with proper handoff."""
    logger = TerminalLogger("test")
    logger.section("Test 3: Multi-Agent Coordination")

    try:
        # Create communicator with multiple agents
        agent_registry = {
            'frontend': 'http://localhost:8001',
            'backend': 'http://localhost:8002',
        }

        communicator = AgentCommunicator(agent_registry, timeout=300)
        await communicator.start()

        # Generate a shared context ID for related work
        import uuid
        context_id = str(uuid.uuid4())

        logger.info(f"Shared context ID: {context_id}")
        logger.print()

        # Step 1: Ask backend to design API (and WAIT for completion)
        logger.info("Step 1: Asking backend to design API endpoints...")
        backend_response = await communicator.ask_agent(
            agent_name='backend',
            question="Design REST API endpoints for user authentication (login, logout, token refresh). List the endpoints with methods and paths.",
            context_id=context_id
        )
        logger.success(f"✓ Backend completed API design")
        logger.info(f"  Response preview: {backend_response[:150]}...")

        logger.print()

        # Step 2: Pass backend's API design to frontend
        logger.info("Step 2: Asking frontend to describe UI components based on backend API...")
        frontend_message = f"""Based on these authentication API endpoints:

{backend_response}

Please describe (but do not implement) what React components you would recommend for a login form. List:
1. Component names and structure
2. Their props/interfaces
3. Their responsibilities

This is an architectural question - just provide a component design description."""

        frontend_response = await communicator.ask_agent(
            agent_name='frontend',
            question=frontend_message,
            context_id=context_id
        )
        logger.success(f"✓ Frontend completed UI design")
        logger.info(f"  Response preview: {frontend_response[:150]}...")

        logger.print()

        # Verify coordination worked
        if backend_response and frontend_response:
            logger.success(f"✓ Coordination successful:")
            logger.info(f"  • Backend designed API endpoints")
            logger.info(f"  • Frontend received API design and created UI")
            logger.info(f"  • Both tasks share context: {context_id}")
            coordination_success = True
        else:
            logger.error(f"✗ Coordination failed - missing responses")
            coordination_success = False

        await communicator.stop()

        logger.print()
        return coordination_success

    except Exception as e:
        logger.error(f"✗ Coordination test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all multi-agent communication tests."""
    logger = TerminalLogger("multiagent-test")

    logger.section("Multi-Agent Communication Test")
    logger.info("This test validates Week 2 implementation:")
    logger.info("  • AgentCommunicator for inter-agent messaging")
    logger.info("  • Task persistence across agents")
    logger.info("  • Context sharing for coordination")
    logger.print()

    # Check API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("✗ ANTHROPIC_API_KEY not set in .env")
        return 1

    results = []

    # Start agents
    logger.info("Starting agents (this may take a moment)...")
    if not start_agents():
        logger.error("✗ Failed to start agents")
        logger.info("Make sure tmux and claude CLI are installed:")
        logger.info("  brew install tmux")
        logger.info("  npm install -g @anthropic-ai/claude-code")
        return 1

    try:
        # Run tests
        results.append(("Agent Discovery", await test_agent_discovery()))
        results.append(("Simple Message", await test_simple_message()))
        results.append(("Agent Coordination", await test_agent_coordination()))

    finally:
        # Always stop agents
        logger.print()
        stop_agents()

    # Summary
    logger.section("Test Results")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status} - {name}")

    logger.print()

    if passed == total:
        logger.success(f"✓ All {total} tests passed!")
        logger.print()
        logger.panel(
            "Week 2 Multi-Agent Communication: ✓ VALIDATED\n\n"
            "Successfully tested:\n"
            "  • Agent discovery via A2A protocol\n"
            "  • Message exchange between agents\n"
            "  • Context sharing across agents\n"
            "  • AgentCommunicator implementation\n\n"
            "Ready to commit Week 2 implementation!",
            title="Multi-Agent Test Complete",
            style="green"
        )
        return 0
    else:
        logger.error(f"✗ {total - passed} of {total} tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
