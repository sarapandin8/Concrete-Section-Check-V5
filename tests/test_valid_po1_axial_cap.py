from __future__ import annotations

from concrete_pmm_pro.verification.po_axial_cap_benchmarks import run_valid_po1_axial_cap_benchmark_pack


def test_valid_po1_axial_cap_benchmark_pack_passes() -> None:
    summary = run_valid_po1_axial_cap_benchmark_pack()

    assert summary.overall_status == "PASS"
    assert summary.fail_count == 0
    assert summary.pass_count >= 7


def test_valid_po1_axial_cap_checks_cover_key_failure_modes() -> None:
    summary = run_valid_po1_axial_cap_benchmark_pack()
    check_ids = {check.check_id for check in summary.checks}

    assert "QA.PO1.RC_ONLY" in check_ids
    assert "QA.PO1.PS_ONLY_FPY" in check_ids
    assert "QA.PO1.RC_PLUS_PS" in check_ids
    assert "QA.PO1.FPU_FALLBACK_NOT_PE" in check_ids
    assert "QA.PO1.COUNT_MULTIPLIER" in check_ids
    assert "QA.PO1.PHIPN_CAP_TIED" in check_ids
    assert "QA.PO1.UNBONDED_EXCLUDED_BY_CALLER" in check_ids


def test_valid_po1_axial_cap_dataframe_is_exportable() -> None:
    df = run_valid_po1_axial_cap_benchmark_pack().to_dataframe()

    assert not df.empty
    assert {"Check ID", "Title", "Status", "Reference", "Solver", "Message"}.issubset(df.columns)
    assert set(df["Status"]) == {"PASS"}
