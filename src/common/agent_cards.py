"""A2A AgentCard generation utilities."""

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .agent_config import AgentConfig


def create_agent_card(config: AgentConfig) -> AgentCard:
    """
    Create an A2A AgentCard from an AgentConfig.

    Args:
        config: Agent configuration

    Returns:
        A2A AgentCard for this agent
    """
    # Create skills from config
    skills = []
    for skill_dict in config.skills:
        skill = AgentSkill(
            id=skill_dict.get('id', f"{config.name}_skill"),
            name=skill_dict.get('name', f"{config.role} Skills"),
            description=skill_dict.get('description', config.description),
            tags=skill_dict.get('tags', []),
            examples=skill_dict.get('examples', [])
        )
        skills.append(skill)

    # If no skills defined, create a default one
    if not skills:
        skills = [
            AgentSkill(
                id=f"{config.name}_general",
                name=f"{config.role} Services",
                description=config.description,
                tags=[config.name],
                examples=[f"Help with {config.name} tasks"]
            )
        ]

    # Create capabilities
    capabilities = AgentCapabilities(
        streaming=True,
        push_notifications=False
    )

    # Create agent card
    return AgentCard(
        name=f"{config.role} Agent",
        description=config.description,
        url=config.url,
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=capabilities,
        skills=skills
    )


def get_agent_card_dict(config: AgentConfig) -> dict:
    """
    Get AgentCard as dictionary (for JSON serialization).

    Args:
        config: Agent configuration

    Returns:
        Dictionary representation of AgentCard
    """
    card = create_agent_card(config)
    return card.model_dump(exclude_none=True)
