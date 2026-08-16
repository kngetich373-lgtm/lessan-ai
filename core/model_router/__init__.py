"""Model Router public API."""

from core.model_router.base_provider import BaseModelProvider
from core.model_router.fallback import FallbackStrategy
from core.model_router.health import ProviderHealthMonitor
from core.model_router.models import (
    CAPABILITY_AUDIO, CAPABILITY_EMBEDDINGS, CAPABILITY_IMAGE_GENERATION,
    CAPABILITY_MULTILINGUAL, CAPABILITY_STREAMING, CAPABILITY_TEXT,
    CAPABILITY_TOOL_CALLING, CAPABILITY_VISION, CostMetadata, ModelCapabilities,
    ModelInfo, ProviderHealth, ProviderInfo, ProviderStatus, RouteDecision,
    RouteRequest, RouteResult,
)
from core.model_router.registry import ProviderRegistry
from core.model_router.router import ModelRouter
from core.model_router.strategy import RoutingStrategy

from core.model_router.automatic_fallback import AutomaticFallback
from core.model_router.benchmark import ProviderBenchmarkService
from core.model_router.capabilities import (
    CAPABILITY_ARCHITECTURE, CAPABILITY_BACKEND_DEV, CAPABILITY_CODE_REVIEW,
    CAPABILITY_DATA_ANALYSIS, CAPABILITY_DATABASE, CAPABILITY_DEBUGGING,
    CAPABILITY_DEVOPS, CAPABILITY_DOCUMENTATION, CAPABILITY_FRONTEND_DEV,
    CAPABILITY_FULLSTACK_DEV, CAPABILITY_GENERAL_CHAT, CAPABILITY_LONG_CONTEXT,
    CAPABILITY_MACHINE_LEARNING, CAPABILITY_MOBILE_DEV, CAPABILITY_PERFORMANCE,
    CAPABILITY_REASONING, CAPABILITY_SECURITY, CAPABILITY_TESTING,
    CAPABILITY_WEB_SCRAPING, ModelCapabilityRegistry,
)
from core.model_router.capability_matcher import CapabilityMatcher, infer_capabilities, match_score
from core.model_router.free_first import (
    PRIORITY_CLOUD_FREE, PRIORITY_LOCAL_FREE, PRIORITY_PAID,
    apply_free_first_priority, boost_free_score,
)
from core.model_router.learning import ProviderLearningSystem
from core.model_router.preferences import ProviderPreferenceManager, ProviderPreferences
from core.model_router.scoring_engine import EnhancedScoringEngine
from core.model_router.statistics import ProviderStatistics, ProviderStatisticsManager

from core.model_router.providers import (
    ClaudeProvider, CloudProviderBase, DeepSeekProvider, GeminiProvider,
    KimiProvider, OllamaProvider, OpenAIProvider, OpenRouterProvider, QwenProvider,
)

from core.model_router.router import (
    EV_PROVIDER_HEALTH_CHANGED, EV_PROVIDER_REGISTERED, EV_PROVIDER_UNREGISTERED,
    EV_ROUTE_FAILED, EV_ROUTE_FALLBACK, EV_ROUTE_REQUESTED, EV_ROUTE_SELECTED,
    EV_ROUTE_STREAM_CHUNK, EV_ROUTE_STREAM_COMPLETED, EV_ROUTE_STREAM_STARTED,
    EV_ROUTE_SUCCEEDED,
)

__all__ = [
    "AutomaticFallback", "BaseModelProvider", "CapabilityMatcher",
    "ClaudeProvider", "CloudProviderBase", "CostMetadata", "DeepSeekProvider",
    "EnhancedScoringEngine", "FallbackStrategy", "GeminiProvider", "KimiProvider",
    "ModelCapabilities", "ModelCapabilityRegistry", "ModelInfo", "ModelRouter",
    "OllamaProvider", "OpenAIProvider", "OpenRouterProvider", "ProviderBenchmarkService",
    "ProviderHealth", "ProviderHealthMonitor", "ProviderInfo", "ProviderLearningSystem",
    "ProviderPreferenceManager", "ProviderPreferences", "ProviderRegistry",
    "ProviderStatistics", "ProviderStatisticsManager", "ProviderStatus", "QwenProvider",
    "RouteDecision", "RouteRequest", "RouteResult", "RoutingStrategy",
    "apply_free_first_priority", "boost_free_score", "infer_capabilities", "match_score",
    "PRIORITY_CLOUD_FREE", "PRIORITY_LOCAL_FREE", "PRIORITY_PAID",
    "CAPABILITY_ARCHITECTURE", "CAPABILITY_AUDIO", "CAPABILITY_BACKEND_DEV",
    "CAPABILITY_CODE_REVIEW", "CAPABILITY_DATA_ANALYSIS", "CAPABILITY_DATABASE",
    "CAPABILITY_DEBUGGING", "CAPABILITY_DEVOPS", "CAPABILITY_DOCUMENTATION",
    "CAPABILITY_EMBEDDINGS", "CAPABILITY_FRONTEND_DEV", "CAPABILITY_FULLSTACK_DEV",
    "CAPABILITY_GENERAL_CHAT", "CAPABILITY_IMAGE_GENERATION", "CAPABILITY_LONG_CONTEXT",
    "CAPABILITY_MACHINE_LEARNING", "CAPABILITY_MOBILE_DEV", "CAPABILITY_MULTILINGUAL",
    "CAPABILITY_PERFORMANCE", "CAPABILITY_REASONING", "CAPABILITY_SECURITY",
    "CAPABILITY_STREAMING", "CAPABILITY_TESTING", "CAPABILITY_TEXT",
    "CAPABILITY_TOOL_CALLING", "CAPABILITY_VISION", "CAPABILITY_WEB_SCRAPING",
    "EV_PROVIDER_HEALTH_CHANGED", "EV_PROVIDER_REGISTERED", "EV_PROVIDER_UNREGISTERED",
    "EV_ROUTE_FAILED", "EV_ROUTE_FALLBACK", "EV_ROUTE_REQUESTED", "EV_ROUTE_SELECTED",
    "EV_ROUTE_STREAM_CHUNK", "EV_ROUTE_STREAM_COMPLETED", "EV_ROUTE_STREAM_STARTED",
    "EV_ROUTE_SUCCEEDED",
]
