from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QLabel, QHBoxLayout, QFrame
from PyQt6.QtCore import Qt
from ui.core.theme import theme

class PanelHeader(QFrame):
    """Custom header for dockable panels."""
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet(f"""
            QFrame {{
                background: {theme.qcol(theme.PANEL, 220).name()};
                border-bottom: 1px solid {theme.BORDER};
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"color: {theme.TEXT_D}; font-weight: bold; font-size: 11px;")
        layout.addWidget(self.title_label)
        layout.addStretch()

class DockablePanel(QDockWidget):
    """Base class for all dockable panels in Lessan AI."""
    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        
        self.container = QWidget()
        self.setWidget(self.container)
        
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        self.header = PanelHeader(title)
        self.setTitleBarWidget(self.header)
        
        self.setStyleSheet(f"""
            QDockWidget {{
                color: {theme.TEXT};
                font-weight: bold;
                border: 1px solid {theme.BORDER};
            }}
            QWidget {{
                background: {theme.qcol(theme.PANEL_GLASS, 180).name()};
            }}
        """)