"""Agent configuration dataclass for multi-agent system."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class AgentConfig:
    """
    Configuration for an agent in the multi-agent system.

    This configuration defines:
    - Agent identity (name, role)
    - Network configuration (port, URLs)
    - Capabilities and skills
    - AI behavior (system prompt)
    - Coordination (related agents)
    - Workspace location
    """

    # Identity
    name: str
    """Agent name (e.g., 'frontend', 'backend')"""

    role: str
    """Agent role description (e.g., 'Frontend Engineer')"""

    description: str
    """Brief description of what the agent does"""

    # Network Configuration
    port: int
    """Port for A2A server (e.g., 8001)"""

    url: Optional[str] = None
    """Full URL for agent (auto-generated if None)"""

    # Capabilities
    capabilities: list[str] = field(default_factory=list)
    """List of agent capabilities (e.g., ['React', 'TypeScript'])"""

    skills: list[dict] = field(default_factory=list)
    """List of agent skills for A2A AgentCard (auto-generated from capabilities)"""

    # AI Behavior
    system_prompt: str = ""
    """System prompt for Claude API defining agent behavior and expertise"""

    # Coordination
    related_agents: list[str] = field(default_factory=list)
    """Names of agents this agent frequently coordinates with"""

    # Workspace
    workspace: Optional[Path] = None
    """Workspace directory for Claude Code (auto-generated if None)"""

    # Model Configuration
    model: str = "claude-sonnet-4-5-20250929"
    """Claude model to use for intelligence layer"""

    max_tokens: int = 4096
    """Maximum tokens for Claude API responses"""

    temperature: float = 1.0
    """Temperature for Claude API responses"""

    def __post_init__(self):
        """Validate and auto-generate missing fields."""
        # Auto-generate URL if not provided
        if self.url is None:
            self.url = f"http://localhost:{self.port}"

        # Auto-generate workspace if not provided
        if self.workspace is None:
            self.workspace = Path(f"./workspaces/{self.name}")
        else:
            self.workspace = Path(self.workspace)

        # Ensure workspace exists
        self.workspace.mkdir(parents=True, exist_ok=True)

        # Auto-generate skills from capabilities if not provided
        if not self.skills and self.capabilities:
            self.skills = [{
                'id': f"{self.name}_skill",
                'name': f"{self.role} Skills",
                'description': f"Expertise in {', '.join(self.capabilities[:3])}",
                'tags': [cap.lower().replace(' ', '_') for cap in self.capabilities[:5]],
                'examples': [f"Help with {self.capabilities[0].lower()}"] if self.capabilities else []
            }]

    def get_agent_card_dict(self) -> dict:
        """
        Generate AgentCard dictionary for A2A protocol.

        Returns:
            Dictionary suitable for creating an A2A AgentCard
        """
        return {
            'name': f"{self.role} Agent",
            'description': self.description,
            'url': self.url,
            'version': '1.0.0',
            'default_input_modes': ['text'],
            'default_output_modes': ['text'],
            'capabilities': {
                'streaming': True,
                'push_notifications': False
            },
            'skills': self.skills
        }

    def get_claude_system_prompt(self) -> str:
        """
        Get the complete system prompt for Claude API.

        Returns:
            Full system prompt including role, capabilities, and instructions
        """
        if self.system_prompt:
            return self.system_prompt

        # Generate default system prompt if not provided
        return f"""You are a {self.role} agent in a multi-agent system.

Your expertise:
{chr(10).join(f'- {cap}' for cap in self.capabilities[:10])}

Your role is to analyze tasks, coordinate with other agents when needed, and execute work autonomously.

When you receive a task:
1. Analyze what needs to be done
2. Determine if you need input from other agents
3. Create a clear execution plan
4. Execute the work professionally

Always provide clear, actionable output."""

    def to_dict(self) -> dict:
        """Convert config to dictionary."""
        return {
            'name': self.name,
            'role': self.role,
            'description': self.description,
            'port': self.port,
            'url': self.url,
            'capabilities': self.capabilities,
            'skills': self.skills,
            'system_prompt': self.system_prompt,
            'related_agents': self.related_agents,
            'workspace': str(self.workspace),
            'model': self.model,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AgentConfig':
        """Create config from dictionary."""
        return cls(**data)
