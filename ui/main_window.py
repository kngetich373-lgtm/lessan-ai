"""Primary PyQt6 shell for Lessan AI."""
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from ui.components.core_panels import ChatPanel, ContextPanel, SimpleListPanel
from ui.components.settings_panel import SettingsPanel
from ui.core.theme import theme
from ui.agents.agent_manager import agent_manager
from ui.workspaces.workspace_manager import workspace_manager


class MainWindow(QMainWindow):
    NAV_ITEMS = [("Overview", "overview"), ("Agents", "agents"), ("Tasks", "tasks"), ("Models", "models"), ("Providers", "providers"), ("Plugins", "plugins"), ("Workspaces", "workspaces"), ("Settings", "settings")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lessan AI")
        self.setMinimumSize(1000, 680)
        self.resize(1440, 900)
        self._build_ui()
        self._apply_theme()
        self._refresh_context()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(218)
        nav = QVBoxLayout(self.sidebar)
        nav.setContentsMargins(14, 18, 14, 14)
        brand = QLabel("LESSAN")
        brand.setObjectName("brand")
        nav.addWidget(brand)
        subtitle = QLabel("AI Engineering OS")
        subtitle.setObjectName("muted")
        nav.addWidget(subtitle)
        nav.addSpacing(16)
        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navList")
        for label, _ in self.NAV_ITEMS:
            self.nav_list.addItem(label)
        self.nav_list.currentRowChanged.connect(self._navigate)
        nav.addWidget(self.nav_list, 1)
        outer.addWidget(self.sidebar)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        topbar = QFrame()
        topbar.setObjectName("topbar")
        top = QHBoxLayout(topbar)
        top.setContentsMargins(16, 10, 16, 10)
        self.page_title = QLabel("Overview")
        self.page_title.setObjectName("topTitle")
        top.addWidget(self.page_title)
        top.addStretch()
        self.connection = QLabel("● Ready")
        self.connection.setObjectName("status")
        top.addWidget(self.connection)
        self.context_button = QPushButton("Context")
        self.context_button.setCheckable(True)
        self.context_button.setChecked(True)
        self.context_button.clicked.connect(self._toggle_context)
        top.addWidget(self.context_button)
        center_layout.addWidget(topbar)

        self.stack = QStackedWidget()
        self.chat = ChatPanel()
        self.stack.addWidget(self.chat)
        self._pages = {"overview": self.chat}
        for page_id, title_text, empty in [
            ("agents", "Agents", "No agents are registered yet. Configure an agent to begin."),
            ("tasks", "Tasks", "No tasks are running. Tasks will appear here when Lessan starts work."),
            ("models", "Models", "No models have been discovered yet."),
            ("providers", "Providers", "No providers are configured. Add credentials in Settings."),
            ("plugins", "Plugins", "No plugins are currently available."),
            ("workspaces", "Workspaces", "Create a workspace to organize engineering work."),
        ]:
            page = SimpleListPanel(title_text, empty)
            self.stack.addWidget(page)
            self._pages[page_id] = page
        self.settings = SettingsPanel()
        self.stack.addWidget(self.settings)
        self._pages["settings"] = self.settings
        center_layout.addWidget(self.stack, 1)
        self.statusBar().showMessage("Lessan ready · No provider required for startup")
        outer.addWidget(center, 1)

        self.context_panel = QFrame()
        self.context_panel.setObjectName("contextPanel")
        self.context_panel.setFixedWidth(270)
        context_layout = QVBoxLayout(self.context_panel)
        context_layout.setContentsMargins(0, 0, 0, 0)
        self.context = ContextPanel()
        context_layout.addWidget(self.context)
        outer.addWidget(self.context_panel)

    def _navigate(self, row: int):
        if row < 0 or row >= len(self.NAV_ITEMS):
            return
        label, page_id = self.NAV_ITEMS[row]
        self.stack.setCurrentWidget(self._pages[page_id])
        self.page_title.setText(label)

    def _toggle_context(self, checked: bool):
        self.context_panel.setVisible(checked)
        self.context_button.setText("Context" if checked else "Show context")

    def _refresh_context(self):
        agent = getattr(agent_manager, "active_agent", None)
        workspace = getattr(workspace_manager, "active_workspace", None)
        self.context.set_value("Agent", getattr(agent, "name", "None"))
        self.context.set_value("Task", "Idle")
        self.context.set_value("Connection", "Ready")
        self.context.set_value("Provider", "Not configured")
        self.context.set_value("Model", "Auto")
        if workspace is not None:
            self.context.set_value("Task", f"Workspace: {workspace.name}")

    def set_connection_status(self, text: str, healthy: bool = True):
        self.connection.setText(f"● {text}")
        self.connection.setProperty("healthy", healthy)
        self.connection.style().unpolish(self.connection)
        self.connection.style().polish(self.connection)

    def _apply_theme(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {theme.BG}; color: {theme.TEXT}; }}
            #sidebar {{ background: {theme.PANEL}; border-right: 1px solid {theme.BORDER}; }}
            #topbar {{ background: {theme.PANEL}; border-bottom: 1px solid {theme.BORDER}; }}
            #contextPanel {{ background: {theme.PANEL}; border-left: 1px solid {theme.BORDER}; }}
            #brand {{ color: {theme.PRIMARY_L}; font-size: 20px; font-weight: 800; letter-spacing: 2px; }}
            #topTitle {{ color: {theme.TEXT}; font-size: 17px; font-weight: 700; }}
            #muted {{ color: {theme.TEXT_D}; }}
            #status {{ color: {theme.SUCCESS}; font-weight: 600; }}
            #navList {{ background: transparent; border: none; outline: none; }}
            #navList::item {{ padding: 10px 12px; border-radius: 7px; color: {theme.TEXT_D}; }}
            #navList::item:selected {{ background: {theme.CARD}; color: {theme.TEXT}; }}
            QPushButton {{ background: {theme.CARD}; color: {theme.TEXT_D}; border: 1px solid {theme.BORDER}; padding: 7px 12px; border-radius: 6px; }}
            QPushButton:hover {{ border-color: {theme.BORDER_L}; color: {theme.TEXT}; }}
            QPushButton#primary {{ background: {theme.PRIMARY_D}; color: {theme.WHITE}; border: none; }}
            QLineEdit, QTextEdit, QListWidget {{ background: {theme.PANEL}; border: 1px solid {theme.BORDER}; border-radius: 8px; color: {theme.TEXT}; padding: 8px; }}
            QStatusBar {{ background: {theme.BG}; color: {theme.TEXT_D}; border-top: 1px solid {theme.BORDER}; }}
        """)

    def _initialize_panels(self):
        return None
    def _connect_event_bus(self):
        return None
    def _initialize_state(self):
        return None
    def _setup_workspace_switcher(self):
        return None
    def _setup_agent_selector(self):
        return None
    def _update_ui_from_state(self):
        self._refresh_context()
