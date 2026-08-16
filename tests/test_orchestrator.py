"""Unit tests for the Lessan AI system orchestrator.

These tests use small in-memory fakes so orchestration behavior can be
validated without network access, model credentials, or a GUI session.
"""

import unittest

from core.orchestrator.models import UserRequest
from core.orchestrator.orchestrator import SystemOrchestrator


class FakeRouter:
    def __init__(self, available=True):
        self.available = available
        self.calls = []

    def is_available(self):
        return self.available

    def complete(self, prompt, *, system=None, **kwargs):
        self.calls.append((prompt, system))
        return f"response:{prompt}"


class FakeWorkspaceSelector:
    def select(self, request):
        return "general"

    def available_workspaces(self):
        return ["general", "engineering"]


class FakeWorkflowSelector:
    def select(self, request, workspace):
        return None

    def available_workflows(self):
        return []


class FakeAgentSelector:
    def select(self, request, workspace):
        return None

    def available_agents(self):
        return []


class FakeMemory:
    def __init__(self):
        self.saved = []

    def load(self):
        return {"preference": "concise"}

    def save(self, update):
        self.saved.append(update)
        return update

    def format_for_prompt(self, memory=None):
        memory = memory or {}
        return "\n".join(f"{k}: {v}" for k, v in memory.items())


class FakeNotifier:
    def __init__(self):
        self.events = []

    def notify(self, state_name, payload):
        self.events.append((state_name, payload))


class FakeEventBus:
    def __init__(self):
        self.events = []

    def publish(self, event, payload):
        self.events.append((event, payload))


class SystemOrchestratorTests(unittest.TestCase):
    def make_orchestrator(self, *, available=True):
        self.router = FakeRouter(available=available)
        self.memory = FakeMemory()
        self.notifier = FakeNotifier()
        self.events = FakeEventBus()
        return SystemOrchestrator(
            model_router=self.router,
            workspace_selector=FakeWorkspaceSelector(),
            workflow_selector=FakeWorkflowSelector(),
            agent_selector=FakeAgentSelector(),
            memory_store=self.memory,
            ui_notifier=self.notifier,
            event_bus_instance=self.events,
        )

    def test_direct_request_is_completed(self):
        orchestrator = self.make_orchestrator()
        result = orchestrator.handle(UserRequest(source="test", text="hello"))

        self.assertTrue(result.success)
        self.assertEqual(result.workspace, "general")
        self.assertEqual(result.output, "response:hello")
        self.assertEqual(self.router.calls[0][0], "hello")
        self.assertTrue(self.memory.saved)
        self.assertIn("orchestrator.request_completed", [e[0] for e in self.events.events])

    def test_unavailable_router_returns_failure(self):
        orchestrator = self.make_orchestrator(available=False)
        result = orchestrator.handle(UserRequest(source="test", text="hello"))

        self.assertFalse(result.success)
        self.assertIn("No AI model route is available", result.error)
        self.assertIn("orchestrator.request_failed", [e[0] for e in self.events.events])
        self.assertEqual(self.notifier.events[-1][0], "ERROR")

    def test_invalid_workspace_hint_is_rejected(self):
        orchestrator = self.make_orchestrator()
        result = orchestrator.handle(
            UserRequest(source="test", text="hello", workspace_hint="missing")
        )

        self.assertFalse(result.success)
        self.assertIn("is not registered", result.error)
        self.assertEqual(self.router.calls, [])


if __name__ == "__main__":
    unittest.main()
