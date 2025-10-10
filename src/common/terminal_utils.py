"""Terminal utilities for rich, colored output and logging."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text


class TerminalLogger:
    """Rich terminal logger with colored output and status displays."""

    def __init__(self, name: str, log_file: Optional[Path] = None):
        """
        Initialize the terminal logger.

        Args:
            name: Name of the logger (e.g., agent name)
            log_file: Optional path to log file
        """
        self.name = name
        self.console = Console()
        self.log_file = log_file

        # Set up file logging if specified
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            logging.basicConfig(
                filename=str(log_file),
                level=logging.DEBUG,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            self.logger = logging.getLogger(name)
        else:
            self.logger = None

    def _log_to_file(self, level: str, message: str):
        """Log to file if logger is configured."""
        if self.logger:
            log_method = getattr(self.logger, level.lower(), self.logger.info)
            log_method(message)

    def info(self, message: str, style: str = ""):
        """Print info message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = f"[{style}]ℹ[/{style}]" if style else "ℹ"
        self.console.print(f"[dim]{timestamp}[/dim] {icon} {message}")
        self._log_to_file("INFO", message)

    def success(self, message: str):
        """Print success message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console.print(f"[dim]{timestamp}[/dim] [green]✓[/] {message}")
        self._log_to_file("INFO", f"SUCCESS: {message}")

    def warning(self, message: str):
        """Print warning message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console.print(f"[dim]{timestamp}[/dim] [yellow]⚠[/] {message}")
        self._log_to_file("WARNING", message)

    def error(self, message: str):
        """Print error message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console.print(f"[dim]{timestamp}[/dim] [red]✗[/] {message}")
        self._log_to_file("ERROR", message)

    def debug(self, message: str):
        """Print debug message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console.print(f"[dim]{timestamp} [DEBUG] {message}[/dim]")
        self._log_to_file("DEBUG", message)

    def section(self, title: str):
        """Print a section header."""
        self.console.print()
        self.console.rule(f"[bold blue]{title}[/bold blue]")
        self.console.print()

    def panel(self, content: str, title: str, style: str = ""):
        """Display content in a panel."""
        self.console.print(Panel(content, title=title, border_style=style))

    def status(self, message: str):
        """Return a context manager for showing status with spinner."""
        return self.console.status(f"[bold blue]{message}...", spinner="dots")

    def agent_header(self, agent_name: str, port: int, status: str = "Starting"):
        """Display agent header with info."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_row("[bold cyan]Agent:[/]", agent_name)
        table.add_row("[bold cyan]Port:[/]", str(port))
        table.add_row("[bold cyan]Status:[/]", f"[yellow]{status}[/]")

        self.console.print(
            Panel(
                table,
                title=f"[bold]{agent_name}[/]",
                border_style="cyan",
                padding=(1, 2)
            )
        )

    def agent_status_update(self, status: str, message: str = ""):
        """Update agent status."""
        status_color = {
            "starting": "yellow",
            "running": "green",
            "working": "blue",
            "completed": "green",
            "failed": "red",
            "stopped": "dim"
        }.get(status.lower(), "white")

        display_text = f"[{status_color}]{status.upper()}[/]"
        if message:
            display_text += f": {message}"

        self.info(display_text)

    def task_info(self, task_id: str, description: str):
        """Display task information."""
        self.panel(
            f"Task ID: [cyan]{task_id}[/cyan]\n\n{description}",
            title="Task Received",
            style="blue"
        )

    def tmux_command(self, session: str, command: str):
        """Display tmux command being executed."""
        self.debug(f"tmux → [{session}]: {command}")

    def terminal_output(self, output: str, max_lines: int = 10):
        """Display terminal output in a panel."""
        lines = output.strip().split('\n')
        if len(lines) > max_lines:
            display_output = '\n'.join(lines[-max_lines:])
            display_output = f"... ({len(lines)} lines total)\n\n{display_output}"
        else:
            display_output = output

        self.panel(
            display_output,
            title="Terminal Output",
            style="dim"
        )

    def a2a_request(self, from_agent: str, to_agent: str, message: str):
        """Display A2A request."""
        self.info(
            f"[cyan]{from_agent}[/] → [green]{to_agent}[/]: {message[:60]}..."
        )

    def a2a_response(self, from_agent: str, status: str):
        """Display A2A response."""
        status_icon = "✓" if status == "completed" else "⋯"
        self.info(f"[green]{from_agent}[/] {status_icon} {status}")

    def print(self, *args, **kwargs):
        """Wrapper for console.print."""
        self.console.print(*args, **kwargs)

    def rule(self, title: str = "", style: str = ""):
        """Print a horizontal rule."""
        self.console.rule(title, style=style)


def create_progress_spinner(message: str) -> Progress:
    """
    Create a progress spinner with custom message.

    Args:
        message: Message to display with spinner

    Returns:
        Progress object (use as context manager)
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        transient=True,
    )
