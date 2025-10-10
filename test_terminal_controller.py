#!/usr/bin/env python3
"""Test script for Claude Code Terminal Controller."""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from common.claude_terminal import ClaudeCodeTerminal
from common.terminal_utils import TerminalLogger


def main():
    """Test the terminal controller."""
    logger = TerminalLogger("test")

    logger.section("Claude Code Terminal Controller - Test")

    # Test configuration
    workspace = Path("./workspaces/test").resolve()
    agent_name = "test"

    logger.info("Test configuration:")
    logger.info(f"  Workspace: {workspace}")
    logger.info(f"  Agent name: {agent_name}")
    logger.info(f"  Session name: claude-{agent_name}")
    logger.print()

    # Create terminal controller
    logger.info("Creating ClaudeCodeTerminal instance...")
    terminal = ClaudeCodeTerminal(
        workspace=workspace,
        agent_name=agent_name,
        auto_open_window=False,  # Don't auto-open during test
        logger=logger
    )

    try:
        # Test 1: Start session
        logger.section("Test 1: Start Claude Code Session")
        success = terminal.start()

        if success:
            logger.success("✓ Session started successfully")
        else:
            logger.error("✗ Failed to start session")
            return 1

        logger.info("Waiting 2 seconds for Claude to settle...")
        time.sleep(2)

        # Test 2: Check if session exists
        logger.section("Test 2: Verify Session Exists")
        if terminal._session_exists():
            logger.success("✓ Session exists")
        else:
            logger.error("✗ Session not found")
            return 1

        # Test 3: Write context files
        logger.section("Test 3: Write Context Files")
        terminal.write_workspace_file("CONTEXT.md", """# Test Context

This is a test context file for the Claude Code terminal controller.
""")
        logger.success("✓ Created CONTEXT.md")

        terminal.write_workspace_file("test.txt", "Hello from test!")
        logger.success("✓ Created test.txt")

        # Test 4: Send a simple command
        logger.section("Test 4: Send Command to Claude")
        logger.info("Sending command: 'list files in this directory'")

        success = terminal.send_command("list files in this directory")
        if success:
            logger.success("✓ Command sent successfully")
        else:
            logger.error("✗ Failed to send command")
            return 1

        # Wait for Claude to process
        logger.info("Waiting 3 seconds for Claude to process...")
        time.sleep(3)

        # Test 5: Capture output
        logger.section("Test 5: Capture Terminal Output")
        output = terminal.capture_output(max_lines=50)

        if output:
            logger.success(f"✓ Captured {len(output.split(chr(10)))} lines of output")
            logger.terminal_output(output, max_lines=20)
        else:
            logger.warning("⚠ No output captured (might need more wait time)")

        # Test 6: List workspace files
        logger.section("Test 6: List Workspace Files")
        files = terminal.get_workspace_files()
        logger.info(f"Found {len(files)} files in workspace:")
        for file in files:
            logger.info(f"  - {file.relative_to(workspace)}")

        # Test 7: Read workspace file
        logger.section("Test 7: Read Workspace File")
        content = terminal.read_workspace_file("test.txt")
        if content:
            logger.success(f"✓ Read test.txt: {content}")
        else:
            logger.warning("⚠ Could not read test.txt")

        # Success
        logger.section("Test Results")
        logger.success("✓ All tests passed!")
        logger.print()
        logger.panel(
            f"tmux session: [cyan]claude-{agent_name}[/]\n"
            f"Workspace: [cyan]{workspace}[/]\n\n"
            f"To manually attach:\n"
            f"  [yellow]tmux attach -t claude-{agent_name}[/]\n\n"
            f"To view session list:\n"
            f"  [yellow]tmux ls[/]",
            title="Manual Testing",
            style="blue"
        )

        return 0

    except Exception as e:
        logger.error(f"Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Cleanup
        logger.section("Cleanup")
        logger.info("Stopping terminal session...")
        terminal.stop()
        logger.success("✓ Session stopped")


if __name__ == "__main__":
    sys.exit(main())
