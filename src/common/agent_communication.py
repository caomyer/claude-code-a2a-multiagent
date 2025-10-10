"""Inter-agent communication helper using A2A protocol."""

import logging
import uuid
from typing import Optional

import httpx
from a2a.client import A2AClient, A2ACardResolver
from a2a.types import (
    AgentCard,
    Message,
    MessageSendParams,
    Role,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
    TextPart,
)

logger = logging.getLogger(__name__)


class AgentCommunicator:
    """
    Helper for inter-agent A2A communication.

    Manages connections to remote agents and provides convenient methods
    for sending messages and receiving responses.
    """

    def __init__(self, agent_registry: dict[str, str], timeout: int = 30):
        """
        Initialize the agent communicator.

        Args:
            agent_registry: Mapping of agent_name -> agent_url
                           e.g., {'frontend': 'http://localhost:8001', ...}
            timeout: HTTP timeout in seconds (default: 30)
        """
        self.agent_registry = agent_registry
        self.timeout = timeout

        # HTTP client for all A2A calls
        self._http_client: Optional[httpx.AsyncClient] = None

        # Cached agent clients and cards
        self._clients: dict[str, A2AClient] = {}
        self._cards: dict[str, AgentCard] = {}

        logger.debug(
            f"Initialized AgentCommunicator with {len(agent_registry)} agents"
        )

    async def start(self):
        """Start the communicator (initialize HTTP client)."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.timeout)
            logger.debug("Started HTTP client for agent communication")

    async def stop(self):
        """Stop the communicator (cleanup HTTP client)."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
            logger.debug("Stopped HTTP client for agent communication")

    async def send_message_to_agent(
        self,
        agent_name: str,
        message_text: str,
        task_id: Optional[str] = None,
        context_id: Optional[str] = None,
    ) -> Task:
        """
        Send a message to another agent and get the task back.

        This is the primary method for inter-agent communication. It:
        1. Connects to the remote agent (if not already connected)
        2. Sends a user message with the given text
        3. Returns the Task object from the response

        Args:
            agent_name: Name of the agent to communicate with
            message_text: Text content of the message
            task_id: Optional task ID to continue an existing task
            context_id: Optional context ID to maintain conversation context

        Returns:
            Task object from the agent's response

        Raises:
            ValueError: If agent not found in registry
            RuntimeError: If communication fails
        """
        # Ensure HTTP client is started
        if not self._http_client:
            await self.start()

        # Connect to agent if not already connected
        if agent_name not in self._clients:
            await self._connect_to_agent(agent_name)

        if agent_name not in self._clients:
            raise ValueError(f"Agent {agent_name} not available")

        # Create message
        message = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[TextPart(text=message_text)],
            task_id=task_id,
            context_id=context_id,
        )

        # Create request
        message_request = SendMessageRequest(
            id=str(uuid.uuid4()),
            params=MessageSendParams(message=message)
        )

        logger.debug(
            f"Sending message to {agent_name}: {message_text[:100]}..."
        )

        try:
            # Send message
            response: SendMessageResponse = await self._clients[agent_name].send_message(
                message_request
            )

            # Extract task from response
            if isinstance(response.root, SendMessageSuccessResponse):
                if isinstance(response.root.result, Task):
                    logger.debug(
                        f"Received task {response.root.result.id} from {agent_name}"
                    )
                    return response.root.result
                elif isinstance(response.root.result, Message):
                    # Agent returned a direct message instead of a task
                    # This shouldn't happen with proper A2A agents, but handle it
                    logger.warning(
                        f"{agent_name} returned Message instead of Task"
                    )
                    raise RuntimeError(
                        f"Agent {agent_name} returned Message instead of Task"
                    )

            raise RuntimeError(
                f"Failed to get task from {agent_name}: Invalid response"
            )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error communicating with {agent_name}: {e}")
            raise RuntimeError(
                f"Failed to communicate with {agent_name}: {e}"
            ) from e

    async def ask_agent(
        self,
        agent_name: str,
        question: str,
        context_id: Optional[str] = None,
    ) -> str:
        """
        Ask another agent a question and get a text response.

        Convenience method for quick questions that extracts text from
        the agent's response (from artifacts or history).

        Args:
            agent_name: Name of the agent to ask
            question: Question text
            context_id: Optional context ID for conversation continuity

        Returns:
            Text response from the agent

        Raises:
            ValueError: If agent not found
            RuntimeError: If communication fails
        """
        # Send message and get task
        task = await self.send_message_to_agent(
            agent_name=agent_name,
            message_text=question,
            task_id=None,  # New task for each question
            context_id=context_id,
        )

        # Extract text from task
        response_text = self._extract_text_from_task(task)

        if not response_text:
            logger.warning(f"No text response from {agent_name}")
            return "No response"

        return response_text

    async def _connect_to_agent(self, agent_name: str):
        """
        Connect to a remote agent.

        Fetches the agent card and creates an A2A client.

        Args:
            agent_name: Name of the agent to connect to
        """
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")

        # Get agent URL from registry
        agent_url = self.agent_registry.get(agent_name)
        if not agent_url:
            raise ValueError(
                f"Agent {agent_name} not found in registry. "
                f"Available agents: {list(self.agent_registry.keys())}"
            )

        try:
            logger.debug(f"Connecting to {agent_name} at {agent_url}")

            # Fetch agent card
            card_resolver = A2ACardResolver(self._http_client, agent_url)
            card = await card_resolver.get_agent_card()

            # Create A2A client
            client = A2AClient(self._http_client, card, url=agent_url)

            # Store
            self._clients[agent_name] = client
            self._cards[agent_name] = card

            logger.info(
                f"Connected to {agent_name} ({card.name}) at {agent_url}"
            )

        except httpx.ConnectError as e:
            logger.error(
                f"Failed to connect to {agent_name} at {agent_url}: {e}"
            )
            raise ValueError(
                f"Cannot connect to {agent_name}. Is the agent running at {agent_url}?"
            ) from e
        except Exception as e:
            logger.error(
                f"Failed to initialize connection to {agent_name}: {e}"
            )
            raise

    def _extract_text_from_task(self, task: Task) -> str:
        """
        Extract text from a task's artifacts or history.

        Tries multiple sources in order:
        1. Last artifact
        2. Last message in history
        3. Status message

        Args:
            task: Task to extract text from

        Returns:
            Extracted text, or empty string if none found
        """
        import json

        def extract_text_from_part(part_root) -> Optional[str]:
            """Helper to extract and normalize text from a part."""
            if hasattr(part_root, 'text'):
                text = part_root.text
                # Handle non-string text (dict, list, etc.)
                if isinstance(text, dict):
                    return json.dumps(text, indent=2)
                elif isinstance(text, (list, tuple)):
                    return json.dumps(text, indent=2)
                elif isinstance(text, str):
                    return text
                else:
                    return str(text)
            return None

        # Try artifacts first
        if task.artifacts:
            last_artifact = task.artifacts[-1]
            for part in last_artifact.parts:
                # Access the part (could be wrapped in RootModel)
                part_root = part.root if hasattr(part, 'root') else part
                text = extract_text_from_part(part_root)
                if text:
                    return text

        # Try history
        if task.history:
            last_message = task.history[-1]
            for part in last_message.parts:
                part_root = part.root if hasattr(part, 'root') else part
                text = extract_text_from_part(part_root)
                if text:
                    return text

        # Try status message
        if task.status.message:
            for part in task.status.message.parts:
                part_root = part.root if hasattr(part, 'root') else part
                text = extract_text_from_part(part_root)
                if text:
                    return text

        return ""

    def get_agent_card(self, agent_name: str) -> Optional[AgentCard]:
        """
        Get the agent card for a connected agent.

        Args:
            agent_name: Name of the agent

        Returns:
            AgentCard if agent is connected, None otherwise
        """
        return self._cards.get(agent_name)

    def is_connected(self, agent_name: str) -> bool:
        """
        Check if connected to an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            True if connected, False otherwise
        """
        return agent_name in self._clients

    def list_available_agents(self) -> list[str]:
        """
        List all agents in the registry.

        Returns:
            List of agent names
        """
        return list(self.agent_registry.keys())

    def list_connected_agents(self) -> list[str]:
        """
        List all currently connected agents.

        Returns:
            List of connected agent names
        """
        return list(self._clients.keys())

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
