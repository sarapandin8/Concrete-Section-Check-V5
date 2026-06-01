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

    return True, False


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
    return list(prestress_elements)


def reinforcement_system_status(source: Any) -> dict[str, bool]:
    return {
        "ordinary_rebar": ordinary_rebar_enabled(source, default=True),
        "prestressing_steel": prestressing_steel_enabled(source, default=True),
    }
