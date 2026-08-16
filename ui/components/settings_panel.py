"""Presentation layer for the Lessan AI settings workspace."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
    QWidget,
)

from ui.core.theme import theme


class SettingsPanel(QWidget):
    """Searchable settings surface with typed, masked controls."""

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
        self._controls = {}
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
        self.form = QFormLayout(page)
        self.form.setContentsMargins(4, 4, 12, 4)
        self.form.setSpacing(12)
        self.heading = QLabel("General")
        self.heading.setObjectName("pageTitle")
        self.description = QLabel(self.CATEGORIES[0][1])
        self.description.setObjectName("muted")
        self.description.setWordWrap(True)
        self.form.addRow(self.heading)
        self.form.addRow(self.description)
        self._show_category("General")
        scroll.setWidget(page)
        root.addWidget(scroll, 1)
        self.categories.setCurrentRow(0)

    def _clear_editor(self):
        while self.form.rowCount() > 2:
            self.form.removeRow(2)
        self._controls.clear()

    def _show_category(self, category):
        self._clear_editor()
        if category == "Providers":
            self._add_secret("API key", "provider.api_key")
            self._add_text("Base URL", "provider.base_url", "https://api.example.com")
            self._add_actions(provider=True)
        elif category == "Models":
            self._add_text("Default provider", "models.default_provider", "gemini")
            self._add_text("Live model", "models.live_model", "Auto")
            self._add_double("Temperature", "models.temperature", 0.0, 2.0, 0.4)
            self._add_int("Max tokens", "models.max_tokens", 1, 200000, 4096)
            self._add_actions()
        elif category == "Model Routing":
            self._add_int("Maximum fallbacks", "model_router.max_fallbacks", 0, 20, 3)
            self._add_double("Health timeout", "model_router.health.timeout", 0.1, 120.0, 5.0)
            self._add_actions()
        elif category == "Security":
            self._add_bool("Sandbox enabled", "security.sandbox_enabled", True)
            self._add_bool("Audit log enabled", "security.audit_log_enabled", True)
            self._add_actions()
        elif category == "Voice":
            self._add_bool("Voice enabled", "voice.enabled", True)
            self._add_text("Voice name", "voice.voice_name", "Charon")
            self._add_actions()
        elif category == "Vision":
            self._add_bool("Vision enabled", "vision.enabled", True)
            self._add_text("OCR language", "vision.ocr_language", "eng")
            self._add_actions()
        elif category == "Memory":
            self._add_bool("Memory enabled", "memory.enabled", True)
            self._add_int("History days", "memory.conversation_history_days", 1, 3650, 7)
            self._add_actions()
        elif category == "Scheduler":
            self._add_bool("Scheduler enabled", "scheduler.enabled", True)
            self._add_double("Tick seconds", "scheduler.tick_seconds", 0.1, 3600.0, 1.0)
            self._add_actions()
        else:
            self._add_text("Configuration", category.lower().replace(" ", "_"), "")
            self._add_actions()

    def _add_text(self, label, key, default):
        control = QLineEdit(default)
        self._controls[key] = control
        self.form.addRow(label, control)

    def _add_secret(self, label, key):
        control = QLineEdit()
        control.setEchoMode(QLineEdit.EchoMode.Password)
        control.setPlaceholderText("Stored securely; leave blank to keep current value")
        self._controls[key] = control
        self.form.addRow(label, control)

    def _add_bool(self, label, key, default):
        control = QCheckBox()
        control.setChecked(default)
        self._controls[key] = control
        self.form.addRow(label, control)

    def _add_int(self, label, key, minimum, maximum, default):
        control = QSpinBox()
        control.setRange(minimum, maximum)
        control.setValue(default)
        self._controls[key] = control
        self.form.addRow(label, control)

    def _add_double(self, label, key, minimum, maximum, default):
        control = QDoubleSpinBox()
        control.setRange(minimum, maximum)
        control.setDecimals(2)
        control.setValue(default)
        self._controls[key] = control
        self.form.addRow(label, control)

    def _add_actions(self, provider=False):
        actions = QHBoxLayout()
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        reset = QPushButton("Reset category")
        reset.clicked.connect(lambda: self.reset_requested.emit(self.heading.text()))
        actions.addWidget(save)
        actions.addWidget(reset)
        if provider:
            test = QPushButton("Test connection")
            test.clicked.connect(lambda: self.test_provider_requested.emit(self._controls.get("provider.base_url", QLineEdit()).text().strip()))
            actions.addWidget(test)
        actions.addStretch()
        self.form.addRow(actions)

    def _save(self):
        values = {key: self._value(control) for key, control in self._controls.items()}
        self.save_requested.emit(self.heading.text(), values)

    @staticmethod
    def _value(control):
        if isinstance(control, QCheckBox):
            return control.isChecked()
        if isinstance(control, (QSpinBox, QDoubleSpinBox)):
            return control.value()
        return control.text()

    def _select_category(self, row):
        if 0 <= row < len(self.CATEGORIES):
            name, description = self.CATEGORIES[row]
            self.heading.setText(name)
            self.description.setText(description)
            self._show_category(name)

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
            QListWidget, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background: {theme.PANEL}; color: {theme.TEXT}; border: 1px solid {theme.BORDER}; border-radius: 7px; }}
            QListWidget::item {{ padding: 9px; border-radius: 6px; color: {theme.TEXT_D}; }}
            QListWidget::item:selected {{ background: {theme.CARD}; color: {theme.TEXT}; }}
            QLineEdit, QSpinBox, QDoubleSpinBox {{ padding: 8px; }}
            QPushButton {{ background: {theme.CARD}; color: {theme.TEXT_D}; border: 1px solid {theme.BORDER}; padding: 7px 12px; border-radius: 6px; }}
            QPushButton:hover {{ border-color: {theme.BORDER_L}; color: {theme.TEXT}; }}
            QPushButton#primary {{ background: {theme.PRIMARY_D}; color: {theme.WHITE}; border: none; }}
        """)
