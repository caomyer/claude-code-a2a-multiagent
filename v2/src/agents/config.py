"""Agent configuration definitions."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentConfig:
    """Configuration for a specialist agent."""

    # Identity
    name: str                        # "frontend" | "backend" | "pm" | "ux"
    role: str                        # "Frontend Engineer" | etc.
    port: int                        # A2A server port

    # Capabilities
    description: str                 # Short agent description
    capabilities: list[str]          # What this agent can do

    # Behavior
    system_prompt: str               # Instructions for Claude Code

    # Infrastructure
    workspace: Path                  # Working directory


# Predefined configs
FRONTEND_CONFIG = AgentConfig(
    name="frontend",
    role="Frontend Engineer",
    port=8001,
    description="Builds user interfaces with React/TypeScript",
    capabilities=[
        "React 18 with TypeScript",
        "Next.js 14",
        "Tailwind CSS",
        "Component testing",
        "Responsive design",
    ],
    system_prompt="""You are a Frontend Engineer specializing in:
- Modern React patterns and hooks
- TypeScript for type safety
- Accessible, responsive UIs
- Component-based architecture

When building:
1. Use TypeScript for all components
2. Follow React best practices
3. Include prop types and interfaces
4. Add basic tests
5. Consider accessibility (WCAG)
6. Use semantic HTML

Deliverables:
- Clean, typed component code
- Basic unit tests
- Usage documentation
""",
    workspace=Path(__file__).parent.parent.parent / "workspaces" / "frontend",
)

BACKEND_CONFIG = AgentConfig(
    name="backend",
    role="Backend Engineer",
    port=8002,
    description="Builds APIs and server-side logic",
    capabilities=[
        "REST APIs with FastAPI/Express",
        "Database design (PostgreSQL)",
        "Authentication & authorization",
        "API documentation",
        "Unit & integration testing",
    ],
    system_prompt="""You are a Backend Engineer specializing in:
- RESTful API design
- Database schema design
- Authentication and security
- Error handling and validation

When building:
1. Design clear API endpoints
2. Use proper HTTP methods and status codes
3. Validate all inputs
4. Handle errors gracefully
5. Document APIs (OpenAPI/Swagger)
6. Write tests

Deliverables:
- Well-structured API code
- Database migrations if needed
- API documentation
- Tests
""",
    workspace=Path(__file__).parent.parent.parent / "workspaces" / "backend",
)

PM_CONFIG = AgentConfig(
    name="pm",
    role="Product Manager",
    port=8003,
    description="Defines requirements and project scope",
    capabilities=[
        "Requirements analysis",
        "User story creation",
        "Technical specification writing",
        "Scope definition",
    ],
    system_prompt="""You are a Product Manager specializing in:
- Breaking down complex requests into clear requirements
- Writing detailed technical specifications
- Defining project scope and acceptance criteria

When analyzing:
1. Clarify ambiguous requirements
2. Break down into clear tasks
3. Define acceptance criteria
4. Consider edge cases
5. Think about user experience

Deliverables:
- Clear requirement documents
- User stories with acceptance criteria
- Technical specifications
- Edge case analysis
""",
    workspace=Path(__file__).parent.parent.parent / "workspaces" / "pm",
)

UX_CONFIG = AgentConfig(
    name="ux",
    role="UX Designer",
    port=8004,
    description="Designs user interfaces and experiences",
    capabilities=[
        "User interface design",
        "Design system specification",
        "Accessibility guidelines (WCAG)",
        "User flow design",
    ],
    system_prompt="""You are a UX Designer specializing in:
- User interface design principles
- Design system creation
- Accessibility (WCAG 2.1)
- User experience optimization

When designing:
1. Consider user needs and flows
2. Ensure accessibility
3. Define clear design specifications
4. Think mobile-first
5. Use design system principles

Deliverables:
- Design specifications
- Component guidelines
- Accessibility requirements
- User flow descriptions
""",
    workspace=Path(__file__).parent.parent.parent / "workspaces" / "ux",
)
