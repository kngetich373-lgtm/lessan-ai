"""Validation tests for the Multi-Provider AI Intelligence Layer.

Covers the six validation scenarios:
1. Backward compatibility of the existing ModelRouter public API.
2. Free-first routing (local free → cloud free → paid).
3. Capability-based routing (task → capability matching).
4. Automatic fallback with retry-once semantics.
5. Learning: statistics adjust routing scores over time.
6. User preferences: provider overrides/disablement.

Run with:  python3 -m unittest tests.test_model_router_intelligence -v
"""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterator, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.model_router.automatic_fallback import AutomaticFallback
from core.model_router.base_provider import BaseModelProvider
from core.model_router.capabilities import (
    CAPABILITY_FRONTEND_DEV,
    CAPABILITY_PYTHON,
    CAPABILITY_REACT,
)
from core.model_router.capability_matcher import CapabilityMatcher
from core.model_router.learning import ProviderLearningSystem
from core.model_router.models import (
    CostMetadata,
    ModelCapabilities,
    ModelInfo,
    ProviderInfo,
    RouteRequest,
)
from core.model_router.preferences import ProviderPreferenceManager
from core.model_router.registry import ProviderRegistry
from core.model_router.router import ModelRouter
from core.model_router.scoring_engine import EnhancedScoringEngine
from core.model_router.statistics import ProviderStatisticsManager
from core.model_router.strategy import RoutingStrategy


# ------------------------------------------------------------------ #
# Mock provider implementation
# ------------------------------------------------------------------ #
class MockProvider(BaseModelProvider):
    """In-memory provider for tests; no network access."""

    def __init__(
        self,
        name: str,
        *,
        capabilities: Optional[List[str]] = None,
        is_local: bool = False,
        priority: int = 100,
        is_free: bool = False,
        fail: bool = False,
        fail_then_succeed: bool = False,
        response: str = "response",
    ) -> None:
        self._name = name
        self._is_local = is_local
        self._priority = priority
        self._is_free = is_free
        self._fail = fail
        self._fail_then_succeed = fail_then_succeed
        self._response = response
        self._calls = 0
        self._extra_caps = {c: True for c in (capabilities or [])}
        self._capabilities = ModelCapabilities(
            streaming=True,
            vision=False,
            tool_calling=True,
            extra=self._extra_caps,
        )

    @property
    def name(self) -> str:
        return self._name

    def available_models(self) -> List[ModelInfo]:
        return [ModelInfo(
            id=f"{self._name}-model",
            capabilities=self._capabilities,
            context_length=32768,
            cost=CostMetadata(is_free=self._is_free),
        )]

    def capabilities(self) -> Dict[str, Any]:
        return {
            "streaming": True,
            "vision": False,
            "tool_calling": True,
            "local": self._is_local,
        }

    def complete(self, request: RouteRequest) -> str:
        self._calls += 1
        if self._fail:
            raise RuntimeError(f"{self._name} simulated failure")
        if self._fail_then_succeed and self._calls == 1:
            raise RuntimeError(f"{self._name} transient failure")
        return f"{self._response} from {self._name}"

    def complete_stream(self, request: RouteRequest) -> Iterator[str]:
        yield "chunk "
        yield "done"

    def check_health(self) -> bool:
        return not self._fail

    def get_status(self) -> Dict[str, Any]:
        return {"available": not self._fail, "configured": True}

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            name=self._name,
            models=[
                ModelInfo(
                    id=f"{self._name}-model",
                    capabilities=self._capabilities,
                    context_length=32768,
                    cost=CostMetadata(is_free=self._is_free),
                )
            ],
            capabilities=self._capabilities,
            context_length=32768,
            supports_streaming=True,
            priority=self._priority,
            is_local=self._is_local,
            cost=CostMetadata(is_free=self._is_free),
        )

    @property
    def calls(self) -> int:
        return self._calls



# ------------------------------------------------------------------ #
# Test suite
# ------------------------------------------------------------------ #
class TestBackwardCompatibility(unittest.TestCase):
    """Scenario 1: existing public API still works unchanged."""

    def test_router_constructs_with_legacy_signature(self) -> None:
        router = ModelRouter()
        self.assertIsNotNone(router)
        self.assertIsInstance(router._strategy, RoutingStrategy)
        self.assertEqual(router.max_fallbacks, 3)

    def test_register_and_complete(self) -> None:
        router = ModelRouter()
        provider = MockProvider("mock")
        router.register_provider(provider)
        self.assertEqual(router.providers(), ["mock"])
        text = router.complete("Hello world")
        self.assertIn("from mock", text)

    def test_route_result_fields(self) -> None:
        router = ModelRouter()
        router.register_provider(MockProvider("mock"))
        result = router.route(RouteRequest(prompt="hi"))
        self.assertTrue(result.success)
        self.assertEqual(result.provider, "mock")
        self.assertEqual(result.fallback_chain, ["mock"])


class TestFreeFirstRouting(unittest.TestCase):
    """Scenario 2: local free beats cloud free beats paid."""

    def _router(self) -> ModelRouter:
        router = ModelRouter()
        router.register_provider(MockProvider(
            "local_free", is_local=True, priority=10, is_free=True,
            capabilities=[CAPABILITY_PYTHON],
        ))
        router.register_provider(MockProvider(
            "cloud_free", priority=30, is_free=True,
            capabilities=[CAPABILITY_PYTHON],
        ))
        router.register_provider(MockProvider(
            "paid", priority=60, is_free=False,
            capabilities=[CAPABILITY_PYTHON],
        ))
        return router

    def test_free_first_ranking_order(self) -> None:
        router = self._router()
        plan = router.plan(RouteRequest(prompt="python task"))
        names = [d.provider for d in plan]
        self.assertEqual(names[0], "local_free")
        self.assertEqual(names[1], "cloud_free")
        self.assertEqual(names[2], "paid")

    def test_free_first_priority_tier(self) -> None:
        from core.model_router.free_first import (
            PRIORITY_CLOUD_FREE,
            PRIORITY_LOCAL_FREE,
            PRIORITY_PAID,
            apply_free_first_priority,
        )
        local = MockProvider("local", is_local=True).info()
        cloud_free = MockProvider("cf", is_free=True).info()
        paid = MockProvider("paid").info()
        self.assertEqual(apply_free_first_priority(local), PRIORITY_LOCAL_FREE)
        self.assertEqual(apply_free_first_priority(cloud_free), PRIORITY_CLOUD_FREE)
        self.assertEqual(apply_free_first_priority(paid), PRIORITY_PAID)



class TestCapabilityRouting(unittest.TestCase):
    """Scenario 3: task-based capability matching selects the right provider."""

    def test_capability_matcher_infers(self) -> None:
        matcher = CapabilityMatcher()
        caps = matcher.infer_capabilities("Build a React dashboard")
        self.assertIn(CAPABILITY_REACT, caps)
        caps2 = matcher.infer_capabilities("Write a Python script")
        self.assertIn(CAPABILITY_PYTHON, caps2)

    def test_task_routes_to_matching_provider(self) -> None:
        router = ModelRouter(capability_matcher=CapabilityMatcher())
        router.register_provider(MockProvider(
            "react_provider", capabilities=[CAPABILITY_REACT, CAPABILITY_FRONTEND_DEV],
        ))
        router.register_provider(MockProvider(
            "python_provider", capabilities=[CAPABILITY_PYTHON],
        ))
        plan = router.plan(RouteRequest(prompt="Build a React dashboard"))
        self.assertEqual(plan[0].provider, "react_provider")

    def test_match_score(self) -> None:
        from core.model_router.capability_matcher import match_score
        self.assertEqual(match_score(["python"], ["python", "react"]), 1.0)
        self.assertEqual(match_score(["python", "react"], ["python"]), 0.5)


class TestFallback(unittest.TestCase):
    """Scenario 4: automatic fallback with retry-once semantics."""

    def test_fallback_to_next_provider(self) -> None:
        router = ModelRouter()
        router.register_provider(MockProvider("failing", fail=True))
        router.register_provider(MockProvider("working"))
        text = router.complete("hello")
        self.assertIn("from working", text)

    def test_retry_once_then_succeed(self) -> None:
        registry = ProviderRegistry()
        strategy = RoutingStrategy()
        fallback = AutomaticFallback(
            registry=registry, routing_strategy=strategy, max_retries=1,
        )
        provider = MockProvider("transient", fail_then_succeed=True)
        router = ModelRouter(registry=registry, strategy=strategy, fallback=fallback)
        router.register_provider(provider)
        text = router.complete("hello")
        self.assertIn("from transient", text)
        self.assertEqual(provider.calls, 2)  # first fails, second succeeds

    def test_all_fail_reports_error(self) -> None:
        router = ModelRouter()
        router.register_provider(MockProvider("a", fail=True))
        router.register_provider(MockProvider("b", fail=True))
        result = router.route(RouteRequest(prompt="hello"))
        self.assertFalse(result.success)
        self.assertTrue(result.error)



class TestLearning(unittest.TestCase):
    """Scenario 5: statistics drive learning-based scoring adjustments."""

    def test_stats_record_and_query(self) -> None:
        with TemporaryDirectory() as tmp:
            stats = ProviderStatisticsManager(storage_path=Path(tmp) / "stats.json")
            stats.record_request("p1", success=True, latency_ms=100, category="python")
            stats.record_request("p1", success=True, latency_ms=200, category="python")
            stats.record_request("p1", success=False, latency_ms=150, category="python")
            self.assertEqual(stats.get_success_rate("p1", "python"), 2 / 3)
            self.assertEqual(stats.get_stats("p1").total_requests, 3)

    def test_learning_adjusts_scores(self) -> None:
        with TemporaryDirectory() as tmp:
            stats = ProviderStatisticsManager(storage_path=Path(tmp) / "stats.json")
            learning = ProviderLearningSystem(stats)

            for _ in range(10):
                stats.record_request("good", True, 100, "python")
            for _ in range(10):
                stats.record_request("bad", False, 300, "python")

            request = RouteRequest(prompt="task", required_capabilities=["python"])
            good_score = learning.calculate_historical_score("good", request)
            bad_score = learning.calculate_historical_score("bad", request)
            self.assertGreater(good_score, bad_score)

    def test_insufficient_data_is_neutral(self) -> None:
        with TemporaryDirectory() as tmp:
            stats = ProviderStatisticsManager(storage_path=Path(tmp) / "stats.json")
            learning = ProviderLearningSystem(stats)
            request = RouteRequest(prompt="task")
            self.assertEqual(learning.calculate_historical_score("unknown", request), 0.5)

class TestPreferences(unittest.TestCase):
    """Scenario 6: user preferences override provider selection."""

    def _enhanced(self, router: ModelRouter, prefs: ProviderPreferenceManager) -> ModelRouter:
        router._strategy = EnhancedScoringEngine(
            base_strategy=RoutingStrategy(),
            preference_manager=prefs,
        )
        return router

    def test_disable_provider_excludes_it(self) -> None:
        with TemporaryDirectory() as tmp:
            prefs = ProviderPreferenceManager(storage_path=Path(tmp) / "prefs.json")
            prefs.disable_provider("paid")
            router = ModelRouter()
            router.register_provider(MockProvider("free", is_free=True))
            router.register_provider(MockProvider("paid", is_free=False))
            self._enhanced(router, prefs)
            plan = router.plan(RouteRequest(prompt="task"))
            names = [d.provider for d in plan]
            self.assertNotIn("paid", names)
            self.assertIn("free", names)

    def test_forced_provider(self) -> None:
        with TemporaryDirectory() as tmp:
            prefs = ProviderPreferenceManager(storage_path=Path(tmp) / "prefs.json")
            prefs.set_forced_provider("paid")
            router = ModelRouter()
            router.register_provider(MockProvider("free", is_free=True))
            router.register_provider(MockProvider("paid", is_free=False))
            self._enhanced(router, prefs)
            plan = router.plan(RouteRequest(prompt="task"))
            self.assertEqual(plan[0].provider, "paid")

    def test_local_only_mode(self) -> None:
        with TemporaryDirectory() as tmp:
            prefs = ProviderPreferenceManager(storage_path=Path(tmp) / "prefs.json")
            prefs.set_local_only(True)
            router = ModelRouter()
            router.register_provider(MockProvider("local", is_local=True))
            router.register_provider(MockProvider("cloud", is_local=False))
            self._enhanced(router, prefs)
            plan = router.plan(RouteRequest(prompt="task"))
            names = [d.provider for d in plan]
            self.assertIn("local", names)
            self.assertNotIn("cloud", names)


class TestOllamaDiscovery(unittest.TestCase):
    """Scenario 7: Ollama discovery is graceful when the server is absent."""

    def test_discovery_handles_unavailable_server(self) -> None:
        from core.model_router.discovery.ollama_discovery import OllamaDiscovery

        discovery = OllamaDiscovery(base_url="http://127.0.0.1:1")
        self.assertFalse(discovery.is_available())
        self.assertEqual(discovery.discover_models(), [])

    def test_ollama_provider_status_when_offline(self) -> None:
        from core.model_router.providers import OllamaProvider

        provider = OllamaProvider(base_url="http://127.0.0.1:1")
        self.assertFalse(provider.get_status()["available"])


class TestBenchmarkService(unittest.TestCase):
    """Benchmark service builds results without crashing."""

    def test_benchmark_runs_with_mock_providers(self) -> None:
        from core.model_router.benchmark import ProviderBenchmarkService

        registry = ProviderRegistry()
        registry.register(MockProvider("mock"))
        with TemporaryDirectory() as tmp:
            stats = ProviderStatisticsManager(storage_path=Path(tmp) / "stats.json")
            benchmark = ProviderBenchmarkService(registry=registry, stats_manager=stats)
            results = benchmark.run_benchmarks(categories=["python", "general_chat"])
            self.assertIn("mock", results)
            self.assertIn("python", results["mock"])
            self.assertTrue(results["mock"]["python"]["success"])


if __name__ == "__main__":
    unittest.main()

