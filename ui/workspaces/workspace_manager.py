from typing import List, Dict
from ui.workspaces.workspace import Workspace
from ui.workspaces.engineering_workspace import EngineeringWorkspace

class WorkspaceManager:
    """Manages multiple workspaces in Lessan AI."""
    
    def __init__(self):
        self.workspaces: List[Workspace] = []
        self.active_workspace: Workspace = None

    def create_workspace(self, name: str, config: Dict, workspace_type: str = "General"):
        """Create and add a new workspace."""
        if workspace_type == "Engineering":
            workspace = EngineeringWorkspace(name, config)
        else:
            workspace = Workspace(name, config)
            
        self.workspaces.append(workspace)
        if not self.active_workspace:
            self.active_workspace = workspace

    def switch_workspace(self, name: str):
        """Switch to an existing workspace by name."""
        for workspace in self.workspaces:
            if workspace.name == name:
                self.active_workspace = workspace
                return
        raise ValueError(f"Workspace '{name}' not found.")

    def delete_workspace(self, name: str):
        """Delete a workspace by name."""
        self.workspaces = [ws for ws in self.workspaces if ws.name != name]
        if self.active_workspace and self.active_workspace.name == name:
            self.active_workspace = self.workspaces[0] if self.workspaces else None

    def list_workspaces(self) -> List[str]:
        """List all workspace names."""
        return [ws.name for ws in self.workspaces]

# Global instance
workspace_manager = WorkspaceManager()