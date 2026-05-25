"""Runtime control helpers for analysis hashing, caching, and profiling.

These helpers intentionally do not alter solver equations. They only build
stable hashes from engineering inputs and measure elapsed wall-clock time around
existing expensive calls.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable, Literal, TypeVar

from pydantic import BaseModel

from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import LoadCase

AccuracyPreset = Literal["Fast", "Standard", "High Accuracy"]

ACCURACY_PRESET_RESOLUTIONS: dict[AccuracyPreset, dict[str, int]] = {
    "Fast": {"neutral_axis_angle_steps": 18, "neutral_axis_depth_steps": 30},
    "Standard": {"neutral_axis_angle_steps": 24, "neutral_axis_depth_steps": 40},
    "High Accuracy": {"neutral_axis_angle_steps": 36, "neutral_axis_depth_steps": 60},
}

_HASH_EXCLUDED_KEYS = {
    "description",
    "id",
    "label",
    "metadata",
    "note",
}

T = TypeVar("T")


@dataclass(frozen=True)
class RuntimeTiming:
    label: str
    elapsed_seconds: float


@dataclass(frozen=True)
class AnalysisRuntimeMetadata:
    input_hash: str | None = None
    accuracy_preset: AccuracyPreset = "Standard"
    status: str = "Not run"
    cache_status: str = "No cached result"
    last_run_time_seconds: float | None = None
    timings: list[RuntimeTiming] = field(default_factory=list)


def accuracy_preset_resolution(preset: str | None) -> dict[str, int]:
    if preset in ACCURACY_PRESET_RESOLUTIONS:
        return dict(ACCURACY_PRESET_RESOLUTIONS[preset])  # type: ignore[index]
    return dict(ACCURACY_PRESET_RESOLUTIONS["Standard"])


def apply_accuracy_preset_to_settings(settings: AnalysisSettings, preset: str | None) -> AnalysisSettings:
    resolution = accuracy_preset_resolution(preset)
    return settings.model_copy(update=resolution)


def _model_dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def normalize_for_hash(value: Any) -> Any:
    value = _model_dump(value)
    if isinstance(value, dict):
        return {
            str(key): normalize_for_hash(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _HASH_EXCLUDED_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [normalize_for_hash(item) for item in value]
    if isinstance(value, set):
        return [normalize_for_hash(item) for item in sorted(value, key=repr)]
    return value


def stable_hash_from_payload(payload: Any) -> str:
    normalized = normalize_for_hash(payload)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def analysis_input_hash(analysis_input: AnalysisInput, accuracy_preset: str | None = "Standard") -> str:
    return stable_hash_from_payload(
        {
            "analysis_input": analysis_input,
            "accuracy_preset": accuracy_preset or "Standard",
        }
    )


def serviceability_input_hash(
    analysis_input: AnalysisInput,
    serviceability_settings: Any,
    custom_stress_check_points: list[Any] | None = None,
    include_default_stress_check_points: bool = True,
) -> str:
    return stable_hash_from_payload(
        {
            "analysis_input": analysis_input,
            "serviceability_settings": serviceability_settings,
            "custom_stress_check_points": custom_stress_check_points or [],
            "include_default_stress_check_points": include_default_stress_check_points,
        }
    )


def demand_capacity_input_hash(
    pmm_result_hash: str | None,
    load_cases: list[LoadCase],
    strength_load_type: str = "ULS",
) -> str:
    """Hash PMM capacity identity plus active demand cases used by D/C checks."""

    active_demands = [
        {
            "name": load_case.name,
            "Pu_N": load_case.Pu_N,
            "Mux_Nmm": load_case.Mux_Nmm,
            "Muy_Nmm": load_case.Muy_Nmm,
            "load_type": load_case.load_type,
            "active": load_case.active,
        }
        for load_case in load_cases
        if load_case.active and load_case.load_type == strength_load_type
    ]
    return stable_hash_from_payload(
        {
            "pmm_result_hash": pmm_result_hash,
            "strength_load_type": strength_load_type,
            "active_demands": active_demands,
        }
    )


def recalculation_required(current_hash: str | None, cached_hash: str | None, has_cached_result: bool) -> bool:
    if not current_hash or not cached_hash or not has_cached_result:
        return True
    return current_hash != cached_hash


def cache_status_for_hash(current_hash: str | None, cached_hash: str | None, has_cached_result: bool) -> str:
    if not current_hash:
        return "Input unavailable"
    if not has_cached_result:
        return "No cached result"
    if not cached_hash:
        return "Cached result has no input hash"
    if current_hash == cached_hash:
        return "Cached result used"
    return "Input changed, recalculation required"


def timed_call(label: str, func: Callable[..., T], *args: Any, **kwargs: Any) -> tuple[T, RuntimeTiming]:
    start = perf_counter()
    result = func(*args, **kwargs)
    return result, RuntimeTiming(label=label, elapsed_seconds=perf_counter() - start)
