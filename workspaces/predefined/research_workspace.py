"""Research workspace for information gathering and analysis."""

from datetime import datetime
from typing import Any, Dict

from workspaces.base_workspace import BaseWorkspace
from workspaces.workspace_registry import workspace_registry


@workspace_registry.register
class ResearchWorkspace(BaseWorkspace):
    """Web research, data gathering, and analysis workspace."""

    name = "research"
    display_name = "Research"
    description = "Search the web, gather information, analyze documents and data."
    icon = "🔬"
    color = "#34d399"
    order = 40

    def on_initialize(self, config: Dict[str, Any]) -> None:
        self.register_tool(
            "web_search",
            "Search the web for information",
            self._tool_web_search,
            {"query": {"type": "string", "description": "Search query"}},
        )
        self.register_tool(
            "analyze_document",
            "Analyze and extract information from a document",
            self._tool_analyze_document,
            {"path": {"type": "string", "description": "Path to the document"}},
        )
        self.register_tool(
            "fetch_url",
            "Fetch and summarize content from a URL",
            self._tool_fetch_url,
            {"url": {"type": "string", "description": "URL to fetch"}},
        )

    def _tool_web_search(self, query: str) -> str:
        try:
            from actions.web_search import web_search

            return web_search(parameters={"query": query}, player=None) or "No results."
        except ImportError:
            return self._fallback_search(query)

    def _fallback_search(self, query: str) -> str:
        import requests
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(
                "https://duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            results = soup.select(".result__title")[:5]
            if not results:
                return f"No results for '{query}'."
            lines = [f"Search results for '{query}':"]
            for r in results:
                lines.append(f"  - {r.get_text(strip=True)}")
            return "\n".join(lines)
        except Exception as exc:
            return f"Search failed: {exc}"

    def _tool_analyze_document(self, path: str) -> str:
        from pathlib import Path

        p = Path(path)
        if not p.exists():
            return f"Document '{path}' not found."

        if p.suffix.lower() == ".pdf":
            try:
                import pdfplumber

                with pdfplumber.open(str(p)) as pdf:
                    text = "\n".join(page.extract_text() or "" for page in pdf.pages[:10])
                return text[:2000] or "No extractable text found in PDF."
            except Exception:
                try:
                    import pypdf

                    reader = pypdf.PdfReader(str(p))
                    text = "\n".join(page.extract_text() or "" for page in reader.pages[:10])
                    return text[:2000] or "No extractable text found in PDF."
                except Exception as exc:
                    return f"Could not read PDF: {exc}"

        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            return text[:2000]
        except Exception as exc:
            return f"Could not read document: {exc}"

    def _tool_fetch_url(self, url: str) -> str:
        import requests
        from bs4 import BeautifulSoup

        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = " ".join(soup.get_text(separator=" ").split())
            return text[:2000] or "No readable content found."
        except Exception as exc:
            return f"Could not fetch URL: {exc}"