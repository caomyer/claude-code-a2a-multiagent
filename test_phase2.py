#!/usr/bin/env python3
"""Test script for Phase 2: Base Agent Architecture."""

import os
import sys
from pathlib import Path

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from common.agent_config import AgentConfig
from common.agent_cards import create_agent_card, get_agent_card_dict
from common.terminal_utils import TerminalLogger

# Import configs directly to avoid relative import issues
sys.path.insert(0, str(Path(__file__).parent / "src" / "agents"))

from frontend.config import FRONTEND_CONFIG
from backend.config import BACKEND_CONFIG
from pm.config import PM_CONFIG
from ux.config import UX_CONFIG


def test_agent_config():
    """Test AgentConfig creation and validation."""
    logger = TerminalLogger("test")
    logger.section("Test 1: AgentConfig Creation")

    configs = {
        "Frontend": FRONTEND_CONFIG,
        "Backend": BACKEND_CONFIG,
        "PM": PM_CONFIG,
        "UX": UX_CONFIG
    }

    for name, config in configs.items():
        logger.info(f"Testing {name} config...")

        # Validate basic fields
        assert config.name, f"{name}: name is required"
        assert config.role, f"{name}: role is required"
        assert config.port > 0, f"{name}: port must be positive"
        assert config.workspace.exists(), f"{name}: workspace should exist"
        assert config.capabilities, f"{name}: capabilities should not be empty"

        # Validate auto-generated fields
        assert config.url, f"{name}: URL should be auto-generated"
        assert "localhost" in config.url, f"{name}: URL should contain localhost"

        # Validate system prompt
        system_prompt = config.get_claude_system_prompt()
        assert system_prompt, f"{name}: system prompt should not be empty"
        assert len(system_prompt) > 100, f"{name}: system prompt should be detailed"

        logger.success(f"✓ {name} config validated")
        logger.info(f"  - Name: {config.name}")
        logger.info(f"  - Role: {config.role}")
        logger.info(f"  - Port: {config.port}")
        logger.info(f"  - URL: {config.url}")
        logger.info(f"  - Capabilities: {len(config.capabilities)} items")
        logger.info(f"  - Workspace: {config.workspace}")
        logger.print()

    logger.success("✓ All agent configs validated successfully")
    return True


def test_agent_cards():
    """Test AgentCard generation from configs."""
    logger = TerminalLogger("test")
    logger.section("Test 2: AgentCard Generation")

    configs = {
        "Frontend": FRONTEND_CONFIG,
        "Backend": BACKEND_CONFIG,
        "PM": PM_CONFIG,
        "UX": UX_CONFIG
    }

    for name, config in configs.items():
        logger.info(f"Testing {name} AgentCard...")

        # Create agent card
        card = create_agent_card(config)

        # Validate card fields
        assert card.name, f"{name}: card name is required"
        assert card.description, f"{name}: card description is required"
        assert card.url, f"{name}: card URL is required"
        assert card.version, f"{name}: card version is required"
        assert card.capabilities, f"{name}: card capabilities is required"
        assert card.skills, f"{name}: card skills should not be empty"

        # Validate capabilities
        assert card.capabilities.streaming == True, f"{name}: should support streaming"

        # Validate skills
        assert len(card.skills) > 0, f"{name}: should have at least one skill"
        for skill in card.skills:
            assert skill.id, f"{name}: skill should have id"
            assert skill.name, f"{name}: skill should have name"
            assert skill.description, f"{name}: skill should have description"

        # Test dictionary conversion
        card_dict = get_agent_card_dict(config)
        assert isinstance(card_dict, dict), f"{name}: card dict should be a dictionary"
        assert "name" in card_dict, f"{name}: card dict should have 'name'"
        assert "skills" in card_dict, f"{name}: card dict should have 'skills'"

        logger.success(f"✓ {name} AgentCard validated")
        logger.info(f"  - Name: {card.name}")
        logger.info(f"  - Version: {card.version}")
        logger.info(f"  - Skills: {len(card.skills)} skills")
        logger.info(f"  - Streaming: {card.capabilities.streaming}")
        logger.print()

    logger.success("✓ All AgentCards generated successfully")
    return True


def test_base_agent_import():
    """Test that BaseAgent can be imported and instantiated."""
    logger = TerminalLogger("test")
    logger.section("Test 3: BaseAgent Import & Instantiation")

    # Check API key
    logger.info("Checking ANTHROPIC_API_KEY...")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("✗ ANTHROPIC_API_KEY not set in environment")
        logger.warning("  Set it in .env file to test BaseAgent instantiation")
        logger.info("  Skipping BaseAgent instantiation test")
        return False

    logger.success("✓ ANTHROPIC_API_KEY is set")

    try:
        from common.base_agent import BaseAgent

        logger.info("Testing BaseAgent instantiation with Frontend config...")

        # Create agent (don't start it to avoid tmux sessions)
        agent = BaseAgent(FRONTEND_CONFIG)

        # Validate agent attributes
        assert agent.config == FRONTEND_CONFIG, "Config should be stored"
        assert agent.claude_api, "Claude API client should be initialized"
        assert agent.claude_terminal, "Claude terminal should be initialized"
        assert agent.logger, "Logger should be initialized"

        logger.success("✓ BaseAgent instantiated successfully")
        logger.info(f"  - Config: {agent.config.name}")
        logger.info(f"  - Claude API: Initialized")
        logger.info(f"  - Claude Terminal: Initialized")
        logger.info(f"  - Logger: {agent.logger.name}")
        logger.print()

        # Test with other configs
        for config_name, config in [("Backend", BACKEND_CONFIG), ("PM", PM_CONFIG), ("UX", UX_CONFIG)]:
            logger.info(f"Testing BaseAgent with {config_name} config...")
            agent = BaseAgent(config)
            assert agent.config.name == config.name, f"{config_name} config should match"
            logger.success(f"✓ {config_name} agent instantiated")

        logger.success("✓ BaseAgent works with all configurations")
        return True

    except ImportError as e:
        logger.error(f"✗ Failed to import BaseAgent: {e}")
        return False
    except Exception as e:
        logger.error(f"✗ Failed to instantiate BaseAgent: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_serialization():
    """Test configuration serialization."""
    logger = TerminalLogger("test")
    logger.section("Test 4: Configuration Serialization")

    logger.info("Testing to_dict() and from_dict()...")

    # Test with frontend config
    original = FRONTEND_CONFIG
    config_dict = original.to_dict()

    # Validate dict
    assert isinstance(config_dict, dict), "to_dict() should return dict"
    assert "name" in config_dict, "Dict should have 'name'"
    assert "role" in config_dict, "Dict should have 'role'"
    assert "port" in config_dict, "Dict should have 'port'"

    # Test round-trip
    restored = AgentConfig.from_dict(config_dict)
    assert restored.name == original.name, "Name should match after round-trip"
    assert restored.role == original.role, "Role should match after round-trip"
    assert restored.port == original.port, "Port should match after round-trip"

    logger.success("✓ Configuration serialization works")
    logger.info(f"  - Serialized {len(config_dict)} fields")
    logger.info(f"  - Round-trip successful")

    return True


def main():
    """Run all Phase 2 tests."""
    logger = TerminalLogger("phase2-test")

    logger.section("Phase 2: Base Agent Architecture - Tests")

    logger.info("Test Suite:")
    logger.info("  1. AgentConfig creation and validation")
    logger.info("  2. AgentCard generation")
    logger.info("  3. BaseAgent import and instantiation")
    logger.info("  4. Configuration serialization")
    logger.print()

    results = []

    # Test 1
    try:
        result = test_agent_config()
        results.append(("AgentConfig", result))
    except Exception as e:
        logger.error(f"Test 1 failed: {e}")
        results.append(("AgentConfig", False))

    # Test 2
    try:
        result = test_agent_cards()
        results.append(("AgentCard", result))
    except Exception as e:
        logger.error(f"Test 2 failed: {e}")
        results.append(("AgentCard", False))

    # Test 3
    try:
        result = test_base_agent_import()
        results.append(("BaseAgent", result))
    except Exception as e:
        logger.error(f"Test 3 failed: {e}")
        import traceback
        traceback.print_exc()
        results.append(("BaseAgent", False))

    # Test 4
    try:
        result = test_config_serialization()
        results.append(("Serialization", result))
    except Exception as e:
        logger.error(f"Test 4 failed: {e}")
        results.append(("Serialization", False))

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
            "Phase 2 validation complete!\n\n"
            "Next steps:\n"
            "1. Set ANTHROPIC_API_KEY in .env if not done\n"
            "2. Proceed to Phase 3: Implement specialized agents with A2A servers\n"
            "3. Create __main__.py for each agent",
            title="Phase 2 Complete",
            style="green"
        )
        return 0
    else:
        logger.error(f"✗ {total - passed} of {total} tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
