"""Section-level reinforcement/prestress enable flags.

The flags introduced in REBAR.SYSTEM1 are intentionally metadata gates.  They
must not delete user-entered rebar/prestress tables; they only determine whether
ordinary rebar and prestressing steel are active for UI display and analysis
input assembly.
"""

from __future__ import annotations

from typing import Any

from concrete_pmm_pro.core.analysis import AnalysisSettings
from concrete_pmm_pro.core.models import PrestressElement, Rebar

ORDINARY_REBAR_FLAG_KEY = "section_has_ordinary_rebar"
PRESTRESSING_STEEL_FLAG_KEY = "section_has_prestressing_steel"
REINFORCEMENT_FLAGS_PRESET_KEY = "reinforcement_flags_preset_key"

# Section-level prestress rows are a generic/legacy input model.  Precast
# girder workflows use the dedicated strand-layout/debonding metadata instead,
# so PS1/PS2-style section rows must be ignored by analysis for these presets.
GIRDER_SECTION_LEVEL_PRESTRESS_IGNORED_PRESET_KEYS = frozenset(
    {
        "parametric_i_girder",
        "u_girder",
        "box_section_fillet",
        "precast_box_beam_exterior",
        "parametric_plank_girder_interior",
        "parametric_plank_girder_exterior",
        "parametric_plank_girder_voided_interior",
        "parametric_plank_girder_voided_exterior",
        "psc_i_girder",
        "single_cell_box_girder",
    }
)


def _get_value(source: Any, key: str, default: Any = None) -> Any:
    if hasattr(source, "get"):
        return source.get(key, default)
    return getattr(source, key, default)


def _to_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "y", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "n", "off", "disabled"}:
        return False
    return bool(value)


def default_section_reinforcement_flags(
    *,
    member_type: str | None,
    section_category: str | None,
    section_preset_key: str | None,
    girder_section_family: str | None = None,
) -> tuple[bool, bool]:
    """Return default ordinary-rebar and prestress flags for a selected section.

    Defaults are intentionally conservative for the two active product
    workflows.  Column/Pier/Wall/Pylon PMM starts as ordinary RC; precast
    composite girders start with prestressing enabled.  General/non-composite
    girders remain unreinforced until the engineer explicitly enables rebar or
    prestress.
    """

    member = (member_type or "").casefold()
    category = (section_category or "").casefold()
    preset = (section_preset_key or "").casefold()
    family = (girder_section_family or "").casefold()

    if member == "beam_girder":
        ordinary_rebar = False
        prestress = family == "precast_composite_girder" or category == "precast composite girder"
        # Legacy PSC I-girder is non-composite in the preset library but is still
        # a prestressed girder by intent.
        if preset == "psc_i_girder":
            prestress = True
        return ordinary_rebar, prestress

    if member == "building_beam_girder":
        # WORKFLOW.TYPE3: shared precast girder geometry can be used in the ACI
        # Building Beam/Girder workflow without enabling bridge-specific tools.
        # For Precast I-Girder, seed prestressing on because that is the usual
        # engineering intent; ordinary RC beam shapes still default to rebar only.
        if preset == "parametric_i_girder":
            return False, True
        return True, False

    return True, False




def _member_type_from_source(source: Any) -> str:
    settings = _get_value(source, "analysis_mode_settings", None)
    if settings is not None:
        if hasattr(settings, "member_type"):
            return str(getattr(settings, "member_type") or "").strip().casefold()
        if hasattr(settings, "get"):
            return str(settings.get("member_type") or "").strip().casefold()
    return str(_get_value(source, "member_type", "") or "").strip().casefold()


def section_level_prestress_ignored_for_girder(source: Any) -> bool:
    """Return True when legacy section-level prestress rows are ignored.

    Precast/simple-supported girder workflows use the dedicated strand layout and
    force-state inputs.  The old section-level tendon table may remain in saved
    projects for compatibility, but it must not be assembled into PMM/SLS
    AnalysisInput for girder presets because that can silently double-count or
    reintroduce stale PS1/PS2 reference rows.
    """

    member_type = _member_type_from_source(source)
    family = str(_get_value(source, "girder_section_family", "") or "").strip().casefold()
    category = str(_get_value(source, "section_category", "") or "").strip().casefold()
    preset = str(_get_value(source, "section_preset_key", "") or "").strip().casefold()
    bridge_dedicated_girder = (
        member_type == "beam_girder"
        and (
            family == "precast_composite_girder"
            or category == "precast composite girder"
            or preset in GIRDER_SECTION_LEVEL_PRESTRESS_IGNORED_PRESET_KEYS
        )
    )
    building_shared_prestressed_girder = member_type == "building_beam_girder" and preset == "parametric_i_girder"
    return bridge_dedicated_girder or building_shared_prestressed_girder


def ordinary_rebar_enabled(source: Any, *, default: bool = True) -> bool:
    return _to_bool(_get_value(source, ORDINARY_REBAR_FLAG_KEY, None), default)


def prestressing_steel_enabled(source: Any, *, default: bool = True) -> bool:
    return _to_bool(_get_value(source, PRESTRESSING_STEEL_FLAG_KEY, None), default)


def effective_rebars_for_analysis(
    rebars: list[Rebar],
    source: Any,
    settings: AnalysisSettings | None = None,
) -> list[Rebar]:
    if settings is not None and not settings.include_rebars:
        return []
    if not ordinary_rebar_enabled(source, default=True):
        return []
    return list(rebars)


def effective_prestress_for_analysis(
    prestress_elements: list[PrestressElement],
    source: Any,
    settings: AnalysisSettings | None = None,
) -> list[PrestressElement]:
    if settings is not None and not settings.include_prestress:
        return []
    if not prestressing_steel_enabled(source, default=True):
        return []
    if section_level_prestress_ignored_for_girder(source):
        return []
    return list(prestress_elements)


def reinforcement_system_status(source: Any) -> dict[str, bool]:
    return {
        "ordinary_rebar": ordinary_rebar_enabled(source, default=True),
        "prestressing_steel": prestressing_steel_enabled(source, default=True),
    }
