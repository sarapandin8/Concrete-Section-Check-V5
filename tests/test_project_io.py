from __future__ import annotations

import json

import pytest

from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.core.concrete_materials import DEFAULT_DECK_TOPPING_MATERIAL, DEFAULT_PRIMARY_CONCRETE_MATERIAL
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
from concrete_pmm_pro.serviceability.girder_sls_load_components import BEAM_GIRDER_SYSTEM_SETTINGS_KEY
from concrete_pmm_pro.serviceability.models import StressCheckPoint
from concrete_pmm_pro.state.dirty_state import (
    ANALYSIS_STATUS_KEY,
    CHANGED_GROUPS_KEY,
    CURRENT_INPUT_HASH_KEY,
    LAST_ANALYSIS_HASH_KEY,
    LAST_REFRESHED_WORKSPACE_KEY,
    PREVIOUS_INPUT_HASH_KEY,
    REPORT_STATUS_KEY,
)


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
        analysis_mode_settings=AnalysisModeSettings(member_type="beam_girder", note="future girder review"),
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
    assert parsed["version"] == "PS.DB1.2"
    assert parsed["analysis_mode_settings"]["member_type"] == "beam_girder"
    assert parsed["include_default_stress_check_points"] is False
    assert parsed["custom_stress_check_points"][1]["active"] is False
    assert parsed["custom_stress_check_points"][1]["include_in_governing"] is False
    assert parsed["concrete_material"]["fc_MPa"] == pytest.approx(35.0)
    assert parsed["active_concrete_material_name"] == "C35"
    assert parsed["deck_topping_material_name"] == DEFAULT_DECK_TOPPING_MATERIAL
    assert any(material["name"] == DEFAULT_PRIMARY_CONCRETE_MATERIAL for material in parsed["concrete_materials"])
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
    assert loaded.analysis_mode_settings.member_type == "beam_girder"
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
    assert project.concrete_material.name == DEFAULT_PRIMARY_CONCRETE_MATERIAL
    assert project.deck_topping_material_name == DEFAULT_DECK_TOPPING_MATERIAL
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
    assert session_state["active_concrete_material_name"] == project.active_concrete_material_name
    assert session_state["deck_topping_material_name"] == project.deck_topping_material_name
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


def test_old_project_with_single_concrete_material_keeps_active_primary() -> None:
    loaded = project_from_json(
        json.dumps(
            {
                "project_name": "Old C35 Project",
                "concrete_material": {
                    "name": "Legacy C35",
                    "fc_MPa": 35.0,
                    "ecu": 0.003,
                    "density_kg_m3": 2400.0,
                    "beta1": 0.8,
                },
            }
        )
    )

    assert loaded.concrete_material.name == "Legacy C35"
    assert loaded.concrete_material.fc_MPa == pytest.approx(35.0)
    assert loaded.active_concrete_material_name == "Legacy C35"
    assert DEFAULT_PRIMARY_CONCRETE_MATERIAL in {material.name for material in loaded.concrete_materials}


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
    assert row["Product"] == "Tendon 6-12"
    assert row["Steel Type"] == "tendon_group"
    assert row["Area_mm2"] == pytest.approx(1680.0)
    assert row["Diameter_mm"] is None
    assert row["Eq Steel Dia_mm"] == pytest.approx(46.27, abs=0.03)
    assert row["fpy_MPa"] == pytest.approx(1580.0)
    assert row["fpu_MPa"] == pytest.approx(1860.0)
    assert row["Ep_MPa"] == pytest.approx(195000.0)
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
    assert row["Product"] == "Tendon 6-25"
    assert row["Area_mm2"] == pytest.approx(3500.0)
    assert row["Diameter_mm"] is None
    assert row["Eq Steel Dia_mm"] == pytest.approx(66.8, abs=0.05)
    assert row["fpy_MPa"] == pytest.approx(1580.0)
    assert row["fpu_MPa"] == pytest.approx(1860.0)
    assert row["Ep_MPa"] == pytest.approx(195000.0)
    assert row["Strand Count"] == 25
    assert row["Breaking Load_kN"] == pytest.approx(6500.0)
    assert row["Duct Type"] == "Round duct"
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
                    "fpy_MPa": 1580.0,
                    "fpu_MPa": 1860.0,
                    "Ep_MPa": 195000.0,
                    "Strand Count": 25,
                    "Breaking Load_kN": 6500.0,
                    "Duct Type": "Round duct",
                    "Duct ID_mm": 125.0,
                }
            ],
        }
    )

    metadata = project.metadata["prestress_table_metadata"][0]
    assert metadata["Product"] == "Tendon 6-25"
    assert metadata["fpy_MPa"] == pytest.approx(1580.0)
    assert metadata["Strand Count"] == 25
    assert metadata["Breaking Load_kN"] == pytest.approx(6500.0)
    assert metadata["Duct ID_mm"] == pytest.approx(125.0)


def test_project_io_preserves_raw_prestress_editor_table_including_inactive_rows() -> None:
    element = PrestressElement(
        x_mm=0.0,
        y_mm=-200.0,
        area_mm2=3500.0,
        steel_type="tendon_group",
        material_name="6-25",
        fpy_mpa=1580.0,
        fpu_mpa=1860.0,
        ep_mpa=195000.0,
        pe_eff_n=2_800_000.0,
        initial_stress_mpa=800.0,
        bonded=True,
        count=1,
        label="T25",
    )
    session = {
        "prestress_elements": [element],
        "prestress_table": [
            {
                "Active": True,
                "Label": "T25",
                "Product": "6-25",
                "Steel Type": "tendon_group",
                "x_mm": 0.0,
                "y_mm": -200.0,
                "Area_mm2": 3500.0,
                "Input Mode": "Pe_eff",
                "Pe_eff_kN": 2800.0,
                "fpe_MPa": 800.0,
                "Bonded": True,
                "Count": 1,
                "Strand Count": 25,
                "Breaking Load_kN": 6500.0,
                "Duct Type": "Round duct",
                "Duct ID_mm": 125.0,
                "Note": "active tendon group",
            },
            {
                "Active": False,
                "Label": "Future row",
                "Product": "Custom",
                "Steel Type": "strand",
                "x_mm": 100.0,
                "y_mm": -180.0,
                "Area_mm2": 140.0,
                "Input Mode": "fpe",
                "Pe_eff_kN": 0.0,
                "fpe_MPa": 1000.0,
                "Bonded": False,
                "Count": 2,
                "Note": "stored inactive row",
            },
        ],
    }

    project = project_from_session_state(session)
    restored: dict[str, object] = {}
    apply_project_to_session_state(project, restored)

    table = restored["prestress_table"]
    assert list(table["Label"]) == ["T25", "Future row"]
    assert table.iloc[0]["Input Mode"] == "Pe_eff"
    assert table.iloc[0]["Pe_eff_kN"] == pytest.approx(2800.0)
    assert table.iloc[0]["Duct ID_mm"] == pytest.approx(125.0)
    assert bool(table.iloc[1]["Active"]) is False
    assert table.iloc[1]["Input Mode"] == "fpe"
    assert bool(table.iloc[1]["Bonded"]) is False
    assert table.iloc[1]["Count"] == 2
    assert table.iloc[1]["Note"] == "stored inactive row"


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


def test_session_state_with_empty_concrete_materials_keeps_existing_primary() -> None:
    session_state = {
        "concrete_material": ConcreteMaterial(name="Session Legacy C35", fc_MPa=35.0, beta1=0.80),
        "concrete_materials": [],
    }

    project = project_from_session_state(session_state)

    assert project.concrete_material.name == "Session Legacy C35"
    assert project.concrete_material.fc_MPa == pytest.approx(35.0)
    assert project.active_concrete_material_name == "Session Legacy C35"
    assert DEFAULT_PRIMARY_CONCRETE_MATERIAL in {material.name for material in project.concrete_materials}


def test_project_session_round_trip_preserves_workflow_load_tables_metadata() -> None:
    session_state = {
        "load_cases": [LoadCase(name="ULS-01", Pu_N=1000.0, Mux_Nmm=2000.0, Muy_Nmm=3000.0)],
        "column_uls_loads_table": [
            {"Active": True, "Case Name": "ULS-COL", "Pu": "1000", "Mux": "200", "Muy": "50", "Vux": "10", "Vuy": "20", "Tu": "0", "Note": "uls"}
        ],
        "column_sls_loads_table": [
            {"Active": True, "Case Name": "SLS-COL", "P": "700", "Mx": "120", "My": "30", "Note": "sls"}
        ],
        "beam_uls_loads_table": [
            {"Active": True, "Case Name": "ULS-G", "Mux": "1000", "Vuy": "250", "Tu": "0", "Muy": "0", "Vux": "0", "Nu": "0", "Note": "girder"}
        ],
        "beam_sls_loads_table": [
            {"Active": True, "Case Name": "SLS-G", "Stage": "Final service", "Load Component": "Total SLS resultant", "Section Basis": "Composite transformed", "N": "0", "Mx": "500", "My": "0", "Vy": "0", "Vx": "0", "T": "0", "Note": "girder sls"}
        ],
    }

    project = project_from_session_state(session_state)
    assert "workflow_load_tables" in project.metadata
    assert project.metadata["workflow_load_tables"]["beam_sls_loads_table"][0]["Case Name"] == "SLS-G"

    restored: dict[str, object] = {}
    apply_project_to_session_state(project, restored)

    assert "beam_sls_loads_table" in restored
    assert restored["beam_sls_loads_table"].iloc[0]["Case Name"] == "SLS-G"
    assert restored["beam_sls_loads_table"].iloc[0]["Stage"] == "Final service"
    assert restored["beam_sls_loads_table"].iloc[0]["Load Component"] == "Total SLS resultant"
    assert restored["column_uls_loads_table"].iloc[0]["Vuy"] == "20"


def test_project_io_empty_workflow_load_tables_overwrite_stale_metadata() -> None:
    session = {
        "project_metadata": {
            "workflow_load_tables": {
                "beam_uls_loads_table": [
                    {
                        "Active": True,
                        "Station x (m)": 0.0,
                        "Case Name": "OLD-ULS",
                        "Mux": "1000",
                        "Vuy": "250",
                        "Tu": "0",
                        "Muy": "0",
                        "Vux": "0",
                        "Nu": "0",
                        "Note": "stale",
                    }
                ],
                "beam_sls_loads_table": [
                    {
                        "Active": True,
                        "Station x (m)": 0.0,
                        "Case Name": "OLD-SLS",
                        "Stage": "Service stage",
                        "Load Component": "Total SLS resultant",
                        "Section Basis": "Composite transformed",
                        "N": "0",
                        "Mx": "500",
                        "My": "0",
                        "Vy": "0",
                        "Vx": "0",
                        "T": "0",
                        "Note": "stale",
                    }
                ],
            }
        },
        "beam_uls_loads_table": [],
        "beam_sls_loads_table": [],
    }

    project = project_from_session_state(session)
    restored: dict[str, object] = {}
    apply_project_to_session_state(project, restored)

    assert project.metadata["workflow_load_tables"]["beam_uls_loads_table"] == []
    assert project.metadata["workflow_load_tables"]["beam_sls_loads_table"] == []
    assert restored["beam_uls_loads_table"].empty
    assert restored["beam_sls_loads_table"].empty


def test_project_session_round_trip_preserves_girder_prestress_force_states_metadata() -> None:
    session_state = {
        "girder_prestress_force_states_table": [
            {
                "Check Stage": "Transfer stage",
                "Prestress State": "Pe_transfer / P_release",
                "Pe_kN": 3500.0,
                "yps_mm_from_bottom": 250.0,
                "Note": "transfer force",
            },
            {
                "Check Stage": "Service stage",
                "Prestress State": "Pe_eff_final",
                "Pe_kN": 2800.0,
                "yps_mm_from_bottom": 260.0,
                "Note": "final force",
            },
        ]
    }

    project = project_from_session_state(session_state)
    assert "girder_prestress_force_states_table" in project.metadata
    assert project.metadata["girder_prestress_force_states_table"][0]["Pe_kN"] == pytest.approx(3500.0)

    restored: dict[str, object] = {}
    apply_project_to_session_state(project, restored)

    assert "girder_prestress_force_states_table" in restored
    table = restored["girder_prestress_force_states_table"]
    assert table.iloc[0]["Prestress State"] == "Pe_transfer / P_release"
    assert table.iloc[0]["Pe_kN"] == pytest.approx(3500.0)
    assert table.iloc[1]["Prestress State"] == "Pe_eff_final"


def test_project_session_round_trip_preserves_girder_strand_layout_metadata() -> None:
    session_state = {
        "girder_prestress_system_settings": {
            "girder_system": "Simple supported precast girder",
            "prestress_type": "Pretensioned straight strands",
            "span_length_m": 32.0,
            "station_convention": "x = 0 at left support, x = L at right support",
            "debond_model": "Left/right independent",
        },
        "girder_strand_layout_table": [
            {
                "Active": True,
                "Group ID": "Row 2",
                "Layer": "Second row",
                "Strand Size": "15.2 mm low-relaxation strand",
                "No. Strands": 8,
                "Area/Strand_mm2": 140.0,
                "Total Aps_mm2": 1120.0,
                "x_mm": 0.0,
                "y_mm_from_bottom": 150.0,
                "Pe_transfer/strand_kN": 150.0,
                "Pe_construction/strand_kN": 140.0,
                "Pe_eff_final/strand_kN": 120.0,
                "Left debond m": 2.0,
                "Right debond m": 3.0,
                "Note": "debonded row",
            }
        ],
    }

    project = project_from_session_state(session_state)
    assert "girder_strand_layout_table" in project.metadata
    assert project.metadata["girder_strand_layout_table"][0]["Left debond m"] == 2.0
    assert project.metadata["girder_prestress_system_settings"]["span_length_m"] == 32.0

    restored: dict[str, object] = {}
    apply_project_to_session_state(project, restored)

    assert "girder_strand_layout_table" in restored
    assert restored["girder_strand_layout_table"].iloc[0]["Group ID"] == "Row 2"
    assert restored["girder_strand_layout_table"].iloc[0]["Right debond m"] == 3.0
    assert restored["girder_prestress_system_settings"]["debond_model"] == "Left/right independent"


def test_project_io_preserves_section_reinforcement_system_flags() -> None:
    session = {
        "section_has_ordinary_rebar": False,
        "section_has_prestressing_steel": True,
        "reinforcement_flags_preset_key": "parametric_i_girder",
    }

    project = project_from_session_state(session)
    restored: dict[str, object] = {}
    apply_project_to_session_state(project, restored)

    assert project.metadata["section_has_ordinary_rebar"] is False
    assert project.metadata["section_has_prestressing_steel"] is True
    assert project.metadata["reinforcement_flags_preset_key"] == "parametric_i_girder"
    assert restored["section_has_ordinary_rebar"] is False
    assert restored["section_has_prestressing_steel"] is True
    assert restored["reinforcement_flags_preset_key"] == "parametric_i_girder"



def test_project_io_preserves_beam_girder_shear_reinforcement_layout() -> None:
    session = {
        "beam_girder_shear_reinforcement_table": [
            {
                "Active": True,
                "Zone": "Left support",
                "x_start_m": 0.0,
                "x_end_m": 3.0,
                "Bar Size": "DB12",
                "Diameter_mm": 12.0,
                "Legs": 2,
                "Spacing_mm": 100.0,
                "fy_MPa": 400.0,
                "Note": "provided support zone",
            }
        ]
    }

    project = project_from_session_state(session)
    restored: dict[str, object] = {}
    apply_project_to_session_state(project, restored)

    assert "beam_girder_shear_reinforcement_table" in project.metadata
    assert project.metadata["beam_girder_shear_reinforcement_table"][0]["Bar Size"] == "DB12"
    assert "beam_girder_shear_reinforcement_table" in restored
    assert restored["beam_girder_shear_reinforcement_table"].iloc[0]["Spacing_mm"] == 100.0


def test_project_io_preserves_raw_longitudinal_rebar_editor_table() -> None:
    session = {
        "rebar_table": [
            {
                "Active": True,
                "Label": "Top-Perimeter",
                "x_mm": 125.0,
                "y_mm": 450.0,
                "Bar Size": "DB25",
                "Diameter_mm": 25.0,
                "Material": "SD40",
                "Count": 4,
                "Note": "torsion Al perimeter bars",
            },
            {
                "Active": False,
                "Label": "Future",
                "x_mm": -125.0,
                "y_mm": 450.0,
                "Bar Size": "DB20",
                "Diameter_mm": 20.0,
                "Material": "SD40",
                "Count": 2,
                "Note": "stored inactive row",
            },
        ],
        "rebars": [Rebar(x_mm=125.0, y_mm=450.0, diameter_mm=25.0, material_name="SD40", label="Top-Perimeter-1")],
    }

    project = project_from_session_state(session)
    assert "longitudinal_rebar_table" in project.metadata
    assert project.metadata["longitudinal_rebar_table"][0]["Bar Size"] == "DB25"
    assert project.metadata["longitudinal_rebar_table"][0]["Count"] == 4
    assert project.metadata["longitudinal_rebar_table"][1]["Active"] is False

    restored: dict[str, object] = {}
    apply_project_to_session_state(project, restored)

    table = restored["rebar_table"]
    assert list(table["Label"]) == ["Top-Perimeter", "Future"]
    assert table.iloc[0]["Bar Size"] == "DB25"
    assert table.iloc[0]["Count"] == 4
    assert bool(table.iloc[1]["Active"]) is False
    assert table.iloc[1]["Note"] == "stored inactive row"
    assert restored["rebar_editor_revision"] == 1


def test_apply_project_prefers_raw_rebar_table_metadata_over_expanded_rebar_objects() -> None:
    project = _sample_project().model_copy(
        update={
            "rebars": [
                Rebar(x_mm=0.0, y_mm=0.0, diameter_mm=25.0, material_name="SD40", label="Expanded-1"),
                Rebar(x_mm=0.0, y_mm=0.0, diameter_mm=25.0, material_name="SD40", label="Expanded-2"),
            ],
            "metadata": {
                "longitudinal_rebar_table": [
                    {
                        "Active": True,
                        "Label": "Grouped",
                        "x_mm": 0.0,
                        "y_mm": 0.0,
                        "Bar Size": "DB25",
                        "Diameter_mm": 25.0,
                        "Material": "SD40",
                        "Count": 2,
                        "Note": "preserve grouped editor row",
                    }
                ]
            },
        }
    )

    restored: dict[str, object] = {"rebar_editor_revision": 7}
    apply_project_to_session_state(project, restored)

    table = restored["rebar_table"]
    assert len(table) == 1
    assert table.iloc[0]["Label"] == "Grouped"
    assert table.iloc[0]["Bar Size"] == "DB25"
    assert table.iloc[0]["Count"] == 2
    assert restored["rebar_editor_revision"] == 8


def test_apply_project_bumps_transverse_rebar_editor_revision_on_load() -> None:
    project = _sample_project().model_copy(
        update={
            "metadata": {
                "beam_girder_shear_reinforcement_table": [
                    {
                        "Active": True,
                        "Zone": "Support",
                        "x_start_m": 0.0,
                        "x_end_m": 2.0,
                        "Bar Size": "DB12",
                        "Diameter_mm": 12.0,
                        "Legs": 2,
                        "Spacing_mm": 100.0,
                        "fy_MPa": 400.0,
                        "Note": "loaded transverse zone",
                    }
                ]
            },
        }
    )

    restored: dict[str, object] = {"beam_girder_shear_reinforcement_editor_revision": 3}
    apply_project_to_session_state(project, restored)

    assert restored["beam_girder_shear_reinforcement_table"].iloc[0]["Zone"] == "Support"
    assert restored["beam_girder_shear_reinforcement_editor_revision"] == 4


def test_apply_project_bumps_prestress_editor_revision_on_load() -> None:
    project = _sample_project()

    restored: dict[str, object] = {"prestress_editor_revision": 5}
    apply_project_to_session_state(project, restored)

    assert restored["prestress_table"].iloc[0]["Label"] == "PS1"
    assert restored["prestress_editor_revision"] == 6


def test_apply_project_resets_stale_dirty_state_after_load() -> None:
    project = _sample_project()
    restored: dict[str, object] = {
        CURRENT_INPUT_HASH_KEY: "old-current",
        PREVIOUS_INPUT_HASH_KEY: "old-previous",
        LAST_ANALYSIS_HASH_KEY: "old-analysis",
        LAST_REFRESHED_WORKSPACE_KEY: "Analysis / ULS",
        "_perf_input_group_hashes": {"Setup": "old"},
        ANALYSIS_STATUS_KEY: "Current",
        REPORT_STATUS_KEY: "Current",
        CHANGED_GROUPS_KEY: ["Loads"],
    }

    apply_project_to_session_state(project, restored)

    assert CURRENT_INPUT_HASH_KEY not in restored
    assert PREVIOUS_INPUT_HASH_KEY not in restored
    assert LAST_ANALYSIS_HASH_KEY not in restored
    assert LAST_REFRESHED_WORKSPACE_KEY not in restored
    assert "_perf_input_group_hashes" not in restored
    assert restored[ANALYSIS_STATUS_KEY] == "Not run"
    assert restored[REPORT_STATUS_KEY] == "Not run"
    assert restored[CHANGED_GROUPS_KEY] == []


def test_project_io_empty_rebar_tables_overwrite_stale_metadata() -> None:
    session = {
        "project_metadata": {
            "longitudinal_rebar_table": [{"Active": True, "Label": "Old", "x_mm": 0, "y_mm": 0, "Bar Size": "DB20", "Diameter_mm": 20, "Material": "SD40", "Count": 1, "Note": "old"}],
            "beam_girder_shear_reinforcement_table": [{"Active": True, "Zone": "Old", "x_start_m": 0, "x_end_m": 1, "Bar Size": "DB12", "Diameter_mm": 12, "Legs": 2, "Spacing_mm": 100, "fy_MPa": 400, "Note": "old"}],
        },
        "rebar_table": [],
        "beam_girder_shear_reinforcement_table": [],
    }

    project = project_from_session_state(session)

    assert project.metadata["longitudinal_rebar_table"] == []
    assert project.metadata["beam_girder_shear_reinforcement_table"] == []


def test_apply_project_syncs_section_girder_length_from_setup_span_source() -> None:
    project = _sample_project().model_copy(
        update={
            "section_preset_key": "precast_i_girder",
            "section_preset_name": "Precast I-Girder",
            "section_parameters": {
                "D_mm": 1800.0,
                "Btop_mm": 900.0,
                "girder_length_mm": 12000.0,
            },
            "metadata": {
                BEAM_GIRDER_SYSTEM_SETTINGS_KEY: {
                    "span_length_m": 30.0,
                    "girder_spacing_m": 1.6,
                    "number_of_girders": 6,
                    "concrete_unit_weight_kN_m3": 24.0,
                    "tributary_width_m": 1.6,
                }
            },
        }
    )

    restored: dict[str, object] = {}
    apply_project_to_session_state(project, restored)

    assert restored[BEAM_GIRDER_SYSTEM_SETTINGS_KEY]["span_length_m"] == pytest.approx(30.0)
    assert restored["section_parameters"]["girder_length_mm"] == pytest.approx(30000.0)
    assert restored["precast_i_girder_girder_length_mm"] == pytest.approx(30000.0)
    assert restored["precast_i_girder_girder_length_mm_locked_from_setup"] == pytest.approx(30000.0)
