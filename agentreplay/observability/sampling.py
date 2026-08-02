"""Sampling policies for AgentReplay observability."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from agentreplay.observability.models import ObservabilityConfig, TelemetryTrace

CustomSampler = Callable[[TelemetryTrace], bool]


class TelemetrySampler:
    """Decide whether a telemetry trace should be exported."""

    def __init__(
        self,
        config: ObservabilityConfig,
        *,
        custom_sampler: CustomSampler | None = None,
    ) -> None:
        """Create a sampler from observability configuration."""
        self._config = config
        self._custom_sampler = custom_sampler

    def should_sample(self, trace: TelemetryTrace) -> bool:
        """Return whether the trace should be exported."""
        if self._config.sampling == "always_off":
            return False
        if self._config.sampling == "always_on":
            return True
        if self._config.sampling == "custom":
            return True if self._custom_sampler is None else self._custom_sampler(trace)
        if self._config.sampling == "parent_based":
            parent = trace.correlation.custom_ids.get("parent_sampled")
            if parent is not None:
                return parent.lower() in {"1", "true", "yes", "on"}
            return _ratio_sample(trace.run_id, self._config.sampling_ratio)
        return _ratio_sample(trace.run_id, self._config.sampling_ratio)


def _ratio_sample(value: str, ratio: float) -> bool:
    bounded = min(max(ratio, 0.0), 1.0)
    if bounded <= 0.0:
        return False
    if bounded >= 1.0:
        return True
    digest = hashlib.sha256(value.encode()).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return bucket <= bounded


__all__ = ["CustomSampler", "TelemetrySampler"]
