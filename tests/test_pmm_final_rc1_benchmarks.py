from __future__ import annotations

from concrete_pmm_pro.verification.pmm_final_rc1_benchmarks import run_pmm_final_rc1_readiness_gate


def test_pmm_final_rc1_readiness_gate_runs_with_expected_warning_status() -> None:
    summary = run_pmm_final_rc1_readiness_gate()

    assert summary.checks
    assert summary.fail_count == 0
    assert summary.overall_status == "WARNING"
    assert "final-readiness blockers" in summary.design_use_status


def test_pmm_final_rc1_readiness_gate_tracks_core_gate_ids() -> None:
    summary = run_pmm_final_rc1_readiness_gate()
    check_ids = {check.check_id for check in summary.checks}

    assert "PMM.FINAL.RC1.SCOPE" in check_ids
    assert "PMM.FINAL.RC1.UNIAXIAL.REF" in check_ids
    assert "PMM.FINAL.RC1.PHI" in check_ids
    assert "PMM.FINAL.RC1.DC.NO_OVERESTIMATE" in check_ids
    assert "PMM.FINAL.RC1.BIAXIAL.REF" in check_ids
    assert "PMM.FINAL.RC1.WARNING" in check_ids


def test_pmm_final_rc1_biaxial_reference_remains_blocking_warning() -> None:
    summary = run_pmm_final_rc1_readiness_gate()
    biaxial = next(check for check in summary.checks if check.check_id == "PMM.FINAL.RC1.BIAXIAL.REF")

    assert biaxial.status == "WARNING"
    assert "true biaxial ACI RC reference case is still required" in biaxial.message


def test_pmm_final_rc1_dataframe_is_report_ready() -> None:
    summary = run_pmm_final_rc1_readiness_gate()
    df = summary.to_dataframe()

    assert not df.empty
    assert {"Check ID", "Title", "Status", "Message", "Details"}.issubset(set(df.columns))

