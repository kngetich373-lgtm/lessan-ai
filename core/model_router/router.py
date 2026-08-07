"""ModelRouter — provider-agnostic AI model routing for Lessan AI.

This is the public face of the Model Router subsystem. It implements the
``ModelRouter`` interface defined by the System Orchestrator
(``core.orchestrator.interfaces.ModelRouter``) while keeping the routing
logic fully provider-agnostic.

The router:
  * receives requests from the System Orchestrator,
  * selects the best provider/model via the :class:`RoutingStrategy`,
  * executes the request on the selected provider,
  * falls back to the next best provider when the primary fails,
  * publishes lifecycle events on the event bus,
  * and stays open/closed compliant — new providers plug in via
    :class:`BaseModelProvider` without requiring router changes.
"""

from typing import Any, Dict, Iterator, List, Optional

from core.event_bus import event_bus as default_event_bus
from core.logging import get_logger

from core.model_router.base_provider import BaseModelProvider
from core.model_router.fallback import FallbackStrategy
from core.model_router.health import ProviderHealthMonitor
from core.model_router.models import (
    ProviderHealth,
    ProviderInfo,
    ProviderStatus,
    RouteDecision,
    RouteRequest,
    RouteResult,
)
from core.model_router.registry import ProviderRegistry
from core.model_router.strategy import RoutingStrategy

logger = get_logger("ModelRouter")

# Event topics published by the router. Other subsystems (UI, telemetry,
# logs) subscribe via the event bus without coupling to the router.
EV_ROUTE_REQUESTED = "model_router.requested"
EV_ROUTE_SELECTED = "model_router.selected"
EV_ROUTE_STREAM_STARTED = "model_router.stream_started"
EV_ROUTE_STREAM_CHUNK = "model_router.stream_chunk"
EV_ROUTE_STREAM_COMPLETED = "model_router.stream_completed"
EV_ROUTE_SUCCEEDED = "model_router.succeeded"
EV_ROUTE_FAILED = "model_router.failed"
EV_ROUTE_FALLBACK = "model_router.fallback"
EV_PROVIDER_REGISTERED = "model_router.provider_registered"
EV_PROVIDER_UNREGISTERED = "model_router.provider_unregistered"
EV_PROVIDER_HEALTH_CHANGED = "model_router.provider_health_changed"


class ModelRouter:
    """Routes AI requests to the most appropriate registered provider.

    Args:
        registry: Provider registry containing all registered providers.
        strategy: Scoring strategy used to rank candidates.
        fallback: Fallback strategy used after a failed attempt.
        health_monitor: Monitors provider health (may be started lazily).
        config: Optional ConfigManager for router defaults.
        event_bus: Event bus to publish lifecycle events on.
    """

    def __init__(
        self,
        registry: Optional[ProviderRegistry] = None,
        strategy: Optional[RoutingStrategy] = None,
        fallback: Optional[FallbackStrategy] = None,
        health_monitor: Optional[ProviderHealthMonitor] = None,
        config: Any = None,
        event_bus: Any = default_event_bus,
        stats_manager: Any = None,
        capability_matcher: Any = None,
    ) -> None:
        self._registry = registry if registry is not None else ProviderRegistry()
        self._config = config
        self._event_bus = event_bus
        self._stats_manager = stats_manager
        self._capability_matcher = capability_matcher

        self._strategy = strategy or RoutingStrategy(
            weights=self._strategy_weights_from_config()
        )
        self._fallback = fallback or FallbackStrategy(
            registry=self._registry,
            routing_strategy=self._strategy,
        )
        self._health = health_monitor or ProviderHealthMonitor(
            registry=self._registry,
            check_interval=float(self._config_get("health.check_interval", 60.0)),
            timeout=float(self._config_get("health.timeout", 5.0)),
            on_status_change=self._on_health_change,
        )

        self._max_fallbacks = int(self._config_get("max_fallbacks", 3))
        self._default_max_tokens = int(self._config_get("max_tokens", 512))
        self._default_temperature = float(self._config_get("temperature", 0.7))

        # Retry-once semantics: transient failures retry on the same provider
        # before moving to the next compatible provider.
        self._retries = int(self._config_get("retries", 1))

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> "ModelRouter":
        """Start the health monitor background thread."""
        self._health.start()
        return self

    def stop(self) -> None:
        """Stop background threads."""
        self._health.stop()

    @property
    def registry(self) -> ProviderRegistry:
        """The provider registry backing this router."""
        return self._registry

    @property
    def health(self) -> ProviderHealthMonitor:
        """The health monitor backing this router."""
        return self._health

    # ------------------------------------------------------------------ #
    # Provider registration (delegated to the registry)
    # ------------------------------------------------------------------ #
    def register_provider(self, provider: BaseModelProvider) -> "ModelRouter":
        """Register a provider adapter with the router."""
        self._registry.register(provider)
        self._publish(EV_PROVIDER_REGISTERED, {"provider": provider.name})
        return self

    def unregister_provider(self, name: str) -> bool:
        """Unregister a provider by name."""
        removed = self._registry.unregister(name)
        if removed:
            self._publish(EV_PROVIDER_UNREGISTERED, {"provider": name})
        return removed

    def providers(self) -> List[str]:
        """Return names of all registered providers."""
        return self._registry.names()

    def provider_info(self, name: str) -> Optional[ProviderInfo]:
        """Return cached info for a provider."""
        return self._registry.get_info(name)

    @property
    def max_fallbacks(self) -> int:
        return self._max_fallbacks

    @max_fallbacks.setter
    def max_fallbacks(self, value: int) -> None:
        self._max_fallbacks = max(0, int(value))

    # ------------------------------------------------------------------ #
    # System Orchestrator interface (core.orchestrator.interfaces.ModelRouter)
    # ------------------------------------------------------------------ #
    def complete(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        model: Optional[str] = None,
        stream: bool = False,
        preferred_provider: Optional[str] = None,
        required_capabilities: Optional[List[str]] = None,
        context_estimate: Optional[int] = None,
        max_cost: Optional[float] = None,
        timeout: Optional[float] = None,
        **extra: Any,
    ) -> str:
        """Complete a prompt using the best available route.

        Kept backward-compatible with the orchestrator's ``complete()``
        signature; additional routing options are accepted as keyword args.

        Raises:
            RuntimeError: When no provider can serve the request.
        """
        request = self._build_request(
            prompt=prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            model=model,
            stream=stream,
            preferred_provider=preferred_provider,
            required_capabilities=required_capabilities,
            context_estimate=context_estimate,
            max_cost=max_cost,
            timeout=timeout,
            extra=extra,
        )
        result = self.route(request)
        if not result.success:
            if result.error:
                raise RuntimeError(result.error)
            raise RuntimeError("No AI model route is available.")
        return result.text

    def is_available(self) -> bool:
        """Return True if at least one provider can serve requests."""
        return len(self._registry) > 0

    def is_healthy(self) -> bool:
        """Return True if at least one provider is healthy (or untested)."""
        for name in self._registry.names():
            health = self._registry.get_health(name)
            if health.is_healthy or health.status == ProviderStatus.UNKNOWN:
                return True
        return False

    # ------------------------------------------------------------------ #
    # Routing API
    # ------------------------------------------------------------------ #
    def route(self, request: RouteRequest) -> RouteResult:
        """Route and execute a request with automatic fallback.

        Returns a :class:`RouteResult` describing the outcome.
        """
        self._publish(EV_ROUTE_REQUESTED, self._request_payload(request))

        used: List[str] = []
        plan = self._build_plan(request)
        if not plan:
            return self._fail(
                request,
                used=[],
                error="No provider can serve this request",
            )

        attempts = min(len(plan), self._max_fallbacks + 1)
        for index in range(attempts):
            decision = plan[index]
            provider = self._registry.get(decision.provider)
            if provider is None:
                continue

            used.append(decision.provider)
            self._publish(EV_ROUTE_SELECTED, {
                **self._request_payload(request),
                **decision.as_dict(),
                "attempt": index + 1,
            })

            # Attempt with retry-once semantics: transient failures retry on
            # the same provider before moving to the next compatible one.
            retries = 0
            error: Optional[str] = None
            while True:
                try:
                    if request.stream and provider.supports_streaming:
                        return self._execute_stream(request, provider, decision, used)
                    text = provider.complete(request)
                    result = RouteResult(
                        request=request,
                        provider=decision.provider,
                        model=decision.model,
                        text=text,
                        cost=decision.cost_estimate or 0.0,
                        latency_ms=self._measure_latency(provider),
                        fallback_chain=list(used),
                        success=True,
                    )
                    self._record_outcome(request, decision.provider, True)
                    self._publish(EV_ROUTE_SUCCEEDED, {
                        **self._request_payload(request),
                        **result.as_dict(),
                    })
                    return result

                except Exception as exc:  # noqa: BLE001 - fallback must trigger
                    error = f"{type(exc).__name__}: {exc}"
                    if retries < self._retries:
                        retries += 1
                        logger.info(
                            f"Retrying provider '{decision.provider}' "
                            f"(attempt {retries}/{self._retries}): {error}",
                            provider=decision.provider,
                        )
                        continue
                    break

            logger.warning(
                f"Provider '{decision.provider}' failed: {error}",
                provider=decision.provider,
                attempt=index + 1,
            )
            self._record_outcome(request, decision.provider, False)
            self._publish(EV_ROUTE_FALLBACK, {
                **self._request_payload(request),
                "failed_provider": decision.provider,
                "error": error,
                "next_provider": plan[index + 1].provider
                if index + 1 < len(plan) else None,
            })
            if index + 1 >= attempts:
                return self._fail(request, used=used, error=error or "unknown error")

        return self._fail(
            request,
            used=used,
            error="All providers exhausted",
        )

    def route_stream(self, request: RouteRequest) -> Iterator[str]:
        """Stream a response from the best available provider.

        Behaves like :meth:`route` but yields text chunks. Consumers can
        iterate the returned generator; the generator drives fallback
        internally.
        """
        yield from self.route(request).stream or ()

    def plan(self, request: RouteRequest) -> List[RouteDecision]:
        """Return the ranked routing plan without executing anything."""
        return self._build_plan(request)

    def select(self, request: RouteRequest) -> Optional[RouteDecision]:
        """Return the single best route without executing anything."""
        plan = self._build_plan(request)
        return plan[0] if plan else None

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _build_plan(self, request: RouteRequest) -> List[RouteDecision]:
        """Build a ranked fallback plan of route decisions.

        Uses the fallback strategy so unhealthy/unsuitable providers are
        excluded and the plan is automatically ordered best-first. When the
        request has no explicit capabilities, they are inferred from the
        prompt so task-based routing works transparently.
        """
        # Transparent task → capability inference for task-based routing.
        if not request.required_capabilities and request.prompt and self._capability_matcher is not None:
            try:
                inferred = self._capability_matcher.infer_capabilities(request.prompt)
                if inferred:
                    request.required_capabilities = inferred
            except Exception:
                pass

        candidates = []
        for name in self._registry.names():
            info = self._registry.get_info(name)
            if info is None:
                continue
            health = self._registry.get_health(name)
            candidates.append((info, health))
        ranked = self._strategy.rank(request, candidates)
        return self._fallback.build_plan(request, ranked)

    def _execute_stream(
        self,
        request: RouteRequest,
        provider: BaseModelProvider,
        decision: RouteDecision,
        used: List[str],
    ) -> RouteResult:
        """Execute a streaming request on a specific provider."""
        self._publish(EV_ROUTE_STREAM_STARTED, {
            **self._request_payload(request),
            **decision.as_dict(),
        })
        try:
            def _gen() -> Iterator[str]:
                for chunk in provider.complete_stream(request):
                    self._publish(EV_ROUTE_STREAM_CHUNK, {
                        **self._request_payload(request),
                        "chunk": chunk,
                    })
                    yield chunk
                self._publish(EV_ROUTE_STREAM_COMPLETED, {
                    **self._request_payload(request),
                    **decision.as_dict(),
                })

            return RouteResult(
                request=request,
                provider=decision.provider,
                model=decision.model,
                stream=_gen(),
                cost=decision.cost_estimate or 0.0,
                fallback_chain=list(used),
                success=True,
            )
        except Exception as exc:  # noqa: BLE001
            return self._fail(
                request,
                used=used,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _fail(self, request: RouteRequest, *, used: List[str], error: str) -> RouteResult:
        result = RouteResult(
            request=request,
            provider=used[-1] if used else "",
            model="",
            error=error,
            fallback_chain=list(used),
            success=False,
        )
        self._publish(EV_ROUTE_FAILED, {
            **self._request_payload(request),
            **result.as_dict(),
        })
        logger.error(
            f"Routing failed: {error}",
            providers=list(self._registry.names()),
            error=list(result.fallback_chain),
        )
        return result

    def _build_request(self, **kwargs: Any) -> RouteRequest:
        """Convert simple keyword options into a RouteRequest."""
        extra = kwargs.pop("extra", {})
        # ``complete`` accepts ``required_capabilities=None``; the model's
        # default is an empty list, so normalise it here to keep downstream
        # consumers (strategy, event payloads) type-safe.
        if kwargs.get("required_capabilities") is None:
            kwargs["required_capabilities"] = []

        # If no capabilities were requested, infer them from the prompt so
        # task-based capability matching works transparently.
        if not kwargs.get("required_capabilities") and kwargs.get("prompt"):
            if self._capability_matcher is not None:
                try:
                    inferred = self._capability_matcher.infer_capabilities(kwargs["prompt"])
                    if inferred:
                        kwargs["required_capabilities"] = inferred
                except Exception:
                    pass  # keep empty list when inference fails

        return RouteRequest(**kwargs, extra=extra)

    def _record_outcome(
        self,
        request: RouteRequest,
        provider_name: str,
        success: bool,
    ) -> None:
        """Record a request outcome in the provider statistics manager."""
        if self._stats_manager is None:
            return
        try:
            category = None
            if request.required_capabilities:
                category = request.required_capabilities[0]
            latency_ms = 0.0
            health = self._registry.get_health(provider_name)
            if health and health.latency_ms:
                latency_ms = health.latency_ms
            self._stats_manager.record_request(
                provider_name=provider_name,
                success=success,
                latency_ms=latency_ms,
                category=category,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Failed to record outcome for '{provider_name}': {exc}")

    def _measure_latency(self, provider: BaseModelProvider) -> Optional[float]:
        health = self._registry.get_health(provider.name)
        return health.latency_ms

    # ------------------------------------------------------------------ #
    # Config helpers
    # ------------------------------------------------------------------ #
    def _config_get(self, key: str, default: Any = None) -> Any:
        if self._config is None:
            return default
        try:
            return self._config.get(f"model_router.{key}", default)
        except Exception:
            return default

    def _strategy_weights_from_config(self) -> Optional[Dict[str, float]]:
        if self._config is None:
            return None
        try:
            weights = self._config.get("model_router.weights", None)
            if isinstance(weights, dict):
                return {k: float(v) for k, v in weights.items()}
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ #
    # Event helpers
    # ------------------------------------------------------------------ #
    def _publish(self, event: str, payload: Dict[str, Any]) -> None:
        try:
            self._event_bus.emit(event, payload)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Event publish failed for {event}: {exc}")

    @staticmethod
    def _request_payload(request: RouteRequest) -> Dict[str, Any]:
        return {
            "prompt": request.prompt,
            "system": request.system,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "model": request.model,
            "stream": request.stream,
            "preferred_provider": request.preferred_provider,
            "required_capabilities": list(request.required_capabilities or []),
        }

    def _on_health_change(self, name: str, health: ProviderHealth) -> None:
        self._publish(EV_PROVIDER_HEALTH_CHANGED, {
            "provider": name,
            **health.as_dict(),
        })