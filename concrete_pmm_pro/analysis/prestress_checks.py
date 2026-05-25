"""Prestress analysis checks and lightweight PMM comparison helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from concrete_pmm_pro.analysis.result_models import PMMSolverResult, pmm_result_to_display_dataframe
from concrete_pmm_pro.core.models import PrestressElement

OK = "OK"
WARNING = "WARNING"
ERROR = "ERROR"
IGNORED = "IGNORED"


@dataclass(frozen=True)
class PrestressElementCheck:
    label: str
    steel_type: str
    bonded: bool
    area_mm2: float
    count: int
    fpu_MPa: float | None
    fpy_MPa: float | None
    Ep_MPa: float | None
    initial_stress_MPa: float | None
    initial_strain: float | None
    pe_eff_N: float | None
    status: str
    messages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PrestressCheckSummary:
    checks: list[PrestressElementCheck] = field(default_factory=list)
    ok_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    ignored_count: int = 0
    bonded_count: int = 0
    unbonded_count: int = 0
    total_area_mm2: float = 0.0
    total_pe_eff_N: float = 0.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _label_for(element: PrestressElement, index: int) -> str:
    return element.label or element.material_name or f"PS{index}"


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _stress_from_pe(pe_eff_N: float | None, area_mm2: float) -> float | None:
    if pe_eff_N is None or pe_eff_N <= 0.0 or area_mm2 <= 0.0:
        return None
    return pe_eff_N / area_mm2


def check_prestress_elements_for_analysis(
    prestress_elements: list[PrestressElement],
) -> PrestressCheckSummary:
    checks: list[PrestressElementCheck] = []
    summary_warnings: list[str] = []
    summary_errors: list[str] = []

    for index, element in enumerate(prestress_elements, start=1):
        label = _label_for(element, index)
        steel_type = str(getattr(element, "steel_type", "custom"))
        bonded = bool(getattr(element, "bonded", True))
        area = _float_or_none(getattr(element, "area_mm2", None)) or 0.0
        count = _int_or_zero(getattr(element, "count", 0))
        fpu = _float_or_none(getattr(element, "fpu_mpa", None))
        fpy = _float_or_none(getattr(element, "fpy_mpa", None))
        ep = _float_or_none(getattr(element, "ep_mpa", None))
        initial_stress = _float_or_none(getattr(element, "initial_stress_mpa", None))
        initial_strain = _float_or_none(getattr(element, "initial_strain", None))
        pe_eff = _float_or_none(getattr(element, "pe_eff_n", None))

        messages: list[str] = []
        errors: list[str] = []
        warnings: list[str] = []

        if area <= 0.0:
            errors.append("area_mm2 must be positive.")
        if count <= 0:
            errors.append("count must be at least 1.")
        if ep is None or ep <= 0.0:
            errors.append("Ep_MPa must be positive.")
        if bonded and (fpu is None or fpu <= 0.0):
            errors.append("fpu_MPa must be positive for active bonded prestress.")
        if fpy is not None and fpu is not None and fpy >= fpu:
            errors.append("fpy_MPa must be less than fpu_MPa.")
        if initial_stress is not None and fpu is not None and initial_stress > fpu:
            errors.append("initial_stress_MPa exceeds fpu_MPa.")

        pe_stress = _stress_from_pe(pe_eff, area)
        if pe_stress is not None and fpu is not None and pe_stress > fpu:
            warnings.append("Pe_eff_N produces stress greater than fpu_MPa.")
        if pe_stress is not None and fpy is not None and pe_stress > fpy and (fpu is None or pe_stress <= fpu):
            warnings.append("Pe_eff_N produces stress greater than fpy_MPa / proof stress.")
        if initial_stress is not None and fpu is not None and initial_stress > 0.85 * fpu and initial_stress <= fpu:
            warnings.append("initial_stress_MPa is high relative to fpu_MPa.")
        if initial_stress is not None and fpy is not None and initial_stress > fpy and (fpu is None or initial_stress <= fpu):
            warnings.append("initial_stress_MPa exceeds fpy_MPa / proof stress.")
        if initial_stress is None and (pe_eff is None or pe_eff <= 0.0) and initial_strain is None:
            warnings.append("No initial stress, initial strain, or Pe_eff_N is provided; element behaves as passive high-strength steel.")
        if not bonded:
            warnings.append("Unbonded prestress is ignored by the current solver.")
        if steel_type == "prestressing_bar" and fpy is None:
            warnings.append("prestressing_bar / PT Bar is missing fpy_MPa or proof stress.")
        if fpy is not None and fpu is not None and fpy < fpu and fpy > 0.90 * fpu:
            warnings.append("fpy_MPa is close to fpu_MPa; verify PT Bar proof stress and ultimate strength inputs.")
        if initial_strain is not None and initial_strain > 0.01:
            warnings.append("initial_strain is unusually high; verify prestress input.")

        messages.extend(errors)
        messages.extend(warnings)
        if not bonded:
            status = IGNORED
        elif errors:
            status = ERROR
        elif warnings:
            status = WARNING
        else:
            status = OK

        checks.append(
            PrestressElementCheck(
                label=label,
                steel_type=steel_type,
                bonded=bonded,
                area_mm2=area,
                count=count,
                fpu_MPa=fpu,
                fpy_MPa=fpy,
                Ep_MPa=ep,
                initial_stress_MPa=initial_stress,
                initial_strain=initial_strain,
                pe_eff_N=pe_eff,
                status=status,
                messages=messages,
            )
        )
        summary_errors.extend(f"{label}: {message}" for message in errors if bonded)
        summary_warnings.extend(f"{label}: {message}" for message in warnings)

    ok_count = sum(check.status == OK for check in checks)
    warning_count = sum(check.status == WARNING for check in checks)
    error_count = sum(check.status == ERROR for check in checks)
    ignored_count = sum(check.status == IGNORED for check in checks)
    bonded_count = sum(check.count for check in checks if check.bonded)
    unbonded_count = sum(check.count for check in checks if not check.bonded)
    total_area = sum(check.area_mm2 * check.count for check in checks if check.bonded and check.area_mm2 > 0)
    total_pe = sum((check.pe_eff_N or 0.0) * check.count for check in checks if check.bonded)

    return PrestressCheckSummary(
        checks=checks,
        ok_count=ok_count,
        warning_count=warning_count,
        error_count=error_count,
        ignored_count=ignored_count,
        bonded_count=bonded_count,
        unbonded_count=unbonded_count,
        total_area_mm2=total_area,
        total_pe_eff_N=total_pe,
        warnings=list(dict.fromkeys(summary_warnings)),
        errors=list(dict.fromkeys(summary_errors)),
    )


def summarize_prestress_contribution(result: PMMSolverResult) -> dict[str, Any]:
    if not result.points:
        return {
            "bonded_prestress_count": 0,
            "unbonded_prestress_ignored_count": 0,
            "max_abs_prestress_force_N": 0.0,
            "max_abs_prestress_force_kN": 0.0,
            "mean_abs_prestress_force_N": 0.0,
            "has_prestress_force": False,
            "point_count_with_prestress": 0,
            "warnings": ["PMM result has no points."],
        }

    warnings: list[str] = []
    forces = [abs(float(getattr(point, "prestress_force_N", 0.0) or 0.0)) for point in result.points]
    bonded_count = max(int(getattr(point, "bonded_prestress_count", 0) or 0) for point in result.points)
    unbonded_count = max(int(getattr(point, "unbonded_prestress_ignored_count", 0) or 0) for point in result.points)
    max_force = max(forces) if forces else 0.0
    mean_force = sum(forces) / len(forces) if forces else 0.0
    point_count_with_prestress = sum(force > 1.0e-9 for force in forces)
    has_prestress_force = max_force > 1.0e-9
    if bonded_count > 0 and not has_prestress_force:
        warnings.append("Bonded prestress is present but PMM points have near-zero prestress force.")
    if unbonded_count > 0:
        warnings.append("Unbonded prestress elements were ignored by the PMM solver.")

    return {
        "bonded_prestress_count": bonded_count,
        "unbonded_prestress_ignored_count": unbonded_count,
        "max_abs_prestress_force_N": max_force,
        "max_abs_prestress_force_kN": max_force / 1000.0,
        "mean_abs_prestress_force_N": mean_force,
        "has_prestress_force": has_prestress_force,
        "point_count_with_prestress": point_count_with_prestress,
        "warnings": warnings,
    }


def _envelope_values(result: PMMSolverResult) -> dict[str, float]:
    df = pmm_result_to_display_dataframe(result)
    if df.empty:
        return {"max_phiPn_kN": 0.0, "max_abs_phiMnx_kNm": 0.0, "max_abs_phiMny_kNm": 0.0}
    return {
        "max_phiPn_kN": float(df["phiPn_kN"].max()),
        "max_abs_phiMnx_kNm": float(df["phiMnx_kNm"].abs().max()),
        "max_abs_phiMny_kNm": float(df["phiMny_kNm"].abs().max()),
    }


def compare_rc_vs_prestress_pmm(
    rc_result: PMMSolverResult,
    prestress_result: PMMSolverResult,
) -> dict[str, Any]:
    rc_values = _envelope_values(rc_result)
    ps_values = _envelope_values(prestress_result)
    warnings: list[str] = []

    rc_point_count = len(rc_result.points)
    ps_point_count = len(prestress_result.points)
    if rc_point_count != ps_point_count:
        warnings.append("RC-only and RC + prestress PMM point counts differ.")

    contribution = summarize_prestress_contribution(prestress_result)
    if not contribution["has_prestress_force"]:
        warnings.append("Prestress PMM result has no measurable prestress force.")

    delta_phiPn = ps_values["max_phiPn_kN"] - rc_values["max_phiPn_kN"]
    delta_mnx = ps_values["max_abs_phiMnx_kNm"] - rc_values["max_abs_phiMnx_kNm"]
    delta_mny = ps_values["max_abs_phiMny_kNm"] - rc_values["max_abs_phiMny_kNm"]
    if contribution["bonded_prestress_count"] > 0 and all(abs(value) <= 1.0e-6 for value in (delta_phiPn, delta_mnx, delta_mny)):
        warnings.append(
            "Bonded prestress elements are present but PMM envelope change is near zero. "
            "Check prestress location, force, and solver settings."
        )

    return {
        "rc_point_count": rc_point_count,
        "ps_point_count": ps_point_count,
        "rc_max_phiPn_kN": rc_values["max_phiPn_kN"],
        "ps_max_phiPn_kN": ps_values["max_phiPn_kN"],
        "delta_max_phiPn_kN": delta_phiPn,
        "rc_max_abs_phiMnx_kNm": rc_values["max_abs_phiMnx_kNm"],
        "ps_max_abs_phiMnx_kNm": ps_values["max_abs_phiMnx_kNm"],
        "delta_max_abs_phiMnx_kNm": delta_mnx,
        "rc_max_abs_phiMny_kNm": rc_values["max_abs_phiMny_kNm"],
        "ps_max_abs_phiMny_kNm": ps_values["max_abs_phiMny_kNm"],
        "delta_max_abs_phiMny_kNm": delta_mny,
        "warnings": list(dict.fromkeys(warnings)),
    }
