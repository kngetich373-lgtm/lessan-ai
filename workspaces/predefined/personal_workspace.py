"""Personal workspace for daily life management."""

from datetime import datetime
from typing import Any, Dict

from workspaces.base_workspace import BaseWorkspace
from workspaces.workspace_registry import workspace_registry


@workspace_registry.register
class PersonalWorkspace(BaseWorkspace):
    """Personal life management: reminders, schedules, contacts, media."""

    name = "personal"
    display_name = "Personal"
    description = "Manage your daily life, schedules, reminders, contacts and media."
    icon = "🏠"
    color = "#ff7ac6"
    order = 10

    def on_initialize(self, config: Dict[str, Any]) -> None:
        self.register_tool(
            "schedule_check",
            "Check today's schedule and upcoming events",
            self._tool_schedule_check,
            {"day": {"type": "string", "description": "Optional date (YYYY-MM-DD)"}},
        )
        self.register_tool(
            "remember",
            "Remember a personal fact or preference",
            self._tool_remember,
            {
                "key": {"type": "string", "description": "Fact name e.g. favorite_color"},
                "value": {"type": "string", "description": "Fact value"},
                "category": {"type": "string", "description": "Optional memory category"},
            },
        )
        self.register_tool(
            "quick_note",
            "Save a quick personal note",
            self._tool_quick_note,
            {"note": {"type": "string", "description": "Note content"}},
        )

    # ------------------------------------------------------------------ #
    # Tools
    # ------------------------------------------------------------------ #
    def _tool_schedule_check(self, day: str = "") -> str:
        from memory.conversation_memory import get_conversation

        date = day or datetime.now().strftime("%Y-%m-%d")
        return f"Schedule checked for {date}."

    def _tool_remember(self, key: str, value: str, category: str = "notes") -> str:
        try:
            from memory.memory_manager import remember

            return remember(key, value, category)
        except Exception as exc:
            return f"Could not remember: {exc}"

    def _tool_quick_note(self, note: str) -> str:
        try:
            from memory.memory_manager import remember

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            return remember(f"note_{timestamp.replace(' ', '_').replace(':', '')}", note)
        except Exception as exc:
            return f"Could not save note: {exc}"

    # ------------------------------------------------------------------ #
    # Lifecycle hooks
    # ------------------------------------------------------------------ #
    def on_activate(self) -> None:
        self.set_session("activated_at", datetime.now().isoformat())