"""Passive prestressing steel validation benchmark pack.

SOLVER.PS.PASSIVE1 separates passive prestressing steel rows from active
prestress rows.  Passive rows (Pe_eff/fpe/initial_strain equal to zero) should
act as bonded high-strength steel in PMM strain compatibility without emitting
active-prestress compression-reversal or fpu-cap warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.analysis.result_models import pmm_result_to_display_dataframe
from concrete_pmm_pro.core.models import PrestressElement
from concrete_pmm_pro.verification.ps_bonded_benchmarks import PASS, FAIL, WARNING, rc_plus_ps_input


@dataclass(frozen=True)
class PSPassiveBenchmarkCheck:
    """Single passive-prestress validation check."""

    check_id: str
    title: str
    status: str
    reference_value: float | None
    solver_value: float | None
    percent_difference: float | None
    tolerance_percent: float | None
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PSPassiveBenchmarkSummary:
    """Summary for the passive prestressing-steel benchmark pack."""

    checks: list[PSPassiveBenchmarkCheck]
    pass_count: int
    warning_count: int
    fail_count: int
    overall_status: str

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "Check ID": check.check_id,
                    "Title": check.title,
                    "Status": check.status,
                    "Reference": check.reference_value,
                    "Solver": check.solver_value,
                    "Difference (%)": check.percent_difference,
                    "Tolerance (%)": check.tolerance_percent,
                    "Message": check.message,
                }
                for check in self.checks
            ]
        )


def _summary(checks: list[PSPassiveBenchmarkCheck]) -> PSPassiveBenchmarkSummary:
    pass_count = sum(check.status == PASS for check in checks)
    warning_count = sum(check.status == WARNING for check in checks)
    fail_count = sum(check.status == FAIL for check in checks)
    overall = FAIL if fail_count else WARNING if warning_count else PASS
    return PSPassiveBenchmarkSummary(checks, pass_count, warning_count, fail_count, overall)


def passive_pt_bar_element(**updates: object) -> PrestressElement:
    """Return a passive bonded PT bar benchmark element."""

    data = {
        "x_mm": 100.0,
        "y_mm": -250.0,
        "area_mm2": 804.2,
        "steel_type": "prestressing_bar",
        "material_name": "PS Bar 32 - 1080/1230",
        "diameter_mm": 32.0,
        "fpy_mpa": 1080.0,
        "fpu_mpa": 1230.0,
        "ep_mpa": 200000.0,
        "pe_eff_n": 0.0,
        "initial_stress_mpa": None,
        "initial_strain": None,
        "bonded": True,
        "count": 1,
        "label": "PS-PASSIVE",
    }
    data.update(updates)
    return PrestressElement(**data)


def passive_rc_plus_ps_input(**updates: object):
    """Return an RC + passive high-strength PS-bar benchmark model."""

    element = passive_pt_bar_element(**updates)
    model = rc_plus_ps_input(pe_eff_n=0.0, initial_stress_mpa=None, initial_strain=None, fpy_mpa=1080.0, fpu_mpa=1230.0)
    model.prestress_elements = [element]
    return model


def _check_no_active_prestress_warnings_for_passive_rows() -> PSPassiveBenchmarkCheck:
    result = run_rc_pmm_solver(passive_rc_plus_ps_input())
    lower_warnings = [warning.lower() for warning in result.warnings]
    active_warning_count = sum(
        ("compression reversal" in warning)
        or ("reached fpu cap" in warning)
        or ("active prestress stress model" in warning)
        or ("bonded prestress is included" in warning)
        for warning in lower_warnings
    )
    ok = active_warning_count == 0
    return PSPassiveBenchmarkCheck(
        check_id="SOLVER.PS.PASSIVE1.NO_ACTIVE_WARNINGS",
        title="Passive PS rows do not emit active-prestress stress warnings",
        status=PASS if ok else FAIL,
        reference_value=0.0,
        solver_value=float(active_warning_count),
        percent_difference=0.0 if ok else 100.0,
        tolerance_percent=0.0,
        message=(
            "Passive Pe_eff=0 rows are included without active-prestress compression-reversal/fpu-cap warnings."
            if ok
            else "Passive rows still emit active-prestress warnings; classification is not clean."
        ),
        details={"warnings": result.warnings},
    )


def _check_passive_rows_contribute_signed_force() -> PSPassiveBenchmarkCheck:
    result = run_rc_pmm_solver(passive_rc_plus_ps_input())
    forces = [point.prestress_force_N for point in result.points]
    has_tension = any(force < 0.0 for force in forces)
    has_compression = any(force > 0.0 for force in forces)
    ok = has_tension and has_compression
    return PSPassiveBenchmarkCheck(
        check_id="SOLVER.PS.PASSIVE1.SIGNED_FORCE",
        title="Passive PS rows contribute signed strain-compatible force",
        status=PASS if ok else FAIL,
        reference_value=1.0,
        solver_value=1.0 if ok else 0.0,
        percent_difference=0.0 if ok else 100.0,
        tolerance_percent=0.0,
        message=(
            "Passive prestressing steel produces tension and compression force states across the PMM sweep."
            if ok
            else "Passive prestressing steel did not produce signed force states; strain compatibility should be reviewed."
        ),
        details={"min_force_N": min(forces) if forces else None, "max_force_N": max(forces) if forces else None},
    )


def _check_passive_rows_track_eps_t_for_phi() -> PSPassiveBenchmarkCheck:
    result = run_rc_pmm_solver(passive_rc_plus_ps_input())
    tension_points = [point for point in result.points if point.eps_t is not None]
    has_transition_or_tension = any(point.strain_condition in {"transition", "tension-controlled"} for point in tension_points)
    ok = bool(tension_points) and has_transition_or_tension
    return PSPassiveBenchmarkCheck(
        check_id="SOLVER.PS.PASSIVE1.EPST_PHI",
        title="Passive PS rows can control eps_t and phi transition",
        status=PASS if ok else FAIL,
        reference_value=1.0,
        solver_value=1.0 if ok else 0.0,
        percent_difference=0.0 if ok else 100.0,
        tolerance_percent=0.0,
        message=(
            "Passive high-strength steel can provide tensile strain control for phi evaluation."
            if ok
            else "Passive high-strength steel did not contribute eps_t for phi evaluation."
        ),
        details={"tension_point_count": len(tension_points)},
    )


def _check_passive_metadata_is_reportable() -> PSPassiveBenchmarkCheck:
    result = run_rc_pmm_solver(passive_rc_plus_ps_input())
    df = pmm_result_to_display_dataframe(result)
    required = {"prestress_force_kN", "max_prestress_stress_MPa", "prestress_compression_reversal_count", "prestress_reached_fpu_cap_count"}
    missing = sorted(required.difference(df.columns))
    no_active_events = True
    if not missing and not df.empty:
        no_active_events = (
            pd.to_numeric(df["prestress_compression_reversal_count"], errors="coerce").fillna(0).sum() == 0
            and pd.to_numeric(df["prestress_reached_fpu_cap_count"], errors="coerce").fillna(0).sum() == 0
        )
    ok = not missing and no_active_events
    return PSPassiveBenchmarkCheck(
        check_id="SOLVER.PS.PASSIVE1.METADATA",
        title="Passive PS metadata remains reportable without active event counts",
        status=PASS if ok else FAIL,
        reference_value=0.0,
        solver_value=float(len(missing)) if missing else 0.0,
        percent_difference=0.0 if ok else 100.0,
        tolerance_percent=0.0,
        message=(
            "Display data keeps prestress-force metadata while active-prestress event counts remain zero."
            if ok
            else "Passive display metadata is incomplete or still reports active-prestress events."
        ),
        details={"missing_columns": missing, "point_count": len(df)},
    )


def run_valid_ps_passive_benchmark_pack() -> PSPassiveBenchmarkSummary:
    """Run SOLVER.PS.PASSIVE1 validation checks."""

    return _summary(
        [
            _check_no_active_prestress_warnings_for_passive_rows(),
            _check_passive_rows_contribute_signed_force(),
            _check_passive_rows_track_eps_t_for_phi(),
            _check_passive_metadata_is_reportable(),
        ]
    )
