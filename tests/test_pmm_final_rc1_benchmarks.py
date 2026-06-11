from __future__ import annotations

from concrete_pmm_pro.verification.pmm_final_rc1_benchmarks import run_pmm_final_rc1_readiness_gate


def test_pmm_final_rc1_readiness_gate_runs_without_failures() -> None:
    summary = run_pmm_final_rc1_readiness_gate()

    assert summary.checks
    assert summary.fail_count == 0
    assert summary.overall_status in {"PASS", "WARNING"}
    assert "Finalized production-preview" in summary.design_use_status or "final-readiness blockers" in summary.design_use_status
    assert "not final certification" in summary.design_use_status or "final-readiness blockers" in summary.design_use_status


def test_pmm_final_rc1_readiness_gate_tracks_core_gate_ids() -> None:
    summary = run_pmm_final_rc1_readiness_gate()
    check_ids = {check.check_id for check in summary.checks}

    assert "PMM.FINAL.RC1.SCOPE" in check_ids
    assert "PMM.FINAL.RC1.UNIAXIAL.REF" in check_ids
    assert "PMM.FINAL.RC1.PHI" in check_ids
    assert "PMM.FINAL.RC1.DC.NO_OVERESTIMATE" in check_ids
    assert "PMM.FINAL.RC1.BIAXIAL.REF" in check_ids
    assert "PMM.FINAL.RC1.WARNING" in check_ids
    assert "PMM.FINAL.RC1.STATUS.READINESS1" in check_ids


def test_pmm_final_rc1_dc_gate_includes_rc_specific_no_overestimate_check() -> None:
    summary = run_pmm_final_rc1_readiness_gate()
    dc = next(check for check in summary.checks if check.check_id == "PMM.FINAL.RC1.DC.NO_OVERESTIMATE")

    assert dc.details["SOLVER.PMM.DC1.RC_RECT_PRIMARY_NO_OVERESTIMATE"] == "PASS"


def test_pmm_final_rc1_biaxial_reference_is_executable() -> None:
    summary = run_pmm_final_rc1_readiness_gate()
    biaxial = next(check for check in summary.checks if check.check_id == "PMM.FINAL.RC1.BIAXIAL.REF")

    assert biaxial.status == "PASS"
    assert "diagonal biaxial reference checks are available" in biaxial.message
    assert biaxial.details["VALID.RC1.BIAX_CDIAG_PN"] == "PASS"
    assert biaxial.details["VALID.RC1.BIAX_CDIAG_MNX"] == "PASS"
    assert biaxial.details["VALID.RC1.BIAX_CDIAG_MNY"] == "PASS"


def test_pmm_final_rc1_status_readiness_keeps_production_preview_separate_from_certification() -> None:
    summary = run_pmm_final_rc1_readiness_gate()
    readiness = next(check for check in summary.checks if check.check_id == "PMM.FINAL.RC1.STATUS.READINESS1")

    assert readiness.details["allowed_status"] == "ACI RC Flexural PMM finalized production preview"
    assert readiness.details["forbidden_status"] == "Final code-certified ACI/AASHTO PMM design"
    assert readiness.details["ui_report_milestone_required"] == "PMM.FINAL.RC1.CLOSEOUT"
    assert "AASHTO LRFD PMM" in readiness.details["excluded"]
    assert "not claim final certification" in readiness.message


def test_pmm_final_rc1_dataframe_is_report_ready() -> None:
    summary = run_pmm_final_rc1_readiness_gate()
    df = summary.to_dataframe()

    assert not df.empty
    assert {"Check ID", "Title", "Status", "Message", "Details"}.issubset(set(df.columns))
