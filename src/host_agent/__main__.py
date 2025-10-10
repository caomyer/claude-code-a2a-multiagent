#!/usr/bin/env python3
"""Host Agent - Interactive CLI Entry Point.

The Host Agent is the orchestrator that receives user requests and coordinates
specialist agents (Frontend, Backend, PM, UX) to fulfill them.
"""

import asyncio
import sys
from pathlib import Path

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from common.terminal_utils import TerminalLogger
from host_agent.config import HOST_CONFIG
from host_agent.executor import HostExecutor


def print_welcome(console: Console):
    """Print welcome banner."""
    welcome_text = """
[bold cyan]Claude Code A2A Multi-Agent System[/bold cyan]

This system coordinates 4 specialist agents to help you build software:

[yellow]• Frontend Agent[/yellow] - React, TypeScript, UI components
[yellow]• Backend Agent[/yellow] - APIs, databases, authentication
[yellow]• PM Agent[/yellow] - Requirements, user stories, specs
[yellow]• UX Agent[/yellow] - UI/UX design, accessibility

[dim]Type your request and the system will coordinate the relevant agents.
Type 'help' for examples, 'status' to check agents, 'quit' to exit.[/dim]
"""
    console.print(Panel(welcome_text, title="[bold]Host Agent[/bold]", border_style="cyan"))
    console.print()


def print_help(console: Console):
    """Print help with example requests."""
    help_text = """
[bold]Example Requests:[/bold]

[yellow]Simple UI Component:[/yellow]
  "Create a login form with email and password validation"

[yellow]Full Feature:[/yellow]
  "Build a user authentication system with signup, login, and password reset"

[yellow]API Development:[/yellow]
  "Create a REST API for managing todo items with CRUD operations"

[yellow]Design Specifications:[/yellow]
  "Design a dashboard layout with navigation, charts, and user profile"

[yellow]Bug Fix:[/yellow]
  "Fix the form validation not showing error messages properly"

[yellow]Requirements:[/yellow]
  "What are the requirements for a real-time chat feature?"

[bold]Special Commands:[/bold]
  • [cyan]help[/cyan] - Show this help
  • [cyan]status[/cyan] - Check specialist agent status
  • [cyan]clear[/cyan] - Clear screen
  • [cyan]quit[/cyan] or [cyan]exit[/cyan] - Exit the system
"""
    console.print(Panel(help_text, title="[bold]Help[/bold]", border_style="yellow"))
    console.print()


async def check_agent_status(executor: HostExecutor, console: Console):
    """Check status of all specialist agents."""
    console.print("\n[bold]Checking Specialist Agent Status...[/bold]\n")

    statuses = []
    for agent_name, agent_url in HOST_CONFIG.specialist_agents.items():
        try:
            # Try to connect
            await executor._connect_to_agent(agent_name, agent_url)
            status = "[green]✓ Online[/green]"
        except Exception as e:
            status = f"[red]✗ Offline[/red] ({str(e)[:30]}...)"

        statuses.append((agent_name.capitalize(), agent_url, status))

    # Display as table
    console.print("[bold]Agent Status:[/bold]\n")
    for name, url, status in statuses:
        console.print(f"  {name:12} {url:30} {status}")

    console.print()


async def main():
    """Run the Host Agent interactive CLI."""
    console = Console()
    logger = TerminalLogger("host-agent")

    # Print welcome
    print_welcome(console)

    # Check if all agents should be started
    console.print("[dim]Starting Host Agent...[/dim]\n")

    # Initialize executor
    executor = HostExecutor(HOST_CONFIG)

    try:
        # Start executor
        await executor.start()

        console.print("[green]✓ Host Agent ready![/green]")
        console.print("[dim]Note: Make sure specialist agents are running on ports 8001-8004[/dim]\n")

        # Interactive loop
        while True:
            try:
                # Get user input
                user_input = Prompt.ask(
                    "[bold cyan]>[/bold cyan]",
                    console=console
                ).strip()

                if not user_input:
                    continue

                # Handle special commands
                if user_input.lower() in ['quit', 'exit', 'q']:
                    console.print("\n[yellow]Goodbye![/yellow]\n")
                    break

                elif user_input.lower() == 'help':
                    print_help(console)
                    continue

                elif user_input.lower() == 'status':
                    await check_agent_status(executor, console)
                    continue

                elif user_input.lower() == 'clear':
                    console.clear()
                    print_welcome(console)
                    continue

                # Process request
                console.print()
                console.print("[dim]Processing request...[/dim]\n")

                # Execute request
                response = await executor.process_request(user_input)

                # Display response
                console.print(Panel(
                    response,
                    title="[bold green]Response[/bold green]",
                    border_style="green"
                ))
                console.print()

            except KeyboardInterrupt:
                console.print("\n\n[yellow]Interrupted. Type 'quit' to exit or continue entering requests.[/yellow]\n")
                continue

            except Exception as e:
                console.print(f"\n[red]Error:[/red] {e}\n")
                logger.error(f"Error processing request: {e}")
                import traceback
                traceback.print_exc()

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Shutting down...[/yellow]\n")

    except Exception as e:
        console.print(f"\n[red]Fatal error:[/red] {e}\n")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Cleanup
        try:
            await executor.stop()
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nShutdown complete.")
        sys.exit(0)
