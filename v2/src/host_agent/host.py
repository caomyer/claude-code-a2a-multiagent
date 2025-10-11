#!/usr/bin/env python3
"""Host agent - orchestrator that delegates to specialist agents."""

import asyncio
import json
import uuid
import httpx
import anthropic
from typing import Any

from a2a.client import A2AClient
from a2a.types import (
    SendMessageRequest,
    MessageSendParams,
    Message,
    TextPart,
    Task,
    TaskState,
)


class HostAgent:
    """Orchestrator that delegates work to specialist agents."""

    def __init__(self, agent_registry: dict[str, str]):
        """
        Initialize host agent.

        Args:
            agent_registry: Mapping of agent names to URLs
                {'frontend': 'http://localhost:8001', ...}
        """
        self.agent_registry = agent_registry
        self.clients: dict[str, A2AClient] = {}
        self.http_client: httpx.AsyncClient = None
        self.claude_client = anthropic.Anthropic()

    async def start(self) -> None:
        """Initialize HTTP client."""
        self.http_client = httpx.AsyncClient(timeout=300.0)

    async def stop(self) -> None:
        """Cleanup resources."""
        if self.http_client:
            await self.http_client.aclose()

    async def process_request(self, user_input: str) -> str:
        """Process user request and delegate to agents."""

        # 1. Analyze request
        print(f"\n🤔 Analyzing request...")
        analysis = await self._analyze_request(user_input)
        print(f"✓ Analysis: {analysis['primary_agent']} (primary)")
        if analysis.get("supporting_agents"):
            print(f"  + Supporting: {', '.join(analysis['supporting_agents'])}")

        # 2. Generate shared context ID
        context_id = str(uuid.uuid4())

        # 3. Delegate to agents in order
        results = {}

        # Primary agent
        primary_agent = analysis["primary_agent"]
        print(f"\n📤 Delegating to {primary_agent}...")

        primary_task = await self._delegate_to_agent(
            agent_name=primary_agent,
            message=user_input,
            context_id=context_id,
        )
        results[primary_agent] = primary_task
        print(f"✓ {primary_agent} completed")

        # Supporting agents (if needed)
        for agent_name in analysis.get("supporting_agents", []):
            print(f"\n📤 Consulting {agent_name}...")

            # Build message with context from primary
            supporting_message = self._build_supporting_message(
                user_input,
                primary_task,
                agent_name,
            )

            supporting_task = await self._delegate_to_agent(
                agent_name=agent_name,
                message=supporting_message,
                context_id=context_id,
            )
            results[agent_name] = supporting_task
            print(f"✓ {agent_name} completed")

        # 4. Synthesize results
        return self._format_results(results)

    async def _analyze_request(self, user_input: str) -> dict[str, Any]:
        """Analyze which agents should handle this request."""

        prompt = f"""Analyze this user request and determine which specialist agents should handle it.

Available agents:
- frontend: React/TypeScript UI development
- backend: API and server-side development
- pm: Requirements analysis and specifications
- ux: User interface/experience design

User request: {user_input}

Return a JSON object with:
- primary_agent: The main agent to handle this (string)
- supporting_agents: Other agents to consult (list of strings, can be empty)
- coordination_needed: Whether agents need to coordinate (boolean)

Example: {{"primary_agent": "frontend", "supporting_agents": ["ux", "backend"], "coordination_needed": true}}
"""

        response = self.claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        result_text = response.content[0].text
        # Extract JSON from response (handle markdown code blocks)
        if "```" in result_text:
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]

        return json.loads(result_text.strip())

    async def _delegate_to_agent(
        self,
        agent_name: str,
        message: str,
        context_id: str | None = None,
    ) -> Task:
        """Delegate to an agent and wait for completion."""

        # Get or create client
        if agent_name not in self.clients:
            agent_url = self.agent_registry.get(agent_name)
            if not agent_url:
                raise ValueError(f"Unknown agent: {agent_name}")

            self.clients[agent_name] = A2AClient(
                http_client=self.http_client,
                agent_url=agent_url,
            )

        client = self.clients[agent_name]

        # Build request
        message_id = str(uuid.uuid4())
        request = SendMessageRequest(
            id=message_id,
            params=MessageSendParams(
                message=Message(
                    role="user",
                    parts=[TextPart(text=message)],
                    messageId=message_id,
                    contextId=context_id,
                )
            ),
        )

        # Send and get task
        response = await client.send_message(request)
        task = response.result.task

        # Wait for completion by polling
        while task.status.state == TaskState.working:
            await asyncio.sleep(2)
            task = await client.get_task(task.id)

        return task

    def _build_supporting_message(
        self,
        original_request: str,
        primary_task: Task,
        supporting_agent: str,
    ) -> str:
        """Build message for supporting agent with context."""

        # Extract primary agent's result
        primary_result = ""
        if primary_task.artifacts:
            for artifact in primary_task.artifacts:
                for part in artifact.parts:
                    if hasattr(part, "text"):
                        primary_result = part.text
                        break

        return f"""Based on this user request: {original_request}

Context from primary agent:
{primary_result}

Please provide your specialist input as a {supporting_agent}."""

    def _format_results(self, results: dict[str, Task]) -> str:
        """Format results from all agents."""

        output = ["\n" + "=" * 60]
        output.append("MULTI-AGENT COLLABORATION RESULTS")
        output.append("=" * 60 + "\n")

        for agent_name, task in results.items():
            output.append(f"\n{agent_name.upper()} AGENT:")
            output.append("-" * 40)

            if task.artifacts:
                for artifact in task.artifacts:
                    for part in artifact.parts:
                        if hasattr(part, "text"):
                            output.append(part.text)
            else:
                output.append("(No output)")

            output.append("")

        output.append("=" * 60)
        return "\n".join(output)


async def main():
    """Run interactive host agent CLI."""

    agent_registry = {
        "frontend": "http://localhost:8001",
        "backend": "http://localhost:8002",
        "pm": "http://localhost:8003",
        "ux": "http://localhost:8004",
    }

    host = HostAgent(agent_registry)
    await host.start()

    print("\n" + "=" * 60)
    print("CLAUDE CODE A2A MULTI-AGENT SYSTEM")
    print("=" * 60)
    print("\nAvailable agents:")
    for name in agent_registry.keys():
        print(f"  • {name}")
    print("\nType your request (or 'quit' to exit)\n")

    try:
        while True:
            user_input = input("You: ").strip()

            if user_input.lower() in ["quit", "exit", "q"]:
                break

            if not user_input:
                continue

            try:
                result = await host.process_request(user_input)
                print(result)
            except Exception as e:
                print(f"\n❌ Error: {e}\n")

    finally:
        await host.stop()
        print("\n👋 Goodbye!\n")


if __name__ == "__main__":
    asyncio.run(main())
