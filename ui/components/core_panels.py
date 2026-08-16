"""Small, dependency-light panels used by the primary Lessan shell.

These panels intentionally contain presentation only. Backend services are
injected by the application layer rather than imported by widgets.
"""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
    QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)
from ui.core.theme import theme


def _card(parent=None):
    frame = QFrame(parent)
    frame.setObjectName("card")
    return frame


class ChatPanel(QWidget):
    """Primary conversation surface; transport is supplied by the caller."""
    send_requested = pyqtSignal(str)
    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 14)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Conversation")
        title.setObjectName("pageTitle")
        self.status = QLabel("Ready")
        self.status.setObjectName("muted")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.status)
        root.addLayout(header)

        self.messages = QTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setPlaceholderText("Your conversation will appear here.")
        root.addWidget(self.messages, 1)

        composer = _card()
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(12, 10, 12, 10)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask Lessan to build, analyze, automate, or explain…")
        self.input.returnPressed.connect(self._send)
        composer_layout.addWidget(self.input)
        actions = QHBoxLayout()
        attach = QPushButton("Attach")
        attach.setEnabled(False)
        actions.addWidget(attach)
        actions.addStretch()
        stop = QPushButton("Stop")
        stop.clicked.connect(self.stop_requested)
        send = QPushButton("Send")
        send.setObjectName("primary")
        send.clicked.connect(self._send)
        actions.addWidget(stop)
        actions.addWidget(send)
        composer_layout.addLayout(actions)
        root.addWidget(composer)

    def _send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.messages.append(f"<b>You</b><br>{text}")
        self.input.clear()
        self.status.setText("Request queued")
        self.send_requested.emit(text)

    def set_status(self, text: str):
        self.status.setText(text)


class SystemStatsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        title = QLabel("System status")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.labels = {}
        for key, value in (("CPU", "—"), ("Memory", "—"), ("Network", "—"), ("Kernel", "Ready")):
            row = QHBoxLayout()
            label = QLabel(key)
            value_label = QLabel(value)
            value_label.setObjectName("value")
            row.addWidget(label)
            row.addStretch()
            row.addWidget(value_label)
            layout.addLayout(row)
            self.labels[key] = value_label
        layout.addStretch()

    def update_metrics(self, data):
        mapping = {"cpu": "CPU", "mem": "Memory", "net": "Network"}
        for source, target in mapping.items():
            if source in data:
                self.labels[target].setText(str(data[source]))


class ContextPanel(QWidget):
    """Compact contextual inspector for the current task."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        title = QLabel("Current context")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.rows = {}
        for key in ("Agent", "Model", "Provider", "Task", "Connection"):
            row = QHBoxLayout()
            label = QLabel(key)
            value = QLabel("Not configured")
            value.setObjectName("value")
            value.setWordWrap(True)
            row.addWidget(label)
            row.addStretch()
            row.addWidget(value)
            layout.addLayout(row)
            self.rows[key] = value
        layout.addStretch()

    def set_value(self, key: str, value: str):
        if key in self.rows:
            self.rows[key].setText(value)


class SimpleListPanel(QWidget):
    def __init__(self, title: str, empty_text: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        hint = QLabel(empty_text)
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.list = QListWidget()
        layout.addWidget(self.list, 1)

    def set_items(self, items):
        self.list.clear()
        self.list.addItems(items)
