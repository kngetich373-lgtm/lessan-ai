# Predefined workspaces for Lessan AI.

from workspaces.predefined.personal_workspace import PersonalWorkspace
from workspaces.predefined.engineering_workspace import EngineeringWorkspace
from workspaces.predefined.cybersecurity_workspace import CybersecurityWorkspace
from workspaces.predefined.research_workspace import ResearchWorkspace
from workspaces.predefined.automation_workspace import AutomationWorkspace
from workspaces.predefined.settings_workspace import SettingsWorkspace


def register_all() -> None:
    """Register all predefined workspaces into the global registry."""
    from workspaces.workspace_registry import workspace_registry

    workspace_registry.register(PersonalWorkspace)
    workspace_registry.register(EngineeringWorkspace)
    workspace_registry.register(CybersecurityWorkspace)
    workspace_registry.register(ResearchWorkspace)
    workspace_registry.register(AutomationWorkspace)
    workspace_registry.register(SettingsWorkspace)