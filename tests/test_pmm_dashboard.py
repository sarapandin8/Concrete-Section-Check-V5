from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import pytest

from concrete_pmm_pro.analysis.capacity_check import DemandCapacityResult, DemandCapacitySummary
from concrete_pmm_pro.analysis.capacity_check import check_uls_demands_against_rc_pmm
from concrete_pmm_pro.analysis.result_models import PMMPoint, PMMSolverResult
from concrete_pmm_pro.core.models import LoadCase
from concrete_pmm_pro.visualization.pmm_dashboard import (
    STATUS_COLORS,
    build_selected_load_case_summary,
    demand_load_cases_to_display_dataframe,
    estimate_directional_capacity_from_slice,
    make_mux_muy_slice_figure,
    make_pmm_3d_dashboard_figure,
    pmm_surface_data_adapter,
    pmm_slice_at_pu,
    pmm_slice_at_pu_interpolated,
    rank_load_cases_by_dcr,
)


def _synthetic_pmm_df() -> pd.DataFrame:
    rows = []
    for p_kN in (900.0, 1000.0, 1100.0):
        for angle in (-math.pi, -3 * math.pi / 4, -math.pi / 2, -math.pi / 4, 0.0, math.pi / 4, math.pi / 2, 3 * math.pi / 4):
            rows.append(
                {
                    "theta_rad": angle,
                    "phiPn_kN": p_kN,
                    "phiPn_capped_kN": p_kN,
                    "phiMnx_kNm": 100.0 * math.cos(angle),
                    "phiMny_kNm": 100.0 * math.sin(angle),
                    "phi": 0.65,
                    "strain_condition": "compression-controlled",
                }
            )
    return pd.DataFrame(rows)


def _synthetic_interpolated_pmm_df(theta_count: int = 8) -> pd.DataFrame:
    rows = []
    for index in range(theta_count):
        theta = 2.0 * math.pi * index / theta_count
        for p_kN, radius, c_mm in ((900.0, 90.0, 100.0), (1100.0, 110.0, 200.0)):
            rows.append(
                {
                    "theta_rad": theta,
                    "c_mm": c_mm,
                    "phiPn_kN": p_kN,
                    "phiPn_capped_kN": p_kN,
                    "phiMnx_kNm": radius * math.cos(theta),
                    "phiMny_kNm": radius * math.sin(theta),
                    "phi": 0.65,
                    "strain_condition": "compression-controlled",
                }
            )
    return pd.DataFrame(rows)


def _circular_slice(radius_kNm: float = 100.0, theta_count: int = 16) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "theta_rad": 2.0 * math.pi * index / theta_count,
                "phiPn_kN": 1000.0,
                "phiMnx_kNm": radius_kNm * math.cos(2.0 * math.pi * index / theta_count),
                "phiMny_kNm": radius_kNm * math.sin(2.0 * math.pi * index / theta_count),
            }
            for index in range(theta_count)
        ]
    )


def _irregular_pmm_point_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"P_kN": 900.0 + 25.0 * index, "Mx_kNm": 80.0 * math.cos(index), "My_kNm": 60.0 * math.sin(index)}
            for index in range(10)
        ]
    )


def _synthetic_interpolated_result() -> PMMSolverResult:
    points = []
    for row in _synthetic_interpolated_pmm_df().itertuples():
        points.append(
            PMMPoint(
                theta_rad=float(row.theta_rad),
                c_mm=float(row.c_mm),
                Pn_N=float(row.phiPn_kN) * 1000.0,
                Mnx_Nmm=float(row.phiMnx_kNm) * 1_000_000.0,
                Mny_Nmm=float(row.phiMny_kNm) * 1_000_000.0,
                phi=0.65,
                phiPn_N=float(row.phiPn_kN) * 1000.0,
                phiPn_capped_N=float(row.phiPn_kN) * 1000.0,
                phiMnx_Nmm=float(row.phiMnx_kNm) * 1_000_000.0,
                phiMny_Nmm=float(row.phiMny_kNm) * 1_000_000.0,
                eps_t=None,
                strain_condition="compression-controlled",
                concrete_area_mm2=1.0,
                concrete_force_N=1.0,
            )
        )
    return PMMSolverResult(points=points)


def _dc_summary() -> DemandCapacitySummary:
    return DemandCapacitySummary(
        results=[
            DemandCapacityResult(
                combo_name="ULS-FAIL",
                Pu_N=1_000_000.0,
                Mux_Nmm=130_000_000.0,
                Muy_Nmm=0.0,
                Mu_Nmm=130_000_000.0,
                moment_angle_rad=0.0,
                capacity_Mn_Nmm=None,
                capacity_phiMn_Nmm=100_000_000.0,
                capacity_phiPn_N=1_000_000.0,
                dcr=1.3,
                status="FAIL",
                message="Synthetic fail.",
            ),
            DemandCapacityResult(
                combo_name="ULS-PASS",
                Pu_N=1_000_000.0,
                Mux_Nmm=70_000_000.0,
                Muy_Nmm=0.0,
                Mu_Nmm=70_000_000.0,
                moment_angle_rad=0.0,
                capacity_Mn_Nmm=None,
                capacity_phiMn_Nmm=100_000_000.0,
                capacity_phiPn_N=1_000_000.0,
                dcr=0.7,
                status="PASS",
                message="Synthetic pass.",
            ),
        ],
        governing_combo="ULS-FAIL",
        max_dcr=1.3,
        overall_status="FAIL",
    )


def test_pmm_slice_at_pu_returns_non_empty_slice_for_synthetic_dataframe() -> None:
    slice_df = pmm_slice_at_pu(_synthetic_pmm_df(), 1000.0)

    assert not slice_df.empty
    assert set(slice_df["phiPn_kN"]) == {1000.0}


def test_pmm_slice_at_pu_widens_tolerance_when_too_few_points_are_near_pu() -> None:
    df = _synthetic_pmm_df()
    df["phiPn_kN"] = 1010.0

    slice_df = pmm_slice_at_pu(df, 1000.0, tolerance_kN=1.0)

    assert not slice_df.empty
    assert any("tolerance widened" in warning for warning in slice_df.attrs["warnings"])


def test_pmm_slice_at_pu_returns_points_sorted_by_angle() -> None:
    slice_df = pmm_slice_at_pu(_synthetic_pmm_df(), 1000.0)
    angles = [math.atan2(row.phiMny_kNm, row.phiMnx_kNm) for row in slice_df.itertuples()]

    assert angles == sorted(angles)


def test_pmm_slice_at_pu_interpolated_returns_non_empty_slice() -> None:
    slice_df = pmm_slice_at_pu_interpolated(_synthetic_interpolated_pmm_df(), 1000.0)

    assert not slice_df.empty
    assert slice_df.attrs["method"] == "interpolated"


def test_pmm_slice_at_pu_interpolated_returns_one_point_per_theta() -> None:
    slice_df = pmm_slice_at_pu_interpolated(_synthetic_interpolated_pmm_df(theta_count=12), 1000.0)

    assert len(slice_df) == 12
    assert set(slice_df["phiPn_kN"]) == {1000.0}


def test_pmm_slice_at_pu_interpolated_sorts_points_by_angle() -> None:
    slice_df = pmm_slice_at_pu_interpolated(_synthetic_interpolated_pmm_df(theta_count=12), 1000.0)
    angles = [math.atan2(row.phiMny_kNm, row.phiMnx_kNm) for row in slice_df.itertuples()]

    assert angles == sorted(angles)


def test_pmm_slice_at_pu_interpolated_falls_back_when_theta_or_c_missing() -> None:
    df = _synthetic_interpolated_pmm_df().drop(columns=["c_mm"])

    slice_df = pmm_slice_at_pu_interpolated(df, 1000.0)

    assert slice_df.attrs["method"] == "tolerance_fallback"
    assert any("requires theta_rad and c_mm" in warning for warning in slice_df.attrs["warnings"])


def test_pmm_slice_at_pu_interpolated_falls_back_when_too_few_points() -> None:
    slice_df = pmm_slice_at_pu_interpolated(_synthetic_interpolated_pmm_df(theta_count=4), 1000.0)

    assert slice_df.attrs["method"] == "tolerance_fallback"
    assert any("too few points" in warning for warning in slice_df.attrs["warnings"])


def test_estimate_directional_capacity_from_slice_returns_capacity_for_circular_slice() -> None:
    estimate = estimate_directional_capacity_from_slice(_circular_slice(100.0), Mux_kNm=50.0, Muy_kNm=0.0)

    assert estimate["capacity_phiMn_kNm"] == pytest.approx(100.0)
    assert estimate["dcr"] == pytest.approx(0.5)


def test_estimate_directional_capacity_from_slice_handles_angle_wrapping() -> None:
    radius = 100.0
    slice_df = pd.DataFrame(
        [
            {"phiMnx_kNm": radius * math.cos(math.radians(170.0)), "phiMny_kNm": radius * math.sin(math.radians(170.0))},
            {"phiMnx_kNm": radius * math.cos(math.radians(-170.0)), "phiMny_kNm": radius * math.sin(math.radians(-170.0))},
        ]
    )
    demand_angle = math.radians(179.0)

    estimate = estimate_directional_capacity_from_slice(
        slice_df,
        Mux_kNm=50.0 * math.cos(demand_angle),
        Muy_kNm=50.0 * math.sin(demand_angle),
    )

    assert estimate["capacity_phiMn_kNm"] == pytest.approx(100.0)
    assert estimate["dcr"] == pytest.approx(0.5)


def test_dcr_from_interpolated_slice_is_demand_radius_over_capacity_radius() -> None:
    estimate = estimate_directional_capacity_from_slice(_circular_slice(200.0), Mux_kNm=60.0, Muy_kNm=80.0)

    assert estimate["demand_Mu_kNm"] == pytest.approx(100.0)
    assert estimate["capacity_phiMn_kNm"] == pytest.approx(200.0)
    assert estimate["dcr"] == pytest.approx(0.5)


def test_check_uls_demands_against_rc_pmm_uses_interpolated_slice_when_possible() -> None:
    summary = check_uls_demands_against_rc_pmm(
        _synthetic_interpolated_result(),
        [LoadCase(name="ULS-INTERP", Pu_N=1_000_000.0, Mux_Nmm=50_000_000.0, Muy_Nmm=0.0)],
    )

    assert summary.results[0].dcr == pytest.approx(0.5)
    assert "PMM slice envelope" in summary.results[0].message


def test_demand_load_cases_to_display_dataframe_converts_units() -> None:
    df = demand_load_cases_to_display_dataframe(
        [LoadCase(name="ULS-01", Pu_N=1_000_000.0, Mux_Nmm=500_000_000.0, Muy_Nmm=300_000_000.0)]
    )

    assert df.loc[0, "Pu_kN"] == pytest.approx(1000.0)
    assert df.loc[0, "Mux_kNm"] == pytest.approx(500.0)
    assert df.loc[0, "Muy_kNm"] == pytest.approx(300.0)
    assert df.loc[0, "Mu_kNm"] == pytest.approx(math.hypot(500.0, 300.0))


def test_rank_load_cases_by_dcr_sorts_fail_before_pass() -> None:
    ranking = rank_load_cases_by_dcr(_dc_summary())

    assert list(ranking["Combo"]) == ["ULS-FAIL", "ULS-PASS"]


def test_build_selected_load_case_summary_returns_expected_status_and_dcr() -> None:
    load_case = LoadCase(name="ULS-PASS", Pu_N=1_000_000.0, Mux_Nmm=70_000_000.0, Muy_Nmm=0.0)
    summary = build_selected_load_case_summary(load_case, _dc_summary(), "RC PMM Prototype", False)

    assert summary["selected_combo"] == "ULS-PASS"
    assert summary["status"] == "PASS"
    assert summary["dcr"] == pytest.approx(0.7)
    assert summary["capacity_phiMn_kNm"] == pytest.approx(100.0)


def test_make_mux_muy_slice_figure_returns_plotly_figure() -> None:
    load_case = LoadCase(name="ULS-PASS", Pu_N=1_000_000.0, Mux_Nmm=70_000_000.0, Muy_Nmm=0.0)

    fig = make_mux_muy_slice_figure(_synthetic_pmm_df(), load_case, _dc_summary())

    assert isinstance(fig, go.Figure)


def test_make_pmm_3d_dashboard_figure_returns_plotly_figure() -> None:
    load_case = LoadCase(name="ULS-PASS", Pu_N=1_000_000.0, Mux_Nmm=70_000_000.0, Muy_Nmm=0.0)
    demand_df = demand_load_cases_to_display_dataframe([load_case])

    fig = make_pmm_3d_dashboard_figure(_synthetic_pmm_df(), demand_df, load_case, _dc_summary())

    assert isinstance(fig, go.Figure)
    assert not any(trace.name == "PMM raw points" for trace in fig.data)


def test_pmm_surface_data_adapter_resolves_common_app_columns() -> None:
    adapted, diagnostics = pmm_surface_data_adapter(_irregular_pmm_point_df())

    assert list(adapted.columns[:3]) == ["phiPn_kN", "phiMnx_kNm", "phiMny_kNm"]
    assert diagnostics["p_column"] == "P_kN"
    assert diagnostics["mx_column"] == "Mx_kNm"
    assert diagnostics["my_column"] == "My_kNm"
    assert diagnostics["valid_point_count"] == 10


def test_make_pmm_3d_dashboard_uses_mesh_when_theta_grid_is_absent() -> None:
    load_case = LoadCase(name="ULS-PASS", Pu_N=1_000_000.0, Mux_Nmm=70_000_000.0, Muy_Nmm=0.0)
    demand_df = demand_load_cases_to_display_dataframe([load_case])

    fig = make_pmm_3d_dashboard_figure(_irregular_pmm_point_df(), demand_df, load_case, _dc_summary())
    diagnostics = fig.layout.meta["pmm_surface_diagnostics"]

    assert any(trace.type == "mesh3d" for trace in fig.data)
    assert diagnostics["surface_generated"] is True
    assert diagnostics["surface_trace_type"] == "Mesh3d"


def test_make_pmm_3d_dashboard_uses_phi_pn_capped_when_phi_pn_is_absent() -> None:
    df = _synthetic_interpolated_pmm_df().drop(columns=["phiPn_kN"])
    load_case = LoadCase(name="ULS-PASS", Pu_N=1_000_000.0, Mux_Nmm=70_000_000.0, Muy_Nmm=0.0)
    demand_df = demand_load_cases_to_display_dataframe([load_case])

    fig = make_pmm_3d_dashboard_figure(df, demand_df, load_case, _dc_summary())
    diagnostics = fig.layout.meta["pmm_surface_diagnostics"]

    assert any(trace.type in {"surface", "mesh3d"} for trace in fig.data)
    assert diagnostics["p_column"] == "phiPn_capped_kN"
    assert diagnostics["surface_generated"] is True


def test_make_pmm_3d_dashboard_figure_adds_surface_from_stored_pmm_grid() -> None:
    load_case = LoadCase(name="ULS-PASS", Pu_N=1_000_000.0, Mux_Nmm=70_000_000.0, Muy_Nmm=0.0)
    demand_df = demand_load_cases_to_display_dataframe([load_case])

    fig = make_pmm_3d_dashboard_figure(
        _synthetic_interpolated_pmm_df(),
        demand_df,
        load_case,
        _dc_summary(),
        show_surface=True,
        show_raw_points=False,
        show_all_uls_load_points=False,
    )

    trace_types = [trace.type for trace in fig.data]
    assert "surface" in trace_types
    assert "mesh3d" in trace_types
    assert "scatter3d" in trace_types
    assert fig.layout.meta["pmm_surface_diagnostics"]["surface_trace_type"] == "Surface+Mesh3d"
    assert any(trace.name == "Selected load point" for trace in fig.data)


def test_make_pmm_3d_dashboard_uses_professional_camera_and_surface_style() -> None:
    load_case = LoadCase(name="ULS-PASS", Pu_N=1_000_000.0, Mux_Nmm=70_000_000.0, Muy_Nmm=0.0)
    demand_df = demand_load_cases_to_display_dataframe([load_case])

    fig = make_pmm_3d_dashboard_figure(_synthetic_interpolated_pmm_df(), demand_df, load_case, _dc_summary())

    surface_trace = next(trace for trace in fig.data if trace.name == "PMM surface")
    assert 0.35 <= surface_trace.opacity <= 0.45
    assert fig.layout.scene.aspectmode == "cube"
    assert fig.layout.scene.camera.eye.x == pytest.approx(1.65)
    assert fig.layout.scene.camera.eye.y == pytest.approx(-1.75)
    assert fig.layout.scene.camera.eye.z == pytest.approx(1.28)
    assert fig.layout.legend.orientation == "h"


def test_make_pmm_3d_dashboard_legend_excludes_hidden_support_mesh_and_raw_points() -> None:
    load_case = LoadCase(name="ULS-PASS", Pu_N=1_000_000.0, Mux_Nmm=70_000_000.0, Muy_Nmm=0.0)
    demand_df = demand_load_cases_to_display_dataframe([load_case])

    fig = make_pmm_3d_dashboard_figure(_synthetic_interpolated_pmm_df(), demand_df, load_case, _dc_summary())

    legend_names = [trace.name for trace in fig.data if trace.showlegend is not False]
    assert "PMM surface" in legend_names
    assert "Current Pu slice" in legend_names
    assert "Selected load point" in legend_names
    assert "PMM surface mesh" not in legend_names
    assert "PMM raw points" not in legend_names


def test_make_pmm_3d_dashboard_figure_keeps_raw_point_layer_available() -> None:
    load_case = LoadCase(name="ULS-PASS", Pu_N=1_000_000.0, Mux_Nmm=70_000_000.0, Muy_Nmm=0.0)
    demand_df = demand_load_cases_to_display_dataframe([load_case])

    fig = make_pmm_3d_dashboard_figure(
        _synthetic_interpolated_pmm_df(),
        demand_df,
        load_case,
        _dc_summary(),
        show_surface=False,
        show_raw_points=True,
        show_selected_load_point=False,
        show_all_uls_load_points=False,
    )

    assert any(trace.name == "PMM raw points" for trace in fig.data)
    assert all(trace.type != "surface" for trace in fig.data)


def test_make_pmm_3d_dashboard_default_slice_is_line_not_point_cloud() -> None:
    load_case = LoadCase(name="ULS-PASS", Pu_N=1_000_000.0, Mux_Nmm=70_000_000.0, Muy_Nmm=0.0)
    demand_df = demand_load_cases_to_display_dataframe([load_case])

    fig = make_pmm_3d_dashboard_figure(_synthetic_interpolated_pmm_df(), demand_df, load_case, _dc_summary())

    slice_trace = next(trace for trace in fig.data if trace.name == "Current Pu slice")
    assert slice_trace.type == "scatter3d"
    assert slice_trace.mode == "lines"
    assert slice_trace.line.width == 5


def test_make_pmm_3d_dashboard_selected_point_is_not_oversized() -> None:
    load_case = LoadCase(name="ULS-PASS", Pu_N=1_000_000.0, Mux_Nmm=70_000_000.0, Muy_Nmm=0.0)
    demand_df = demand_load_cases_to_display_dataframe([load_case])

    fig = make_pmm_3d_dashboard_figure(_synthetic_interpolated_pmm_df(), demand_df, load_case, _dc_summary())

    selected_trace = next(trace for trace in fig.data if trace.name == "Selected load point")
    assert 6 <= selected_trace.marker.size <= 8


def test_make_pmm_3d_dashboard_figure_can_show_all_uls_points() -> None:
    load_case = LoadCase(name="ULS-SELECT", Pu_N=1_000_000.0, Mux_Nmm=20_000_000.0, Muy_Nmm=0.0)
    pass_case = LoadCase(name="ULS-PASS", Pu_N=1_000_000.0, Mux_Nmm=70_000_000.0, Muy_Nmm=0.0)
    other_case = LoadCase(name="ULS-FAIL", Pu_N=1_000_000.0, Mux_Nmm=130_000_000.0, Muy_Nmm=0.0)
    demand_df = demand_load_cases_to_display_dataframe([pass_case, other_case])

    fig = make_pmm_3d_dashboard_figure(
        _synthetic_interpolated_pmm_df(),
        demand_df,
        load_case,
        _dc_summary(),
        show_surface=False,
        show_raw_points=False,
        show_selected_load_point=True,
        show_all_uls_load_points=True,
    )

    all_points_trace = next(trace for trace in fig.data if trace.name == "All ULS load points")
    assert all_points_trace.mode == "markers"
    assert all_points_trace.marker.size == 4
    assert tuple(all_points_trace.marker.color) == (STATUS_COLORS["PASS"], STATUS_COLORS["FAIL"])
    assert any(trace.name == "Selected load point" for trace in fig.data)


def test_analysis_page_imports_without_error_for_pmm_dashboard() -> None:
    from concrete_pmm_pro.ui import analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
