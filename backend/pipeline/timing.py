"""
Collects thread-safe per-stage pipeline timing metrics and provides helpers to snapshot, format, and log execution-time reports.
"""
from __future__ import annotations

import copy
import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


class TimingCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stages: Dict[str, Dict[str, Any]] = {}
        self._metadata: Dict[str, Any] = {}

    def record_stage(self, name: str, elapsed_seconds: float, **extra: Any) -> None:
        if not name:
            return
        elapsed_seconds = max(0.0, float(elapsed_seconds))
        with self._lock:
            stage = dict(self._stages.get(name) or {})
            total_seconds = float(stage.get("seconds", 0.0) or 0.0) + elapsed_seconds
            count = int(stage.get("count", 0) or 0) + 1
            stage["seconds"] = round(total_seconds, 6)
            stage["milliseconds"] = round(total_seconds * 1000.0, 3)
            stage["count"] = count
            if extra:
                stage.update(extra)
            self._stages[name] = stage

    def set_metadata(self, key: str, value: Any) -> None:
        if not key:
            return
        with self._lock:
            self._metadata[key] = value

    @contextmanager
    def stage(self, name: str, **extra: Any):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.record_stage(name, time.perf_counter() - started, **extra)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "stages": copy.deepcopy(self._stages),
                "metadata": copy.deepcopy(self._metadata),
            }


@contextmanager
def timed_stage(
    collector: Optional[TimingCollector],
    name: str,
    **extra: Any,
):
    if collector is None:
        yield
        return
    with collector.stage(name, **extra):
        yield


def format_timing_report(payload: Optional[Dict[str, Any]]) -> str:
    if not payload:
        return "no timings captured"
    stages = payload.get("stages") or {}
    if not stages:
        return "no timings captured"
    ordered = sorted(
        stages.items(),
        key=lambda item: float((item[1] or {}).get("seconds", 0.0) or 0.0),
        reverse=True,
    )
    return ", ".join(
        f"{name}={float(values.get('seconds', 0.0) or 0.0):.3f}s"
        for name, values in ordered
    )


def log_timing_report(prefix: str, collector: Optional[TimingCollector]) -> None:
    if collector is None:
        return
    logger.info("%s %s", prefix, format_timing_report(collector.snapshot()))
