"""Beam/Girder staged service-stress case helpers.

GIRDER.SLS2A adds a pure-Python, preview-safe stage-case kernel for future
prestressed bridge-girder SLS workflows.  It combines the existing elastic
service-load stress kernel and the effective-prestress stress-effect kernel for
an explicitly selected section basis.

This module deliberately does **not**:
- generate construction-stage loads
- apply AASHTO allowable stress limits
- calculate prestress losses
- change PMM, prestress input, rebar, report, load-case, material, or geometry
  behavior

Sign convention is inherited from the girder SLS kernels:
- compression stress is negative
- tension stress is positive
- axial compression N_kN is positive
- sagging M_kNm is positive and gives top compression / bottom tension
- Pe_eff_kN is positive compressive effective prestress after losses
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from concrete_pmm_pro.serviceability.girder_prestress import (
    GirderPrestressStressResult,
    run_girder_prestress_stress_effect,
)
from concrete_pmm_pro.serviceability.girder_stress import (
    GirderSectionBasis,
    GirderServiceStressResult,
    SectionBasisName,
    run_basic_girder_service_stress,
)


@dataclass(frozen=True)
class GirderServiceStageCase:
    """Manual service-stage action case for a selected girder section basis.

    The case stores explicit trial actions only.  It does not infer loads from
    self-weight, deck geometry, lane loads, or construction sequence.  The
    caller must choose the appropriate basis and action values for the stage.
    """

    stage_id: str
    title: str
    basis_name: SectionBasisName
    N_kN: float = 0.0
    M_kNm: float = 0.0
    include_prestress: bool = False
    Pe_eff_kN: float = 0.0
    tendon_y_from_bottom_mm: float | None = None
    note: str = ""


@dataclass(frozen=True)
class GirderStageFiberStress:
    """Combined service-load plus optional prestress stress at one fiber."""

    location: str
    y_from_bottom_mm: float
    service_axial_stress_MPa: float
    service_bending_stress_MPa: float
    service_total_stress_MPa: float
    prestress_axial_stress_MPa: float
    prestress_eccentric_stress_MPa: float
    prestress_total_stress_MPa: float
    total_stress_MPa: float
    stress_type: str


@dataclass(frozen=True)
class GirderServiceStageStressResult:
    """Top/bottom stress result for one manual girder service-stage case."""

    stage_id: str
    title: str
    basis_name: SectionBasisName
    N_kN: float
    M_kNm: float
    service_result: GirderServiceStressResult
    prestress_result: GirderPrestressStressResult | None
    top: GirderStageFiberStress
    bottom: GirderStageFiberStress
    warnings: tuple[str, ...] = ()
    note: str = ""

    @property
    def max_compression_MPa(self) -> float:
        """Return the most compressive combined stress as a negative value."""

        return min(self.top.total_stress_MPa, self.bottom.total_stress_MPa)

    @property
    def max_tension_MPa(self) -> float:
        """Return the maximum combined tensile stress as a positive value."""

        return max(self.top.total_stress_MPa, self.bottom.total_stress_MPa)


@dataclass(frozen=True)
class GirderServiceStageTemplate:
    """Suggested stage label and basis guidance without auto-generated loads."""

    stage_id: str
    title: str
    recommended_basis_name: SectionBasisName
    include_prestress: bool
    engineering_note: str


def _stress_type(stress_MPa: float, *, zero_tolerance_MPa: float = 1.0e-9) -> str:
    if abs(float(stress_MPa)) <= zero_tolerance_MPa:
        return "zero"
    return "compression" if float(stress_MPa) < 0.0 else "tension"


def _require_finite(name: str, value: float) -> None:
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite.")


def _combine_fiber_stress(service_fiber: Any, prestress_fiber: Any | None, *, location: str) -> GirderStageFiberStress:
    ps_axial = float(getattr(prestress_fiber, "axial_stress_MPa", 0.0) or 0.0)
    ps_ecc = float(getattr(prestress_fiber, "eccentric_bending_stress_MPa", 0.0) or 0.0)
    ps_total = float(getattr(prestress_fiber, "total_stress_MPa", 0.0) or 0.0)
    service_total = float(service_fiber.total_stress_MPa)
    total = service_total + ps_total
    return GirderStageFiberStress(
        location=location,
        y_from_bottom_mm=float(service_fiber.y_from_bottom_mm),
        service_axial_stress_MPa=float(service_fiber.axial_stress_MPa),
        service_bending_stress_MPa=float(service_fiber.bending_stress_MPa),
        service_total_stress_MPa=service_total,
        prestress_axial_stress_MPa=ps_axial,
        prestress_eccentric_stress_MPa=ps_ecc,
        prestress_total_stress_MPa=ps_total,
        total_stress_MPa=total,
        stress_type=_stress_type(total),
    )


def run_girder_service_stage_stress(
    basis: GirderSectionBasis,
    stage_case: GirderServiceStageCase,
) -> GirderServiceStageStressResult:
    """Return top/bottom combined stress for one manual girder stage case.

    ``stage_case`` is intentionally explicit.  The function does not decide
    which load should act in each stage; it only combines the trial service
    actions and optional effective prestress on the selected basis.
    """

    if not str(stage_case.stage_id).strip():
        raise ValueError("stage_id must not be blank.")
    if not str(stage_case.title).strip():
        raise ValueError("stage title must not be blank.")
    _require_finite("N_kN", stage_case.N_kN)
    _require_finite("M_kNm", stage_case.M_kNm)
    _require_finite("Pe_eff_kN", stage_case.Pe_eff_kN)
    if float(stage_case.Pe_eff_kN) < 0.0:
        raise ValueError("Pe_eff_kN must be nonnegative.")

    warnings: list[str] = []
    if stage_case.basis_name != basis.basis_name:
        warnings.append(
            f"Stage case basis '{stage_case.basis_name}' does not match selected basis '{basis.basis_name}'."
        )

    service_result = run_basic_girder_service_stress(
        basis,
        N_kN=float(stage_case.N_kN),
        M_kNm=float(stage_case.M_kNm),
        case_name=stage_case.title,
    )

    prestress_result: GirderPrestressStressResult | None = None
    if stage_case.include_prestress:
        if float(stage_case.Pe_eff_kN) <= 0.0:
            warnings.append("Prestress was requested for this stage, but Pe_eff_kN is zero. Prestress stress is omitted.")
        elif stage_case.tendon_y_from_bottom_mm is None:
            warnings.append("Prestress was requested for this stage, but tendon_y_from_bottom_mm is not defined. Prestress stress is omitted.")
        else:
            _require_finite("tendon_y_from_bottom_mm", stage_case.tendon_y_from_bottom_mm)
            prestress_result = run_girder_prestress_stress_effect(
                basis,
                Pe_eff_kN=float(stage_case.Pe_eff_kN),
                tendon_y_from_bottom_mm=float(stage_case.tendon_y_from_bottom_mm),
                case_name=stage_case.title,
            )
            warnings.extend(prestress_result.warnings)

    top = _combine_fiber_stress(
        service_result.top,
        prestress_result.top if prestress_result is not None else None,
        location="top",
    )
    bottom = _combine_fiber_stress(
        service_result.bottom,
        prestress_result.bottom if prestress_result is not None else None,
        location="bottom",
    )
    warnings.extend(service_result.warnings)
    return GirderServiceStageStressResult(
        stage_id=str(stage_case.stage_id),
        title=str(stage_case.title),
        basis_name=basis.basis_name,
        N_kN=float(stage_case.N_kN),
        M_kNm=float(stage_case.M_kNm),
        service_result=service_result,
        prestress_result=prestress_result,
        top=top,
        bottom=bottom,
        warnings=tuple(warnings),
        note=str(stage_case.note or ""),
    )


def default_girder_service_stage_templates() -> list[GirderServiceStageTemplate]:
    """Return suggested manual stage templates with no auto-generated actions.

    These templates are guidance for future UI/report layers only.  They do not
    calculate self-weight, deck weight, live load, losses, or code limits.
    """

    return [
        GirderServiceStageTemplate(
            stage_id="TRANSFER_PRECAST",
            title="Transfer / Precast-only stage",
            recommended_basis_name="precast_gross",
            include_prestress=True,
            engineering_note="Use precast gross properties; enter transfer-stage actions and effective prestress explicitly.",
        ),
        GirderServiceStageTemplate(
            stage_id="DECK_CASTING_PRECOMPOSITE",
            title="Deck casting / Pre-composite stage",
            recommended_basis_name="precast_gross",
            include_prestress=True,
            engineering_note="Use precast gross properties for wet deck/topping load before composite action is effective.",
        ),
        GirderServiceStageTemplate(
            stage_id="FINAL_SERVICE_COMPOSITE",
            title="Final service / Composite stage",
            recommended_basis_name="composite_transformed",
            include_prestress=True,
            engineering_note="Use transformed composite properties after composite action is active; enter superimposed/service actions explicitly.",
        ),
        GirderServiceStageTemplate(
            stage_id="LIVE_LOAD_COMPOSITE",
            title="Live load / Composite stage",
            recommended_basis_name="composite_transformed",
            include_prestress=False,
            engineering_note="Use transformed composite properties for live-load stress increment; combine with sustained stresses separately.",
        ),
    ]


def girder_service_stage_result_rows(result: GirderServiceStageStressResult) -> list[dict[str, Any]]:
    """Return stable top/bottom rows for future UI/report display."""

    return [
        {
            "Stage ID": result.stage_id,
            "Stage": result.title,
            "Fiber": "Top",
            "y from bottom (mm)": result.top.y_from_bottom_mm,
            "Service axial (MPa)": result.top.service_axial_stress_MPa,
            "Service bending (MPa)": result.top.service_bending_stress_MPa,
            "Service total (MPa)": result.top.service_total_stress_MPa,
            "PS axial (MPa)": result.top.prestress_axial_stress_MPa,
            "PS eccentric (MPa)": result.top.prestress_eccentric_stress_MPa,
            "PS total (MPa)": result.top.prestress_total_stress_MPa,
            "Total stress (MPa)": result.top.total_stress_MPa,
            "Stress type": result.top.stress_type,
        },
        {
            "Stage ID": result.stage_id,
            "Stage": result.title,
            "Fiber": "Bottom",
            "y from bottom (mm)": result.bottom.y_from_bottom_mm,
            "Service axial (MPa)": result.bottom.service_axial_stress_MPa,
            "Service bending (MPa)": result.bottom.service_bending_stress_MPa,
            "Service total (MPa)": result.bottom.service_total_stress_MPa,
            "PS axial (MPa)": result.bottom.prestress_axial_stress_MPa,
            "PS eccentric (MPa)": result.bottom.prestress_eccentric_stress_MPa,
            "PS total (MPa)": result.bottom.prestress_total_stress_MPa,
            "Total stress (MPa)": result.bottom.total_stress_MPa,
            "Stress type": result.bottom.stress_type,
        },
    ]


def girder_service_stage_result_to_dict(result: GirderServiceStageStressResult) -> dict[str, Any]:
    """Return a compact UI/report-friendly dictionary for one stage result."""

    return {
        "stage_id": result.stage_id,
        "title": result.title,
        "basis_name": result.basis_name,
        "N_kN": result.N_kN,
        "M_kNm": result.M_kNm,
        "includes_prestress": result.prestress_result is not None,
        "Pe_eff_kN": result.prestress_result.Pe_eff_kN if result.prestress_result is not None else 0.0,
        "tendon_y_from_bottom_mm": result.prestress_result.tendon_y_from_bottom_mm if result.prestress_result is not None else None,
        "top_total_stress_MPa": result.top.total_stress_MPa,
        "bottom_total_stress_MPa": result.bottom.total_stress_MPa,
        "max_compression_MPa": result.max_compression_MPa,
        "max_tension_MPa": result.max_tension_MPa,
        "warnings": list(result.warnings),
        "note": result.note,
    }
