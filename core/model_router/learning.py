"""Learning System — integrates provider statistics into routing decisions."""

from typing import List, Optional, Tuple

from core.logging import get_logger
from core.model_router.models import ProviderHealth, ProviderInfo, RouteRequest
from core.model_router.statistics import ProviderStatisticsManager
from core.model_router.capability_matcher import infer_capabilities

logger = get_logger("LearningSystem")


class ProviderLearningSystem:
    """Uses historical statistics to improve routing decisions."""
    
    def __init__(self, stats_manager: ProviderStatisticsManager) -> None:
        self._stats = stats_manager
    
    def calculate_historical_score(
        self,
        provider_name: str,
        request: RouteRequest,
    ) -> float:
        """Calculate a score based on historical performance.
        
        Args:
            provider_name: Name of the provider.
            request: The routing request.
        
        Returns:
            Score between 0.0 and 1.0.
        """
        stats = self._stats.get_stats(provider_name)
        if stats is None or stats.total_requests < 5:
            # Not enough data: return neutral score
            return 0.5
        
        # Base score from overall success rate
        base_score = stats.success_rate
        
        # If request has required capabilities, check category-specific success
        if request.required_capabilities:
            # Infer primary category from capabilities
            primary_cap = request.required_capabilities[0]
            category_success = stats.get_category_success_rate(primary_cap)
            # Weight category-specific performance higher
            base_score = (base_score * 0.3) + (category_success * 0.7)
        
        # Penalize providers with high latency
        if stats.average_latency_ms > 5000:  # > 5 seconds
            base_score *= 0.8
        elif stats.average_latency_ms > 10000:  # > 10 seconds
            base_score *= 0.6
        
        # Bonus for high quality responses (user feedback)
        if stats.average_response_quality > 0.8:
            base_score *= 1.1
        
        return min(1.0, max(0.0, base_score))
    
    def rank_providers_by_learning(
        self,
        providers: List[Tuple[ProviderInfo, ProviderHealth]],
        request: RouteRequest,
    ) -> List[Tuple[str, float]]:
        """Rank providers based on learned performance.
        
        Args:
            providers: List of (ProviderInfo, ProviderHealth) tuples.
            request: The routing request.
        
        Returns:
            List of (provider_name, score) tuples, sorted best-first.
        """
        scores = []
        for info, health in providers:
            score = self.calculate_historical_score(info.name, request)
            scores.append((info.name, score))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores
    
    def should_explore(self, provider_name: str, exploration_rate: float = 0.1) -> bool:
        """Decide whether to explore an underused provider.
        
        Args:
            provider_name: Name of the provider.
            exploration_rate: Probability of exploration (0.0-1.0).
        
        Returns:
            True if the provider should be explored.
        """
        stats = self._stats.get_stats(provider_name)
        if stats is None or stats.total_requests < 10:
            # Low sample size: explore more
            return True
        
        # Occasionally explore even well-known providers
        import random
        return random.random() < exploration_rate
