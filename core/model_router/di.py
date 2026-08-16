"""Dependency-injection wiring for the Model Router subsystem."""

from typing import Any

from core.configuration.config import config as global_config
from core.di.container import container as global_container
from core.event_bus import event_bus as global_event_bus
from core.orchestrator.interfaces import ModelRouter as ModelRouterInterface

from core.model_router.automatic_fallback import AutomaticFallback
from core.model_router.benchmark import ProviderBenchmarkService
from core.model_router.credentials import CredentialStore
from core.model_router.fallback import FallbackStrategy
from core.model_router.health import ProviderHealthMonitor
from core.model_router.learning import ProviderLearningSystem
from core.model_router.preferences import ProviderPreferenceManager
from core.model_router.registry import ProviderRegistry
from core.model_router.router import ModelRouter
from core.model_router.scoring_engine import EnhancedScoringEngine
from core.model_router.statistics import ProviderStatisticsManager
from core.model_router.strategy import RoutingStrategy


def register_model_router(container: Any = None, config: Any = None, event_bus: Any = None) -> ModelRouter:
    """Register the Model Router subsystem and its provider adapters."""
    container = container or global_container
    config = config or global_config
    event_bus = event_bus or global_event_bus

    if not container.has(CredentialStore):
        container.register_instance(CredentialStore, CredentialStore(config))

    if not container.has(ProviderRegistry):
        container.register_factory(ProviderRegistry, lambda c: ProviderRegistry())
    if not container.has(RoutingStrategy):
        container.register_factory(RoutingStrategy, lambda c: RoutingStrategy(weights=_read_weights(config)))
    if not container.has(ProviderHealthMonitor):
        container.register_factory(
            ProviderHealthMonitor,
            lambda c: ProviderHealthMonitor(
                registry=c.resolve(ProviderRegistry),
                check_interval=float(config.get("model_router.health.check_interval", 60.0)),
                timeout=float(config.get("model_router.health.timeout", 5.0)),
            ),
        )
    if not container.has(FallbackStrategy):
        container.register_factory(
            FallbackStrategy,
            lambda c: FallbackStrategy(
                registry=c.resolve(ProviderRegistry),
                routing_strategy=c.resolve(RoutingStrategy),
            ),
        )

    if not container.has(ProviderStatisticsManager):
        container.register_factory(
            ProviderStatisticsManager,
            lambda c: ProviderStatisticsManager(storage_path=_read_stats_path(config)),
        )
    if not container.has(ProviderLearningSystem):
        container.register_factory(
            ProviderLearningSystem,
            lambda c: ProviderLearningSystem(stats_manager=c.resolve(ProviderStatisticsManager)),
        )
    if not container.has(ProviderPreferenceManager):
        container.register_factory(
            ProviderPreferenceManager,
            lambda c: ProviderPreferenceManager(storage_path=_read_prefs_path(config)),
        )
    if not container.has(EnhancedScoringEngine):
        container.register_factory(
            EnhancedScoringEngine,
            lambda c: EnhancedScoringEngine(
                base_strategy=c.resolve(RoutingStrategy),
                learning_system=c.resolve(ProviderLearningSystem),
                preference_manager=c.resolve(ProviderPreferenceManager),
            ),
        )
    if not container.has(AutomaticFallback):
        container.register_factory(
            AutomaticFallback,
            lambda c: AutomaticFallback(
                registry=c.resolve(ProviderRegistry),
                routing_strategy=c.resolve(RoutingStrategy),
                max_retries=int(config.get("model_router.retries", 1)),
            ),
        )
        container.register_instance(FallbackStrategy, container.resolve(AutomaticFallback))

    if not container.has(ProviderBenchmarkService):
        container.register_factory(
            ProviderBenchmarkService,
            lambda c: ProviderBenchmarkService(
                registry=c.resolve(ProviderRegistry),
                stats_manager=c.resolve(ProviderStatisticsManager),
                interval_seconds=int(config.get("model_router.benchmark.interval", 3600)),
                run_once=bool(config.get("model_router.benchmark.run_once", True)),
            ),
        )

    if container.has(ModelRouter):
        router = container.resolve(ModelRouter)
    else:
        router = ModelRouter(
            registry=container.resolve(ProviderRegistry),
            strategy=container.resolve(EnhancedScoringEngine),
            fallback=container.resolve(FallbackStrategy),
            health_monitor=container.resolve(ProviderHealthMonitor),
            config=config,
            event_bus=event_bus,
            stats_manager=container.resolve(ProviderStatisticsManager),
            capability_matcher=_resolve_capability_matcher(container),
        )
        container.register_instance(ModelRouter, router)
        _register_builtin_providers(router, container.resolve(CredentialStore))

    if not container.has(ModelRouterInterface):
        container.register_instance(ModelRouterInterface, router)
    return router


def _read_weights(config: Any) -> dict:
    try:
        weights = config.get("model_router.weights", None)
        if isinstance(weights, dict):
            return {k: float(v) for k, v in weights.items()}
    except Exception:
        pass
    return {}


def _register_builtin_providers(router: ModelRouter, credentials: CredentialStore) -> None:
    """Create adapters with resolved credentials; isolate each provider failure."""
    from core.model_router.providers import (
        ClaudeProvider, DeepSeekProvider, GeminiProvider, KimiProvider,
        OllamaProvider, OpenAIProvider, OpenRouterProvider, QwenProvider,
    )

    factories = [
        ("ollama", lambda: OllamaProvider()),
        ("gemini", lambda: GeminiProvider(api_key=credentials.get("gemini"))),
        ("claude", lambda: ClaudeProvider(api_key=credentials.get("claude"))),
        ("openai", lambda: OpenAIProvider(api_key=credentials.get("openai"))),
        ("openrouter", lambda: OpenRouterProvider(api_key=credentials.get("openrouter"))),
        ("kimi", lambda: KimiProvider(api_key=credentials.get("kimi"))),
        ("qwen", lambda: QwenProvider(api_key=credentials.get("qwen"))),
        ("deepseek", lambda: DeepSeekProvider(api_key=credentials.get("deepseek"))),
    ]

    for name, factory in factories:
        try:
            provider = factory()
            status = provider.get_status()
            if name == "ollama" or status.get("configured") or status.get("available"):
                router.register_provider(provider)
        except Exception:
            continue


def _read_stats_path(config: Any) -> Any:
    try:
        path = config.get("model_router.statistics_path", None)
        if path:
            from pathlib import Path
            return Path(path)
    except Exception:
        pass
    return None


def _resolve_capability_matcher(container: Any) -> Any:
    try:
        from core.model_router.capability_matcher import CapabilityMatcher
        if not container.has(CapabilityMatcher):
            container.register_instance(CapabilityMatcher, CapabilityMatcher())
        return container.resolve(CapabilityMatcher)
    except Exception:
        return None


def _read_prefs_path(config: Any) -> Any:
    try:
        path = config.get("model_router.preferences_path", None)
        if path:
            from pathlib import Path
            return Path(path)
    except Exception:
        pass
    return None


if not global_container.has(ModelRouter):
    register_model_router()
