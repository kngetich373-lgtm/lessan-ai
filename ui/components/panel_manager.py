from PyQt6.QtWidgets import QMainWindow
from ui.components.base import DockablePanel

class PanelManager:
    """Manages dockable panels in Lessan AI."""
    
    def __init__(self, main_window: QMainWindow):
        self.main_window = main_window
        self.panels = {}

    def register_panel(self, panel_id: str, panel: DockablePanel):
        """Register a new dockable panel."""
        self.panels[panel_id] = panel
        self.main_window.addDockWidget(panel.allowedAreas(), panel)

    def show_panel(self, panel_id: str):
        """Show a registered panel."""
        if panel_id in self.panels:
            self.panels[panel_id].show()

    def hide_panel(self, panel_id: str):
        """Hide a registered panel."""
        if panel_id in self.panels:
            self.panels[panel_id].hide()

    def toggle_panel(self, panel_id: str):
        """Toggle visibility of a registered panel."""
        if panel_id in self.panels:
            panel = self.panels[panel_id]
            if panel.isVisible():
                panel.hide()
            else:
                panel.show()