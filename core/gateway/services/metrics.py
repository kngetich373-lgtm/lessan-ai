"""Metrics Service — collects and aggregates gateway usage metrics."""

from typing import Dict, List

from core.gateway.hub import GatewayHub
from core.gateway.models import GatewayMetrics
from core.logging import get_logger

logger = get_logger("MetricsService")


class MetricsService:
    """Aggregates metrics from all gateways and exposes reporting helpers."""

    def __init__(self, hub: GatewayHub) -> None:
        self._hub = hub

    def snapshot(self) -> List[GatewayMetrics]:
        return self._hub.metrics()

    def total_requests(self) -> int:
        return sum(m.total_requests for m in self._hub.metrics())

    def total_successes(self) -> int:
        return sum(m.successful_requests for m in self._hub.metrics())

    def total_failures(self) -> int:
        return sum(m.failed_requests for m in self._hub.metrics())

    def global_success_rate(self) -> float:
        total = self.total_requests()
        if total == 0:
            return 0.0
        return self.total_successes() / total

    def avg_latency_ms(self) -> float:
        metrics = self._hub.metrics()
        if not metrics:
            return 0.0
        return sum(m.avg_latency_ms for m in metrics) / len(metrics)
