"""Automatic Fallback — retry-once-then-fallback execution for resilience.

Extends :class:`FallbackStrategy` with per-provider retry: each provider in
the plan is attempted once, and on failure the same provider may be retried
once (transient errors) before moving to the next compatible provider.
"""

from typing import Dict, List, Optional, Set

from core.logging import get_logger

from core.model_router.fallback import FallbackStrategy
from core.model_router.models import (
    ProviderHealth,
    RouteDecision,
    RouteRequest,
    RouteResult,
)
from core.model_router.registry import ProviderRegistry
from core.model_router.strategy import RoutingStrategy

logger = get_logger("AutomaticFallback")


class AutomaticFallback(FallbackStrategy):
    """Fallback strategy with automatic retry and transient-error handling.

    Args:
        registry: Provider registry used to resolve fallback providers.
        routing_strategy: Strategy used to choose the primary route and
            to re-rank remaining candidates for each fallback step.
        max_retries: Number of retry attempts per provider (default 1).
        retry_on_errors: Set of error class names to retry. When empty,
            retries happen for any failure.
        allow_health_bypass: When True, fallback may still use a provider
            whose health is UNKNOWN. Unhealthy providers are always skipped.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        routing_strategy: RoutingStrategy,
        max_retries: int = 1,
        retry_on_errors: Optional[Set[str]] = None,
        allow_health_bypass: bool = True,
    ) -> None:
        super().__init__(
            registry=registry,
            routing_strategy=routing_strategy,
            allow_health_bypass=allow_health_bypass,
        )
        self._max_retries = max(0, int(max_retries))
        self._retry_on_errors = retry_on_errors or set()
        self._retry_counters: Dict[str, int] = {}

    def build_plan(
        self,
        request: RouteRequest,
        decisions: List[RouteDecision],
        *,
        excluded: Optional[List[str]] = None,
    ) -> List[RouteDecision]:
        """Return a fallback plan: ranked route decisions, best-first."""
        plan = super().build_plan(request, decisions, excluded=excluded)

        # Pre-sort plan so the best-ranked provider is always first.
        plan.sort(key=lambda d: d.score, reverse=True)
        return plan

    def execute_with_retry(
        self,
        request: RouteRequest,
        plan: List[RouteDecision],
        providers: Dict[str, object],
    ) -> RouteResult:
        """Execute a request against a plan with retry-once semantics.

        For each decision in ``plan`` (best-first):

        1. Attempt the provider once.
        2. On failure, retry the *same* provider up to ``max_retries``
           times when the failure looks transient.
        3. If retries are exhausted, move to the next provider in the plan.

        Args:
            request: The routing request.
            plan: Ordered list of route decisions (best-first).
            providers: Mapping of provider name to provider instance.

        Returns:
            A :class:`RouteResult` describing the outcome.
        """
        used: List[str] = []
        last_error: Optional[str] = None

        for decision in plan:
            provider = providers.get(decision.provider)
            if provider is None:
                continue

            used.append(decision.provider)
            retries = 0

            while True:
                try:
                    text = provider.complete(request)
                    return RouteResult(
                        request=request,
                        provider=decision.provider,
                        model=decision.model,
                        text=text,
                        cost=decision.cost_estimate or 0.0,
                        fallback_chain=list(used),
                        success=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    error = f"{type(exc).__name__}: {exc}"
                    last_error = error

                    # Retry the same provider when configured and eligible.
                    if retries < self._max_retries and self._should_retry(exc):
                        retries += 1
                        logger.info(
                            f"Retrying provider '{decision.provider}' "
                            f"(attempt {retries}/{self._max_retries}): {error}"
                        )
                        continue

                    logger.warning(
                        f"Provider '{decision.provider}' failed: {error}",
                        provider=decision.provider,
                        retries=retries,
                    )
                    break

        return RouteResult(
            request=request,
            provider=used[-1] if used else "",
            model="",
            error=last_error or "No provider could serve the request",
            fallback_chain=list(used),
            success=False,
        )

    def _should_retry(self, exc: Exception) -> bool:
        """Decide whether a failure is worth retrying on the same provider."""
        if not self._retry_on_errors:
            return True
        return type(exc).__name__ in self._retry_on_errors
