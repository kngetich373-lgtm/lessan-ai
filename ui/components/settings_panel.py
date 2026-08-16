"""Presentation layer for the Lessan AI settings workspace."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from ui.core.theme import theme


class SettingsPanel(QWidget):
    """Searchable settings surface kept independent from persistence."""

    save_requested = pyqtSignal(str, object)
    reset_requested = pyqtSignal(str)
    test_provider_requested = pyqtSignal(str)

    CATEGORIES = (
        ("General", "Application behaviour and defaults."),
        ("Appearance", "Theme and interface preferences."),
        ("Models", "Default model and generation settings."),
        ("Model Routing", "Routing, retry and fallback behaviour."),
        ("Providers", "Provider configuration and connection tests."),
        ("Voice", "Voice input and output settings."),
        ("Vision", "Vision and screenshot settings."),
        ("Memory", "Conversation memory behaviour."),
        ("Scheduler", "Background scheduling preferences."),
        ("Plugins", "Plugin discovery and management."),
        ("Security", "Sandbox and security controls."),
        ("Automation", "Automation and tool execution controls."),
        ("Paths", "Application and workspace locations."),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self._apply_theme()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        nav = QVBoxLayout()
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        nav.addWidget(title)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search settings...")
        self.search.textChanged.connect(self._filter)
        nav.addWidget(self.search)
        self.categories = QListWidget()
        for name, _ in self.CATEGORIES:
            self.categories.addItem(name)
        self.categories.currentRowChanged.connect(self._select_category)
        nav.addWidget(self.categories, 1)
        root.addLayout(nav, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        page = QWidget()
        content = QVBoxLayout(page)
        content.setContentsMargins(4, 4, 12, 4)
        content.setSpacing(12)
        self.heading = QLabel("General")
        self.heading.setObjectName("pageTitle")
        self.description = QLabel(self.CATEGORIES[0][1])
        self.description.setObjectName("muted")
        self.description.setWordWrap(True)
        content.addWidget(self.heading)
        content.addWidget(self.description)
        self.value = QLineEdit()
        self.value.setPlaceholderText("Setting value")
        content.addWidget(self.value)

        actions = QHBoxLayout()
        self.save = QPushButton("Save")
        self.save.setObjectName("primary")
        self.save.clicked.connect(lambda: self.save_requested.emit(self.heading.text(), self.value.text()))
        self.reset = QPushButton("Reset")
        self.reset.clicked.connect(lambda: self.reset_requested.emit(self.heading.text()))
        self.test = QPushButton("Test connection")
        self.test.clicked.connect(lambda: self.test_provider_requested.emit(self.value.text().strip()))
        actions.addWidget(self.save)
        actions.addWidget(self.reset)
        actions.addWidget(self.test)
        actions.addStretch()
        content.addLayout(actions)
        content.addStretch()
        scroll.setWidget(page)
        root.addWidget(scroll, 1)
        self.categories.setCurrentRow(0)

    def _select_category(self, row):
        if row < 0 or row >= len(self.CATEGORIES):
            return
        name, description = self.CATEGORIES[row]
        self.heading.setText(name)
        self.description.setText(description)
        self.value.clear()
        self.test.setVisible(name == "Providers")

    def _filter(self, text):
        needle = text.strip().lower()
        for index in range(self.categories.count()):
            item = self.categories.item(index)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _apply_theme(self):
        self.setStyleSheet(f"""
            QWidget {{ background: {theme.BG}; color: {theme.TEXT}; }}
            #pageTitle {{ color: {theme.TEXT}; font-size: 17px; font-weight: 700; }}
            #muted {{ color: {theme.TEXT_D}; }}
            QListWidget, QLineEdit {{ background: {theme.PANEL}; color: {theme.TEXT}; border: 1px solid {theme.BORDER}; border-radius: 7px; }}
            QListWidget::item {{ padding: 9px; border-radius: 6px; color: {theme.TEXT_D}; }}
            QListWidget::item:selected {{ background: {theme.CARD}; color: {theme.TEXT}; }}
            QLineEdit {{ padding: 8px; }}
            QPushButton {{ background: {theme.CARD}; color: {theme.TEXT_D}; border: 1px solid {theme.BORDER}; padding: 7px 12px; border-radius: 6px; }}
            QPushButton:hover {{ border-color: {theme.BORDER_L}; color: {theme.TEXT}; }}
            QPushButton#primary {{ background: {theme.PRIMARY_D}; color: {theme.WHITE}; border: none; }}
        """)
