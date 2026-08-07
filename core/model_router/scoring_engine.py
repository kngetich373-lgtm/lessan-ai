"""Enhanced Scoring Engine — integrates learning, free-first, and capability matching."""

from typing import Dict, List, Optional, Tuple

from core.logging import get_logger
from core.model_router.models import (
    ProviderHealth, ProviderInfo, ProviderStatus, RouteDecision, RouteRequest,
)
from core.model_router.strategy import RoutingStrategy
from core.model_router.learning import ProviderLearningSystem
from core.model_router.free_first import boost_free_score, apply_free_first_priority
from core.model_router.capability_matcher import match_score
from core.model_router.preferences import ProviderPreferenceManager

logger = get_logger("ScoringEngine")

# Enhanced scoring weights
ENHANCED_WEIGHTS = {
    "priority": 0.15,
    "health": 0.20,
    "cost": 0.20,
    "latency": 0.10,
    "context": 0.08,
    "capability_match": 0.15,
    "historical_success": 0.12,
}


class EnhancedScoringEngine:
    """Enhanced scoring engine with learning and free-first logic."""
    
    def __init__(
        self,
        base_strategy: RoutingStrategy,
        learning_system: Optional[ProviderLearningSystem] = None,
        preference_manager: Optional[ProviderPreferenceManager] = None,
        weights: Optional[Dict[str, float]] = None,
    ) -> None:
        self._base_strategy = base_strategy
        self._learning = learning_system
        self._preferences = preference_manager
        self._weights = {**ENHANCED_WEIGHTS, **(weights or {})}
    
    def rank(
        self,
        request: RouteRequest,
        providers: List[Tuple[ProviderInfo, ProviderHealth]],
    ) -> List[RouteDecision]:
        """Alias for :meth:`score_and_rank` — strategy-compatible interface.

        The :class:`ModelRouter` and :class:`FallbackStrategy` call
        ``strategy.rank(...)``; this engine keeps that contract while adding
        the enhanced scoring pipeline.
        """
        return self.score_and_rank(request, providers)

    def score_and_rank(
        self,
        request: RouteRequest,
        providers: List[Tuple[ProviderInfo, ProviderHealth]],
    ) -> List[RouteDecision]:
        """Score and rank providers with enhanced logic.
        
        Args:
            request: The routing request.
            providers: List of (ProviderInfo, ProviderHealth) tuples.
        
        Returns:
            List of RouteDecision objects, sorted best-first.
        """
        # Apply preferences first
        providers = self._apply_preferences(providers, request)
        
        # If a provider is forced, return only that one
        if self._preferences:
            forced = self._preferences.get_forced_provider()
            if forced:
                for info, health in providers:
                    if info.name == forced:
                        model = info.models[0] if info.models else None
                        if model:
                            return [RouteDecision(
                                provider=info.name,
                                model=model.id,
                                score=100.0,
                                reason=f"Forced by user preference",
                            )]
        
        # Use base strategy to get initial ranking
        base_decisions = self._base_strategy.rank(request, providers)
        
        # Enhance scores with learning and free-first
        enhanced_decisions = []
        for decision in base_decisions:
            enhanced_score = self._enhance_score(decision, request, providers)
            enhanced_decisions.append(RouteDecision(
                provider=decision.provider,
                model=decision.model,
                score=enhanced_score,
                reason=self._build_reason(decision, enhanced_score),
                cost_estimate=decision.cost_estimate,
                latency_ms=decision.latency_ms,
            ))
        
        # Re-sort by enhanced scores
        enhanced_decisions.sort(key=lambda d: d.score, reverse=True)
        return enhanced_decisions
    
    def _enhance_score(
        self,
        decision: RouteDecision,
        request: RouteRequest,
        providers: List[Tuple[ProviderInfo, ProviderHealth]],
    ) -> float:
        """Enhance a base score with learning and free-first logic."""
        base_score = decision.score
        
        # Find provider info
        provider_info = None
        for info, _ in providers:
            if info.name == decision.provider:
                provider_info = info
                break
        
        if provider_info is None:
            return base_score
        
        # Apply free-first boost
        if provider_info.cost:
            base_score = boost_free_score(base_score, provider_info.cost)
        
        # Apply learning-based adjustment
        if self._learning:
            historical_score = self._learning.calculate_historical_score(
                decision.provider, request
            )
            # Blend base and historical scores
            learning_weight = self._weights.get("historical_success", 0.12)
            base_score = (base_score * (1 - learning_weight)) + (historical_score * learning_weight * 100)
        
        # Apply capability match bonus
        if request.required_capabilities and provider_info.primary_capabilities():
            cap_match = match_score(
                request.required_capabilities,
                list(provider_info.primary_capabilities().as_dict().keys())
            )
            cap_weight = self._weights.get("capability_match", 0.15)
            base_score += cap_match * cap_weight * 100
        
        return min(100.0, base_score)
    
    def _apply_preferences(
        self,
        providers: List[Tuple[ProviderInfo, ProviderHealth]],
        request: RouteRequest,
    ) -> List[Tuple[ProviderInfo, ProviderHealth]]:
        """Filter providers based on user preferences."""
        if not self._preferences:
            return providers
        
        filtered = []
        for info, health in providers:
            # Skip disabled providers
            if not self._preferences.is_provider_enabled(info.name):
                continue
            
            # Apply local/cloud filters
            if self._preferences.is_local_only() and not info.is_local:
                continue
            if self._preferences.is_cloud_only() and info.is_local:
                continue
            
            # Apply priority overrides
            priority_override = self._preferences.get_priority_override(info.name)
            if priority_override is not None:
                info.priority = priority_override
            
            filtered.append((info, health))
        
        return filtered
    
    @staticmethod
    def _build_reason(decision: RouteDecision, enhanced_score: float) -> str:
        """Build a human-readable reason for the decision."""
        if enhanced_score > 90:
            return f"Excellent match ({decision.reason})"
        elif enhanced_score > 75:
            return f"Good match ({decision.reason})"
        elif enhanced_score > 50:
            return f"Acceptable match ({decision.reason})"
        else:
            return f"Fallback option ({decision.reason})"
