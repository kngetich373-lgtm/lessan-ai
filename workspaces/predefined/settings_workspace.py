"""Settings workspace for application configuration."""

from typing import Any, Dict, List

from workspaces.base_workspace import BaseWorkspace
from workspaces.workspace_registry import workspace_registry


@workspace_registry.register
class SettingsWorkspace(BaseWorkspace):
    """System settings, preferences, and configuration."""

    name = "settings"
    display_name = "Settings"
    description = "Manage system settings, preferences, and application configuration."
    icon = "🔧"
    color = "#67e8f9"
    order = 60

    def on_initialize(self, config: Dict[str, Any]) -> None:
        self.register_tool("get_setting", "Read a configuration value", self._tool_get_setting,
                           {"key": {"type": "string", "description": "Dot-notation config key"}})
        self.register_tool("set_setting", "Update a configuration value", self._tool_set_setting,
                           {
                               "key": {"type": "string", "description": "Dot-notation config key"},
                               "value": {"description": "New value"},
                           })
        self.register_tool("list_settings", "List configuration sections", self._tool_list_settings)

    def _tool_get_setting(self, key: str) -> str:
        from core.configuration import config

        value = config.get(key)
        return f"{key} = {value}"

    def _tool_set_setting(self, key: str, value: Any) -> str:
        from core.configuration import config

        # Attempt minimal type coercion
        if isinstance(value, str):
            if value.lower() in ("true", "false"):
                value = value.lower() == "true"
            else:
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        pass
        config.set(key, value)
        return f"Set {key} = {value}"

    def _tool_list_settings(self) -> str:
        from core.configuration import config

        sections = config.all()
        lines = ["Configuration:"]
        for section, values in sorted(sections.items()):
            lines.append(f"  {section}: {list(values.keys()) if isinstance(values, dict) else values}")
        return "\n".join(lines)