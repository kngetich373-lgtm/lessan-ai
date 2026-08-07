"""Provider Statistics — tracking and persistence of provider performance."""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from core.logging import get_logger

logger = get_logger("ProviderStatistics")

DEFAULT_STATS_FILE = Path.home() / ".local" / "share" / "lessan" / "provider_stats.json"


@dataclass
class TaskCategoryStats:
    """Statistics for a specific task category."""
    
    category: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_latency_ms: float = 0.0
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests
    
    def as_dict(self) -> Dict:
        return {
            "category": self.category,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "average_latency_ms": self.average_latency_ms,
            "success_rate": self.success_rate,
        }


@dataclass
class ProviderStatistics:
    """Comprehensive statistics for a single provider."""
    
    provider_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_latency_ms: float = 0.0
    average_response_quality: float = 0.0
    task_categories: Dict[str, TaskCategoryStats] = field(default_factory=dict)
    first_seen: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    
    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests
    
    def record_request(
        self, success: bool, latency_ms: float,
        category: Optional[str] = None, quality_score: Optional[float] = None,
    ) -> None:
        """Record a single request outcome."""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
        
        self.average_latency_ms = (
            (self.average_latency_ms * (self.total_requests - 1) + latency_ms)
            / self.total_requests
        )
        
        if quality_score is not None:
            self.average_response_quality = (
                (self.average_response_quality * (self.total_requests - 1) + quality_score)
                / self.total_requests
            )
        
        if category:
            if category not in self.task_categories:
                self.task_categories[category] = TaskCategoryStats(category=category)
            cat_stats = self.task_categories[category]
            cat_stats.total_requests += 1
            if success:
                cat_stats.successful_requests += 1
            else:
                cat_stats.failed_requests += 1
            cat_stats.average_latency_ms = (
                (cat_stats.average_latency_ms * (cat_stats.total_requests - 1) + latency_ms)
                / cat_stats.total_requests
            )
        self.last_updated = datetime.now()
    
    def get_category_success_rate(self, category: str) -> float:
        if category in self.task_categories:
            return self.task_categories[category].success_rate
        return self.success_rate
    
    def as_dict(self) -> Dict:
        return {
            "provider_name": self.provider_name,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "average_latency_ms": self.average_latency_ms,
            "average_response_quality": self.average_response_quality,
            "success_rate": self.success_rate,
            "task_categories": {cat: stats.as_dict() for cat, stats in self.task_categories.items()},
            "first_seen": self.first_seen.isoformat(),
            "last_updated": self.last_updated.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ProviderStatistics":
        task_categories = {
            cat: TaskCategoryStats(
                category=cat_data["category"],
                total_requests=cat_data["total_requests"],
                successful_requests=cat_data["successful_requests"],
                failed_requests=cat_data["failed_requests"],
                average_latency_ms=cat_data["average_latency_ms"],
            )
            for cat, cat_data in data.get("task_categories", {}).items()
        }
        return cls(
            provider_name=data["provider_name"],
            total_requests=data.get("total_requests", 0),
            successful_requests=data.get("successful_requests", 0),
            failed_requests=data.get("failed_requests", 0),
            average_latency_ms=data.get("average_latency_ms", 0.0),
            average_response_quality=data.get("average_response_quality", 0.0),
            task_categories=task_categories,
            first_seen=datetime.fromisoformat(data.get("first_seen", datetime.now().isoformat())),
            last_updated=datetime.fromisoformat(data.get("last_updated", datetime.now().isoformat())),
        )


class ProviderStatisticsManager:
    """Manages statistics for all registered providers."""
    
    def __init__(self, storage_path: Optional[Path] = None) -> None:
        # Accept either Path or str for convenience.
        if isinstance(storage_path, str):
            storage_path = Path(storage_path)
        self._storage_path = storage_path or DEFAULT_STATS_FILE
        self._stats: Dict[str, ProviderStatistics] = {}
        self._lock = threading.RLock()
        self._load()
    
    def record_request(
        self, provider_name: str, success: bool, latency_ms: float,
        category: Optional[str] = None, quality_score: Optional[float] = None,
    ) -> None:
        """Record a request outcome for a provider."""
        with self._lock:
            if provider_name not in self._stats:
                self._stats[provider_name] = ProviderStatistics(provider_name=provider_name)
            self._stats[provider_name].record_request(success, latency_ms, category, quality_score)
            if self._stats[provider_name].total_requests % 10 == 0:
                self._save()
    
    def get_stats(self, provider_name: str) -> Optional[ProviderStatistics]:
        with self._lock:
            return self._stats.get(provider_name)
    
    def get_all_stats(self) -> Dict[str, ProviderStatistics]:
        with self._lock:
            return dict(self._stats)
    
    def get_success_rate(self, provider_name: str, category: Optional[str] = None) -> float:
        stats = self.get_stats(provider_name)
        if stats is None:
            return 0.5
        return stats.get_category_success_rate(category) if category else stats.success_rate
    
    def get_average_latency(self, provider_name: str) -> float:
        stats = self.get_stats(provider_name)
        return stats.average_latency_ms if stats else 0.0
    
    def clear_stats(self, provider_name: Optional[str] = None) -> None:
        with self._lock:
            if provider_name:
                self._stats.pop(provider_name, None)
            else:
                self._stats.clear()
            self._save()
    
    def save(self) -> None:
        with self._lock:
            self._save()
    
    def _load(self) -> None:
        if not self._storage_path.exists():
            logger.info(f"No statistics file found, starting fresh")
            return
        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for provider_name, provider_data in data.items():
                self._stats[provider_name] = ProviderStatistics.from_dict(provider_data)
            logger.info(f"Loaded statistics for {len(self._stats)} providers")
        except Exception as exc:
            logger.warning(f"Failed to load statistics: {exc}")
    
    def _save(self) -> None:
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {name: stats.as_dict() for name, stats in self._stats.items()}
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved statistics for {len(self._stats)} providers")
        except Exception as exc:
            logger.error(f"Failed to save statistics: {exc}")

