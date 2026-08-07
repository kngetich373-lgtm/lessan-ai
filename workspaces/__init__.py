# Lessan AI Workspace Framework
#
# Domain-specific workspaces built on the BaseWorkspace infrastructure.
# Each workspace inherits from BaseWorkspace and provides domain-specific
# capabilities, tools, and configurations.

from workspaces.base_workspace import BaseWorkspace
from workspaces.workspace_registry import workspace_registry

__all__ = ["BaseWorkspace", "workspace_registry"]