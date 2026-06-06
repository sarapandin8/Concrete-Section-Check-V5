"""Beam/Girder service-stress code-limit preview helpers.

CODE.SLS.LIMIT3 keeps this as an editable preview framework while making
stage and code-profile meaning explicit.  The helpers are intentionally pure
Python so the UI, validation suite, and future reports can all use the same
stage-aware profile metadata without changing stress or solver logic.

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
class GirderStressLimitProfileOption:
    """Selectable code/stage limit-profile default for CODE.SLS.LIMIT3.

    Values are still preview defaults.  This object exists so the UI can show
    a clear AASHTO/ACI code-profile selector instead of hiding a single generic
    ratio in the advanced override panel.
    """

    key: str
    label: str
    description: str
    compression_limit_ratio: float
    tension_limit_mode: TensionLimitMode
    tension_sqrt_fc_ratio: float = 0.0
    tension_limit_MPa: float = 0.0
    tension_limit_cap_MPa: float | None = None
    clause_note: str = ""


@dataclass(frozen=True)
class GirderTensionLimitGuidance:
    """Guided tensile stress-limit profile recommendation for CODE.SLS.LIMIT4.

    The recommendation is a selection aid only.  It does not change stress
    values, code formulas, reinforcement design, cracked-section analysis, or
    final code compliance.
    """

    recommended_profile_key: str
    status: Literal["OK", "REVIEW"]
    basis: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class AciTransferEndZoneTensionLimitTrace:
    """Piecewise ACI 318 transfer tension-limit trace for simply supported ends.

    This helper is used only as display/check-limit metadata.  It does not alter
    the SLS stress solver or prestress Pe(x) calculation.
    """

    x_m: tuple[float, ...]
    y_MPa: tuple[float, ...]
    end_zone_length_m: float
    interior_limit_MPa: float
    end_zone_limit_MPa: float
    formula_note: str


@dataclass(frozen=True)
class GirderServiceStressLimitProfile:
    """Concrete service-stress limit profile for one Beam/Girder preview check."""

    code: GirderSLSCode
    stage: str
    compression_limit_ratio: float
    tension_limit_mode: TensionLimitMode
    tension_sqrt_fc_ratio: float = 0.0
    tension_limit_MPa: float = 0.0
    tension_limit_cap_MPa: float | None = None
    stress_zero_tolerance_MPa: float = 5.0e-4
    clause_note: str = ""
    limitation_note: str = ""
    concrete_strength_label: str = "f'c"
    prestress_force_basis: str = "Pe_eff after losses"
    recommended_section_basis: str = "Engineer-selected"
    stage_guidance: str = ""
    limit_profile_key: str = "default"
    limit_profile_label: str = "Default editable preview profile"
    limit_profile_description: str = "Engineer-controlled preview default; confirm final code clauses."

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
            value = float(self.tension_limit_MPa)
        else:
            if float(self.tension_sqrt_fc_ratio) < 0.0:
                raise ValueError("tension_sqrt_fc_ratio must not be negative.")
            value = float(self.tension_sqrt_fc_ratio) * math.sqrt(float(fc_MPa))
        if self.tension_limit_cap_MPa is not None:
            value = min(value, float(self.tension_limit_cap_MPa))
        return value


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
    """Readable formula text for one editable stress-limit profile."""

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


def girder_sls_limit_profile_options(
    code: GirderSLSCode = "AASHTO LRFD Bridge",
    stage: GirderSLSStage = STAGE_FINAL_SERVICE,
) -> tuple[GirderStressLimitProfileOption, ...]:
    """Return selectable preview-limit profiles for one code/stage.

    The coefficients are in MPa form when used as ``ratio × sqrt(fc_MPa)``.
    AASHTO ksi-form square-root coefficients are converted to MPa-form
    coefficients here (for example 0.19 ksi√ksi ≈ 0.50 MPa√MPa).
    """

    if code not in DEFAULT_GIRDER_SLS_CODES:
        raise ValueError(f"Unsupported girder SLS code profile: {code!r}")
    stage = normalize_girder_sls_stage(stage)
    if stage not in DEFAULT_GIRDER_SLS_STAGES:
        raise ValueError(f"Unsupported girder SLS stage: {stage!r}")

    if code == "AASHTO LRFD Bridge":
        if stage == STAGE_TRANSFER:
            return (
                GirderStressLimitProfileOption(
                    key="aashto_transfer_no_aux",
                    label="Temporary release — no bonded auxiliary tension reinforcement",
                    description="0.60 f'ci compression; 0.25√f'ci tension capped at 1.38 MPa. Use for conservative temporary release preview where the project permits this profile.",
                    compression_limit_ratio=0.60,
                    tension_limit_mode="sqrt(fc) ratio",
                    tension_sqrt_fc_ratio=0.25,
                    tension_limit_cap_MPa=1.38,
                    clause_note="AASHTO-style temporary stress preview: release-stage compression and tensile stress profile. Confirm member type, reinforcement condition, and project edition before final design.",
                ),
                GirderStressLimitProfileOption(
                    key="aashto_transfer_bonded_aux",
                    label="Temporary release — bonded auxiliary reinforcement condition",
                    description="0.60 f'ci compression; 0.58√f'ci tension preview where bonded reinforcement condition is satisfied.",
                    compression_limit_ratio=0.60,
                    tension_limit_mode="sqrt(fc) ratio",
                    tension_sqrt_fc_ratio=0.58,
                    clause_note="AASHTO-style temporary stress preview with bonded auxiliary reinforcement assumption. Confirm reinforcement condition before use.",
                ),
                GirderStressLimitProfileOption(
                    key="aashto_transfer_no_tension",
                    label="Temporary release — no tension permitted",
                    description="Conservative no-tension release preview.",
                    compression_limit_ratio=0.60,
                    tension_limit_mode="No tension",
                    clause_note="Conservative release preview with no positive tensile stress permitted.",
                ),
            )
        if stage == STAGE_DECK_CASTING:
            return (
                GirderStressLimitProfileOption(
                    key="aashto_deck_precomp_user",
                    label="Pre-composite construction stage — no bonded auxiliary reinforcement",
                    description="0.55 f'c_stage compression; 0.25√f'c_stage tension capped at 1.38 MPa. Use where bonded auxiliary reinforcement condition is not verified.",
                    compression_limit_ratio=0.55,
                    tension_limit_mode="sqrt(fc) ratio",
                    tension_sqrt_fc_ratio=0.25,
                    tension_limit_cap_MPa=1.38,
                    clause_note="AASHTO-style construction/deck-casting temporary stress preview without verified bonded auxiliary reinforcement. Confirm project-specific temporary stress limits.",
                ),
                GirderStressLimitProfileOption(
                    key="aashto_deck_precomp_bonded_aux",
                    label="Pre-composite construction stage — bonded auxiliary reinforcement condition",
                    description="0.55 f'c_stage compression; 0.58√f'c_stage tension preview where bonded auxiliary reinforcement condition is satisfied.",
                    compression_limit_ratio=0.55,
                    tension_limit_mode="sqrt(fc) ratio",
                    tension_sqrt_fc_ratio=0.58,
                    clause_note="AASHTO-style construction/deck-casting temporary stress preview with verified bonded auxiliary reinforcement assumption. Confirm reinforcement condition before final design.",
                ),
                GirderStressLimitProfileOption(
                    key="aashto_deck_no_tension",
                    label="Pre-composite construction stage — no tension permitted",
                    description="Conservative no-tension pre-composite construction-stage preview.",
                    compression_limit_ratio=0.55,
                    tension_limit_mode="No tension",
                    clause_note="Conservative pre-composite preview with no positive tensile stress permitted.",
                ),
            )
        if stage == STAGE_FINAL_SERVICE:
            return (
                GirderStressLimitProfileOption(
                    key="aashto_service_bonded_moderate_full",
                    label="Service III — bonded, moderate exposure / full-service compression",
                    description="0.60 f'c compression for full service preview; 0.50√f'c tensile stress profile for bonded tendon/reinforcement under moderate exposure.",
                    compression_limit_ratio=0.60,
                    tension_limit_mode="sqrt(fc) ratio",
                    tension_sqrt_fc_ratio=0.50,
                    clause_note="AASHTO bridge service preview. Use Service III-type tension profile as applicable; final clause selection remains engineer-controlled.",
                ),
                GirderStressLimitProfileOption(
                    key="aashto_service_bonded_severe_full",
                    label="Service III — bonded, severe exposure / full-service compression",
                    description="0.60 f'c compression for full service preview; 0.25√f'c tensile stress profile for severe exposure.",
                    compression_limit_ratio=0.60,
                    tension_limit_mode="sqrt(fc) ratio",
                    tension_sqrt_fc_ratio=0.25,
                    clause_note="AASHTO bridge service preview for severe exposure bonded condition. Confirm exposure and tendon/reinforcement condition.",
                ),
                GirderStressLimitProfileOption(
                    key="aashto_service_unbonded_no_tension",
                    label="Service III — unbonded / no tension",
                    description="0.60 f'c compression for full service preview; no positive tension permitted.",
                    compression_limit_ratio=0.60,
                    tension_limit_mode="No tension",
                    clause_note="AASHTO bridge service preview for unbonded/no-tension condition.",
                ),
                GirderStressLimitProfileOption(
                    key="aashto_service_sustained_bonded_moderate",
                    label="Service sustained/permanent — bonded, moderate exposure",
                    description="0.45 f'c compression for sustained/permanent load preview; 0.50√f'c tension profile.",
                    compression_limit_ratio=0.45,
                    tension_limit_mode="sqrt(fc) ratio",
                    tension_sqrt_fc_ratio=0.50,
                    clause_note="AASHTO/PCI-style sustained compression preview. Use only when the supplied stress rows represent sustained/permanent effects.",
                ),
            )
        return (
            GirderStressLimitProfileOption(
                key="aashto_user_defined",
                label="AASHTO user-defined editable profile",
                description="Engineer-defined bridge stress-limit profile.",
                compression_limit_ratio=0.45,
                tension_limit_mode="User-defined",
                tension_limit_MPa=0.0,
                clause_note="User-defined AASHTO bridge preview profile.",
            ),
        )

    # ACI 318 preview profiles.
    if stage == STAGE_TRANSFER:
        return (
            GirderStressLimitProfileOption(
                key="aci_transfer_basic",
                label="Initial transfer — general span limit",
                description="0.60 f'ci compression; 0.25√f'ci tension for general/interior transfer-stage sections.",
                compression_limit_ratio=0.60,
                tension_limit_mode="sqrt(fc) ratio",
                tension_sqrt_fc_ratio=0.25,
                clause_note="ACI 318-14/19 Table 24.5.3.2 transfer-stage preview: general/interior tension limit. End-zone higher limit is separate and requires verified ACI R24.5.3 condition.",
            ),
            GirderStressLimitProfileOption(
                key="aci_transfer_end_zone_verified",
                label="Initial transfer — end-zone limit verified",
                description="Piecewise ACI transfer tension preview: 0.50√f'ci at simply supported end zones and 0.25√f'ci in the interior span. Requires verified ACI R24.5.3 condition.",
                compression_limit_ratio=0.60,
                tension_limit_mode="sqrt(fc) ratio",
                tension_sqrt_fc_ratio=0.25,
                clause_note="ACI 318-14/19 Table 24.5.3.2 allows 0.50√f'ci at ends of simply supported members when ACI R24.5.3 condition is satisfied. The scalar profile value is the interior 0.25√f'ci limit; full-length diagrams use a piecewise line.",
            ),
            GirderStressLimitProfileOption(
                key="aci_transfer_no_tension",
                label="Initial transfer — no tension permitted",
                description="Conservative no-tension initial transfer preview.",
                compression_limit_ratio=0.60,
                tension_limit_mode="No tension",
                clause_note="Conservative ACI transfer preview with no positive tensile stress permitted.",
            ),
        )
    if stage == STAGE_DECK_CASTING:
        return (
            GirderStressLimitProfileOption(
                key="aci_deck_precomp_cip_pour_fr",
                label="CIP pour / construction — modulus-of-rupture tension limit",
                description="0.60 f'c compression; fr = 0.62√f'c tension for temporary CIP pour construction stress preview of the precast beam.",
                compression_limit_ratio=0.60,
                tension_limit_mode="sqrt(fc) ratio",
                tension_sqrt_fc_ratio=0.62,
                clause_note="ACI-style construction/CIP pour preview for the precast beam concrete: use modulus of rupture fr = 0.62√f'c as the temporary construction tensile limit. This is not the ACI transfer Table 24.5.3.2 end-zone provision; confirm project criteria before final design.",
            ),
        )
    if stage == STAGE_FINAL_SERVICE:
        return (
            GirderStressLimitProfileOption(
                key="aci_service_class_u_one_way",
                label="Service — Class U threshold, one-way beam/slab",
                description="0.60 f'c compression for total service preview; 0.62√f'c Class U tension threshold.",
                compression_limit_ratio=0.60,
                tension_limit_mode="sqrt(fc) ratio",
                tension_sqrt_fc_ratio=0.62,
                clause_note="ACI 318-style service preview: Class U tension threshold for one-way prestressed flexural members. Confirm system type and code edition.",
            ),
            GirderStressLimitProfileOption(
                key="aci_service_class_t_upper",
                label="Service — Class T upper threshold",
                description="0.60 f'c compression for total service preview; 1.00√f'c Class T upper threshold. Use for classification/review, not automatically final acceptance.",
                compression_limit_ratio=0.60,
                tension_limit_mode="sqrt(fc) ratio",
                tension_sqrt_fc_ratio=1.00,
                clause_note="ACI 318-style service classification preview. Class T/C design implications are not automated in this milestone.",
            ),
            GirderStressLimitProfileOption(
                key="aci_service_sustained_class_u",
                label="Service sustained/permanent — Class U threshold",
                description="0.45 f'c compression for sustained/permanent effects; 0.62√f'c Class U tension threshold.",
                compression_limit_ratio=0.45,
                tension_limit_mode="sqrt(fc) ratio",
                tension_sqrt_fc_ratio=0.62,
                clause_note="ACI sustained/permanent compression preview. Use only when supplied stress rows represent sustained/permanent effects.",
            ),
            GirderStressLimitProfileOption(
                key="aci_service_no_tension",
                label="Service — no tension permitted",
                description="Conservative no-tension service preview.",
                compression_limit_ratio=0.60,
                tension_limit_mode="No tension",
                clause_note="Conservative ACI service preview with no positive tensile stress permitted.",
            ),
        )
    return (
        GirderStressLimitProfileOption(
            key="aci_user_defined",
            label="ACI user-defined editable profile",
            description="Engineer-defined ACI stress-limit profile.",
            compression_limit_ratio=0.45,
            tension_limit_mode="User-defined",
            tension_limit_MPa=0.0,
            clause_note="User-defined ACI preview profile.",
        ),
    )


def _profile_option_by_key(
    *,
    code: GirderSLSCode,
    stage: GirderSLSStage,
    limit_profile_key: str | None,
) -> GirderStressLimitProfileOption:
    options = girder_sls_limit_profile_options(code, stage)
    if limit_profile_key:
        for option in options:
            if option.key == str(limit_profile_key):
                return option
    return options[0]



def recommend_girder_tension_limit_profile(
    *,
    code: GirderSLSCode,
    stage: GirderSLSStage,
    bonded_tension_reinforcement_verified: bool | None = None,
    exposure_condition: str | None = None,
    aci_service_class: str | None = None,
    effect_duration: str | None = None,
) -> GirderTensionLimitGuidance:
    """Recommend a preview tensile stress-limit profile from user-visible conditions.

    CODE.SLS.LIMIT4 deliberately separates *profile selection guidance* from
    the stress solver.  The caller may use the returned key to pre-select one
    of ``girder_sls_limit_profile_options``; it must still show the basis and
    warnings because reinforcement-aware tension limits require engineering
    confirmation.
    """

    if code not in DEFAULT_GIRDER_SLS_CODES:
        raise ValueError(f"Unsupported girder SLS code profile: {code!r}")
    stage = normalize_girder_sls_stage(stage)
    if stage not in DEFAULT_GIRDER_SLS_STAGES:
        raise ValueError(f"Unsupported girder SLS stage: {stage!r}")

    exposure = str(exposure_condition or "moderate").strip().casefold()
    aci_class = str(aci_service_class or "class u").strip().casefold()
    duration = str(effect_duration or "full service").strip().casefold()
    verified = bonded_tension_reinforcement_verified
    warnings: list[str] = []

    def status() -> Literal["OK", "REVIEW"]:
        return "REVIEW" if warnings else "OK"

    if code == "AASHTO LRFD Bridge":
        if stage == STAGE_TRANSFER:
            if verified is True:
                key = "aashto_transfer_bonded_aux"
                basis = "Transfer tension reinforcement condition verified; auxiliary bonded-reinforcement profile selected."
            elif verified is False:
                key = "aashto_transfer_no_aux"
                basis = "No verified auxiliary bonded tension reinforcement; conservative capped release-tension profile selected."
                warnings.append("Do not use the higher transfer tensile limit unless bonded auxiliary reinforcement condition is verified at the tensile face.")
            else:
                key = "aashto_transfer_no_aux"
                basis = "Auxiliary bonded tension reinforcement not verified; conservative capped release-tension profile selected."
                warnings.append("Reinforcement condition is not verified; keep REVIEW before final transfer/release acceptance.")
            return GirderTensionLimitGuidance(key, status(), basis, tuple(warnings))

        if stage == STAGE_DECK_CASTING:
            if "no" in exposure or verified is False:
                key = "aashto_deck_no_tension" if "no" in exposure else "aashto_deck_precomp_user"
                basis = (
                    "Pre-composite construction selected as no-tension preview."
                    if key == "aashto_deck_no_tension"
                    else "No verified auxiliary bonded tension reinforcement; conservative capped construction-stage tension profile selected."
                )
                if key == "aashto_deck_precomp_user":
                    warnings.append("Do not use the higher construction-stage tensile limit unless bonded auxiliary reinforcement condition is verified at the tensile face.")
            elif verified is True:
                key = "aashto_deck_precomp_bonded_aux"
                basis = "Pre-composite construction tension reinforcement condition verified; bonded auxiliary reinforcement profile selected."
            else:
                key = "aashto_deck_precomp_user"
                basis = "Auxiliary bonded tension reinforcement not verified; conservative capped construction-stage tension profile selected."
                warnings.append("Construction-stage bonded auxiliary reinforcement condition is not verified; keep REVIEW before final construction-stage acceptance.")
            return GirderTensionLimitGuidance(key, status(), basis, tuple(warnings))

        if stage == STAGE_FINAL_SERVICE:
            if "unbond" in exposure or "no" in exposure:
                key = "aashto_service_unbonded_no_tension"
                basis = "Unbonded/no-tension service condition selected."
            elif "sust" in duration or "perm" in duration:
                key = "aashto_service_sustained_bonded_moderate"
                basis = "Sustained/permanent service stress effect selected."
                if verified is not True:
                    warnings.append("Sustained bonded profile assumes bonded tendon/reinforcement condition; verify before final design.")
            elif "severe" in exposure:
                key = "aashto_service_bonded_severe_full"
                basis = "Severe-exposure bonded service condition selected."
                if verified is not True:
                    warnings.append("Severe bonded profile still assumes bonded tendon/reinforcement condition; verify before final design.")
            else:
                key = "aashto_service_bonded_moderate_full"
                basis = "Moderate-exposure bonded service condition selected."
                if verified is not True:
                    warnings.append("Moderate-exposure tensile profile assumes bonded tendon/reinforcement condition; verify before final design.")
            return GirderTensionLimitGuidance(key, status(), basis, tuple(warnings))

        return GirderTensionLimitGuidance(
            "aashto_user_defined",
            "REVIEW",
            "User-defined AASHTO stage; select project-specific tensile stress limit.",
            ("User-defined stage cannot be classified automatically.",),
        )

    # ACI 318 preview profiles.
    if stage == STAGE_TRANSFER:
        if exposure and "no" in exposure:
            return GirderTensionLimitGuidance(
                "aci_transfer_no_tension",
                "OK",
                "Initial transfer selected as no-tension preview.",
            )
        if verified is True:
            return GirderTensionLimitGuidance(
                "aci_transfer_end_zone_verified",
                "OK",
                "ACI transfer end-zone condition verified; use piecewise 0.50√f'ci end-zone limit and 0.25√f'ci interior limit.",
            )
        if verified is False:
            warnings.append("ACI R24.5.3 end-zone condition is not verified; use 0.25√f'ci general transfer tension limit.")
        else:
            warnings.append("ACI transfer end-zone condition is not verified by the app; use 0.25√f'ci general transfer tension limit unless the engineer verifies R24.5.3.")
        return GirderTensionLimitGuidance(
            "aci_transfer_basic",
            status(),
            "Initial-transfer general span prestressed-member preview selected.",
            tuple(warnings),
        )

    if stage == STAGE_DECK_CASTING:
        warnings.append("ACI construction/CIP pour tensile limit uses modulus of rupture fr = 0.62√f'c as a temporary-stage preview; confirm project criteria before final design.")
        return GirderTensionLimitGuidance(
            "aci_deck_precomp_cip_pour_fr",
            "REVIEW",
            "CIP pour construction-stage modulus-of-rupture tensile limit selected for the precast beam concrete.",
            tuple(warnings),
        )

    if stage == STAGE_FINAL_SERVICE:
        if "no" in aci_class:
            return GirderTensionLimitGuidance(
                "aci_service_no_tension",
                "OK",
                "ACI service no-tension preview selected.",
            )
        if "sust" in duration or "perm" in duration:
            return GirderTensionLimitGuidance(
                "aci_service_sustained_class_u",
                "OK",
                "ACI sustained/permanent service Class U threshold selected.",
            )
        if "class t" in aci_class or aci_class.endswith("t"):
            if verified is not True:
                warnings.append("Class T selection requires engineering confirmation of bonded reinforcement/cracked-section implications; app does not certify Class T design.")
            return GirderTensionLimitGuidance(
                "aci_service_class_t_upper",
                status(),
                "ACI service Class T upper threshold selected for classification/review.",
                tuple(warnings),
            )
        return GirderTensionLimitGuidance(
            "aci_service_class_u_one_way",
            "OK",
            "ACI service Class U threshold selected for one-way prestressed flexural member preview.",
        )

    return GirderTensionLimitGuidance(
        "aci_user_defined",
        "REVIEW",
        "User-defined ACI stage; select project-specific tensile stress limit.",
        ("User-defined stage cannot be classified automatically.",),
    )




def aci_transfer_end_zone_length_m(
    *,
    strand_diameter_mm: float | None = None,
    member_depth_mm: float | None = None,
    user_defined_length_m: float | None = None,
    basis: str = "Transfer length 60db",
) -> float:
    """Return practical ACI transfer end-zone length in metres.

    ACI 318 states the higher transfer tension limit at the ends of simply
    supported members but does not prescribe a numeric end-zone length.  The
    project default is transfer length, ``60db``.  This helper is intentionally
    explicit so UI/reporting can show the assumption instead of hiding it.
    """

    text = str(basis or "Transfer length 60db").strip().casefold()
    if "face" in text or "conservative" in text:
        return 0.0
    if "user" in text:
        value = 0.0 if user_defined_length_m is None else float(user_defined_length_m)
        if not math.isfinite(value) or value < 0.0:
            raise ValueError("user_defined_length_m must be a non-negative finite value.")
        return value
    if "depth" in text or text == "h":
        value_mm = 0.0 if member_depth_mm is None else float(member_depth_mm)
        if not math.isfinite(value_mm) or value_mm <= 0.0:
            raise ValueError("member_depth_mm must be positive when using member depth as end-zone length.")
        return value_mm / 1000.0
    db_mm = 12.7 if strand_diameter_mm is None else float(strand_diameter_mm)
    if not math.isfinite(db_mm) or db_mm <= 0.0:
        raise ValueError("strand_diameter_mm must be positive when using transfer length 60db.")
    return 60.0 * db_mm / 1000.0


def aci_transfer_tension_limit_trace(
    *,
    span_length_m: float,
    fci_MPa: float,
    end_zone_length_m: float,
    use_end_zone_limit: bool = True,
) -> AciTransferEndZoneTensionLimitTrace:
    """Return the ACI transfer-stage piecewise tension limit line.

    Interior/general span limit = 0.25√f'ci.  End-zone limit for simply
    supported member ends = 0.50√f'ci when the ACI R24.5.3 condition is
    verified by the engineer.  Units are MPa and metres.
    """

    _require_positive("span_length_m", span_length_m)
    _require_positive("fci_MPa", fci_MPa)
    interior = 0.25 * math.sqrt(float(fci_MPa))
    end_zone = 0.50 * math.sqrt(float(fci_MPa))
    length = max(0.0, float(end_zone_length_m))
    length = min(length, float(span_length_m) / 2.0)
    if (not use_end_zone_limit) or length <= 1.0e-9:
        return AciTransferEndZoneTensionLimitTrace(
            x_m=(0.0, float(span_length_m)),
            y_MPa=(interior, interior),
            end_zone_length_m=0.0,
            interior_limit_MPa=interior,
            end_zone_limit_MPa=end_zone if use_end_zone_limit else interior,
            formula_note="ACI transfer general span: ft = 0.25√f'ci.",
        )
    left = length
    right = float(span_length_m) - length
    return AciTransferEndZoneTensionLimitTrace(
        x_m=(0.0, left, left, right, right, float(span_length_m)),
        y_MPa=(end_zone, end_zone, interior, interior, end_zone, end_zone),
        end_zone_length_m=length,
        interior_limit_MPa=interior,
        end_zone_limit_MPa=end_zone,
        formula_note="ACI transfer end zone: ft = 0.50√f'ci at ends; interior: ft = 0.25√f'ci.",
    )


def default_girder_sls_limit_profile(
    code: GirderSLSCode = "AASHTO LRFD Bridge",
    stage: GirderSLSStage = STAGE_FINAL_SERVICE,
    limit_profile_key: str | None = None,
) -> GirderServiceStressLimitProfile:
    """Return an editable default profile for one code/stage/profile combination."""

    if code not in DEFAULT_GIRDER_SLS_CODES:
        raise ValueError(f"Unsupported girder SLS code profile: {code!r}")
    stage = normalize_girder_sls_stage(stage)
    if stage not in DEFAULT_GIRDER_SLS_STAGES:
        raise ValueError(f"Unsupported girder SLS stage: {stage!r}")

    meta = girder_sls_stage_metadata(stage)
    option = _profile_option_by_key(code=code, stage=stage, limit_profile_key=limit_profile_key)
    base_note = (
        "Editable preview profile only. Confirm code edition, authority/project specifications, prestress class, "
        "reinforcement/cracking assumptions, concrete strength at stage, exposure/tendon condition, and prestress-force state before final design."
    )
    code_note = (
        "AASHTO bridge-girder preview defaults use bridge service/temporary stress profiles and MPa-form square-root coefficients."
        if code == "AASHTO LRFD Bridge"
        else "ACI prestressed-member preview defaults use ACI-style service class / transfer profiles."
    )
    return GirderServiceStressLimitProfile(
        code=code,
        stage=stage,
        compression_limit_ratio=option.compression_limit_ratio,
        tension_limit_mode=option.tension_limit_mode,
        tension_sqrt_fc_ratio=option.tension_sqrt_fc_ratio,
        tension_limit_MPa=option.tension_limit_MPa,
        tension_limit_cap_MPa=option.tension_limit_cap_MPa,
        clause_note=option.clause_note,
        limitation_note=f"{base_note} {code_note}",
        concrete_strength_label=meta["concrete_strength_label"],
        prestress_force_basis=meta["prestress_force_basis"],
        recommended_section_basis=meta["recommended_section_basis"],
        stage_guidance=meta["stage_guidance"],
        limit_profile_key=option.key,
        limit_profile_label=option.label,
        limit_profile_description=option.description,
    )


def build_girder_sls_limit_profile(
    *,
    code: GirderSLSCode,
    stage: GirderSLSStage,
    limit_profile_key: str | None = None,
    compression_limit_ratio: float | None = None,
    tension_limit_mode: TensionLimitMode | None = None,
    tension_sqrt_fc_ratio: float | None = None,
    tension_limit_MPa: float | None = None,
    tension_limit_cap_MPa: float | None = None,
    stress_zero_tolerance_MPa: float | None = None,
) -> GirderServiceStressLimitProfile:
    """Build a profile from code/stage defaults plus optional user overrides."""

    base = default_girder_sls_limit_profile(code, stage, limit_profile_key=limit_profile_key)
    profile = GirderServiceStressLimitProfile(
        code=base.code,
        stage=base.stage,
        compression_limit_ratio=float(base.compression_limit_ratio if compression_limit_ratio is None else compression_limit_ratio),
        tension_limit_mode=base.tension_limit_mode if tension_limit_mode is None else tension_limit_mode,
        tension_sqrt_fc_ratio=float(base.tension_sqrt_fc_ratio if tension_sqrt_fc_ratio is None else tension_sqrt_fc_ratio),
        tension_limit_MPa=float(base.tension_limit_MPa if tension_limit_MPa is None else tension_limit_MPa),
        tension_limit_cap_MPa=base.tension_limit_cap_MPa if tension_limit_cap_MPa is None else tension_limit_cap_MPa,
        stress_zero_tolerance_MPa=float(base.stress_zero_tolerance_MPa if stress_zero_tolerance_MPa is None else stress_zero_tolerance_MPa),
        clause_note=base.clause_note,
        limitation_note=base.limitation_note,
        concrete_strength_label=base.concrete_strength_label,
        prestress_force_basis=base.prestress_force_basis,
        recommended_section_basis=base.recommended_section_basis,
        stage_guidance=base.stage_guidance,
        limit_profile_key=base.limit_profile_key,
        limit_profile_label=base.limit_profile_label,
        limit_profile_description=base.limit_profile_description,
    )
    _require_positive("compression_limit_ratio", profile.compression_limit_ratio)
    if profile.tension_limit_mode == "sqrt(fc) ratio" and profile.tension_sqrt_fc_ratio < 0.0:
        raise ValueError("tension_sqrt_fc_ratio must not be negative.")
    if profile.tension_limit_mode == "User-defined" and profile.tension_limit_MPa < 0.0:
        raise ValueError("tension_limit_MPa must not be negative.")
    if profile.tension_limit_cap_MPa is not None and profile.tension_limit_cap_MPa < 0.0:
        raise ValueError("tension_limit_cap_MPa must not be negative.")
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
        base_formula = f"{profile.tension_sqrt_fc_ratio:.3f} × √({strength_label})"
        uncapped = float(profile.tension_sqrt_fc_ratio) * math.sqrt(float(fc_MPa))
        if profile.tension_limit_cap_MPa is not None:
            tension_formula = f"f_t,allow = min({base_formula}, {profile.tension_limit_cap_MPa:.3f} MPa)"
            tension_substitution = (
                f"min({profile.tension_sqrt_fc_ratio:.3f} × √{float(fc_MPa):.3f} = {uncapped:.3f}, "
                f"{profile.tension_limit_cap_MPa:.3f}) = {tension_limit:.3f} MPa"
            )
        else:
            tension_formula = f"f_t,allow = {base_formula}"
            tension_substitution = f"{profile.tension_sqrt_fc_ratio:.3f} × √{float(fc_MPa):.3f} = {tension_limit:.3f} MPa"

    return GirderStressLimitFormulaSummary(
        compression_formula=compression_formula,
        compression_substitution=compression_substitution,
        compression_limit_MPa=compression_limit,
        tension_formula=tension_formula,
        tension_substitution=tension_substitution,
        tension_limit_MPa=tension_limit,
        strength_label=strength_label,
        profile_note=f"{profile.code} · {profile.stage} · {profile.limit_profile_label} · editable preview formula",
    )


def girder_sls_stage_basis_consistency_warnings(
    *,
    profile_stage: str,
    section_basis_label: str | None = None,
    load_stage: str | None = None,
    load_component: str | None = None,
    stress_includes_prestress: bool | None = None,
    prestress_force_state: str | None = None,
) -> tuple[str, ...]:
    """Return engineering warnings for inconsistent stage/load/basis selections.

    ``stress_includes_prestress`` is intentionally optional so older callers
    keep their existing behavior.  When supplied for a transfer/release
    preview, it prevents a service-only stress result from being presented as
    a meaningful transfer-stage prestressed-girder check.
    """

    warnings: list[str] = []
    stage = normalize_girder_sls_stage(profile_stage)
    basis = str(section_basis_label or "").strip().casefold()
    row_stage_text = str(load_stage or "").strip()
    row_stage_cf = row_stage_text.casefold()
    component_text = str(load_component or "").strip()
    component_cf = component_text.casefold()
    prestress_state_text = str(prestress_force_state or "").strip()
    prestress_state_cf = prestress_state_text.casefold()

    def row_stage_family() -> str | None:
        if not row_stage_cf:
            return None
        if "transfer" in row_stage_cf or "release" in row_stage_cf:
            return STAGE_TRANSFER
        if "construction" in row_stage_cf or "deck" in row_stage_cf or "pre-composite" in row_stage_cf or "pre composite" in row_stage_cf:
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

    if stage == STAGE_TRANSFER and stress_includes_prestress is False:
        warnings.append(
            "Transfer prestress warning: Transfer / Release checks normally require Pe_transfer or initial prestress effect. "
            "The current preview stress result does not include transfer prestress."
        )

    if stage == STAGE_TRANSFER and stress_includes_prestress is True:
        if (not prestress_state_cf) or "pe_eff" in prestress_state_cf or "after loss" in prestress_state_cf or "final" in prestress_state_cf:
            warnings.append(
                "Transfer prestress-force warning: Transfer / Release checks should normally use Pe_transfer / initial prestress, "
                "not final Pe_eff after losses or an unverified generic Pe_eff value."
            )

    if stage == STAGE_TRANSFER and "total" in component_cf:
        warnings.append(
            "Load component warning: a Total SLS resultant is not appropriate for a transfer/release check. "
            "Use transfer-stage prestress and self-weight actions with f'ci and precast gross section."
        )

    if "total sls" in component_cf and stage != STAGE_FINAL_SERVICE and ("precast" in basis or "composite" in basis):
        warnings.append(
            "Staged-effect warning: Total SLS resultant is intended for final service. "
            "Use Transfer or Construction stage resultants for earlier-stage checks."
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
        "CODE.SLS.LIMIT3 is a code-profile preview framework only. It does not auto-generate staged loads, compute losses, or certify final code compliance.",
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
