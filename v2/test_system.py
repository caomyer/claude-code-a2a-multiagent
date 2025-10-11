#!/usr/bin/env python3
"""Test script for V2 multi-agent system."""

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from a2a.client import A2AClient
from a2a.types import SendMessageRequest, MessageSendParams, GetTaskRequest, TaskQueryParams

# Load environment variables from .env file
load_dotenv()


class AgentTester:
    """Test harness for the multi-agent system."""

    def __init__(self):
        self.project_root = Path(__file__).parent
        self.agents = {
            "frontend": {"port": 8001, "process": None},
            "backend": {"port": 8002, "process": None},
            "pm": {"port": 8003, "process": None},
            "ux": {"port": 8004, "process": None},
        }
        self.log_dir = self.project_root / "logs"
        self.pid_dir = self.project_root / "pids"

    def setup(self):
        """Create necessary directories."""
        self.log_dir.mkdir(exist_ok=True)
        self.pid_dir.mkdir(exist_ok=True)
        print("✓ Created log and pid directories")

    def start_agent(self, agent_name: str) -> bool:
        """Start a single agent."""
        agent_info = self.agents[agent_name]
        port = agent_info["port"]

        print(f"\n🚀 Starting {agent_name} agent on port {port}...")

        # Start agent process
        log_file = self.log_dir / f"{agent_name}.log"
        with open(log_file, "w") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", f"src.agents.{agent_name}_agent"],
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=self.project_root,
                env=os.environ.copy(),
            )

        agent_info["process"] = process

        # Save PID
        pid_file = self.pid_dir / f"{agent_name}.pid"
        pid_file.write_text(str(process.pid))

        # Wait for agent to be ready
        print(f"  Waiting for {agent_name} to be ready...", end="", flush=True)
        for i in range(30):  # 30 second timeout
            try:
                response = httpx.get(
                    f"http://localhost:{port}/.well-known/agent.json",
                    timeout=1.0,
                )
                if response.status_code == 200:
                    print(f" ✓ (took {i+1}s)")
                    return True
            except (httpx.ConnectError, httpx.TimeoutException):
                time.sleep(1)
                print(".", end="", flush=True)

        print(" ✗ TIMEOUT")
        return False

    def start_all_agents(self) -> bool:
        """Start all specialist agents."""
        print("\n" + "=" * 60)
        print("STARTING SPECIALIST AGENTS")
        print("=" * 60)

        for agent_name in self.agents.keys():
            if not self.start_agent(agent_name):
                print(f"\n❌ Failed to start {agent_name} agent")
                self.cleanup()
                return False

        print("\n✓ All specialist agents started successfully!")
        return True

    def test_agent_cards(self) -> bool:
        """Test that all agents return valid agent cards."""
        print("\n" + "=" * 60)
        print("TESTING AGENT CARDS")
        print("=" * 60)

        all_ok = True
        for agent_name, agent_info in self.agents.items():
            port = agent_info["port"]
            try:
                response = httpx.get(
                    f"http://localhost:{port}/.well-known/agent.json",
                    timeout=5.0,
                )
                if response.status_code == 200:
                    card = response.json()
                    print(f"\n✓ {agent_name.upper()} Agent:")
                    print(f"  Name: {card.get('name')}")
                    print(f"  Description: {card.get('description')}")
                    print(f"  Version: {card.get('version')}")
                else:
                    print(f"\n✗ {agent_name} agent returned {response.status_code}")
                    all_ok = False
            except Exception as e:
                print(f"\n✗ {agent_name} agent error: {e}")
                all_ok = False

        return all_ok

    async def test_simple_request(self) -> bool:
        """Test a simple request to the PM agent."""
        print("\n" + "=" * 60)
        print("TESTING SIMPLE REQUEST")
        print("=" * 60)

        print("\n📤 Sending test request to PM agent...")
        print("   Request: 'List 3 key requirements for a login form'")

        try:
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                # Create A2A client
                pm_client = A2AClient(
                    httpx_client=http_client,
                    url="http://localhost:8003"
                )

                # Create message request
                message_id = "test-msg-1"
                request = SendMessageRequest(
                    id=message_id,
                    params=MessageSendParams.model_validate({
                        "message": {
                            "role": "user",
                            "parts": [
                                {"type": "text", "text": "List 3 key requirements for a login form"}
                            ],
                            "messageId": message_id,
                        }
                    })
                )

                # Send message
                response = await pm_client.send_message(request)

                # Check if successful
                if hasattr(response.root, 'result'):
                    task = response.root.result
                    task_id = task.id
                    print(f"\n✓ Request accepted, task ID: {task_id}")

                    # Poll for completion
                    print("  Waiting for response...", end="", flush=True)
                    for i in range(60):  # 60 second timeout
                        task_request = GetTaskRequest(
                            id=f"get-task-{i}",
                            params=TaskQueryParams(id=task_id)
                        )
                        task_response = await pm_client.get_task(task_request)

                        if hasattr(task_response.root, 'result'):
                            task = task_response.root.result
                            state = task.status.state

                            if state == "completed":
                                print(f" ✓ (took {i+1}s)")
                                if task.artifacts:
                                    print("\n📄 Response:")
                                    for artifact in task.artifacts:
                                        for part in artifact.parts:
                                            # Part has a root attribute containing TextPart
                                            if hasattr(part.root, 'text'):
                                                print(f"\n{part.root.text}\n")
                                return True
                            elif state == "failed":
                                print(" ✗ FAILED")
                                if task.status.message:
                                    print(f"   Error: {task.status.message}")
                                return False

                        await asyncio.sleep(1)
                        print(".", end="", flush=True)

                    print(" ✗ TIMEOUT")
                    return False
                else:
                    print(f"\n✗ Request failed with error")
                    print(f"   Response: {response}")
                    return False

        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def cleanup(self):
        """Stop all agents and clean up."""
        print("\n" + "=" * 60)
        print("CLEANING UP")
        print("=" * 60)

        for agent_name, agent_info in self.agents.items():
            process = agent_info["process"]
            if process:
                print(f"\n🛑 Stopping {agent_name} agent (PID: {process.pid})...")
                try:
                    process.send_signal(signal.SIGTERM)
                    process.wait(timeout=5)
                    print(f"   ✓ Stopped")
                except subprocess.TimeoutExpired:
                    print(f"   Force killing...")
                    process.kill()
                    print(f"   ✓ Killed")
                except Exception as e:
                    print(f"   ✗ Error: {e}")

        # Clean up PID files
        for pid_file in self.pid_dir.glob("*.pid"):
            pid_file.unlink()

        print("\n✓ Cleanup complete")

    async def run_tests(self):
        """Run all tests."""
        print("\n" + "=" * 60)
        print("V2 MULTI-AGENT SYSTEM TEST SUITE")
        print("=" * 60)

        # Setup
        self.setup()

        # Start agents
        if not self.start_all_agents():
            return False

        # Test agent cards
        if not self.test_agent_cards():
            print("\n❌ Agent card tests failed")
            self.cleanup()
            return False

        # Test simple request
        if not await self.test_simple_request():
            print("\n❌ Simple request test failed")
            self.cleanup()
            return False

        # Success!
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)

        # Cleanup
        self.cleanup()
        return True


async def main():
    """Main entry point."""
    # Check environment
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ Error: ANTHROPIC_API_KEY environment variable not set")
        print("   Please set it in .env file or export it")
        sys.exit(1)

    tester = AgentTester()

    try:
        success = await tester.run_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        tester.cleanup()
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        tester.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
