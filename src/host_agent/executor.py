"""Host Agent Executor - Task delegation and coordination logic."""

import asyncio
import json
import os
from typing import Any
from uuid import uuid4

import anthropic
import httpx
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    MessageSendParams,
    SendStreamingMessageRequest,
    SendStreamingMessageResponse,
    TextPart,
    TaskState,
)

from common.terminal_utils import TerminalLogger
from host_agent.config import HostAgentConfig


class HostExecutor:
    """
    Host Agent executor that coordinates specialist agents.

    Unlike BaseAgent (which implements AgentExecutor), the HostExecutor
    is a custom orchestrator that:
    1. Analyzes user requests with Claude API
    2. Determines which agents to involve
    3. Delegates tasks via A2A protocol
    4. Collects and synthesizes results
    """

    def __init__(self, config: HostAgentConfig):
        """Initialize the Host Agent executor.

        Args:
            config: Host agent configuration
        """
        self.config = config
        self.logger = TerminalLogger("host-executor")

        # Initialize Claude API client
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment")

        self.claude_api = anthropic.Anthropic(api_key=api_key)

        # A2A clients for specialist agents (lazy-loaded)
        self._agent_clients: dict[str, A2AClient] = {}

        # HTTP client for A2A communication
        self._http_client = httpx.AsyncClient(timeout=120.0)

        self.logger.info(f"Host Agent executor initialized")

    async def start(self):
        """Start the host agent (no Claude terminal needed)."""
        self.logger.section("Starting Host Agent")
        self.logger.info("Initializing connections to specialist agents...")

        # Connect to all specialist agents
        for agent_name, agent_url in self.config.specialist_agents.items():
            try:
                await self._connect_to_agent(agent_name, agent_url)
                self.logger.success(f"✓ Connected to {agent_name} agent ({agent_url})")
            except Exception as e:
                self.logger.warning(f"⚠ Could not connect to {agent_name}: {e}")
                self.logger.info(f"  (Agent may not be running yet)")

        self.logger.success("Host Agent ready to receive requests")
        self.logger.print()

    async def stop(self):
        """Stop the host agent and cleanup."""
        self.logger.info("Shutting down Host Agent...")

        # Close HTTP client
        await self._http_client.aclose()

        # A2A clients don't need explicit cleanup
        self._agent_clients.clear()

        self.logger.success("Host Agent stopped")

    async def process_request(self, user_request: str) -> str:
        """
        Process a user request by coordinating specialist agents.

        Args:
            user_request: The user's natural language request

        Returns:
            Synthesized response from all agents
        """
        self.logger.section(f"Processing Request")
        self.logger.info(f"User Request: {user_request}")
        self.logger.print()

        # Phase 1: Analyze request
        self.logger.info("Phase 1: Analyzing request with Claude API...")
        analysis = await self._analyze_request(user_request)

        if not analysis:
            return "I couldn't analyze that request. Please try rephrasing it."

        self.logger.success(f"✓ Analysis complete")
        self.logger.info(f"  Request Type: {analysis.get('request_type', 'unknown')}")
        self.logger.info(f"  Complexity: {analysis.get('complexity', 'unknown')}")
        self.logger.info(f"  Agents Needed: {', '.join(analysis.get('agents_needed', []))}")
        self.logger.print()

        # Phase 2: Execute plan
        self.logger.info("Phase 2: Delegating to specialist agents...")
        results = await self._execute_plan(analysis, user_request)

        if not results:
            return "No agents were able to process the request."

        self.logger.success(f"✓ Received responses from {len(results)} agent(s)")
        self.logger.print()

        # Phase 3: Synthesize results
        self.logger.info("Phase 3: Synthesizing results...")
        final_response = await self._synthesize_results(user_request, analysis, results)

        self.logger.success("✓ Request complete")
        self.logger.print()

        return final_response

    async def _analyze_request(self, user_request: str) -> dict[str, Any] | None:
        """
        Analyze user request with Claude API to determine execution plan.

        Args:
            user_request: User's natural language request

        Returns:
            Analysis dict with agents_needed, execution_plan, etc.
        """
        try:
            response = self.claude_api.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2000,
                system=self.config.system_prompt,
                messages=[{
                    "role": "user",
                    "content": f"Analyze this request and determine which agents to involve:\n\n{user_request}\n\nRespond with ONLY a JSON object following the format specified in the system prompt."
                }]
            )

            # Extract JSON from response
            response_text = response.content[0].text.strip()

            # Handle markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                # Remove first line (```json) and last line (```)
                response_text = "\n".join(lines[1:-1])

            analysis = json.loads(response_text)
            return analysis

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse Claude response as JSON: {e}")
            self.logger.debug(f"Response: {response_text}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to analyze request: {e}")
            return None

    async def _execute_plan(self, analysis: dict[str, Any], user_request: str) -> dict[str, str]:
        """
        Execute the plan by delegating to specialist agents.

        Args:
            analysis: Analysis from _analyze_request
            user_request: Original user request

        Returns:
            Dict mapping agent name to response
        """
        results = {}
        execution_plan = analysis.get("execution_plan", {})
        steps = execution_plan.get("steps", [])

        if not steps:
            # Fallback: just send to all agents in parallel
            agents_needed = analysis.get("agents_needed", [])
            tasks = []
            for agent_name in agents_needed:
                tasks.append(self._ask_agent(agent_name, user_request))

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            for agent_name, response in zip(agents_needed, responses):
                if isinstance(response, Exception):
                    self.logger.warning(f"⚠ {agent_name} failed: {response}")
                else:
                    results[agent_name] = response

            return results

        # Execute steps according to plan
        completed = set()

        for step in steps:
            agent_name = step.get("agent")
            prompt = step.get("prompt")
            depends_on = step.get("depends_on", [])

            # Wait for dependencies
            while not all(dep in completed for dep in depends_on):
                await asyncio.sleep(0.5)

            # Execute this step
            self.logger.info(f"  → Asking {agent_name} agent...")

            try:
                # Include context from dependencies
                context = ""
                if depends_on:
                    context = "\n\nContext from other agents:\n"
                    for dep in depends_on:
                        if dep in results:
                            context += f"\n**{dep.upper()} Agent Response:**\n{results[dep][:500]}...\n"

                full_prompt = f"{prompt}{context}"
                response = await self._ask_agent(agent_name, full_prompt)
                results[agent_name] = response
                completed.add(agent_name)

                self.logger.success(f"    ✓ {agent_name} completed")

            except Exception as e:
                self.logger.warning(f"    ⚠ {agent_name} failed: {e}")

        return results

    async def _ask_agent(self, agent_name: str, prompt: str) -> str:
        """
        Send a request to a specialist agent via A2A.

        Args:
            agent_name: Name of agent (frontend, backend, pm, ux)
            prompt: Prompt to send to the agent

        Returns:
            Agent's response text
        """
        # Get or create A2A client
        if agent_name not in self._agent_clients:
            agent_url = self.config.specialist_agents.get(agent_name)
            if not agent_url:
                raise ValueError(f"Unknown agent: {agent_name}")

            await self._connect_to_agent(agent_name, agent_url)

        client = self._agent_clients[agent_name]

        # Create A2A streaming message request (for long-running tasks like coding)
        message_payload = {
            'message': {
                'role': 'user',
                'parts': [
                    {'kind': 'text', 'text': prompt}
                ],
                'messageId': uuid4().hex,
            },
        }

        request = SendStreamingMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(**message_payload)
        )

        # Send message via A2A with streaming (get progress updates)
        self.logger.info(f"    Streaming response from {agent_name}...")
        stream = client.send_message_streaming(request)

        response_text = ""
        task_completed = False

        # Process streaming events
        async for event in stream:
            if hasattr(event, 'root') and hasattr(event.root, 'result'):
                result = event.root.result

                # Handle TaskStatusUpdateEvent (status changes)
                if hasattr(result, 'status'):
                    status = result.status.state

                    # Show progress
                    if status == TaskState.working:
                        self.logger.info(f"      {agent_name}: working...")
                    elif status == TaskState.completed:
                        self.logger.success(f"      {agent_name}: completed!")
                        task_completed = True
                    elif status == TaskState.failed:
                        self.logger.error(f"      {agent_name}: failed!")

                    # Check if this is the final event
                    if hasattr(result, 'final') and result.final:
                        if task_completed:
                            break

                # Handle TaskArtifactUpdateEvent (actual results)
                elif hasattr(result, 'artifact'):
                    artifact = result.artifact
                    if hasattr(artifact, 'parts'):
                        for part in artifact.parts:
                            if hasattr(part, 'root') and hasattr(part.root, 'text'):
                                response_text = part.root.text
                                self.logger.info(f"      {agent_name}: received {len(response_text)} chars")

        return response_text

    async def _connect_to_agent(self, agent_name: str, agent_url: str):
        """
        Connect to a specialist agent via A2A.

        Args:
            agent_name: Name of agent
            agent_url: URL of agent's A2A server
        """
        # First, fetch the agent card
        resolver = A2ACardResolver(
            httpx_client=self._http_client,
            base_url=agent_url
        )

        agent_card = await resolver.get_agent_card()

        # Create A2A client with the fetched agent card
        client = A2AClient(
            httpx_client=self._http_client,
            agent_card=agent_card
        )

        self._agent_clients[agent_name] = client

    async def _synthesize_results(
        self,
        user_request: str,
        analysis: dict[str, Any],
        results: dict[str, str]
    ) -> str:
        """
        Synthesize results from multiple agents into final response.

        Args:
            user_request: Original user request
            analysis: Analysis from _analyze_request
            results: Dict mapping agent name to response

        Returns:
            Synthesized final response
        """
        if not results:
            return "No agent responses received."

        # Build synthesis prompt
        results_summary = "\n\n".join([
            f"**{agent.upper()} Agent:**\n{response}"
            for agent, response in results.items()
        ])

        synthesis_prompt = f"""The user requested: "{user_request}"

I delegated this to {len(results)} specialist agent(s). Here are their responses:

{results_summary}

Please synthesize these responses into a clear, cohesive summary for the user. Focus on:
1. What was accomplished
2. Key details and deliverables
3. Next steps or recommendations

Keep it concise but informative."""

        try:
            response = self.claude_api.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1500,
                messages=[{
                    "role": "user",
                    "content": synthesis_prompt
                }]
            )

            return response.content[0].text.strip()

        except Exception as e:
            self.logger.error(f"Failed to synthesize results: {e}")
            # Fallback: just concatenate results
            return f"Here are the responses from the specialist agents:\n\n{results_summary}"
