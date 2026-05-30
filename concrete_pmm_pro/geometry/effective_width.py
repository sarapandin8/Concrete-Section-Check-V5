"""Effective slab-width helper for Beam/Girder composite metadata.

AASHTO.BE1 is intentionally a conservative helper, not a full bridge-design
engine.  It computes a transparent preliminary effective deck/topping width for
composite transformed-section display while preserving manual override and
leaving all solver/report logic unchanged.

The helper keeps every candidate limit visible so engineers can review the
controlling assumption before the value is used in later SLS milestones.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

BeamPosition = Literal["interior", "exterior"]


@dataclass(frozen=True)
class EffectiveWidthCandidate:
    """One effective-width candidate limit in mm."""

    label: str
    value_mm: float
    note: str = ""


@dataclass(frozen=True)
class EffectiveWidthInput:
    """Input metadata for preliminary AASHTO-style effective slab width.

    Parameters use mm.  ``top_width_mm`` is the physical width of the precast top
    flange/plank top.  ``girder_spacing_mm`` is center-to-center spacing for an
    interior girder or spacing to the adjacent interior girder for an exterior
    girder.  ``deck_overhang_mm`` is only used for exterior girders.
    """

    span_length_mm: float
    slab_thickness_mm: float
    girder_spacing_mm: float
    top_width_mm: float
    position: BeamPosition = "interior"
    deck_overhang_mm: float = 0.0


@dataclass(frozen=True)
class EffectiveWidthResult:
    """Calculated preliminary effective slab width."""

    effective_width_mm: float
    governing_limit: str
    candidates: tuple[EffectiveWidthCandidate, ...]
    position: BeamPosition
    method: str = "AASHTO-style helper"
    warnings: tuple[str, ...] = ()

    @property
    def governing_candidate(self) -> EffectiveWidthCandidate:
        for candidate in self.candidates:
            if candidate.label == self.governing_limit:
                return candidate
        return min(self.candidates, key=lambda item: item.value_mm)


def _finite_positive(value: float) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0.0


def _require_positive(label: str, value: float) -> float:
    if not _finite_positive(value):
        raise ValueError(f"{label} must be a positive finite value.")
    return float(value)


def _require_non_negative(label: str, value: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite non-negative value.") from exc
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be a finite non-negative value.")
    return number


def calculate_aashto_effective_slab_width(data: EffectiveWidthInput) -> EffectiveWidthResult:
    """Return a transparent preliminary effective slab width in mm.

    The helper uses common bridge-girder/T-beam effective-width limits in a
    deliberately conservative form:

    * interior: min(span/4, girder spacing, top width + 16*slab thickness)
    * exterior: min(span/4, tributary width to edge/adjacent girder,
      top width + limited interior-side slab + limited exterior overhang)

    The result is intended for SECTION.COMPOSITE/AASHTO.BE metadata display and
    validation only.  It does not certify a final design-code check and must not
    change PMM, prestress, or report calculations.
    """

    span = _require_positive("span_length_mm", data.span_length_mm)
    tslab = _require_positive("slab_thickness_mm", data.slab_thickness_mm)
    spacing = _require_positive("girder_spacing_mm", data.girder_spacing_mm)
    top_width = _require_positive("top_width_mm", data.top_width_mm)
    overhang = _require_non_negative("deck_overhang_mm", data.deck_overhang_mm)
    position = data.position if data.position in {"interior", "exterior"} else "interior"

    warnings: list[str] = []
    if spacing < top_width:
        warnings.append("Girder spacing is smaller than top flange/plank width; review spacing input.")
    if position == "exterior" and overhang <= 0.0:
        warnings.append("Exterior girder overhang is zero; effective width will be conservative.")

    if position == "interior":
        candidates = (
            EffectiveWidthCandidate("L/4", span / 4.0, "Span-based global limit"),
            EffectiveWidthCandidate("Girder spacing S", spacing, "Tributary width to adjacent girders"),
            EffectiveWidthCandidate(
                "Top width + 16Tslab",
                top_width + 16.0 * tslab,
                "Flange-width style local slab participation limit",
            ),
        )
    else:
        half_clear_to_adjacent = max((spacing - top_width) / 2.0, 0.0)
        interior_side = min(half_clear_to_adjacent, 8.0 * tslab)
        exterior_side = min(overhang, 8.0 * tslab)
        side_limited_total = top_width + interior_side + exterior_side
        tributary_width = spacing / 2.0 + overhang
        candidates = (
            EffectiveWidthCandidate("L/4", span / 4.0, "Span-based global limit"),
            EffectiveWidthCandidate("Exterior tributary width", tributary_width, "Half spacing plus deck overhang"),
            EffectiveWidthCandidate(
                "Top width + side limits",
                side_limited_total,
                "Top width plus limited interior-side slab and exterior overhang",
            ),
        )

    controlling = min(candidates, key=lambda item: item.value_mm)
    return EffectiveWidthResult(
        effective_width_mm=float(controlling.value_mm),
        governing_limit=controlling.label,
        candidates=candidates,
        position=position,
        warnings=tuple(warnings),
    )
