"""RC phi-transition validation benchmark pack.

VALID.RC2 verifies the ACI-style strength-reduction factor transition used by
Concrete PMM Pro for ordinary RC sections.  It deliberately stays independent
from Streamlit and uses the public phi helper as the transparent reference for
compression-controlled, transition, and tension-controlled strain states.
"""

from __future__ import annotations

import math
from typing import Any

from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.code_checks import aci_phi_and_strain_condition
from concrete_pmm_pro.verification.rc_rectangular_benchmarks import (
    FAIL,
    PASS,
    WARNING,
    RCBenchmarkCheck,
    RCBenchmarkSummary,
    _summary,
    build_valid_rc1_rectangular_input,
)


def _percent_difference(reference: float, solver: float) -> float:
    return abs(solver - reference) / max(abs(reference), 1.0) * 100.0


def _direct_phi_spot_check(
    check_id: str,
    title: str,
    eps_t: float | None,
    expected_phi: float,
    expected_condition: str,
    fy_MPa: float = 420.0,
    Es_MPa: float = 200000.0,
    tolerance: float = 1.0e-9,
) -> RCBenchmarkCheck:
    phi, condition = aci_phi_and_strain_condition(eps_t, fy_MPa, Es_MPa, "tied")
    ok = abs(phi - expected_phi) <= tolerance and condition == expected_condition
    return RCBenchmarkCheck(
        check_id=check_id,
        title=title,
        status=PASS if ok else FAIL,
        reference_value=expected_phi,
        solver_value=phi,
        percent_difference=_percent_difference(expected_phi, phi),
        tolerance_percent=0.0,
        message=(
            f"Phi helper returns {expected_condition} behavior as expected."
            if ok
            else f"Phi helper returned phi={phi:g}, condition={condition!r}; expected phi={expected_phi:g}, condition={expected_condition!r}."
        ),
        details={"eps_t": eps_t, "condition": condition, "expected_condition": expected_condition},
    )


def run_valid_rc2_phi_transition_benchmark_pack() -> RCBenchmarkSummary:
    """Run VALID.RC2 phi-transition checks for a rectangular RC section."""

    fy = 420.0
    Es = 200000.0
    eps_y = fy / Es
    tension_threshold = eps_y + 0.003
    transition_eps = eps_y + 0.0015
    expected_transition_phi = 0.65 + 0.5 * (0.90 - 0.65)
    checks: list[RCBenchmarkCheck] = [
        _direct_phi_spot_check(
            "VALID.RC2.PHI_COMPRESSION_EDGE",
            "Phi compression-controlled boundary",
            eps_y,
            0.65,
            "compression-controlled",
            fy,
            Es,
        ),
        _direct_phi_spot_check(
            "VALID.RC2.PHI_TRANSITION_MID",
            "Phi transition interpolation midpoint",
            transition_eps,
            expected_transition_phi,
            "transition",
            fy,
            Es,
        ),
        _direct_phi_spot_check(
            "VALID.RC2.PHI_TENSION_EDGE",
            "Phi tension-controlled boundary",
            tension_threshold,
            0.90,
            "tension-controlled",
            fy,
            Es,
        ),
        _direct_phi_spot_check(
            "VALID.RC2.PHI_NONE_COMPRESSION",
            "Phi when no tensile strain controls",
            None,
            0.65,
            "compression-controlled",
            fy,
            Es,
        ),
    ]

    analysis_input = build_valid_rc1_rectangular_input(fy_MPa=fy)
    # Use enough depth resolution to sample all phi regions while keeping the
    # benchmark fast and deterministic.
    analysis_input.settings.neutral_axis_depth_steps = 121
    result = run_rc_pmm_solver(analysis_input)

    if not result.points:
        checks.append(
            RCBenchmarkCheck(
                check_id="VALID.RC2.EMPTY",
                title="Solver points are available for phi validation",
                status=FAIL,
                reference_value=None,
                solver_value=None,
                percent_difference=None,
                tolerance_percent=None,
                message="Solver returned no PMM points for RC phi-transition validation.",
            )
        )
        return _summary(checks)

    condition_counts = {"compression-controlled": 0, "transition": 0, "tension-controlled": 0}
    phi_mismatch_count = 0
    worst_phi_error = 0.0
    mismatch_examples: list[dict[str, Any]] = []
    for point in result.points:
        condition_counts[point.strain_condition] = condition_counts.get(point.strain_condition, 0) + 1
        reference_phi, reference_condition = aci_phi_and_strain_condition(point.eps_t, fy, Es, "tied")
        phi_error = abs(point.phi - reference_phi)
        worst_phi_error = max(worst_phi_error, phi_error)
        if phi_error > 1.0e-12 or point.strain_condition != reference_condition:
            phi_mismatch_count += 1
            if len(mismatch_examples) < 5:
                mismatch_examples.append(
                    {
                        "theta_rad": point.theta_rad,
                        "c_mm": point.c_mm,
                        "eps_t": point.eps_t,
                        "solver_phi": point.phi,
                        "reference_phi": reference_phi,
                        "solver_condition": point.strain_condition,
                        "reference_condition": reference_condition,
                    }
                )

    has_all_regions = all(condition_counts.get(condition, 0) > 0 for condition in condition_counts)
    checks.append(
        RCBenchmarkCheck(
            check_id="VALID.RC2.SOLVER_REGION_COVERAGE",
            title="Solver samples compression, transition, and tension-controlled phi regions",
            status=PASS if has_all_regions else FAIL,
            reference_value=3.0,
            solver_value=float(sum(1 for count in condition_counts.values() if count > 0)),
            percent_difference=0.0 if has_all_regions else 100.0,
            tolerance_percent=0.0,
            message=(
                "The rectangular RC benchmark samples all ACI phi strain regions."
                if has_all_regions
                else "The rectangular RC benchmark did not sample every phi strain region."
            ),
            details={"condition_counts": condition_counts, "point_count": len(result.points)},
        )
    )

    checks.append(
        RCBenchmarkCheck(
            check_id="VALID.RC2.SOLVER_PHI_MATCH",
            title="Solver point phi values match independent ACI phi helper",
            status=PASS if phi_mismatch_count == 0 and worst_phi_error <= 1.0e-12 else FAIL,
            reference_value=0.0,
            solver_value=float(phi_mismatch_count),
            percent_difference=0.0 if phi_mismatch_count == 0 else 100.0,
            tolerance_percent=0.0,
            message=(
                "Every RC benchmark PMM point has phi and strain-condition labels consistent with the independent phi helper."
                if phi_mismatch_count == 0
                else "At least one PMM point has inconsistent phi or strain-condition classification."
            ),
            details={
                "mismatch_count": phi_mismatch_count,
                "worst_phi_error": worst_phi_error,
                "examples": mismatch_examples,
            },
        )
    )

    phi_min = min(point.phi for point in result.points)
    phi_max = max(point.phi for point in result.points)
    phi_range_ok = math.isclose(phi_min, 0.65, rel_tol=0.0, abs_tol=1.0e-12) and math.isclose(
        phi_max, 0.90, rel_tol=0.0, abs_tol=1.0e-12
    )
    checks.append(
        RCBenchmarkCheck(
            check_id="VALID.RC2.SOLVER_PHI_RANGE",
            title="Solver phi range remains within tied-column ACI limits",
            status=PASS if phi_range_ok else WARNING,
            reference_value=0.90,
            solver_value=phi_max,
            percent_difference=0.0 if phi_range_ok else _percent_difference(0.90, phi_max),
            tolerance_percent=0.0,
            message=(
                "Solver phi range spans the tied-column limits 0.65 to 0.90."
                if phi_range_ok
                else "Solver phi range does not span the expected tied-column limits exactly; review discretization and phi inputs."
            ),
            details={"phi_min": phi_min, "phi_max": phi_max},
        )
    )

    return _summary(checks)
