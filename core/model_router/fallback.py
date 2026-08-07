"""Fallback Strategy — ordered fallback across providers for resilience.

When the primary route fails (provider error, timeout, unhealthy status),
the fallback strategy walks a prioritised list of remaining providers so
requests still succeed even if the best choice is unavailable. This module
has no vendor-specific logic.
"""

from typing import Dict, List, Optional

from core.logging import get_logger

from core.model_router.models import (
    ProviderHealth,
    ProviderStatus,
    RouteDecision,
    RouteRequest,
)
from core.model_router.registry import ProviderRegistry
from core.model_router.strategy import RoutingStrategy

logger = get_logger("FallbackStrategy")


class FallbackStrategy:
    """Builds and executes an ordered fallback plan.

    Args:
        registry: Provider registry used to resolve fallback providers.
        routing_strategy: The strategy used to choose the primary route
            and to re-rank remaining candidates for each fallback step.
        allow_health_bypass: When True, fallback may still use a provider
            whose health is UNKNOWN (never probed yet). Unhealthy providers
            are always skipped.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        routing_strategy: RoutingStrategy,
        allow_health_bypass: bool = True,
    ) -> None:
        self._registry = registry
        self._routing = routing_strategy
        self._allow_health_bypass = allow_health_bypass

    # ------------------------------------------------------------------ #
    # Plan construction
    # ------------------------------------------------------------------ #
    def build_plan(
        self,
        request: RouteRequest,
        decisions: List[RouteDecision],
        *,
        excluded: Optional[List[str]] = None,
    ) -> List[RouteDecision]:
        """Return a fallback plan: ranked route decisions, best-first.

        The plan is derived from ``decisions`` (already scored best-first),
        with ``excluded`` provider names removed. If no decisions are given,
        a fresh ranking is computed from all registered providers.

        Args:
            request: The routing request.
            decisions: Pre-computed ranked decisions (best-first).
            excluded: Provider names to skip entirely.

        Returns:
            Ordered list of fallback route decisions (best-first).
        """
        excluded = set(excluded or ())
        plan: List[RouteDecision] = []

        for decision in decisions:
            if decision.provider in excluded:
                continue
            health = self._registry.get_health(decision.provider)
            if not self._acceptable(health):
                continue
            plan.append(decision)

        if plan:
            return plan

        # No usable pre-computed decisions: rank from scratch.
        fresh = self._routing.rank(request, self._candidate_providers(excluded))
        return [
            decision
            for decision in fresh
            if decision.provider not in excluded
            and self._acceptable(self._registry.get_health(decision.provider))
        ]

    # ------------------------------------------------------------------ #
    # Execution helpers
    # ------------------------------------------------------------------ #
    def next_fallback(
        self,
        request: RouteRequest,
        used: List[str],
        plans: Optional[List[RouteDecision]] = None,
    ) -> Optional[RouteDecision]:
        """Return the next fallback decision after ``used`` providers.

        Args:
            request: The routing request.
            used: Provider names already attempted.
            plans: Optional pre-computed plan; when omitted, the plan is
                built on the fly from all registered providers.

        Returns:
            The next :class:`RouteDecision`, or None when no provider
            remains.
        """
        if plans is None:
            plans = self.build_plan(request, self._routing.rank(
                request, self._candidate_providers()
            ))
        for decision in plans:
            if decision.provider in used:
                continue
            health = self._registry.get_health(decision.provider)
            if not self._acceptable(health):
                continue
            return decision
        return None

    def remaining_after(self, used: List[str]) -> List[str]:
        """Return provider names not yet attempted and still usable."""
        return [
            name
            for name in self._registry.names()
            if name not in used and self._acceptable(self._registry.get_health(name))
        ]

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _acceptable(self, health: ProviderHealth) -> bool:
        if health.status == ProviderStatus.HEALTHY:
            return True
        if health.status == ProviderStatus.DEGRADED:
            return True
        if health.status == ProviderStatus.UNKNOWN:
            return self._allow_health_bypass
        return False  # UNHEALTHY

    def _candidate_providers(self, excluded: Optional[set] = None) -> List:
        """Build (ProviderInfo, ProviderHealth) tuples for scoring."""
        excluded = excluded or set()
        candidates = []
        for name in self._registry.names():
            if name in excluded:
                continue
            info = self._registry.get_info(name)
            if info is None:
                continue
            health = self._registry.get_health(name)
            if not self._acceptable(health):
                continue
            candidates.append((info, health))
        return candidates