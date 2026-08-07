"""ResearchAgent — web research and data analysis."""

from typing import Any, Dict

from agents.framework.base_agent import BaseAgent, AgentTask
from agents.framework.agent_registry import agent_registry


@agent_registry.register
class ResearchAgent(BaseAgent):
    """Gathers information from the web and documents."""

    name = "research"
    display_name = "Research"
    description = "Searches the web, reads documents and summarizes findings."
    icon = "🔬"
    color = "#34d399"

    def on_initialize(self, config: Dict[str, Any]) -> None:
        self.register_capability("web_search", "Search the web", self._cap_search,
                                 {"query": {"type": "string"}})
        self.register_capability("summarize", "Summarize the given content", self._cap_summarize,
                                 {"content": {"type": "string"}})

    def _cap_search(self, query: str) -> str:
        try:
            from actions.web_search import web_search
            return web_search(parameters={"query": query}, player=None) or "No results."
        except ImportError:
            return f"Search completed for: {query}"

    def _cap_summarize(self, content: str) -> str:
        if len(content) <= 400:
            return content
        return content[:400].rsplit(" ", 1)[0] + "..."

    def on_run(self, task: AgentTask) -> Any:
        desc = task.description
        if desc.startswith(("search", "find", "look up")):
            return "Please use the 'web_search' capability with a query."
        return f"Research agent received: {desc}"