"""Claude Code terminal controller using tmux."""

import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Optional

from .terminal_utils import TerminalLogger


class ClaudeCodeTerminal:
    """
    Controller for Claude Code CLI running in a tmux session.

    This class manages:
    - Creating tmux sessions with Claude Code
    - Sending commands to Claude via tmux
    - Capturing output from the terminal
    - Auto-opening terminal windows for visibility
    """

    def __init__(
        self,
        workspace: Path,
        agent_name: str,
        auto_open_window: bool = True,
        logger: Optional[TerminalLogger] = None
    ):
        """
        Initialize Claude Code terminal controller.

        Args:
            workspace: Path to workspace directory for this agent
            agent_name: Name of the agent (for tmux session naming)
            auto_open_window: Whether to auto-open terminal window
            logger: Optional logger instance
        """
        self.workspace = Path(workspace).resolve()
        self.agent_name = agent_name
        self.session_name = f"claude-{agent_name}"
        self.auto_open_window = auto_open_window
        self.logger = logger or TerminalLogger(f"claude-terminal-{agent_name}")

        # Ensure workspace exists
        self.workspace.mkdir(parents=True, exist_ok=True)

        # Configuration
        self.claude_cli_path = os.getenv("CLAUDE_CLI_PATH", "claude")
        self.startup_timeout = int(os.getenv("CLAUDE_STARTUP_TIMEOUT", "5"))

        # State
        self.is_running = False
        self.session_exists = False

    def start(self) -> bool:
        """
        Start Claude Code in a tmux session.

        Returns:
            True if started successfully, False otherwise
        """
        if self.is_running:
            self.logger.warning(f"Session {self.session_name} already running")
            return True

        try:
            self.logger.info(f"Starting Claude Code session: {self.session_name}")

            # Check if session already exists
            if self._session_exists():
                self.logger.warning(f"Session {self.session_name} already exists")
                self.is_running = True
                self.session_exists = True
                return True

            # Create new tmux session with Claude Code
            self._create_session()

            # Wait for Claude to initialize
            self.logger.info(f"Waiting {self.startup_timeout}s for Claude to initialize...")
            time.sleep(self.startup_timeout)

            # Auto-open terminal window if requested
            if self.auto_open_window:
                self._open_terminal_window()

            self.is_running = True
            self.session_exists = True
            self.logger.success(f"Claude Code session started: {self.session_name}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to start Claude Code: {e}")
            return False

    def stop(self) -> bool:
        """
        Stop the Claude Code tmux session.

        Returns:
            True if stopped successfully, False otherwise
        """
        if not self.session_exists:
            self.logger.info("Session not running")
            return True

        try:
            self.logger.info(f"Stopping Claude Code session: {self.session_name}")

            # Kill the tmux session
            subprocess.run(
                ["tmux", "kill-session", "-t", self.session_name],
                check=True,
                capture_output=True
            )

            self.is_running = False
            self.session_exists = False
            self.logger.success(f"Session stopped: {self.session_name}")

            return True

        except subprocess.CalledProcessError as e:
            if "session not found" in e.stderr.decode().lower():
                self.logger.info("Session already stopped")
                self.is_running = False
                self.session_exists = False
                return True
            else:
                self.logger.error(f"Failed to stop session: {e}")
                return False

    def send_command(self, command: str) -> bool:
        """
        Send a command to Claude Code via tmux.

        Args:
            command: The command/prompt to send to Claude

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_running:
            self.logger.error("Session not running, cannot send command")
            return False

        try:
            self.logger.tmux_command(self.session_name, command)

            # Send the command followed by Enter
            subprocess.run(
                ["tmux", "send-keys", "-t", self.session_name, command, "Enter"],
                check=True,
                capture_output=True
            )

            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to send command: {e}")
            return False

    def capture_output(self, max_lines: int = 100) -> str:
        """
        Capture output from the Claude Code terminal.

        Args:
            max_lines: Maximum number of lines to capture

        Returns:
            Terminal output as string
        """
        if not self.session_exists:
            self.logger.error("Session not running, cannot capture output")
            return ""

        try:
            # Capture pane content
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", self.session_name, "-p", "-S", f"-{max_lines}"],
                check=True,
                capture_output=True,
                text=True
            )

            output = result.stdout
            return output

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to capture output: {e}")
            return ""

    def _session_exists(self) -> bool:
        """Check if tmux session exists."""
        try:
            result = subprocess.run(
                ["tmux", "has-session", "-t", self.session_name],
                capture_output=True,
                check=False
            )
            return result.returncode == 0
        except Exception:
            return False

    def _create_session(self):
        """Create tmux session with Claude Code."""
        # Build the command to run in tmux
        # Start Claude in the workspace directory
        claude_command = f"cd {self.workspace} && {self.claude_cli_path}"

        # Create detached tmux session
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", self.session_name, "-c", str(self.workspace)],
            check=True,
            capture_output=True
        )

        # Send command to start Claude
        subprocess.run(
            ["tmux", "send-keys", "-t", self.session_name, self.claude_cli_path, "Enter"],
            check=True,
            capture_output=True
        )

    def _open_terminal_window(self):
        """
        Auto-open terminal window showing the tmux session.
        Platform-specific implementation.
        """
        system = platform.system()
        terminal_emulator = os.getenv("TERMINAL_EMULATOR", "").lower()

        try:
            if system == "Darwin":  # macOS
                self._open_macos_terminal(terminal_emulator)
            elif system == "Linux":
                self._open_linux_terminal(terminal_emulator)
            else:
                self.logger.warning(f"Auto-open not supported on {system}")

        except Exception as e:
            self.logger.warning(f"Failed to auto-open terminal: {e}")
            self.logger.info(f"You can manually attach with: tmux attach -t {self.session_name}")

    def _open_macos_terminal(self, terminal_emulator: str):
        """Open terminal on macOS."""
        if "iterm" in terminal_emulator:
            # iTerm2
            applescript = f"""
            tell application "iTerm"
                activate
                create window with default profile
                tell current session of current window
                    write text "tmux attach -t {self.session_name}"
                end tell
            end tell
            """
        else:
            # Default to Terminal.app
            applescript = f"""
            tell application "Terminal"
                activate
                do script "tmux attach -t {self.session_name}"
                set custom title of window 1 to "Claude Code - {self.agent_name}"
            end tell
            """

        subprocess.run(["osascript", "-e", applescript], check=True)
        self.logger.info(f"Opened terminal window for {self.session_name}")

    def _open_linux_terminal(self, terminal_emulator: str):
        """Open terminal on Linux."""
        # Try to auto-detect or use specified terminal
        terminals = []

        if terminal_emulator:
            terminals.append(terminal_emulator)

        # Add common terminals to try
        terminals.extend(["gnome-terminal", "konsole", "xterm", "xfce4-terminal"])

        for term in terminals:
            try:
                if term == "gnome-terminal":
                    subprocess.Popen([
                        "gnome-terminal",
                        "--title", f"Claude Code - {self.agent_name}",
                        "--", "tmux", "attach", "-t", self.session_name
                    ])
                elif term == "konsole":
                    subprocess.Popen([
                        "konsole",
                        "-p", f"tabtitle=Claude Code - {self.agent_name}",
                        "-e", "tmux", "attach", "-t", self.session_name
                    ])
                elif term == "xfce4-terminal":
                    subprocess.Popen([
                        "xfce4-terminal",
                        "--title", f"Claude Code - {self.agent_name}",
                        "-e", f"tmux attach -t {self.session_name}"
                    ])
                else:  # xterm
                    subprocess.Popen([
                        "xterm",
                        "-title", f"Claude Code - {self.agent_name}",
                        "-e", f"tmux attach -t {self.session_name}"
                    ])

                self.logger.info(f"Opened {term} window for {self.session_name}")
                return

            except (FileNotFoundError, subprocess.SubprocessError):
                continue

        self.logger.warning(f"No terminal emulator found")
        self.logger.info(f"Manually attach with: tmux attach -t {self.session_name}")

    def get_workspace_files(self) -> list[Path]:
        """
        Get list of files in the workspace.

        Returns:
            List of file paths
        """
        files = []
        for item in self.workspace.rglob("*"):
            if item.is_file() and not any(part.startswith('.') for part in item.parts):
                files.append(item)
        return files

    def read_workspace_file(self, filename: str) -> str:
        """
        Read a file from the workspace.

        Args:
            filename: Name of file to read

        Returns:
            File contents as string
        """
        file_path = self.workspace / filename
        if file_path.exists():
            return file_path.read_text()
        else:
            return ""

    def write_workspace_file(self, filename: str, content: str):
        """
        Write a file to the workspace.

        Args:
            filename: Name of file to write
            content: Content to write
        """
        file_path = self.workspace / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        self.logger.debug(f"Wrote file: {filename}")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
