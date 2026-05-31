"""Beam/Girder service-stress code-limit preview helpers.

CODE.SLS.LIMIT2 keeps this as an editable preview framework while making
stage meaning explicit.  The helpers are intentionally pure Python so the UI,
validation suite, and future reports can all use the same stage-aware profile
metadata without changing stress or solver logic.

Important scope guard:
- This module does not generate loads or stages.
- This module does not calculate prestress losses.
- This module does not change PMM, prestress, rebar, report, or geometry logic.
- Default profiles are editable preview profiles and must be verified against
  the governing project specification and code edition before final design.

Stress convention:
- compression stress is negative
- tension stress is positive
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, TypeAlias

GirderSLSCode = Literal["AASHTO LRFD Bridge", "ACI 318"]
GirderSLSStage: TypeAlias = str
TensionLimitMode = Literal["No tension", "sqrt(fc) ratio", "User-defined"]
StressLimitStatus = Literal["PASS", "FAIL", "NOT_CHECKED"]

STAGE_TRANSFER = "Transfer / Release"
STAGE_DECK_CASTING = "Deck casting / Pre-composite"
STAGE_FINAL_SERVICE = "Final service / Composite"
STAGE_USER_DEFINED = "User-defined"

_LEGACY_STAGE_ALIASES: dict[str, str] = {
    "Transfer": STAGE_TRANSFER,
    "Release": STAGE_TRANSFER,
    "Service / Final": STAGE_FINAL_SERVICE,
    "Final service": STAGE_FINAL_SERVICE,
    "Composite service": STAGE_FINAL_SERVICE,
}

DEFAULT_GIRDER_SLS_CODES: tuple[GirderSLSCode, ...] = ("AASHTO LRFD Bridge", "ACI 318")
DEFAULT_GIRDER_SLS_STAGES: tuple[str, ...] = (
    STAGE_TRANSFER,
    STAGE_DECK_CASTING,
    STAGE_FINAL_SERVICE,
    STAGE_USER_DEFINED,
)
DEFAULT_TENSION_LIMIT_MODES: tuple[TensionLimitMode, ...] = ("No tension", "sqrt(fc) ratio", "User-defined")


@dataclass(frozen=True)
class GirderServiceStressLimitProfile:
    """Concrete service-stress limit profile for one Beam/Girder preview check."""

    code: GirderSLSCode
    stage: str
    compression_limit_ratio: float
    tension_limit_mode: TensionLimitMode
    tension_sqrt_fc_ratio: float = 0.0
    tension_limit_MPa: float = 0.0
    stress_zero_tolerance_MPa: float = 5.0e-4
    clause_note: str = ""
    limitation_note: str = ""
    concrete_strength_label: str = "f'c"
    prestress_force_basis: str = "Pe_eff after losses"
    recommended_section_basis: str = "Engineer-selected"
    stage_guidance: str = ""

    def compression_limit_MPa(self, fc_MPa: float) -> float:
        _require_positive("fc_MPa", fc_MPa)
        _require_positive("compression_limit_ratio", self.compression_limit_ratio)
        return float(self.compression_limit_ratio) * float(fc_MPa)

    def tension_allowable_MPa(self, fc_MPa: float) -> float:
        _require_positive("fc_MPa", fc_MPa)
        if self.tension_limit_mode == "No tension":
            return 0.0
        if self.tension_limit_mode == "User-defined":
            if float(self.tension_limit_MPa) < 0.0:
                raise ValueError("tension_limit_MPa must not be negative.")
            return float(self.tension_limit_MPa)
        if float(self.tension_sqrt_fc_ratio) < 0.0:
            raise ValueError("tension_sqrt_fc_ratio must not be negative.")
        return float(self.tension_sqrt_fc_ratio) * math.sqrt(float(fc_MPa))


@dataclass(frozen=True)
class GirderStressLimitPointResult:
    """Limit-check result for one reported fiber stress."""

    fiber: str
    stress_MPa: float
    stress_type: str
    compression_limit_MPa: float
    tension_limit_MPa: float
    utilization: float | None
    status: StressLimitStatus
    message: str


@dataclass(frozen=True)
class GirderServiceStressLimitCheckResult:
    """Limit-check result for one Beam/Girder stress preview case."""

    profile: GirderServiceStressLimitProfile
    fc_MPa: float
    points: tuple[GirderStressLimitPointResult, ...]
    overall_status: StressLimitStatus
    warnings: tuple[str, ...] = ()

    @property
    def max_utilization(self) -> float | None:
        values = [point.utilization for point in self.points if point.utilization is not None]
        return max(values) if values else None

    @property
    def failed_count(self) -> int:
        return sum(1 for point in self.points if point.status == "FAIL")




@dataclass(frozen=True)
class GirderStressLimitFormulaSummary:
    """Readable formula text for one editable stress-limit profile.

    Formula text is deliberately kept as preview metadata so UI, validation,
    and future reports can show how a displayed limit was produced without
    turning this milestone into a final code-clause engine.
    """

    compression_formula: str
    compression_substitution: str
    compression_limit_MPa: float
    tension_formula: str
    tension_substitution: str
    tension_limit_MPa: float
    strength_label: str
    profile_note: str


@dataclass(frozen=True)
class StressLimitInputRow:
    """Simple stress row accepted by the pure limit checker."""

    fiber: str
    stress_MPa: float


def _require_positive(name: str, value: float) -> None:
    if not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be a positive finite value.")


def _require_finite(name: str, value: float) -> None:
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite.")


def normalize_girder_sls_stage(stage: str | None) -> str:
    """Normalize legacy CODE.SLS.LIMIT1 labels into stage-aware labels."""

    raw = str(stage or "").strip()
    if not raw:
        return STAGE_FINAL_SERVICE
    return _LEGACY_STAGE_ALIASES.get(raw, raw)


def girder_sls_stage_metadata(stage: str) -> dict[str, str]:
    """Return stage-aware display metadata used by UI and validation."""

    stage = normalize_girder_sls_stage(stage)
    if stage == STAGE_TRANSFER:
        return {
            "concrete_strength_label": "f'ci at transfer / release",
            "prestress_force_basis": "Pe_transfer / initial effective force before long-term losses",
            "recommended_section_basis": "Precast gross section",
            "stage_guidance": "Use concrete strength and prestress force applicable at release. Long-term losses are not calculated in this preview.",
        }
    if stage == STAGE_DECK_CASTING:
        return {
            "concrete_strength_label": "f'c at deck-casting stage",
            "prestress_force_basis": "Pe at deck-casting stage, user-defined",
            "recommended_section_basis": "Precast gross section",
            "stage_guidance": "Wet deck/topping weight usually acts before composite action; use precast gross basis unless the project stage model says otherwise.",
        }
    if stage == STAGE_FINAL_SERVICE:
        return {
            "concrete_strength_label": "f'c at service",
            "prestress_force_basis": "Pe_eff after losses",
            "recommended_section_basis": "Staged combination; post-composite SDL/LL+IM use composite transformed basis",
            "stage_guidance": "Final service stress should be assembled from staged effects. This preview checks the stresses currently supplied to it; it does not auto-sum staged loads or losses.",
        }
    return {
        "concrete_strength_label": "f'c for selected user-defined stage",
        "prestress_force_basis": "User-defined prestress force basis",
        "recommended_section_basis": "Engineer-selected",
        "stage_guidance": "User-defined preview stage. Confirm strength, section basis, and prestress force state before final design.",
    }


def default_girder_sls_limit_profile(
    code: GirderSLSCode = "AASHTO LRFD Bridge",
    stage: GirderSLSStage = STAGE_FINAL_SERVICE,
) -> GirderServiceStressLimitProfile:
    """Return an editable default profile for one code/stage combination.

    The values remain conservative preview defaults, not final locked clauses.
    Stage metadata makes it harder to accidentally use final f'c for transfer
    or Pe_eff-after-losses for release-stage checking.
    """

    if code not in DEFAULT_GIRDER_SLS_CODES:
        raise ValueError(f"Unsupported girder SLS code profile: {code!r}")
    stage = normalize_girder_sls_stage(stage)
    if stage not in DEFAULT_GIRDER_SLS_STAGES:
        raise ValueError(f"Unsupported girder SLS stage: {stage!r}")

    meta = girder_sls_stage_metadata(stage)
    base_note = (
        "Editable preview profile only. Confirm code edition, authority/project specifications, prestress class, "
        "reinforcement/cracking assumptions, concrete strength at stage, and prestress-force state before final design."
    )
    code_note = (
        "AASHTO bridge-girder preview defaults are intentionally separated from ACI building/member preview defaults."
        if code == "AASHTO LRFD Bridge"
        else "ACI prestressed-member preview defaults are intentionally separated from AASHTO bridge defaults."
    )
    common = dict(
        code=code,
        stage=stage,
        concrete_strength_label=meta["concrete_strength_label"],
        prestress_force_basis=meta["prestress_force_basis"],
        recommended_section_basis=meta["recommended_section_basis"],
        stage_guidance=meta["stage_guidance"],
        limitation_note=f"{base_note} {code_note}",
    )

    # Preview defaults are code-profile-specific but still engineer-editable.
    # They are not a final locked clause-selection engine.  Transfer values are
    # intentionally similar because many prestressed-code checks use comparable
    # release-stage compression/tension concepts; final-service tension defaults
    # are separated so AASHTO/ACI do not appear identical in the UI.
    if code == "AASHTO LRFD Bridge":
        transfer_comp, transfer_tension = 0.60, 0.25
        deck_comp, deck_tension = 0.55, 0.25
        final_comp, final_tension = 0.45, 0.19
        family_note = "AASHTO LRFD Bridge editable preview profile"
    else:
        transfer_comp, transfer_tension = 0.60, 0.25
        deck_comp, deck_tension = 0.55, 0.25
        final_comp, final_tension = 0.45, 0.50
        family_note = "ACI 318 editable prestressed-member preview profile"

    if stage == STAGE_TRANSFER:
        return GirderServiceStressLimitProfile(
            **common,
            compression_limit_ratio=transfer_comp,
            tension_limit_mode="sqrt(fc) ratio",
            tension_sqrt_fc_ratio=transfer_tension,
            clause_note=f"{family_note}: transfer/release stage. Use f'ci and transfer-stage prestress force.",
        )
    if stage == STAGE_DECK_CASTING:
        return GirderServiceStressLimitProfile(
            **common,
            compression_limit_ratio=deck_comp,
            tension_limit_mode="sqrt(fc) ratio",
            tension_sqrt_fc_ratio=deck_tension,
            clause_note=f"{family_note}: deck-casting/pre-composite stage. Wet deck generally acts on precast gross section.",
        )
    if stage == STAGE_FINAL_SERVICE:
        return GirderServiceStressLimitProfile(
            **common,
            compression_limit_ratio=final_comp,
            tension_limit_mode="sqrt(fc) ratio",
            tension_sqrt_fc_ratio=final_tension,
            clause_note=f"{family_note}: final-service stage. Use service strength and effective prestress after losses.",
        )
    return GirderServiceStressLimitProfile(
        **common,
        compression_limit_ratio=0.45,
        tension_limit_mode="User-defined",
        tension_limit_MPa=0.0,
        clause_note=f"{code} user-defined editable stress profile.",
    )


def build_girder_sls_limit_profile(
    *,
    code: GirderSLSCode,
    stage: GirderSLSStage,
    compression_limit_ratio: float | None = None,
    tension_limit_mode: TensionLimitMode | None = None,
    tension_sqrt_fc_ratio: float | None = None,
    tension_limit_MPa: float | None = None,
    stress_zero_tolerance_MPa: float | None = None,
) -> GirderServiceStressLimitProfile:
    """Build a profile from defaults plus optional user overrides."""

    base = default_girder_sls_limit_profile(code, stage)
    profile = GirderServiceStressLimitProfile(
        code=base.code,
        stage=base.stage,
        compression_limit_ratio=float(base.compression_limit_ratio if compression_limit_ratio is None else compression_limit_ratio),
        tension_limit_mode=base.tension_limit_mode if tension_limit_mode is None else tension_limit_mode,
        tension_sqrt_fc_ratio=float(base.tension_sqrt_fc_ratio if tension_sqrt_fc_ratio is None else tension_sqrt_fc_ratio),
        tension_limit_MPa=float(base.tension_limit_MPa if tension_limit_MPa is None else tension_limit_MPa),
        stress_zero_tolerance_MPa=float(base.stress_zero_tolerance_MPa if stress_zero_tolerance_MPa is None else stress_zero_tolerance_MPa),
        clause_note=base.clause_note,
        limitation_note=base.limitation_note,
        concrete_strength_label=base.concrete_strength_label,
        prestress_force_basis=base.prestress_force_basis,
        recommended_section_basis=base.recommended_section_basis,
        stage_guidance=base.stage_guidance,
    )
    _require_positive("compression_limit_ratio", profile.compression_limit_ratio)
    if profile.tension_limit_mode == "sqrt(fc) ratio" and profile.tension_sqrt_fc_ratio < 0.0:
        raise ValueError("tension_sqrt_fc_ratio must not be negative.")
    if profile.tension_limit_mode == "User-defined" and profile.tension_limit_MPa < 0.0:
        raise ValueError("tension_limit_MPa must not be negative.")
    if profile.stress_zero_tolerance_MPa < 0.0:
        raise ValueError("stress_zero_tolerance_MPa must not be negative.")
    return profile


def girder_sls_limit_formula_summary(
    *,
    profile: GirderServiceStressLimitProfile,
    fc_MPa: float,
) -> GirderStressLimitFormulaSummary:
    """Return formula strings for the displayed compression/tension limits."""

    _require_positive("fc_MPa", fc_MPa)
    strength_label = profile.concrete_strength_label or "f'c"
    compression_limit = profile.compression_limit_MPa(fc_MPa)
    compression_formula = f"f_c,allow = {profile.compression_limit_ratio:.3f} × {strength_label}"
    compression_substitution = f"{profile.compression_limit_ratio:.3f} × {float(fc_MPa):.3f} = {compression_limit:.3f} MPa"

    tension_limit = profile.tension_allowable_MPa(fc_MPa)
    if profile.tension_limit_mode == "No tension":
        tension_formula = "f_t,allow = 0.000 MPa (no tension)"
        tension_substitution = "No positive tensile stress is permitted in this preview profile."
    elif profile.tension_limit_mode == "User-defined":
        tension_formula = "f_t,allow = user-defined tension limit"
        tension_substitution = f"{tension_limit:.3f} MPa"
    else:
        tension_formula = f"f_t,allow = {profile.tension_sqrt_fc_ratio:.3f} × √({strength_label})"
        tension_substitution = f"{profile.tension_sqrt_fc_ratio:.3f} × √{float(fc_MPa):.3f} = {tension_limit:.3f} MPa"

    return GirderStressLimitFormulaSummary(
        compression_formula=compression_formula,
        compression_substitution=compression_substitution,
        compression_limit_MPa=compression_limit,
        tension_formula=tension_formula,
        tension_substitution=tension_substitution,
        tension_limit_MPa=tension_limit,
        strength_label=strength_label,
        profile_note=f"{profile.code} · {profile.stage} · editable preview formula",
    )


def girder_sls_stage_basis_consistency_warnings(
    *,
    profile_stage: str,
    section_basis_label: str | None = None,
    load_stage: str | None = None,
    load_component: str | None = None,
) -> tuple[str, ...]:
    """Return engineering warnings for inconsistent stage/load/basis selections.

    These are guidance warnings only.  They do not change stress values or
    pass/fail calculations, but they prevent a preview result from appearing
    more authoritative than its stage/load context supports.
    """

    warnings: list[str] = []
    stage = normalize_girder_sls_stage(profile_stage)
    basis = str(section_basis_label or "").strip().casefold()
    row_stage_text = str(load_stage or "").strip()
    row_stage_cf = row_stage_text.casefold()
    component_text = str(load_component or "").strip()
    component_cf = component_text.casefold()

    def row_stage_family() -> str | None:
        if not row_stage_cf:
            return None
        if "transfer" in row_stage_cf or "release" in row_stage_cf:
            return STAGE_TRANSFER
        if "deck" in row_stage_cf or "pre-composite" in row_stage_cf or "pre composite" in row_stage_cf:
            return STAGE_DECK_CASTING
        if "final" in row_stage_cf or "service" in row_stage_cf or "composite" in row_stage_cf:
            return STAGE_FINAL_SERVICE
        return None

    load_family = row_stage_family()
    if load_family is not None and stage != STAGE_USER_DEFINED and load_family != stage:
        warnings.append(
            f"Stage mismatch: selected Loads row is {row_stage_text!r}, but the code-limit stage is {stage!r}. "
            "Use matching stage actions for transfer, deck-casting, or final-service checks."
        )

    if stage in {STAGE_TRANSFER, STAGE_DECK_CASTING} and "composite" in basis:
        warnings.append(
            f"Section basis warning: {stage} checks should normally use precast gross section properties, "
            "not composite transformed properties."
        )

    if stage == STAGE_TRANSFER and "total" in component_cf:
        warnings.append(
            "Load component warning: a Total SLS resultant is not appropriate for a transfer/release check. "
            "Use transfer-stage prestress and self-weight actions with f'ci and precast gross section."
        )

    if "total sls" in component_cf and ("precast" in basis or "composite" in basis):
        warnings.append(
            "Staged-effect warning: Total SLS resultant on a single section basis is suitable for quick preview only. "
            "For final prestressed-girder SLS, split self-weight, wet deck, SDL, and LL+IM into staged rows."
        )

    if stage == STAGE_FINAL_SERVICE and ("wet deck" in component_cf or "girder self" in component_cf) and "composite" in basis:
        warnings.append(
            "Stage/basis warning: girder self-weight or wet deck/topping effects usually act before composite action; "
            "check those components on the precast gross section before assembling final service stress."
        )

    if stage == STAGE_FINAL_SERVICE and ("sdl" in component_cf or "ll" in component_cf or "live" in component_cf) and "precast" in basis:
        warnings.append(
            "Stage/basis warning: post-composite SDL or LL+IM effects usually use the composite transformed section basis."
        )

    return tuple(dict.fromkeys(warnings))


def _stress_type(stress_MPa: float, *, zero_tolerance_MPa: float) -> str:
    if abs(float(stress_MPa)) <= float(zero_tolerance_MPa):
        return "zero"
    return "compression" if float(stress_MPa) < 0.0 else "tension"


def check_girder_stress_limit_point(
    *,
    fiber: str,
    stress_MPa: float,
    fc_MPa: float,
    profile: GirderServiceStressLimitProfile,
) -> GirderStressLimitPointResult:
    """Check one top/bottom fiber stress against the selected profile."""

    if not str(fiber).strip():
        raise ValueError("fiber name must not be blank.")
    _require_finite("stress_MPa", stress_MPa)
    _require_positive("fc_MPa", fc_MPa)
    compression_limit = profile.compression_limit_MPa(fc_MPa)
    tension_limit = profile.tension_allowable_MPa(fc_MPa)
    stress_type = _stress_type(stress_MPa, zero_tolerance_MPa=profile.stress_zero_tolerance_MPa)

    if stress_type == "zero":
        return GirderStressLimitPointResult(
            fiber=str(fiber),
            stress_MPa=float(stress_MPa),
            stress_type=stress_type,
            compression_limit_MPa=compression_limit,
            tension_limit_MPa=tension_limit,
            utilization=0.0,
            status="PASS",
            message="Stress is near zero.",
        )

    if stress_type == "compression":
        utilization = abs(float(stress_MPa)) / compression_limit
        status: StressLimitStatus = "PASS" if utilization <= 1.0 else "FAIL"
        message = "Compression stress within preview limit." if status == "PASS" else "Compression stress exceeds preview limit."
        return GirderStressLimitPointResult(
            fiber=str(fiber),
            stress_MPa=float(stress_MPa),
            stress_type=stress_type,
            compression_limit_MPa=compression_limit,
            tension_limit_MPa=tension_limit,
            utilization=utilization,
            status=status,
            message=message,
        )

    if profile.tension_limit_mode == "No tension" or tension_limit <= profile.stress_zero_tolerance_MPa:
        return GirderStressLimitPointResult(
            fiber=str(fiber),
            stress_MPa=float(stress_MPa),
            stress_type=stress_type,
            compression_limit_MPa=compression_limit,
            tension_limit_MPa=tension_limit,
            utilization=None,
            status="FAIL",
            message="Tension stress violates no-tension preview limit.",
        )

    utilization = float(stress_MPa) / tension_limit
    status = "PASS" if utilization <= 1.0 else "FAIL"
    message = "Tension stress within preview limit." if status == "PASS" else "Tension stress exceeds preview limit."
    return GirderStressLimitPointResult(
        fiber=str(fiber),
        stress_MPa=float(stress_MPa),
        stress_type=stress_type,
        compression_limit_MPa=compression_limit,
        tension_limit_MPa=tension_limit,
        utilization=utilization,
        status=status,
        message=message,
    )


def run_girder_service_stress_limit_check(
    *,
    stresses: list[StressLimitInputRow] | tuple[StressLimitInputRow, ...],
    fc_MPa: float,
    profile: GirderServiceStressLimitProfile,
) -> GirderServiceStressLimitCheckResult:
    """Check a set of top/bottom stresses against a preview code-limit profile."""

    _require_positive("fc_MPa", fc_MPa)
    if not stresses:
        return GirderServiceStressLimitCheckResult(
            profile=profile,
            fc_MPa=float(fc_MPa),
            points=(),
            overall_status="NOT_CHECKED",
            warnings=("No stresses were provided for limit checking.",),
        )
    points = tuple(
        check_girder_stress_limit_point(
            fiber=row.fiber,
            stress_MPa=float(row.stress_MPa),
            fc_MPa=float(fc_MPa),
            profile=profile,
        )
        for row in stresses
    )
    overall: StressLimitStatus = "FAIL" if any(point.status == "FAIL" for point in points) else "PASS"
    warnings = (
        "CODE.SLS.LIMIT2 is a stage-aware preview framework only. It does not auto-generate staged loads, compute losses, or certify final code compliance.",
        profile.stage_guidance,
    )
    return GirderServiceStressLimitCheckResult(
        profile=profile,
        fc_MPa=float(fc_MPa),
        points=points,
        overall_status=overall,
        warnings=warnings,
    )


def girder_service_limit_check_rows(result: GirderServiceStressLimitCheckResult) -> list[dict[str, object]]:
    """Return stable table rows for Streamlit/report display."""

    return [
        {
            "Fiber": point.fiber,
            "Stress (MPa)": point.stress_MPa,
            "Stress type": point.stress_type,
            "Compression limit (MPa)": point.compression_limit_MPa,
            "Tension limit (MPa)": point.tension_limit_MPa,
            "Utilization": point.utilization,
            "Status": point.status,
            "Message": point.message,
        }
        for point in result.points
    ]
