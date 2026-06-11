from __future__ import annotations

import math

from concrete_pmm_pro.verification.rc_rectangular_benchmarks import (
    FAIL,
    PASS,
    build_valid_rc1_rectangular_input,
    reference_biaxial_pmm_point,
    reference_rc_po_N,
    reference_tied_phiPn_max_N,
    reference_uniaxial_mx_point,
    run_valid_rc1_benchmark_pack,
)
from concrete_pmm_pro.verification.validation_framework import run_pmm_solver_validation_report


def test_valid_rc1_input_is_rc_only_rectangular_benchmark() -> None:
    model = build_valid_rc1_rectangular_input()

    assert model.section_geometry.metadata["validation_case"] == "VALID.RC1"
    assert len(model.rebars) == 4
    assert model.settings.include_prestress is False
    assert not model.prestress_elements


def test_reference_rc_po_and_phi_cap_are_positive() -> None:
    model = build_valid_rc1_rectangular_input()
    po = reference_rc_po_N(40.0, 400.0, 600.0, model.rebars, 420.0)
    phi_pn = reference_tied_phiPn_max_N(po)

    assert po > 0.0
    assert phi_pn == 0.80 * 0.65 * po


def test_reference_uniaxial_mx_point_has_expected_components() -> None:
    point = reference_uniaxial_mx_point(c_mm=300.0)

    assert point["Pn_N"] > 0.0
    assert math.isfinite(point["Mnx_Nmm"])
    assert point["a_mm"] > 0.0
    assert len(point["rebar_details"]) == 4


def test_reference_biaxial_pmm_point_has_nonzero_biaxial_components() -> None:
    point = reference_biaxial_pmm_point(theta_rad=math.pi / 4.0, c_mm=300.0)

    assert point["Pn_N"] > 0.0
    assert math.isfinite(point["Mnx_Nmm"])
    assert math.isfinite(point["Mny_Nmm"])
    assert abs(point["Mnx_Nmm"]) > 0.0
    assert abs(point["Mny_Nmm"]) > 0.0
    assert point["concrete_area_mm2"] > 0.0
    assert point["compression_vertex_count"] >= 3
    assert len(point["rebar_details"]) == 4


def test_valid_rc1_benchmark_pack_runs_without_failures() -> None:
    summary = run_valid_rc1_benchmark_pack()

    assert summary.checks
    assert summary.overall_status != FAIL
    assert any(check.check_id == "VALID.RC1.PHI_PN_MAX" for check in summary.checks)
    assert any(check.check_id == "VALID.RC1.MX_C300_MNX" for check in summary.checks)
    assert any(check.check_id == "VALID.RC1.BIAX_CDIAG_PN" for check in summary.checks)
    assert any(check.check_id == "VALID.RC1.BIAX_CDIAG_MNX" for check in summary.checks)
    assert any(check.check_id == "VALID.RC1.BIAX_CDIAG_MNY" for check in summary.checks)
    assert any(check.check_id == "VALID.RC1.NUMERIC_SCHEMA" and check.status == PASS for check in summary.checks)


def test_valid_rc1_dataframe_is_report_ready() -> None:
    summary = run_valid_rc1_benchmark_pack()
    df = summary.to_dataframe()

    assert not df.empty
    assert {"Check ID", "Title", "Status", "Reference", "Solver", "Difference (%)", "Tolerance (%)"}.issubset(df.columns)


def test_validation_report_includes_valid_rc1_execution() -> None:
    report = run_pmm_solver_validation_report()
    case_ids = {case.case_id for case in report.validation_cases}

    assert "VALID.RC1" in case_ids
    assert report.rc_benchmarks.checks
    assert report.rc_benchmarks.overall_status != FAIL
