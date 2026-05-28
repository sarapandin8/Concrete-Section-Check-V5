from __future__ import annotations

from concrete_pmm_pro.verification.dc_directional_benchmarks import run_valid_dc1_directional_benchmark_pack


def test_valid_dc1_directional_benchmark_pack_passes() -> None:
    summary = run_valid_dc1_directional_benchmark_pack()

    assert summary.overall_status == "PASS"
    assert summary.fail_count == 0
    assert summary.pass_count == 3


def test_valid_dc1_summary_dataframe_contains_expected_checks() -> None:
    summary = run_valid_dc1_directional_benchmark_pack()
    df = summary.to_dataframe()

    assert set(df["Check ID"]) == {
        "SOLVER.PMM.DC1.RECT_X_RAY",
        "SOLVER.PMM.DC1.RECT_DIAGONAL_RAY",
        "SOLVER.PMM.DC1.DC_SUMMARY_PRIMARY",
    }
