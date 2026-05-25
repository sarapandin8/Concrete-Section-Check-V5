from __future__ import annotations

import math

import pandas as pd

from concrete_pmm_pro.analysis.capacity_check import DemandCapacityResult, DemandCapacitySummary
from concrete_pmm_pro.analysis.result_models import check_pmm_dataframe_numerics
from concrete_pmm_pro.analysis.slice_envelope import build_slice_envelope
from concrete_pmm_pro.analysis.warnings import (
    DCR_PROTOTYPE_WARNING,
    PMM_PROTOTYPE_WARNING,
    deduplicate_warnings,
)
from concrete_pmm_pro.visualization.pmm_dashboard import (
    demand_capacity_result_to_display_dataframe,
    pmm_slice_export_dataframe,
    slice_envelope_export_dataframe,
)


def _dc_summary() -> DemandCapacitySummary:
    return DemandCapacitySummary(
        results=[
            DemandCapacityResult(
                combo_name="ULS-01",
                Pu_N=1_000_000.0,
                Mux_Nmm=50_000_000.0,
                Muy_Nmm=0.0,
                Mu_Nmm=50_000_000.0,
                moment_angle_rad=0.0,
                capacity_Mn_Nmm=None,
                capacity_phiMn_Nmm=100_000_000.0,
                capacity_phiPn_N=1_000_000.0,
                dcr=0.5,
                status="PASS",
                message="Checked using PMM slice envelope at Pu.",
                capacity_method="slice_envelope",
                slice_method="interpolated",
                envelope_method="polar_max",
                used_fallback=False,
                warning_count=1,
            )
        ]
    )


def _slice_df() -> pd.DataFrame:
    rows = []
    for index in range(12):
        angle = 2.0 * math.pi * index / 12
        rows.append(
            {
                "phiPn_kN": 1000.0,
                "phiMnx_kNm": 100.0 * math.cos(angle),
                "phiMny_kNm": 100.0 * math.sin(angle),
                "theta_rad": angle,
                "c_mm": 250.0,
            }
        )
    df = pd.DataFrame(rows)
    df.attrs["method"] = "interpolated"
    return df


def test_pmm_dataframe_numerics_detects_nan() -> None:
    result = check_pmm_dataframe_numerics(pd.DataFrame({"phiPn_kN": [1.0, float("nan")]}))

    assert result["has_nan"] is True
    assert "phiPn_kN" in result["nan_columns"]


def test_pmm_dataframe_numerics_detects_inf() -> None:
    result = check_pmm_dataframe_numerics(pd.DataFrame({"phiMnx_kNm": [1.0, float("inf")]}))

    assert result["has_inf"] is True
    assert "phiMnx_kNm" in result["inf_columns"]


def test_pmm_dataframe_numerics_clean_dataframe_has_no_nan_inf() -> None:
    result = check_pmm_dataframe_numerics(
        pd.DataFrame({"phiPn_kN": [1.0], "phiMnx_kNm": [2.0], "phiMny_kNm": [3.0]})
    )

    assert result["has_nan"] is False
    assert result["has_inf"] is False
    assert result["warnings"] == []


def test_pmm_dataframe_numerics_handles_large_clean_dataframe() -> None:
    df = pd.DataFrame(
        {
            "phiPn_kN": [float(index) for index in range(1000)],
            "phiMnx_kNm": [float(index) * 2.0 for index in range(1000)],
            "phiMny_kNm": [float(index) * -1.5 for index in range(1000)],
        }
    )

    result = check_pmm_dataframe_numerics(df)

    assert result["row_count"] == 1000
    assert result["has_nan"] is False
    assert result["has_inf"] is False


def test_demand_capacity_display_dataframe_includes_method_fields() -> None:
    df = demand_capacity_result_to_display_dataframe(_dc_summary())

    for column in ["Capacity Method", "Slice Method", "Envelope Method", "Used Fallback"]:
        assert column in df.columns
    assert df.loc[0, "Capacity Method"] == "slice_envelope"


def test_demand_capacity_display_dataframe_preserves_essential_columns() -> None:
    df = demand_capacity_result_to_display_dataframe(_dc_summary())

    for column in ["Combo", "Pu_kN", "Mux_kNm", "Muy_kNm", "Mu_kNm", "Capacity_phiMn_kNm", "D/C", "Status", "Message"]:
        assert column in df.columns


def test_standardized_warning_constants_are_importable() -> None:
    assert "prototype" in PMM_PROTOTYPE_WARNING.lower()
    assert "Demand/capacity" in DCR_PROTOTYPE_WARNING


def test_duplicate_warning_cleanup_preserves_order() -> None:
    warnings = deduplicate_warnings(["A", "B", "A", "", "C", "B"])

    assert warnings == ["A", "B", "C"]


def test_pmm_slice_csv_dataframe_can_be_generated_for_synthetic_slice() -> None:
    export_df = pmm_slice_export_dataframe(_slice_df())

    assert {"phiPn_kN", "phiMnx_kNm", "phiMny_kNm", "angle_rad", "radius_kNm", "slice_method"}.issubset(export_df.columns)


def test_slice_envelope_csv_dataframe_can_be_generated_for_synthetic_envelope() -> None:
    envelope = build_slice_envelope(_slice_df())
    export_df = slice_envelope_export_dataframe(envelope)

    assert {"phiMnx_kNm", "phiMny_kNm", "angle_rad", "radius_kNm", "envelope_method"}.issubset(export_df.columns)


def test_analysis_page_imports_without_error_for_cleanup_milestone() -> None:
    from concrete_pmm_pro.ui import analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
