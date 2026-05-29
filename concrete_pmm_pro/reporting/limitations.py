"""Engineering limitations registry for pre-report QA."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from concrete_pmm_pro.core.analysis import AnalysisModeSettings


@dataclass(frozen=True)
class EngineeringLimitation:
    key: str
    title: str
    status: str
    risk_level: str
    category: str
    user_note: str
    engineering_note: str
    recommended_action: str | None = None


def get_engineering_limitations() -> list[EngineeringLimitation]:
    return [
        EngineeringLimitation(
            "ixy_coupling_sls",
            "Ixy coupling in service stress",
            "SIMPLIFIED",
            "HIGH",
            "SLS",
            "Service stress checks use an uncoupled Ix/Iy formula.",
            "Unsymmetric bending with significant Ixy is not fully represented in current SLS stress checks.",
            "Review unsymmetric sections independently.",
        ),
        EngineeringLimitation(
            "dc_directional_slice_envelope",
            "Directional D/C method",
            "PROTOTYPE",
            "HIGH",
            "PMM",
            "ULS D/C uses directional slice/envelope interpolation.",
            "This is not a fully validated PMM surface-containment check for all section shapes.",
            "Independently verify irregular or non-symmetric sections.",
        ),
        EngineeringLimitation(
            "convex_hull_slice_envelope",
            "Convex hull fallback for PMM slice envelope",
            "PROTOTYPE",
            "CRITICAL",
            "PMM",
            "Convex hull fallback may overestimate PMM capacity for non-convex interaction shapes.",
            "Convex hulls can enclose regions that are not actually available capacity.",
            "Treat D/C as approximate whenever convex hull fallback is used.",
        ),
        EngineeringLimitation(
            "neutral_axis_sweep_resolution",
            "Neutral-axis sweep resolution",
            "SIMPLIFIED",
            "MEDIUM",
            "PMM",
            "Neutral-axis depth sweep may be sparse in sensitive regions.",
            "Balanced and tension-controlled transition regions may need adaptive/log refinement in future work.",
            "Review sensitive cases and increase analysis steps where practical.",
        ),
        EngineeringLimitation(
            "cracked_section_sls",
            "Cracked section SLS",
            "FUTURE_WORK",
            "HIGH",
            "SLS",
            "Current transformed section stress check is uncracked only.",
            "Cracked stress redistribution and cracked transformed neutral-axis iteration are not implemented.",
            "Use independent cracked-section checks where required.",
        ),
        EngineeringLimitation(
            "prestress_axial_cap",
            "Prestress-aware axial cap",
            "SIMPLIFIED",
            "HIGH",
            "Prestress",
            "ACI axial cap uses the QA.PO1-validated prestress-aware Po helper including ordinary rebar and bonded prestress steel.",
            "Bonded prestress uses fpy or 0.90 fpu as the nominal strength reference; unbonded prestress is excluded from the axial-cap helper by solver policy.",
            "Review code-specific axial-compression limits and project-specific detailing before final design.",
        ),
        EngineeringLimitation(
            "prestress_compression_reversal",
            "Prestress compression reversal",
            "SIMPLIFIED",
            "MEDIUM",
            "Prestress",
            "Prestress compression reversal is not fully modeled.",
            "Negative total tensile strain is clamped to zero; this should not be assumed to be universally conservative.",
            "Review cases where tendons may enter compression.",
        ),
        EngineeringLimitation(
            "unbonded_prestress",
            "Unbonded prestress",
            "IGNORED_WITH_WARNING",
            "HIGH",
            "Prestress",
            "Unbonded prestress can be entered but is ignored by current PMM/SLS solvers.",
            "A separate unbonded prestress model is future work.",
            "Do not rely on current results for unbonded prestress contribution.",
        ),
        EngineeringLimitation(
            "crack_width_check",
            "Crack width check",
            "FUTURE_WORK",
            "MEDIUM",
            "SLS",
            "Crack width calculation is not implemented.",
            "Cracking classification is based on selected stress points only.",
            "Use independent crack-width checks where required.",
        ),
        EngineeringLimitation(
            "beam_girder_shear_torsion",
            "Beam/Girder shear and torsion",
            "FUTURE_WORK",
            "MEDIUM",
            "Beam/Girder",
            "Beam/girder flexure, shear, torsion, transfer-stage, deflection, and camber checks are not implemented.",
            "Beam/Girder mode is a future workflow placeholder.",
            "Use dedicated beam/girder design checks outside this prototype.",
        ),
        EngineeringLimitation(
            "lightweight_concrete_ec",
            "Lightweight concrete Ec",
            "SIMPLIFIED",
            "MEDIUM",
            "SLS",
            "Normal-weight ACI Ec formula is used unless future methods are implemented.",
            "Density may not affect Ec when method is aci_normal_weight; lightweight concrete Ec may be overestimated.",
            "Review Ec for lightweight concrete independently.",
        ),
        EngineeringLimitation(
            "ultimate_concrete_strain_ecu",
            "Ultimate concrete strain ecu",
            "SIMPLIFIED",
            "MEDIUM",
            "PMM",
            "Default ecu = 0.003 is ACI/AASHTO-style.",
            "Eurocode/DRT or project-specific workflows may require a different ultimate concrete strain.",
            "Review ecu and code basis for non-ACI/AASHTO workflows.",
        ),
    ]


def engineering_limitations_to_dataframe(limitations: list[EngineeringLimitation]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Key": item.key,
                "Title": item.title,
                "Status": item.status,
                "Risk Level": item.risk_level,
                "Category": item.category,
                "User Note": item.user_note,
                "Engineering Note": item.engineering_note,
                "Recommended Action": item.recommended_action or "",
            }
            for item in limitations
        ],
        columns=[
            "Key",
            "Title",
            "Status",
            "Risk Level",
            "Category",
            "User Note",
            "Engineering Note",
            "Recommended Action",
        ],
    )


def _get(mapping: Any, key: str, default: Any = None) -> Any:
    if mapping is None:
        return default
    if hasattr(mapping, "get"):
        try:
            return mapping.get(key, default)
        except (AttributeError, TypeError, ValueError):
            return default
    return getattr(mapping, key, default)


def _is_truthy_context_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, bytes)):
        return bool(value)
    if isinstance(value, (int, float)):
        return value != 0
    for attr in ("empty",):
        marker = getattr(value, attr, None)
        if isinstance(marker, bool):
            return not marker
    try:
        return bool(value)
    except (TypeError, ValueError):
        return False


def _has_key_or_truthy(session_state: Any, keys: list[str]) -> bool:
    for key in keys:
        value = _get(session_state, key, None)
        if _is_truthy_context_value(value):
            return True
    return False


def _detect_member_type(session_state: Any) -> str | None:
    mode = _get(session_state, "analysis_mode_settings")
    if isinstance(mode, AnalysisModeSettings):
        return mode.member_type
    if isinstance(mode, dict):
        return mode.get("member_type")
    member_type = getattr(mode, "member_type", None)
    return str(member_type) if member_type else None


def _detect_pmm_presence(session_state: Any) -> bool:
    return _has_key_or_truthy(
        session_state,
        ["rc_pmm_result", "pmm_result", "rc_demand_capacity_result", "dc_summary", "demand_capacity_summary"],
    )


def _detect_sls_presence(session_state: Any) -> bool:
    return _has_key_or_truthy(session_state, ["serviceability_summary", "crack_classification_summary"])


def _detect_prestress_presence(session_state: Any) -> bool:
    prestress_elements = _get(session_state, "prestress_elements", None)
    if _is_truthy_context_value(prestress_elements):
        return True
    prestress_check = _get(session_state, "prestress_check_summary", None)
    if prestress_check is not None:
        for attr in ("bonded_count", "unbonded_count", "total_area_mm2", "total_pe_eff_N"):
            value = getattr(prestress_check, attr, None)
            if value:
                return True
    for key in ("result_traceability_snapshot", "pre_report_snapshot", "traceability_snapshot", "project"):
        candidate = _get(session_state, key, None)
        if candidate is not None and getattr(candidate, "prestress_count", 0):
            return True
    if _get(session_state, "prestress_count", 0):
        return True
    return False


def deduplicate_limitations_by_key(limitations: list[EngineeringLimitation]) -> list[EngineeringLimitation]:
    """Remove duplicate limitations by key while preserving first occurrence."""

    seen: set[str] = set()
    unique: list[EngineeringLimitation] = []
    for limitation in limitations:
        if limitation.key in seen:
            continue
        seen.add(limitation.key)
        unique.append(limitation)
    return unique


def collect_limitations_for_report(session_state: Any = None, include_all: bool = True) -> list[EngineeringLimitation]:
    """Return limitations for report-readiness review.

    The filtered path still always retains every HIGH and CRITICAL limitation
    so report-oriented filtering cannot silently hide severe engineering risks.
    """

    limitations = get_engineering_limitations()
    if include_all:
        return limitations

    selected = [item for item in limitations if item.risk_level in {"HIGH", "CRITICAL"}]
    relevant_keys: set[str] = set()
    if _detect_pmm_presence(session_state):
        relevant_keys.add("neutral_axis_sweep_resolution")
        relevant_keys.add("ultimate_concrete_strain_ecu")
    if _detect_prestress_presence(session_state):
        relevant_keys.add("prestress_compression_reversal")
    if _detect_sls_presence(session_state):
        relevant_keys.add("crack_width_check")
        relevant_keys.add("lightweight_concrete_ec")
    if _detect_member_type(session_state) == "beam_girder":
        relevant_keys.add("beam_girder_shear_torsion")
    selected.extend(item for item in limitations if item.key in relevant_keys)
    return deduplicate_limitations_by_key(selected)
