from PyQt6.QtWidgets import QMainWindow
from ui.core.event_bus import bus
from ui.core.state import state
from ui.core.theme import theme
from ui.components.panel_manager import PanelManager
from ui.workspaces.workspace_manager import workspace_manager
from ui.agents.agent_manager import agent_manager
from ui.plugins.plugin_manager import plugin_manager
from ui.components.base import DockablePanel

class MainWindow(QMainWindow):
    """Main application window for Lessan AI."""
    
    def __init__(self, face_image: str = "face.png"):
        super().__init__()
        self.setWindowTitle("Lessan AI")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet(f"background: {theme.BG};")
        
        # Initialize managers
        self.panel_manager = PanelManager(self)
        self.workspace_manager = workspace_manager
        self.agent_manager = agent_manager
        self.plugin_manager = plugin_manager
        
        # Initialize panels
        self._initialize_panels()
        
        # Connect event bus
        self._connect_event_bus()
        
        # Initialize state
        self._initialize_state()
        
        # Show workspace switcher
        self._setup_workspace_switcher()
        
        # Show agent selector
        self._setup_agent_selector()
        
        # Initialize plugins
        self.plugin_manager.discover_plugins()
        
        # Update UI from state
        self._update_ui_from_state()
        
        # Show window
        self.show()

    def _initialize_panels(self):
        """Create and register all main panels."""
        # System Stats Panel
        self.system_panel = SystemStatsPanel()
        self.panel_manager.register_panel("system", self.system_panel)
        
        # Chat Panel
        self.chat_panel = ChatPanel()
        self.panel_manager.register_panel("chat", self.chat_panel)
        
        # Astral Core Panel
        self.astral_core = AstralCorePanel()
        self.panel_manager.register_panel("astral_core", self.astral_core)
        
        # Plugin Panel
        self.plugin_panel = PluginPanel()
        self.panel_manager.register_panel("plugins", self.plugin_panel)
        
        # Workspace Panel
        self.workspace_panel = WorkspacePanel()
        self.panel_manager.register_panel("workspaces", self.workspace_panel)
        
        # Agent Panel
        self.agent_panel = AgentPanel()
        self.panel_manager.register_panel("agents", self.agent_panel)

    def _connect_event_bus(self):
        """Connect event bus signals to UI updates."""
        bus.agent_state_changed.connect(self._on_agent_state_changed)
        bus.metric_updated.connect(self._on_metric_updated)
        bus.workspace_switched.connect(self._on_workspace_switched)
        bus.plugin_loaded.connect(self._on_plugin_loaded)
        bus.file_dropped.connect(self._on_file_dropped)

    def _on_agent_state_changed(self, data: dict):
        """Handle agent state changes."""
        self.agent_panel.update_agent_status(data)

    def _on_metric_updated(self, data: dict):
        """Handle metric updates."""
        self.system_panel.update_metrics(data)

    def _on_workspace_switched(self, name: str):
        """Handle workspace switches."""
        self.workspace_panel.update_workspace(name)

    def _on_plugin_loaded(self, name: str):
        """Handle plugin loading."""
        self.plugin_panel.update_plugin_list()

    def _on_file_dropped(self, file_path: str):
        """Handle file drop events."""
        self.chat_panel.handle_file_drop(file_path)

    def _initialize_state(self):
        """Initialize state from saved data."""
        state.update_state("metrics", {
            "cpu": 0.0,
            "mem": 0.0,
            "net": 0.0,
            "gpu": -1.0,
            "tmp": -1.0,
            "bat": -1.0,
            "charging": False
        })

    def _setup_workspace_switcher(self):
        """Create workspace switcher in status bar."""
        workspace_menu = self.menuBar().addMenu("Workspaces")
        for workspace in workspace_manager.list_workspaces():
            action = workspace_menu.addAction(workspace)
            action.triggered.connect(lambda _, n=workspace: self.workspace_manager.switch_workspace(n))

    def _setup_agent_selector(self):
        """Create agent selector in status bar."""
        agent_menu = self.menuBar().addMenu("Agents")
        for agent in agent_manager.agents:
            action = agent_menu.addAction(agent.name)
            action.triggered.connect(lambda _, n=agent.name: self.agent_manager.set_active_agent(n))

    def _update_ui_from_state(self):
        """Update UI elements from state."""
        self.system_panel.update_metrics(state.get_state()["metrics"])
        self.agent_panel.update_agent_list(agent_manager.agents)
        self.workspace_panel.update_workspace_list(workspace_manager.list_workspaces())