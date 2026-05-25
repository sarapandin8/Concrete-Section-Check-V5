from __future__ import annotations

import math

import pytest
from shapely.geometry import Polygon

from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.analysis.result_models import pmm_result_to_display_dataframe
from concrete_pmm_pro.analysis.strain_compatibility import is_point_inside_compression_block, rebar_net_force_n
from concrete_pmm_pro.code_checks import nominal_po_rc
from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, Rebar, RebarMaterial
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.io.project_io import project_from_json, project_to_json
from concrete_pmm_pro.core.project import ProjectModel


def _analysis_input(subtract: bool = True) -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=500.0, height_mm=500.0),
        concrete_material=ConcreteMaterial(name="C35", fc_MPa=35.0, ecu=0.003, beta1=0.80),
        rebar_materials=[RebarMaterial(name="Grade420", fy_MPa=420.0, Es_MPa=200000.0)],
        rebars=[
            Rebar(x_mm=-180.0, y_mm=-180.0, diameter_mm=25.0, material_name="Grade420", label="B1"),
            Rebar(x_mm=180.0, y_mm=-180.0, diameter_mm=25.0, material_name="Grade420", label="B2"),
            Rebar(x_mm=180.0, y_mm=180.0, diameter_mm=25.0, material_name="Grade420", label="B3"),
            Rebar(x_mm=-180.0, y_mm=180.0, diameter_mm=25.0, material_name="Grade420", label="B4"),
        ],
        load_cases=[LoadCase(name="ULS-01", Pu_N=800_000.0, Mux_Nmm=50_000_000.0, Muy_Nmm=20_000_000.0)],
        settings=AnalysisSettings(
            neutral_axis_angle_steps=12,
            neutral_axis_depth_steps=10,
            subtract_rebar_displaced_concrete=subtract,
        ),
    )


def test_rebar_net_force_outside_compression_block_returns_gross_force() -> None:
    force, metadata = rebar_net_force_n(100.0, 300.0, 35.0, inside_compression_block=False)

    assert force == pytest.approx(30_000.0)
    assert metadata["concrete_stress_subtracted_MPa"] == pytest.approx(0.0)


def test_rebar_net_force_inside_compression_block_subtracts_concrete_stress() -> None:
    force, metadata = rebar_net_force_n(100.0, 300.0, 35.0, inside_compression_block=True)

    assert force == pytest.approx(100.0 * (300.0 - 0.85 * 35.0))
    assert metadata["net_stress_MPa"] == pytest.approx(270.25)


def test_rebar_net_force_can_be_negative_when_compression_stress_is_low() -> None:
    force, metadata = rebar_net_force_n(100.0, 10.0, 35.0, inside_compression_block=True)

    assert force < 0.0
    assert metadata["net_stress_MPa"] == pytest.approx(10.0 - 0.85 * 35.0)


def test_is_point_inside_compression_block_true_inside_polygon() -> None:
    polygon = Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)])

    assert is_point_inside_compression_block(5.0, 5.0, polygon) is True


def test_is_point_inside_compression_block_true_on_boundary() -> None:
    polygon = Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)])

    assert is_point_inside_compression_block(0.0, 5.0, polygon) is True


def test_is_point_inside_compression_block_false_outside_polygon() -> None:
    polygon = Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)])

    assert is_point_inside_compression_block(15.0, 5.0, polygon) is False


def test_analysis_settings_default_subtract_rebar_displaced_concrete_is_true() -> None:
    assert AnalysisSettings().subtract_rebar_displaced_concrete is True


def test_analysis_settings_round_trip_preserves_subtract_rebar_displaced_concrete() -> None:
    project = ProjectModel(analysis_settings=AnalysisSettings(subtract_rebar_displaced_concrete=False))

    loaded = project_from_json(project_to_json(project))

    assert loaded.analysis_settings is not None
    assert loaded.analysis_settings.subtract_rebar_displaced_concrete is False


def test_old_project_json_defaults_subtract_rebar_displaced_concrete_true() -> None:
    project = ProjectModel()
    data = project.model_dump(mode="json")
    data["analysis_settings"] = {"neutral_axis_angle_steps": 72, "neutral_axis_depth_steps": 120}

    loaded = ProjectModel.model_validate(data)

    assert loaded.analysis_settings is not None
    assert loaded.analysis_settings.subtract_rebar_displaced_concrete is True


def test_pmm_solver_with_subtraction_enabled_produces_finite_result() -> None:
    result = run_rc_pmm_solver(_analysis_input(subtract=True))

    assert result.points
    assert all(math.isfinite(point.Pn_N) for point in result.points)


def test_pmm_solver_with_subtraction_disabled_still_works() -> None:
    result = run_rc_pmm_solver(_analysis_input(subtract=False))

    assert result.points
    assert any("not subtracted" in warning for warning in result.warnings)


def test_pmm_solver_enabled_vs_disabled_differs_for_compression_states() -> None:
    enabled = run_rc_pmm_solver(_analysis_input(subtract=True))
    disabled = run_rc_pmm_solver(_analysis_input(subtract=False))

    assert any(
        enabled_point.Pn_N != pytest.approx(disabled_point.Pn_N)
        for enabled_point, disabled_point in zip(enabled.points, disabled.points)
        if enabled_point.rebar_inside_compression_count > 0
    )
    assert max(point.Pn_N for point in enabled.points) <= max(point.Pn_N for point in disabled.points)


def test_pmm_display_dataframe_includes_displaced_concrete_columns() -> None:
    df = pmm_result_to_display_dataframe(run_rc_pmm_solver(_analysis_input()))

    assert {
        "rebar_displaced_concrete_subtracted_N",
        "rebar_displaced_concrete_subtracted_kN",
        "rebar_inside_compression_count",
    }.issubset(df.columns)
    assert df["rebar_displaced_concrete_subtracted_N"].max() > 0.0


def test_nominal_po_rc_uses_ag_minus_ast_formulation() -> None:
    rebars = [Rebar(x_mm=0.0, y_mm=0.0, diameter_mm=20.0, material_name="Grade420")]
    material = RebarMaterial(name="Grade420", fy_MPa=420.0)
    ast = rebars[0].area_mm2

    po = nominal_po_rc(fc_MPa=35.0, Ag_mm2=100_000.0, rebars=rebars, rebar_material_default=material)

    assert po == pytest.approx(0.85 * 35.0 * (100_000.0 - ast) + 420.0 * ast)
