"""Routing Strategy — scores providers/models and selects the best route.

The router stays provider-agnostic by delegating the *decision* to this
strategy, which only works with the neutral ``ProviderInfo``, ``ModelInfo``
and ``RouteRequest`` value objects. No vendor logic lives here.
"""

from typing import Dict, List, Optional, Tuple

from core.logging import get_logger

from core.model_router.models import (
    CAPABILITY_STREAMING,
    CAPABILITY_TEXT,
    CAPABILITY_TOOL_CALLING,
    CAPABILITY_VISION,
    ModelCapabilities,
    ModelInfo,
    ProviderHealth,
    ProviderInfo,
    ProviderStatus,
    RouteDecision,
    RouteRequest,
)
from core.model_router.free_first import apply_free_first_priority

logger = get_logger("RoutingStrategy")

# Tunable scoring weights. These can be overridden from configuration.
DEFAULT_WEIGHTS = {
    "priority": 0.25,     # provider priority (lower number = better)
    "health": 0.25,       # availability/health status
    "cost": 0.20,         # estimated cost (lower = better)
    "latency": 0.15,      # response speed (lower = better)
    "context": 0.10,      # context/support for the requested size
    "capability": 0.05,   # capability fit bonus
}


class RoutingStrategy:
    """Scores candidate (provider, model) pairs for a route request.

    The strategy produces a ranked list of :class:`RouteDecision` instances.
    It applies hard filters first (health, capabilities, context size,
    cost limit), then scores the survivors. A ``preferred_provider`` is a
    strong *preference* that boosts a candidate to the top of the ranking —
    it never removes the other candidates, so automatic fallback keeps
    working when the preferred provider fails.
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None) -> None:
        self._weights = {**DEFAULT_WEIGHTS, **(weights or {})}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def select(
        self,
        request: RouteRequest,
        providers: List[Tuple[ProviderInfo, ProviderHealth]],
    ) -> Optional[RouteDecision]:
        """Return the best route for ``request``, or None if none qualify."""
        decisions = self.rank(request, providers)
        return decisions[0] if decisions else None

    def rank(
        self,
        request: RouteRequest,
        providers: List[Tuple[ProviderInfo, ProviderHealth]],
    ) -> List[RouteDecision]:
        """Return all qualified routes sorted best-first."""
        candidates: List[Tuple[float, RouteDecision]] = []

        for info, health in providers:
            model_choice = self._pick_model(request, info)
            if model_choice is None:
                continue

            model, context_length = model_choice
            scored = self._score(request, info, model, health)
            if scored is None:
                continue
            score, reason = scored

            cost_estimate = self._estimate_cost(request, model)
            decision = RouteDecision(
                provider=info.name,
                model=model.id,
                score=score,
                reason=reason,
                cost_estimate=cost_estimate,
                latency_ms=health.latency_ms,
            )
            candidates.append((score, decision))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return [decision for _, decision in candidates]

    # ------------------------------------------------------------------ #
    # Model selection within a provider
    # ------------------------------------------------------------------ #
    def _pick_model(
        self,
        request: RouteRequest,
        info: ProviderInfo,
    ) -> Optional[Tuple[ModelInfo, int]]:
        """Choose the best model from ``info`` for the request.

        Respects ``request.model`` / ``request.preferred_models`` when set,
        the required capabilities, and the needed context window.
        Returns ``(model, context_length)`` or None when nothing fits.
        """
        candidates = self._filter_models(request, info)
        if not candidates:
            return None

        # Prefer explicitly requested model ordering
        for wanted in (request.preferred_models or []):
            for model in candidates:
                if model.id == wanted:
                    return model, model.context_length or info.context_length

        # Otherwise prefer the largest context that still satisfies cost caps
        def _context(model: ModelInfo) -> int:
            return model.context_length or info.context_length

        chosen = max(candidates, key=_context)
        return chosen, _context(chosen)

    def _filter_models(
        self,
        request: RouteRequest,
        info: ProviderInfo,
    ) -> List[ModelInfo]:
        """Filter a provider's models against request constraints."""
        required = {cap.lower() for cap in (request.required_capabilities or [])}
        if not required:
            required = {CAPABILITY_STREAMING} if request.stream else {CAPABILITY_TEXT}

        if request.max_cost is not None and info.cost is None and not info.is_local:
            return []  # remote provider with unknown cost can't satisfy a cap

        models = info.models or [self._fallback_model(info)]
        filtered = []
        for model in models:
            if not self._model_matches(request, info, model, required):
                continue
            filtered.append(model)

        if filtered:
            return filtered

        # Fall back to provider-level capabilities if no model advertises
        # the required set explicitly (common for aggregators/local hosts).
        if self._provider_matches(request, info, required):
            return [models[0]]
        return []

    def _model_matches(
        self,
        request: RouteRequest,
        info: ProviderInfo,
        model: ModelInfo,
        required: set,
    ) -> bool:
        caps = model.capabilities or info.primary_capabilities()
        if model.id and request.model and model.id != request.model:
            return False
        if not self._capabilities_cover(caps, required):
            return False
        if not self._context_ok(request, model.context_length or info.context_length):
            return False
        if request.max_cost is not None:
            cost = model.cost or info.cost
            if cost is not None and cost.estimated_cost(
                request.context_estimate or 1000, request.max_tokens
            ) > request.max_cost:
                return False
        return True

    def _provider_matches(
        self,
        request: RouteRequest,
        info: ProviderInfo,
        required: set,
    ) -> bool:
        caps = info.primary_capabilities()
        if not self._capabilities_cover(caps, required):
            return False
        return self._context_ok(request, info.context_length)

    def _capabilities_cover(self, caps: ModelCapabilities, required: set) -> bool:
        return all(caps.supports(cap) for cap in required)

    def _context_ok(self, request: RouteRequest, context_length: int) -> bool:
        if context_length <= 0:
            return True  # unknown context: assume sufficient
        needed = request.context_estimate or 0
        return needed <= context_length

    @staticmethod
    def _fallback_model(info: ProviderInfo) -> ModelInfo:
        """Synthesise a single model entry when the provider lists none."""
        return ModelInfo(
            id=info.name,
            context_length=info.context_length,
            capabilities=info.primary_capabilities(),
            cost=info.cost,
        )

    # ------------------------------------------------------------------ #
    # Scoring
    # ------------------------------------------------------------------ #
    def _score(
        self,
        request: RouteRequest,
        info: ProviderInfo,
        model: ModelInfo,
        health: ProviderHealth,
    ) -> Optional[Tuple[float, str]]:
        """Return (score, reason) or None if the route is unacceptable."""
        if not health.is_healthy and health.status != ProviderStatus.UNKNOWN:
            return None

        components = self._score_components(request, info, model, health)
        total = sum(
            weight * component
            for weight, component in zip(
                [self._weights[k] for k in DEFAULT_WEIGHTS.keys()],
                components,
            )
        )

        # ``preferred_provider`` is a strong *preference*, not an exclusion:
        # the preferred provider is boosted to the top of the ranking, but
        # other providers stay in the plan so automatic fallback still works
        # when the preferred provider fails at runtime.
        if request.preferred_provider:
            total *= 2.0 if self._is_preferred_alias(request.preferred_provider, info.name) else 0.5

        reason = self._describe(
            info.name, model.id,
            priority=components[0],
            health=components[1],
            cost=components[2],
            latency=components[3],
            context=components[4],
        )
        return total, reason

    def _score_components(
        self,
        request: RouteRequest,
        info: ProviderInfo,
        model: ModelInfo,
        health: ProviderHealth,
    ) -> Tuple[float, float, float, float, float, float]:
        """Compute normalised sub-scores (0..1) for each criterion."""
        # 1. Provider priority (lower number = better), blended with the
        # free-first tier (local free → cloud free → paid) so cost-tier
        # ordering always wins while explicit priority is still respected.
        free_first_priority = apply_free_first_priority(info)
        effective_priority = min(info.priority, free_first_priority)
        priority_score = self._normalise_priority(effective_priority)

        # 2. Health / availability
        if health.status == ProviderStatus.HEALTHY:
            health_score = 1.0
        elif health.status == ProviderStatus.DEGRADED:
            health_score = 0.5
        elif health.status == ProviderStatus.UNKNOWN:
            health_score = 0.5  # treat unknown as average, allow routing
        else:
            health_score = 0.0

        # 3. Cost (lower = better); local/free wins
        cost = model.cost or info.cost
        cost_score = self._normalise_cost(request, cost)

        # 4. Latency (lower ms = better)
        latency_score = self._normalise_latency(health.latency_ms)

        # 5. Context fit (bigger than needed = better, but diminishing)
        context_score = self._context_score(request, model.context_length or info.context_length)

        # 6. Capability fit bonus
        cap_score = self._capability_score(request, info, model)

        return (
            priority_score,
            health_score,
            cost_score,
            latency_score,
            context_score,
            cap_score,
        )

    @staticmethod
    def _normalise_priority(priority: int) -> float:
        """Map priority (0 = best) to a 0..1 score where 1 = best."""
        return 1.0 / (1.0 + max(0, priority))

    @staticmethod
    def _normalise_cost(request: RouteRequest, cost) -> float:
        if cost is None:
            return 0.3  # unknown cost: mid-low score
        if getattr(cost, "is_free", False):
            return 1.0
        estimate = cost.estimated_cost(
            request.context_estimate or 1000, request.max_tokens
        )
        # Scale: $0 → 1.0, >= $1 per request → ~0
        return max(0.0, min(1.0, 1.0 - estimate))

    @staticmethod
    def _normalise_latency(latency_ms: Optional[float]) -> float:
        if latency_ms is None:
            return 0.5
        # 0ms → 1.0, >= 10s → ~0
        return max(0.0, min(1.0, 1.0 - latency_ms / 10_000.0))

    @staticmethod
    def _context_score(request: RouteRequest, context_length: int) -> float:
        if context_length <= 0:
            return 0.5
        needed = request.context_estimate or 0
        if needed == 0:
            return 0.8
        ratio = needed / context_length
        if ratio > 1.0:
            return 0.0
        return max(0.1, 1.0 - ratio)

    @staticmethod
    def _capability_score(request: RouteRequest, info: ProviderInfo, model: ModelInfo) -> float:
        caps = model.capabilities or info.primary_capabilities()
        required = {cap.lower() for cap in (request.required_capabilities or [])}
        if not required:
            return 0.7

        covered = sum(1 for cap in required if caps.supports(cap))
        return covered / len(required)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _estimate_cost(self, request: RouteRequest, model: ModelInfo) -> Optional[float]:
        # Estimate without provider lookup: only when request context known.
        if request.context_estimate is None:
            return None
        cost = model.cost
        if cost is None:
            return None
        return cost.estimated_cost(request.context_estimate, request.max_tokens)

    @staticmethod
    def _is_preferred_alias(preferred: str, candidate: str) -> bool:
        """Match provider names case-insensitively on either side."""
        return preferred.strip().lower() == candidate.strip().lower()

    @staticmethod
    def _describe(
        name: str,
        model_id: str,
        *,
        priority: float,
        health: float,
        cost: float,
        latency: float,
        context: float,
    ) -> str:
        parts = []
        if priority > 0.8:
            parts.append("high priority")
        elif priority < 0.3:
            parts.append("low priority")
        if health >= 1.0:
            parts.append("healthy")
        elif health <= 0.0:
            parts.append("unavailable")
        if cost >= 0.9:
            parts.append("cheap")
        elif cost < 0.4:
            parts.append("expensive")
        if latency > 0.9:
            parts.append("fast")
        elif latency < 0.4:
            parts.append("slow")
        if context > 0.9:
            parts.append("ample context")
        desc = ", ".join(parts) if parts else "balanced"
        return f"{name}/{model_id} chosen ({desc})"