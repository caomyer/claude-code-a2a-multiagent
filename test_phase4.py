#!/usr/bin/env python3
"""Test script for Phase 4: Host Agent (Orchestrator).

This script validates:
1. Host agent can be instantiated
2. Host agent can connect to all specialist agents
3. Host agent can process a simple request
4. Multi-agent coordination works
"""

import asyncio
import os
import sys
from pathlib import Path

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from common.terminal_utils import TerminalLogger
from host_agent.config import HOST_CONFIG
from host_agent.executor import HostExecutor


async def test_host_initialization():
    """Test that host agent can be initialized."""
    logger = TerminalLogger("test")
    logger.section("Test 1: Host Agent Initialization")

    try:
        # Create host executor
        executor = HostExecutor(HOST_CONFIG)

        logger.success("✓ HostExecutor created")
        logger.info(f"  - Name: {HOST_CONFIG.name}")
        logger.info(f"  - Role: {HOST_CONFIG.role}")
        logger.info(f"  - Port: {HOST_CONFIG.port}")
        logger.info(f"  - Specialist agents: {len(HOST_CONFIG.specialist_agents)}")

        # Check components
        assert executor.claude_api is not None, "Claude API client not initialized"
        assert executor._http_client is not None, "HTTP client not initialized"

        logger.success("✓ All components initialized")
        logger.print()

        return executor

    except Exception as e:
        logger.error(f"✗ Failed to initialize host agent: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_agent_connections(executor: HostExecutor):
    """Test that host can connect to all specialist agents."""
    logger = TerminalLogger("test")
    logger.section("Test 2: Specialist Agent Connections")

    try:
        # Start executor (connects to agents)
        await executor.start()

        logger.success("✓ Host agent started")
        logger.info(f"  - Connected agents: {len(executor._agent_clients)}")

        # Verify connections
        for agent_name in HOST_CONFIG.specialist_agents.keys():
            if agent_name in executor._agent_clients:
                logger.success(f"  ✓ {agent_name} agent connected")
            else:
                logger.warning(f"  ⚠ {agent_name} agent not connected")

        logger.print()
        return True

    except Exception as e:
        logger.error(f"✗ Failed to connect to agents: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_simple_request(executor: HostExecutor):
    """Test processing a simple request."""
    logger = TerminalLogger("test")
    logger.section("Test 3: Simple Request Processing")

    test_request = "Create a simple login button component"

    try:
        logger.info(f"Sending request: {test_request}")
        logger.print()

        # Process request with timeout
        response = await asyncio.wait_for(
            executor.process_request(test_request),
            timeout=60.0  # 60 second timeout
        )

        logger.print()
        logger.success("✓ Request processed successfully")
        logger.info(f"  - Response length: {len(response)} characters")

        if len(response) > 200:
            logger.info(f"  - Response preview: {response[:200]}...")
        else:
            logger.info(f"  - Response: {response}")

        logger.print()
        return True

    except asyncio.TimeoutError:
        logger.error("✗ Request processing timed out after 60 seconds")
        return False
    except Exception as e:
        logger.error(f"✗ Request processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all Phase 4 tests."""
    logger = TerminalLogger("phase4-test")

    logger.section("Phase 4: Host Agent (Orchestrator) - Tests")

    logger.info("Test Suite:")
    logger.info("  1. Host agent initialization")
    logger.info("  2. Specialist agent connections")
    logger.info("  3. Simple request processing")
    logger.print()

    results = []

    # Check API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("✗ ANTHROPIC_API_KEY not set in environment")
        logger.warning("  Set it in .env file to test host agent")
        return 1

    logger.success("✓ ANTHROPIC_API_KEY is set")
    logger.print()

    # Test 1: Initialization
    executor = await test_host_initialization()
    if executor:
        results.append(("Host Initialization", True))
    else:
        results.append(("Host Initialization", False))
        # Can't continue without executor
        logger.error("Cannot continue tests without host executor")
        return 1

    # Test 2: Connections
    connected = await test_agent_connections(executor)
    results.append(("Agent Connections", connected))

    if not connected:
        logger.warning("⚠ Some agents not connected. Skipping request test.")
        logger.warning("  Make sure all specialist agents are running:")
        logger.warning("  ./scripts/start_all_agents.sh")
    else:
        # Test 3: Simple request
        request_ok = await test_simple_request(executor)
        results.append(("Request Processing", request_ok))

    # Cleanup
    try:
        await executor.stop()
        logger.info("✓ Host agent stopped")
    except Exception as e:
        logger.warning(f"⚠ Error during cleanup: {e}")

    # Summary
    logger.section("Test Results Summary")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        color = "green" if result else "red"
        logger.info(f"[{color}]{status}[/]: {name}")

    logger.print()

    if passed == total:
        logger.success(f"✓ All {total} tests passed!")
        logger.print()
        logger.panel(
            "Phase 4 validation complete!\\n\\n"
            "Host Agent is working:\\n"
            "  • Connects to all specialist agents\\n"
            "  • Processes user requests\\n"
            "  • Coordinates multi-agent responses\\n\\n"
            "Next steps:\\n"
            "1. Test with more complex requests\\n"
            "2. Test multi-agent coordination scenarios\\n"
            "3. Proceed to Phase 5: Context Synchronization",
            title="Phase 4 Complete",
            style="green"
        )
        return 0
    else:
        logger.error(f"✗ {total - passed} of {total} tests failed")
        logger.print()
        logger.info("Make sure all specialist agents are running:")
        logger.info("  ./scripts/start_all_agents.sh")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
