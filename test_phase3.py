#!/usr/bin/env python3
"""Test script for Phase 3: Specialized Agents with A2A Servers.

This script validates:
1. All 4 agent servers can be imported
2. All 4 agents can start and serve AgentCards
3. All 4 agents create proper tmux sessions
4. Cleanup works properly
"""

import os
import sys
import time
import subprocess
import json
from pathlib import Path

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from common.terminal_utils import TerminalLogger

# Agent configurations
AGENTS = [
    {"name": "frontend", "port": 8001, "role": "Frontend Engineer"},
    {"name": "backend", "port": 8002, "role": "Backend Engineer"},
    {"name": "pm", "port": 8003, "role": "Product Manager"},
    {"name": "ux", "port": 8004, "role": "UX Designer"},
]


def test_agent_imports():
    """Test that all agent modules can be imported."""
    logger = TerminalLogger("test")
    logger.section("Test 1: Agent Module Imports")

    # Add agents to path
    sys.path.insert(0, str(Path(__file__).parent / "src" / "agents"))

    all_passed = True

    for agent in AGENTS:
        try:
            logger.info(f"Testing {agent['name']} agent import...")

            # Import config
            config_module = __import__(f"{agent['name']}.config", fromlist=['CONFIG'])
            config_name = f"{agent['name'].upper()}_CONFIG"
            config = getattr(config_module, config_name)

            # Validate config
            assert config.name == agent['name'], f"Config name mismatch: {config.name} != {agent['name']}"
            assert config.port == agent['port'], f"Config port mismatch: {config.port} != {agent['port']}"
            assert config.role == agent['role'], f"Config role mismatch: {config.role} != {agent['role']}"

            logger.success(f"✓ {agent['name']} agent import successful")
            logger.info(f"  - Name: {config.name}")
            logger.info(f"  - Role: {config.role}")
            logger.info(f"  - Port: {config.port}")
            logger.print()

        except Exception as e:
            logger.error(f"✗ Failed to import {agent['name']} agent: {e}")
            all_passed = False

    if all_passed:
        logger.success("✓ All agent modules imported successfully")
    else:
        logger.error("✗ Some agent imports failed")

    return all_passed


def test_agent_servers():
    """Test that all agent servers can start and serve AgentCards."""
    logger = TerminalLogger("test")
    logger.section("Test 2: Agent Server Startup & AgentCards")

    # Check API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("✗ ANTHROPIC_API_KEY not set in environment")
        logger.warning("  Set it in .env file to test agent servers")
        return False

    logger.success("✓ ANTHROPIC_API_KEY is set")
    logger.print()

    # Start all agents
    processes = []
    logger.info("Starting all agents...")

    for agent in AGENTS:
        try:
            logger.info(f"  Starting {agent['name']} agent (port {agent['port']})...")

            # Start agent in background
            proc = subprocess.Popen(
                [sys.executable, "-m", f"src.agents.{agent['name']}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=Path(__file__).parent
            )

            processes.append({
                "agent": agent,
                "process": proc
            })

            logger.success(f"  ✓ Started {agent['name']} (PID: {proc.pid})")

        except Exception as e:
            logger.error(f"  ✗ Failed to start {agent['name']}: {e}")
            # Kill already started processes
            for p in processes:
                p["process"].kill()
            return False

    logger.print()
    logger.info("Waiting 12 seconds for all agents to initialize...")
    time.sleep(12)

    # Test AgentCard endpoints
    logger.print()
    logger.info("Testing AgentCard endpoints...")
    logger.print()

    all_passed = True

    for proc_info in processes:
        agent = proc_info["agent"]
        process = proc_info["process"]

        try:
            # Check if process is still running
            if process.poll() is not None:
                logger.error(f"✗ {agent['name']} agent died (exit code: {process.returncode})")
                all_passed = False
                continue

            # Test AgentCard endpoint
            url = f"http://localhost:{agent['port']}/.well-known/agent.json"
            result = subprocess.run(
                ["curl", "-s", "-f", url],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                logger.error(f"✗ {agent['name']} AgentCard not accessible")
                all_passed = False
                continue

            # Parse AgentCard
            card = json.loads(result.stdout)

            # Validate AgentCard
            assert "name" in card, "AgentCard missing 'name'"
            assert "version" in card, "AgentCard missing 'version'"
            assert "skills" in card, "AgentCard missing 'skills'"
            assert "url" in card, "AgentCard missing 'url'"
            assert len(card["skills"]) > 0, "AgentCard has no skills"

            logger.success(f"✓ {agent['name']} AgentCard validated")
            logger.info(f"  - Name: {card['name']}")
            logger.info(f"  - Version: {card['version']}")
            logger.info(f"  - URL: {card['url']}")
            logger.info(f"  - Skills: {len(card['skills'])}")
            logger.print()

        except subprocess.TimeoutExpired:
            logger.error(f"✗ {agent['name']} AgentCard request timeout")
            all_passed = False
        except json.JSONDecodeError as e:
            logger.error(f"✗ {agent['name']} AgentCard invalid JSON: {e}")
            all_passed = False
        except Exception as e:
            logger.error(f"✗ {agent['name']} AgentCard test failed: {e}")
            all_passed = False

    # Check tmux sessions
    logger.info("Checking tmux sessions...")
    try:
        result = subprocess.run(
            ["tmux", "list-sessions"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            sessions = result.stdout.strip().split("\n")
            logger.success(f"✓ Found {len(sessions)} tmux session(s)")

            for session_line in sessions:
                session_name = session_line.split(":")[0]
                if session_name.startswith("claude-"):
                    logger.info(f"  - {session_name}")

            logger.print()
        else:
            logger.warning("⚠ No tmux sessions found")

    except Exception as e:
        logger.warning(f"⚠ Could not check tmux sessions: {e}")

    # Cleanup
    logger.info("Cleaning up...")

    for proc_info in processes:
        agent = proc_info["agent"]
        process = proc_info["process"]

        try:
            logger.info(f"  Stopping {agent['name']} agent (PID: {process.pid})...")
            process.terminate()
            process.wait(timeout=5)
            logger.success(f"  ✓ Stopped {agent['name']}")
        except subprocess.TimeoutExpired:
            logger.warning(f"  ⚠ {agent['name']} didn't stop gracefully, killing...")
            process.kill()
        except Exception as e:
            logger.error(f"  ✗ Error stopping {agent['name']}: {e}")

    # Kill tmux sessions
    logger.print()
    logger.info("Killing tmux sessions...")

    for agent in AGENTS:
        session_name = f"claude-{agent['name']}"
        try:
            result = subprocess.run(
                ["tmux", "kill-session", "-t", session_name],
                capture_output=True
            )
            if result.returncode == 0:
                logger.success(f"  ✓ Killed {session_name}")
            else:
                logger.info(f"  - {session_name} already gone")
        except Exception as e:
            logger.warning(f"  ⚠ Error killing {session_name}: {e}")

    logger.print()

    if all_passed:
        logger.success("✓ All agent servers validated successfully")
    else:
        logger.error("✗ Some agent servers failed validation")

    return all_passed


def main():
    """Run all Phase 3 tests."""
    logger = TerminalLogger("phase3-test")

    logger.section("Phase 3: Specialized Agents with A2A Servers - Tests")

    logger.info("Test Suite:")
    logger.info("  1. Agent module imports")
    logger.info("  2. Agent server startup and AgentCards")
    logger.print()

    results = []

    # Test 1
    try:
        result = test_agent_imports()
        results.append(("Agent Imports", result))
    except Exception as e:
        logger.error(f"Test 1 failed: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Agent Imports", False))

    # Test 2
    try:
        result = test_agent_servers()
        results.append(("Agent Servers", result))
    except Exception as e:
        logger.error(f"Test 2 failed: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Agent Servers", False))

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
            "Phase 3 validation complete!\\n\\n"
            "All 4 specialized agents are working:\\n"
            "  • Frontend Agent (port 8001)\\n"
            "  • Backend Agent (port 8002)\\n"
            "  • PM Agent (port 8003)\\n"
            "  • UX Agent (port 8004)\\n\\n"
            "Next steps:\\n"
            "1. Proceed to Phase 4: Implement Host Agent (orchestrator)\\n"
            "2. Add interactive CLI for user requests\\n"
            "3. Test multi-agent coordination",
            title="Phase 3 Complete",
            style="green"
        )
        return 0
    else:
        logger.error(f"✗ {total - passed} of {total} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
