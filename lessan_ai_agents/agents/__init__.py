"""
The eleven concrete role agents for Lessan AI's Agent Framework.

Each agent is architecture only: it declares responsibilities,
objectives, capabilities, an execution interface (inherited from
BaseAgent), a prompt template, and a memory interface hookup. None of
them generate software or implement multi-step workflows — see
`_role_agent.RoleAgent._run` for the shared, deliberately inert
execution stub, and `ceo_agent.CEOAgent` for the coordination-only
delegation method.
"""

from .ceo_agent import CEOAgent
from .product_manager_agent import ProductManagerAgent
from .solution_architect_agent import SolutionArchitectAgent
from .ui_designer_agent import UIDesignerAgent
from .frontend_engineer_agent import FrontendEngineerAgent
from .backend_engineer_agent import BackendEngineerAgent
from .database_engineer_agent import DatabaseEngineerAgent
from .qa_engineer_agent import QAEngineerAgent
from .security_engineer_agent import SecurityEngineerAgent
from .devops_engineer_agent import DevOpsEngineerAgent
from .documentation_engineer_agent import DocumentationEngineerAgent

__all__ = [
    "CEOAgent",
    "ProductManagerAgent",
    "SolutionArchitectAgent",
    "UIDesignerAgent",
    "FrontendEngineerAgent",
    "BackendEngineerAgent",
    "DatabaseEngineerAgent",
    "QAEngineerAgent",
    "SecurityEngineerAgent",
    "DevOpsEngineerAgent",
    "DocumentationEngineerAgent",
]


def build_default_roster(memory=None, communication_bus=None) -> list:
    """Convenience factory: instantiate all eleven agents wired to the
    same memory/communication-bus instances (if provided). Purely a
    constructor convenience — it registers nothing and dispatches
    nothing, keeping AgentRegistry/AgentManager as the only places
    that own agent lifecycle.
    """
    agent_classes = [
        CEOAgent,
        ProductManagerAgent,
        SolutionArchitectAgent,
        UIDesignerAgent,
        FrontendEngineerAgent,
        BackendEngineerAgent,
        DatabaseEngineerAgent,
        QAEngineerAgent,
        SecurityEngineerAgent,
        DevOpsEngineerAgent,
        DocumentationEngineerAgent,
    ]
    return [cls(memory=memory, communication_bus=communication_bus) for cls in agent_classes]
