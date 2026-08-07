"""Tests for the lessan_ai_agents multi-agent build integration.

Covers:
- llm_backend parsing helpers (strip_fences / parse_json_response)
- RoleAgent executor wiring through the framework (AgentManager,
  AgentRegistry, TaskQueue) and the preserved no-executor stub
- end-to-end build_project() writing REAL files with a fake executor
  (no network, no API keys) and the expected agent dispatch order
- graceful handling of an invalid file plan
- backward-compatible dev_agent import from actions
"""

import json
import tempfile
import unittest
from pathlib import Path

from lessan_ai_agents.agents import build_default_roster
from lessan_ai_agents.core.agent_manager import AgentManager
from lessan_ai_agents.core.agent_registry import AgentRegistry
from lessan_ai_agents.core.task_queue import InMemoryTaskQueue, Task
from lessan_ai_agents.execution.llm_backend import parse_json_response, strip_fences
from lessan_ai_agents.orchestrator import build_project, _is_frontend_file

PLAN = {
    "project_name": "demo_app",
    "entry_point": "main.py",
    "run_command": "python main.py",
    "dependencies": [],
    "files": [
        {"path": "utils/helpers.py", "description": "greeting helper", "imports": []},
        {"path": "main.py", "description": "entry point", "imports": ["utils.helpers"]},
    ],
}


class FakeExecutor:
    """Deterministic stand-in for the LLM backend. Records every prompt
    and answers based on which kind of task the prompt is for."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        low = prompt.lower()
        if "return only valid json" in low:
            return json.dumps(PLAN)
        if "complete source code for" in low:
            if "complete source code for utils/helpers.py" in prompt:
                return "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n"
            return (
                "from utils.helpers import greet\n\n"
                "if __name__ == '__main__':\n"
                "    print(greet('world'))\n"
            )
        if "fixed code for" in low:
            return "print('fixed')\n"
        if "readme markdown content" in low:
            return "# demo_app\n\nA small CLI app that greets the user.\n"
        return f"Advisory: {low[:60]}"


class TestLlmBackend(unittest.TestCase):
    def test_strip_fences(self) -> None:
        self.assertEqual(strip_fences("```python\nx = 1\n```"), "x = 1")
        self.assertEqual(strip_fences('```json\n{"a": 1}\n```'), '{"a": 1}')
        self.assertEqual(strip_fences("plain text"), "plain text")
        self.assertEqual(strip_fences(""), "")
        self.assertEqual(strip_fences("  ```\ncode\n```  "), "code")

    def test_parse_json_response_tolerates_fences_and_prose(self) -> None:
        text = (
            "Sure! Here you go:\n```json\n"
            '{"project_name": "x", "files": []}\n```\nHope this helps.'
        )
        data = parse_json_response(text)
        self.assertEqual(data["project_name"], "x")
        self.assertEqual(data["files"], [])


class TestFrameworkWiring(unittest.TestCase):
    def test_executor_routed_through_manager(self) -> None:
        fake = FakeExecutor()
        roster = build_default_roster()
        agent = next(a for a in roster if a.name == "CEOAgent")
        agent.executor = fake
        registry = AgentRegistry()
        registry.register(agent)
        manager = AgentManager(registry, InMemoryTaskQueue())
        manager.submit(
            Task(
                title="delegate objective",
                target_agent="CEOAgent",
                payload={"objective": "build a greeting app", "constraints": "python"},
            )
        )
        result = manager.dispatch_next()
        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertEqual(
            result.output["note"], "Executed via injected LLM executor."
        )
        self.assertTrue(str(result.output["output"]).startswith("Advisory"))
        self.assertEqual(len(fake.calls), 1)

    def test_without_executor_keeps_architecture_stub(self) -> None:
        roster = build_default_roster()
        agent = next(a for a in roster if a.name == "ProductManagerAgent")
        registry = AgentRegistry()
        registry.register(agent)
        manager = AgentManager(registry, InMemoryTaskQueue())
        manager.submit(
            Task(
                title="scope feature",
                target_agent="ProductManagerAgent",
                payload={"feature_request": "x", "user_context": "y"},
            )
        )
        result = manager.dispatch_next()
        self.assertTrue(result.success)
        self.assertEqual(
            result.output["note"],
            "Architecture stub: no software generation performed.",
        )
        self.assertNotIn("output", result.output)


class TestBuildProject(unittest.TestCase):
    def test_build_project_writes_real_files_and_readme(self) -> None:
        fake = FakeExecutor()
        with tempfile.TemporaryDirectory() as tmp:
            out = build_project(
                description="A small CLI app that greets the user",
                language="python",
                project_name="demo_app",
                timeout=15,
                executor=fake,
                projects_dir=Path(tmp),
                open_editor=False,
            )
            project_dir = Path(tmp) / "demo_app"
            self.assertTrue((project_dir / "main.py").exists())
            self.assertTrue((project_dir / "utils" / "helpers.py").exists())
            self.assertTrue((project_dir / "README.md").exists())
            main_src = (project_dir / "main.py").read_text(encoding="utf-8")
            self.assertIn("greet", main_src)
            self.assertIn("working", out)

            # Expected dispatch order:
            # CEO -> PM -> Architect(plan) -> helpers -> main -> DevOps -> Doc
            prompts = fake.calls
            self.assertIn("You are the CEO Agent", prompts[0])
            self.assertIn("You are the Product Manager Agent", prompts[1])
            plan_idx = next(
                i for i, p in enumerate(prompts) if "return only valid json" in p.lower()
            )
            helpers_idx = next(
                i for i, p in enumerate(prompts) if "utils/helpers.py" in p
            )
            main_idx = next(
                i
                for i, p in enumerate(prompts)
                if "complete source code for main.py" in p
            )
            readme_idx = next(
                i
                for i, p in enumerate(prompts)
                if "readme markdown content" in p.lower()
            )
            self.assertLess(plan_idx, helpers_idx)
            self.assertLess(helpers_idx, main_idx)
            self.assertLess(main_idx, readme_idx)

    def test_build_project_handles_invalid_plan(self) -> None:
        class BadExecutor:
            def __call__(self, prompt: str) -> str:  # noqa: ARG002
                return "I am not JSON at all."

        with tempfile.TemporaryDirectory() as tmp:
            out = build_project(
                description="something",
                executor=BadExecutor(),
                projects_dir=Path(tmp),
                open_editor=False,
            )
            self.assertIn("Planning failed", out)

    def test_empty_description_returns_early(self) -> None:
        out = build_project("   ")
        self.assertIn("describe the project", out)


class TestDevAgentBackwardCompat(unittest.TestCase):
    def test_dev_agent_still_importable(self) -> None:
        from actions.dev_agent import dev_agent

        self.assertTrue(callable(dev_agent))

    def test_dev_agent_delegates_to_orchestrator(self) -> None:
        from unittest import mock

        from actions.dev_agent import dev_agent

        with mock.patch(
            "lessan_ai_agents.orchestrator.build_project",
            return_value="orchestrator result",
        ) as build_project_mock:
            out = dev_agent(
                {
                    "description": "build a tiny thing",
                    "language": "python",
                    "project_name": "tiny",
                    "timeout": 10,
                }
            )
        self.assertEqual(out, "orchestrator result")
        self.assertEqual(build_project_mock.call_count, 1)
        _, kwargs = build_project_mock.call_args
        self.assertEqual(kwargs["description"], "build a tiny thing")
        self.assertEqual(kwargs["language"], "python")
        self.assertEqual(kwargs["project_name"], "tiny")
        self.assertEqual(kwargs["timeout"], 10)

    def test_dev_agent_falls_back_to_legacy_builder(self) -> None:
        from unittest import mock

        from actions.dev_agent import dev_agent

        with mock.patch(
            "lessan_ai_agents.orchestrator.build_project",
            side_effect=RuntimeError("orchestrator boom"),
        ), mock.patch(
            "actions.dev_agent._build_project", return_value="legacy result"
        ) as legacy_mock:
            out = dev_agent({"description": "build a tiny thing"})
        self.assertEqual(out, "legacy result")
        legacy_mock.assert_called_once()


class TestHelpers(unittest.TestCase):
    def test_is_frontend_file(self) -> None:
        self.assertTrue(_is_frontend_file("index.html", "python"))
        self.assertTrue(_is_frontend_file("app.js", "javascript"))
        self.assertFalse(_is_frontend_file("main.py", "python"))
        self.assertFalse(_is_frontend_file("server.js", "python"))


if __name__ == "__main__":
    unittest.main()
