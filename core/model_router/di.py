"""Dependency Injection wiring for the Model Router subsystem.

Registers every Model Router component with the container and binds the
concrete :class:`ModelRouter` under the System Orchestrator's
``core.orchestrator.interfaces.ModelRouter`` interface so the orchestrator
can resolve it without knowing the implementation.

The wiring also connects the Multi-Provider AI Intelligence Layer:

* :class:`ProviderStatisticsManager` — persistent provider performance stats
* :class:`ProviderLearningSystem` — uses stats to adjust routing scores
* :class:`ProviderPreferenceManager` — user overrides for provider selection
* :class:`EnhancedScoringEngine` — free-first + learning-aware scoring
* :class:`AutomaticFallback` — retry-once-then-fallback resilience
* :class:`ProviderBenchmarkService` — periodic provider benchmarking
* Built-in provider adapters (Ollama, Gemini, Claude, OpenAI, OpenRouter,
  Kimi) registered when they are configured/available.
"""

from typing import Any

from core.configuration.config import config as global_config
from core.di.container import container as global_container
from core.event_bus import event_bus as global_event_bus
from core.orchestrator.interfaces import ModelRouter as ModelRouterInterface

from core.model_router.automatic_fallback import AutomaticFallback
from core.model_router.benchmark import ProviderBenchmarkService
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
    """Register the Model Router subsystem with a DI container.

    Args:
        container: The container to register into. Defaults to the global
            container.
        config: The configuration manager to use. Defaults to the global
            config instance.
        event_bus: The event bus to publish on. Defaults to the global
            event bus.

    Returns:
        The constructed :class:`ModelRouter` (singleton).
    """
    container = container or global_container
    config = config or global_config
    event_bus = event_bus or global_event_bus

    # ------------------------------------------------------------------ #
    # Core components
    #
    # Each registration is idempotent: re-invoking ``register_model_router``
    # must not clobber already-constructed singletons (the router, health
    # monitor and fallback all share the same ProviderRegistry instance).
    # ------------------------------------------------------------------ #
    if not container.has(ProviderRegistry):
        container.register_factory(
            ProviderRegistry,
            lambda c: ProviderRegistry(),
        )
    if not container.has(RoutingStrategy):
        container.register_factory(
            RoutingStrategy,
            lambda c: RoutingStrategy(
                weights=_read_weights(config),
            ),
        )
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

    # ------------------------------------------------------------------ #
    # Multi-Provider AI Intelligence Layer components
    # ------------------------------------------------------------------ #
    if not container.has(ProviderStatisticsManager):
        container.register_factory(
            ProviderStatisticsManager,
            lambda c: ProviderStatisticsManager(
                storage_path=_read_stats_path(config),
            ),
        )
    if not container.has(ProviderLearningSystem):
        container.register_factory(
            ProviderLearningSystem,
            lambda c: ProviderLearningSystem(
                stats_manager=c.resolve(ProviderStatisticsManager),
            ),
        )
    if not container.has(ProviderPreferenceManager):
        container.register_factory(
            ProviderPreferenceManager,
            lambda c: ProviderPreferenceManager(
                storage_path=_read_prefs_path(config),
            ),
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

    # Replace the plain fallback with the retry-aware automatic fallback.
    if not container.has(AutomaticFallback):
        container.register_factory(
            AutomaticFallback,
            lambda c: AutomaticFallback(
                registry=c.resolve(ProviderRegistry),
                routing_strategy=c.resolve(RoutingStrategy),
                max_retries=int(config.get("model_router.retries", 1)),
            ),
        )
        # Override the base FallbackStrategy binding so any consumer
        # resolving FallbackStrategy gets retry semantics.
        container.register_instance(
            FallbackStrategy,
            container.resolve(AutomaticFallback),
        )

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

    # ------------------------------------------------------------------ #
    # The router itself (singleton instance)
    # ------------------------------------------------------------------ #
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

        # Register built-in providers on first wiring.
        _register_builtin_providers(container, router)

    # Bind the concrete router under the orchestrator's interface so the
    # System Orchestrator can resolve it without import coupling.
    if not container.has(ModelRouterInterface):
        container.register_instance(ModelRouterInterface, router)

    return router


def _read_weights(config: Any) -> dict:
    """Read routing weights from config, falling back to defaults."""
    try:
        weights = config.get("model_router.weights", None)
        if isinstance(weights, dict):
            return {k: float(v) for k, v in weights.items()}
    except Exception:
        pass
    return {}


def _register_builtin_providers(container: Any, router: ModelRouter) -> None:
    """Register provider adapters that are configured or locally available.

    Cloud providers only register when an API key is present. Ollama
    registers automatically when a local Ollama instance is reachable.
    """
    from core.model_router.providers import (
        ClaudeProvider,
        DeepSeekProvider,
        GeminiProvider,
        KimiProvider,
        OllamaProvider,
        OpenAIProvider,
        OpenRouterProvider,
        QwenProvider,
    )

    providers = [
        OllamaProvider(),
        GeminiProvider(),
        ClaudeProvider(),
        OpenAIProvider(),
        OpenRouterProvider(),
        KimiProvider(),
        QwenProvider(),
        DeepSeekProvider(),
    ]

    for provider in providers:
        try:
            status = provider.get_status()
            if status.get("available") or status.get("configured"):
                router.register_provider(provider)
        except Exception:
            # A provider that fails to introspect is simply not registered.
            continue


def _read_stats_path(config: Any) -> Any:
    """Read the provider-stats storage path from config, if configured."""
    try:
        path = config.get("model_router.statistics_path", None)
        if path:
            from pathlib import Path
            return Path(path)
    except Exception:
        pass
    return None


def _resolve_capability_matcher(container: Any) -> Any:
    """Return the shared CapabilityMatcher singleton if present."""
    try:
        from core.model_router.capability_matcher import CapabilityMatcher

        if not container.has(CapabilityMatcher):
            container.register_instance(CapabilityMatcher, CapabilityMatcher())
        return container.resolve(CapabilityMatcher)
    except Exception:
        return None


def _read_prefs_path(config: Any) -> Any:
    """Read the provider-preferences storage path from config, if configured."""
    try:
        path = config.get("model_router.preferences_path", None)
        if path:
            from pathlib import Path
            return Path(path)
    except Exception:
        pass
    return None


# Auto-register on import only when the global container is empty.
# This keeps the module import-safe when applications provide their own
# container wiring.
if not global_container.has(ModelRouter):
    register_model_router()