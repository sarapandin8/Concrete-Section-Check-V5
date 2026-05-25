from __future__ import annotations

import json

import pytest

from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, PrestressElement, PrestressSteelMaterial, Rebar, RebarMaterial
from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.io.project_io import (
    ProjectIOError,
    _prestress_to_table,
    apply_project_to_session_state,
    project_from_json,
    project_from_session_state,
    project_to_json,
)
from concrete_pmm_pro.serviceability import dataframe_to_stress_check_points, stress_check_points_to_dataframe
from concrete_pmm_pro.serviceability.models import StressCheckPoint


def _sample_project() -> ProjectModel:
    return ProjectModel(
        project_name="Bridge Pier P1",
        designer="Concrete Team",
        description="Milestone save-load test",
        code="ACI 318",
        section_preset_key="rectangle",
        section_preset_name="Rectangle",
        section_parameters={"width_mm": 500.0, "height_mm": 700.0},
        section_geometry=rectangle(width_mm=500, height_mm=700),
        concrete_material=ConcreteMaterial(name="C35", fc_MPa=35.0, beta1=0.80),
        rebar_materials=[RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        prestress_materials=[
            PrestressSteelMaterial(
                name="PT Bar 32",
                steel_type="prestressing_bar",
                diameter_mm=32.0,
                area_mm2=804.2,
                grade="1080/1230",
                fpy_MPa=1080.0,
                fpu_MPa=1230.0,
                Ep_MPa=200000.0,
                source="test",
                area_source="manual",
            )
        ],
        active_rebar_material_name="SD40",
        active_prestress_material_name="PT Bar 32",
        loads=[LoadCase(name="ULS-01", Pu_N=1_000_000.0, Mux_Nmm=200_000_000.0, Muy_Nmm=50_000_000.0)],
        rebars=[Rebar(x_mm=100.0, y_mm=-200.0, diameter_mm=25.0, material_name="SD40", label="B1")],
        analysis_mode_settings=AnalysisModeSettings(member_type="general_section", note="general review"),
        custom_stress_check_points=[
            StressCheckPoint(
                name="Tendon Zone",
                x_mm=0.0,
                y_mm=150.0,
                point_type="tendon_zone",
                active=True,
                include_in_governing=True,
                source="user",
                note="active review point",
            ),
            StressCheckPoint(
                name="Joint",
                x_mm=100.0,
                y_mm=0.0,
                point_type="segmental_joint",
                active=False,
                include_in_governing=False,
                source="user",
                note="stored inactive point",
            ),
        ],
        include_default_stress_check_points=False,
        prestress_elements=[
            PrestressElement(
                x_mm=-100.0,
                y_mm=-250.0,
                area_mm2=140.0,
                steel_type="strand",
                fpy_mpa=1600.0,
                fpu_mpa=1860.0,
                pe_eff_n=120_000.0,
                initial_stress_mpa=857.142857,
                initial_strain=857.142857 / 195000.0,
                label="PS1",
            )
        ],
        metadata={"rebars_valid_for_analysis": True, "prestress_valid_for_analysis": True},
    )


def test_project_model_can_store_current_milestone_data() -> None:
    project = _sample_project()

    assert project.section_geometry is not None
    assert project.loads[0].Pu_N == pytest.approx(1_000_000.0)
    assert project.rebars[0].diameter_mm == pytest.approx(25.0)
    assert project.prestress_elements[0].pe_eff_n == pytest.approx(120_000.0)


def test_project_to_json_returns_valid_json() -> None:
    json_text = project_to_json(_sample_project())
    parsed = json.loads(json_text)

    assert parsed["project_name"] == "Bridge Pier P1"
    assert parsed["version"] == "PS.DB1.1"
    assert parsed["analysis_mode_settings"]["member_type"] == "general_section"
    assert parsed["include_default_stress_check_points"] is False
    assert parsed["custom_stress_check_points"][1]["active"] is False
    assert parsed["custom_stress_check_points"][1]["include_in_governing"] is False
    assert parsed["concrete_material"]["fc_MPa"] == pytest.approx(35.0)
    assert parsed["active_rebar_material_name"] == "SD40"
    assert parsed["active_prestress_material_name"] == "PT Bar 32"
    assert parsed["loads"][0]["Mux_Nmm"] == pytest.approx(200_000_000.0)
    assert parsed["loads"][0]["Muy_Nmm"] == pytest.approx(50_000_000.0)
    assert "Mx_Nmm" not in parsed["loads"][0]
    assert "My_Nmm" not in parsed["loads"][0]


def test_project_from_json_recreates_project_model() -> None:
    loaded = project_from_json(project_to_json(_sample_project()))

    assert isinstance(loaded, ProjectModel)
    assert loaded.project_name == "Bridge Pier P1"
    assert loaded.section_geometry is not None
    assert isinstance(loaded.loads[0], LoadCase)
    assert isinstance(loaded.rebars[0], Rebar)
    assert isinstance(loaded.prestress_elements[0], PrestressElement)


def test_project_round_trip_preserves_key_engineering_data() -> None:
    loaded = project_from_json(project_to_json(_sample_project()))

    assert loaded.project_name == "Bridge Pier P1"
    assert loaded.section_geometry is not None
    assert loaded.section_geometry.outer_polygon[0].x == pytest.approx(-250.0)
    assert loaded.loads[0].Pu_N == pytest.approx(1_000_000.0)
    assert loaded.loads[0].Mux_Nmm == pytest.approx(200_000_000.0)
    assert loaded.loads[0].Muy_Nmm == pytest.approx(50_000_000.0)
    assert loaded.concrete_material.fc_MPa == pytest.approx(35.0)
    assert loaded.prestress_materials[0].steel_type == "prestressing_bar"
    assert loaded.rebars[0].x_mm == pytest.approx(100.0)
    assert loaded.rebars[0].y_mm == pytest.approx(-200.0)
    assert loaded.rebars[0].diameter_mm == pytest.approx(25.0)
    assert loaded.prestress_elements[0].pe_eff_n == pytest.approx(120_000.0)
    assert loaded.prestress_elements[0].initial_stress_mpa == pytest.approx(857.142857)
    assert loaded.analysis_mode_settings is not None
    assert loaded.analysis_mode_settings.member_type == "general_section"
    assert loaded.include_default_stress_check_points is False
    assert len(loaded.custom_stress_check_points) == 2
    assert loaded.custom_stress_check_points[0].point_type == "tendon_zone"
    assert loaded.custom_stress_check_points[1].active is False
    assert loaded.custom_stress_check_points[1].include_in_governing is False
    assert loaded.custom_stress_check_points[1].note == "stored inactive point"


def test_project_from_json_rejects_invalid_json_with_clear_exception() -> None:
    with pytest.raises(ProjectIOError, match="Invalid project JSON"):
        project_from_json("{not valid json")


def test_project_from_json_maps_legacy_mx_my_load_fields() -> None:
    project_data = json.loads(project_to_json(_sample_project()))
    project_data["version"] = "1.6"
    project_data["loads"][0]["Mx_Nmm"] = project_data["loads"][0].pop("Mux_Nmm")
    project_data["loads"][0]["My_Nmm"] = project_data["loads"][0].pop("Muy_Nmm")

    loaded = project_from_json(json.dumps(project_data))

    assert loaded.loads[0].Mux_Nmm == pytest.approx(200_000_000.0)
    assert loaded.loads[0].Muy_Nmm == pytest.approx(50_000_000.0)


def test_project_from_session_state_handles_missing_values_safely() -> None:
    project = project_from_session_state({})

    assert project.project_name == "Untitled Project"
    assert project.concrete_material.fc_MPa > 0
    assert project.section_geometry is None
    assert project.loads == []
    assert project.rebars == []
    assert project.prestress_elements == []
    assert project.analysis_mode_settings is not None
    assert project.analysis_mode_settings.member_type == "column_pier_pmm"
    assert project.custom_stress_check_points == []
    assert project.include_default_stress_check_points is True


def test_apply_project_to_session_state_restores_core_objects() -> None:
    project = _sample_project()
    session_state: dict[str, object] = {}

    apply_project_to_session_state(project, session_state)

    assert session_state["section_geometry"] == project.section_geometry
    assert session_state["concrete_material"] == project.concrete_material
    assert session_state["rebar_materials"] == project.rebar_materials
    assert session_state["prestress_materials"] == project.prestress_materials
    assert session_state["active_rebar_material_name"] == "SD40"
    assert session_state["active_prestress_material_name"] == "PT Bar 32"
    assert session_state["load_cases"] == project.loads
    assert session_state["rebars"] == project.rebars
    assert session_state["prestress_elements"] == project.prestress_elements
    assert session_state["analysis_mode_settings"] == project.analysis_mode_settings
    assert session_state["custom_stress_check_points"] == project.custom_stress_check_points
    assert session_state["include_default_stress_check_points"] is False
    assert "custom_stress_check_points_table" in session_state
    assert session_state["rebars_valid_for_analysis"] is True
    assert session_state["prestress_valid_for_analysis"] is True
    assert "loads_table" in session_state
    assert "rebar_table" in session_state
    assert "prestress_table" in session_state


def test_prestress_to_table_restores_standard_tendon_metadata_from_product_label() -> None:
    table = _prestress_to_table(
        [
            PrestressElement(
                x_mm=0.0,
                y_mm=-200.0,
                area_mm2=1680.0,
                steel_type="tendon_group",
                material_name="6-12",
                fpu_mpa=1860.0,
                count=1,
                label="T12",
            )
        ]
    )

    row = table.iloc[0]
    assert row["Product"] == "6-12"
    assert row["Steel Type"] == "tendon_group"
    assert row["Area_mm2"] == pytest.approx(1680.0)
    assert row["Diameter_mm"] is None
    assert row["Strand Count"] == 12
    assert row["Breaking Load_kN"] == pytest.approx(3120.0)
    assert row["Duct ID_mm"] == pytest.approx(80.0)
    assert row["Count"] == 1


def test_prestress_to_table_preserves_custom_tendon_metadata_without_inventing_duct_info() -> None:
    table = _prestress_to_table(
        [
            PrestressElement(
                x_mm=0.0,
                y_mm=-200.0,
                area_mm2=3500.0,
                steel_type="tendon_group",
                material_name="6-25",
                fpu_mpa=1860.0,
                count=1,
                label="T25",
            )
        ],
        [
            {
                "Label": "T25",
                "Product": "6-25",
                "Steel Type": "tendon_group",
                "Strand Count": 25,
                "Breaking Load_kN": 6500.0,
            }
        ],
    )

    row = table.iloc[0]
    assert row["Product"] == "6-25"
    assert row["Area_mm2"] == pytest.approx(3500.0)
    assert row["Diameter_mm"] is None
    assert row["Strand Count"] == 25
    assert row["Breaking Load_kN"] == pytest.approx(6500.0)
    assert row["Duct Type"] == ""
    assert row["Duct ID_mm"] is None
    assert row["Count"] == 1


def test_project_from_session_state_stores_prestress_table_metadata_for_reload() -> None:
    element = PrestressElement(
        x_mm=0.0,
        y_mm=-200.0,
        area_mm2=3500.0,
        steel_type="tendon_group",
        material_name="6-25",
        fpu_mpa=1860.0,
        count=1,
        label="T25",
    )
    project = project_from_session_state(
        {
            "prestress_elements": [element],
            "prestress_table": [
                {
                    "Label": "T25",
                    "Product": "6-25",
                    "Steel Type": "tendon_group",
                    "Area_mm2": 3500.0,
                    "Strand Count": 25,
                    "Breaking Load_kN": 6500.0,
                    "Duct Type": "Round duct",
                    "Duct ID_mm": 125.0,
                }
            ],
        }
    )

    metadata = project.metadata["prestress_table_metadata"][0]
    assert metadata["Product"] == "6-25"
    assert metadata["Strand Count"] == 25
    assert metadata["Breaking Load_kN"] == pytest.approx(6500.0)
    assert metadata["Duct ID_mm"] == pytest.approx(125.0)


def test_old_project_json_without_custom_stress_points_loads_safely() -> None:
    project_data = json.loads(project_to_json(_sample_project()))
    project_data.pop("custom_stress_check_points")
    project_data.pop("include_default_stress_check_points")
    project_data.pop("analysis_mode_settings")

    loaded = project_from_json(json.dumps(project_data))

    assert loaded.custom_stress_check_points == []
    assert loaded.include_default_stress_check_points is True
    assert loaded.analysis_mode_settings is not None
    assert loaded.analysis_mode_settings.member_type == "column_pier_pmm"


def test_stress_check_point_dataframe_round_trip_preserves_metadata() -> None:
    points = _sample_project().custom_stress_check_points

    df = stress_check_points_to_dataframe(points)
    round_trip = dataframe_to_stress_check_points(df)

    assert {"Active", "Name", "x_mm", "y_mm", "Point Type", "Include in Governing", "Note"}.issubset(df.columns)
    assert len(round_trip) == 2
    assert round_trip[0].point_type == "tendon_zone"
    assert round_trip[1].active is False
    assert round_trip[1].include_in_governing is False
    assert round_trip[1].note == "stored inactive point"
