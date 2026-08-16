"""Provider-agnostic routing strategy."""

from typing import Dict, List, Optional, Tuple

from core.logging import get_logger
from core.model_router.capabilities import ModelCapabilityRegistry
from core.model_router.models import (
    CAPABILITY_STREAMING, CAPABILITY_TEXT, ModelCapabilities, ModelInfo,
    ProviderHealth, ProviderInfo, ProviderStatus, RouteDecision, RouteRequest,
)
from core.model_router.free_first import apply_free_first_priority

logger = get_logger("RoutingStrategy")

DEFAULT_WEIGHTS = {
    "priority": 0.25, "health": 0.25, "cost": 0.20,
    "latency": 0.15, "context": 0.10, "capability": 0.05,
}


class RoutingStrategy:
    """Scores qualified provider/model routes without vendor-specific logic."""

    def __init__(self, weights: Optional[Dict[str, float]] = None,
                 capability_registry: Optional[ModelCapabilityRegistry] = None) -> None:
        self._weights = {**DEFAULT_WEIGHTS, **(weights or {})}
        self._capabilities = capability_registry

    def select(self, request: RouteRequest,
               providers: List[Tuple[ProviderInfo, ProviderHealth]]) -> Optional[RouteDecision]:
        decisions = self.rank(request, providers)
        return decisions[0] if decisions else None

    def rank(self, request: RouteRequest,
             providers: List[Tuple[ProviderInfo, ProviderHealth]]) -> List[RouteDecision]:
        candidates: List[Tuple[float, RouteDecision]] = []
        for info, health in providers:
            model_choice = self._pick_model(request, info)
            if model_choice is None:
                continue
            model, _ = model_choice
            scored = self._score(request, info, model, health)
            if scored is None:
                continue
            score, reason = scored
            candidates.append((score, RouteDecision(
                provider=info.name, model=model.id, score=score, reason=reason,
                cost_estimate=self._estimate_cost(request, model),
                latency_ms=health.latency_ms,
            )))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [decision for _, decision in candidates]

    def _pick_model(self, request: RouteRequest, info: ProviderInfo) -> Optional[Tuple[ModelInfo, int]]:
        candidates = self._filter_models(request, info)
        if not candidates:
            return None
        for wanted in (request.preferred_models or []):
            for model in candidates:
                if model.id == wanted:
                    return model, model.context_length or info.context_length
        chosen = max(candidates, key=lambda m: m.context_length or info.context_length)
        return chosen, chosen.context_length or info.context_length

    def _filter_models(self, request: RouteRequest, info: ProviderInfo) -> List[ModelInfo]:
        required = {cap.lower() for cap in (request.required_capabilities or [])}
        if not required:
            required = {CAPABILITY_STREAMING} if request.stream else {CAPABILITY_TEXT}
        if request.max_cost is not None and info.cost is None and not info.is_local:
            return []

        # The registry is authoritative when populated. ProviderInfo remains
        # the compatibility fallback for providers created directly in tests
        # or third-party integrations that have not registered metadata yet.
        models = self._capability_models(info)
        if not models:
            models = info.models or [self._fallback_model(info)]

        filtered = [m for m in models if self._model_matches(request, info, m, required)]
        if filtered:
            return filtered
        if self._provider_matches(request, info, required):
            return [models[0]]
        return []

    def _capability_models(self, info: ProviderInfo) -> List[ModelInfo]:
        if self._capabilities is None:
            return []
        return self._capabilities.models_for_provider(info.name)

    def _model_matches(self, request: RouteRequest, info: ProviderInfo,
                       model: ModelInfo, required: set) -> bool:
        if model.id and request.model and model.id != request.model:
            return False
        caps = model.capabilities or info.primary_capabilities()
        if self._capabilities is not None:
            registered = self._capabilities.get(info.name, model.id)
            if registered is not None:
                caps = registered.capabilities or ModelCapabilities()
        if not self._capabilities_cover(caps, required):
            return False
        if not self._context_ok(request, model.context_length or info.context_length):
            return False
        if request.max_cost is not None:
            cost = model.cost or info.cost
            if cost is not None and cost.estimated_cost(request.context_estimate or 1000, request.max_tokens) > request.max_cost:
                return False
        return True

    def _provider_matches(self, request: RouteRequest, info: ProviderInfo, required: set) -> bool:
        return self._capabilities_cover(info.primary_capabilities(), required) and self._context_ok(request, info.context_length)

    @staticmethod
    def _capabilities_cover(caps: ModelCapabilities, required: set) -> bool:
        return all(caps.supports(cap) for cap in required)

    @staticmethod
    def _context_ok(request: RouteRequest, context_length: int) -> bool:
        return context_length <= 0 or (request.context_estimate or 0) <= context_length

    @staticmethod
    def _fallback_model(info: ProviderInfo) -> ModelInfo:
        return ModelInfo(id=info.name, context_length=info.context_length,
                         capabilities=info.primary_capabilities(), cost=info.cost)

    def _score(self, request: RouteRequest, info: ProviderInfo,
               model: ModelInfo, health: ProviderHealth) -> Optional[Tuple[float, str]]:
        if not health.is_healthy and health.status != ProviderStatus.UNKNOWN:
            return None
        components = self._score_components(request, info, model, health)
        total = sum(self._weights[k] * component for k, component in zip(DEFAULT_WEIGHTS, components))
        if request.preferred_provider:
            total *= 2.0 if self._is_preferred_alias(request.preferred_provider, info.name) else 0.5
        return total, self._describe(info.name, model.id, priority=components[0], health=components[1], cost=components[2], latency=components[3], context=components[4])

    def _score_components(self, request: RouteRequest, info: ProviderInfo,
                          model: ModelInfo, health: ProviderHealth):
        effective_priority = min(info.priority, apply_free_first_priority(info))
        priority_score = self._normalise_priority(effective_priority)
        health_score = {ProviderStatus.HEALTHY: 1.0, ProviderStatus.DEGRADED: 0.5, ProviderStatus.UNKNOWN: 0.5}.get(health.status, 0.0)
        cost_score = self._normalise_cost(request, model.cost or info.cost)
        latency_score = self._normalise_latency(health.latency_ms)
        context_score = self._context_score(request, model.context_length or info.context_length)
        cap_score = self._capability_score(request, info, model)
        return priority_score, health_score, cost_score, latency_score, context_score, cap_score

    @staticmethod
    def _normalise_priority(priority: int) -> float:
        return 1.0 / (1.0 + max(0, priority))

    @staticmethod
    def _normalise_cost(request: RouteRequest, cost) -> float:
        if cost is None:
            return 0.3
        if getattr(cost, "is_free", False):
            return 1.0
        estimate = cost.estimated_cost(request.context_estimate or 1000, request.max_tokens)
        return max(0.0, min(1.0, 1.0 - estimate))

    @staticmethod
    def _normalise_latency(latency_ms: Optional[float]) -> float:
        if latency_ms is None:
            return 0.5
        return max(0.0, min(1.0, 1.0 - latency_ms / 10_000.0))

    @staticmethod
    def _context_score(request: RouteRequest, context_length: int) -> float:
        if context_length <= 0:
            return 0.5
        needed = request.context_estimate or 0
        if needed == 0:
            return 0.8
        ratio = needed / context_length
        return 0.0 if ratio > 1.0 else max(0.1, 1.0 - ratio)

    @staticmethod
    def _capability_score(request: RouteRequest, info: ProviderInfo, model: ModelInfo) -> float:
        caps = model.capabilities or info.primary_capabilities()
        required = {cap.lower() for cap in (request.required_capabilities or [])}
        if not required:
            return 0.7
        return sum(1 for cap in required if caps.supports(cap)) / len(required)

    @staticmethod
    def _estimate_cost(request: RouteRequest, model: ModelInfo) -> Optional[float]:
        if request.context_estimate is None or model.cost is None:
            return None
        return model.cost.estimated_cost(request.context_estimate, request.max_tokens)

    @staticmethod
    def _is_preferred_alias(preferred: str, candidate: str) -> bool:
        return preferred.strip().lower() == candidate.strip().lower()

    @staticmethod
    def _describe(name: str, model_id: str, *, priority: float, health: float,
                  cost: float, latency: float, context: float) -> str:
        parts = []
        if priority > 0.8: parts.append("high priority")
        elif priority < 0.3: parts.append("low priority")
        if health >= 1.0: parts.append("healthy")
        if cost >= 0.9: parts.append("cheap")
        elif cost < 0.4: parts.append("expensive")
        if latency > 0.9: parts.append("fast")
        elif latency < 0.4: parts.append("slow")
        if context > 0.9: parts.append("ample context")
        return f"{name}/{model_id} chosen ({', '.join(parts) if parts else 'balanced'})"
