"""Integration tests for the real ModelRouter/SystemOrchestrator boundary."""

import unittest

from core.model_router.base_provider import BaseModelProvider
from core.model_router.models import ModelCapabilities, ModelInfo, ProviderInfo, RouteRequest
from core.model_router.router import ModelRouter
from core.orchestrator.models import UserRequest
from core.orchestrator.orchestrator import SystemOrchestrator


class FakeProvider(BaseModelProvider):
    def __init__(self, name, priority, response="ok", failures=0):
        self._name = name
        self.priority = priority
        self.response = response
        self.failures = failures
        self.calls = 0

    @property
    def name(self):
        return self._name

    def available_models(self):
        return [ModelInfo(id=f"{self._name}-model", capabilities=ModelCapabilities(streaming=True))]

    def capabilities(self):
        return {"streaming": True, "tool_calling": True}

    def info(self):
        return ProviderInfo(
            name=self._name,
            models=self.available_models(),
            capabilities=ModelCapabilities(streaming=True, tool_calling=True),
            supports_streaming=True,
            supports_tool_calling=True,
            priority=self.priority,
        )

    def complete(self, request: RouteRequest):
        self.calls += 1
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError(f"{self._name} temporary failure")
        return self.response

    def complete_stream(self, request: RouteRequest):
        yield self.response

    def check_health(self):
        return True

    def get_status(self):
        return {"available": True}


class FakeWorkspaceSelector:
    def select(self, request):
        return "general"

    def available_workspaces(self):
        return ["general"]


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
    def load(self):
        return {}

    def save(self, update):
        return update

    def format_for_prompt(self, memory=None):
        return ""


class FakeUI:
    def notify(self, state_name, payload):
        pass


class FakeEvents:
    def __init__(self):
        self.events = []

    def emit(self, event, data=None, **kwargs):
        self.events.append((event, data, kwargs))


class ModelRouterOrchestratorIntegrationTests(unittest.TestCase):
    def make_orchestrator(self, router, events):
        return SystemOrchestrator(
            model_router=router,
            workspace_selector=FakeWorkspaceSelector(),
            workflow_selector=FakeWorkflowSelector(),
            agent_selector=FakeAgentSelector(),
            memory_store=FakeMemory(),
            ui_notifier=FakeUI(),
            event_bus_instance=events,
        )

    def test_real_router_executes_through_orchestrator(self):
        events = FakeEvents()
        router = ModelRouter(event_bus=events)
        provider = FakeProvider("primary", priority=1, response="hello from model")
        router.register_provider(provider)

        result = self.make_orchestrator(router, events).handle(
            UserRequest(source="integration-test", text="hello")
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, "hello from model")
        self.assertEqual(provider.calls, 1)
        event_names = [event[0] for event in events.events]
        self.assertIn("model_router.succeeded", event_names)
        self.assertIn("orchestrator.request_completed", event_names)

    def test_router_falls_back_after_provider_failure(self):
        events = FakeEvents()
        router = ModelRouter(event_bus=events)
        primary = FakeProvider("primary", priority=1, failures=2)
        backup = FakeProvider("backup", priority=2, response="backup response")
        router.register_provider(primary)
        router.register_provider(backup)
        router._retries = 0
        router.max_fallbacks = 1

        result = self.make_orchestrator(router, events).handle(
            UserRequest(source="integration-test", text="fallback")
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, "backup response")
        self.assertEqual(primary.calls, 1)
        self.assertEqual(backup.calls, 1)
        self.assertTrue([e for e in events.events if e[0] == "model_router.fallback"])

    def test_router_reports_no_route_cleanly(self):
        events = FakeEvents()
        router = ModelRouter(event_bus=events)
        result = self.make_orchestrator(router, events).handle(
            UserRequest(source="integration-test", text="hello")
        )

        self.assertFalse(result.success)
        self.assertIn("No provider", result.error)
        self.assertIn("model_router.failed", [event[0] for event in events.events])


if __name__ == "__main__":
    unittest.main()
