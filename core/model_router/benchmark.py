"""Provider Benchmark Service — periodic provider performance evaluation."""

import threading
import time
from typing import Callable, Dict, List, Optional

from core.logging import get_logger
from core.model_router.models import RouteRequest, RouteResult
from core.model_router.registry import ProviderRegistry
from core.model_router.statistics import ProviderStatisticsManager

logger = get_logger("BenchmarkService")

# Standard benchmark prompts for common task categories
BENCHMARK_PROMPTS = {
    "general_chat": "What is the capital of France? Answer in one sentence.",
    "python": "Write a Python function to compute the Fibonacci sequence.",
    "react": "Write a minimal React component that displays a counter.",
    "reasoning": "If a train travels 60km in 45 minutes, what is its average speed? Explain briefly.",
    "documentation": "Write a concise docstring for a function that parses JSON files.",
}


class ProviderBenchmarkService:
    """Periodically benchmarks providers to track performance."""
    
    def __init__(
        self,
        registry: ProviderRegistry,
        stats_manager: Optional[ProviderStatisticsManager] = None,
        interval_seconds: int = 3600,
        run_once: bool = True,
    ) -> None:
        self._registry = registry
        self._stats = stats_manager
        self._interval = max(60, int(interval_seconds))
        self._run_once = run_once
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
    
    def start(self) -> "ProviderBenchmarkService":
        """Start the background benchmark loop (idempotent)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="provider-benchmark",
                daemon=True,
            )
            self._thread.start()
            logger.info(f"Benchmark service started (interval={self._interval}s, run_once={self._run_once})")
        return self
    
    def stop(self) -> None:
        """Stop the background benchmark loop."""
        self._stop.set()
        with self._lock:
            thread = self._thread
            self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
    
    def run_benchmarks(self, categories: Optional[List[str]] = None) -> Dict[str, Dict[str, float]]:
        """Run a benchmark round against all registered providers.
        
        Args:
            categories: Optional list of task categories to benchmark.
                When omitted, all standard categories are used.
        
        Returns:
            Dict mapping provider name to benchmark results.
        """
        targets = categories or list(BENCHMARK_PROMPTS.keys())
        results: Dict[str, Dict[str, float]] = {}
        
        for provider in self._registry.all():
            name = provider.name
            provider_results = {}
            
            for category in targets:
                prompt = BENCHMARK_PROMPTS.get(category)
                if not prompt:
                    continue
                
                request = RouteRequest(
                    prompt=prompt,
                    max_tokens=100,
                    required_capabilities=[category],
                )
                
                start = time.monotonic()
                try:
                    text = provider.complete(request)
                    latency_ms = (time.monotonic() - start) * 1000
                    success = bool(text and text.strip())
                    
                    if self._stats:
                        self._stats.record_request(
                            provider_name=name,
                            success=success,
                            latency_ms=latency_ms,
                            category=category,
                        )
                    
                    provider_results[category] = {
                        "success": success,
                        "latency_ms": latency_ms,
                    }
                except Exception as exc:
                    logger.warning(f"Benchmark {name}/{category} failed: {exc}")
                    if self._stats:
                        self._stats.record_request(
                            provider_name=name,
                            success=False,
                            latency_ms=0.0,
                            category=category,
                        )
                    provider_results[category] = {
                        "success": False,
                        "error": str(exc),
                    }
            
            results[name] = provider_results
        
        return results
    
    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                logger.info("Running provider benchmark round...")
                self.run_benchmarks()
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Benchmark round failed: {exc}")
            
            if self._run_once:
                break
            self._stop.wait(self._interval)
