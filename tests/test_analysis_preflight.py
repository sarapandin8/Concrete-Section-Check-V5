from __future__ import annotations

import pytest

from concrete_pmm_pro.analysis.preflight import build_analysis_input_from_session_state, check_analysis_readiness
from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import (
    ConcreteMaterial,
    LoadCase,
    PrestressElement,
    PrestressSteelMaterial,
    Rebar,
    RebarMaterial,
)
from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.io.project_io import apply_project_to_session_state, project_from_json, project_to_json


def _valid_session() -> dict[str, object]:
    rebar = Rebar(x_mm=0, y_mm=0, diameter_mm=25, label="B1")
    prestress = PrestressElement(
        x_mm=50,
        y_mm=-100,
        area_mm2=100,
        steel_type="strand",
        pe_eff_n=50_000,
        bonded=True,
        count=2,
        label="PS1",
    )
    return {
        "section_geometry": rectangle(width_mm=500, height_mm=700),
        "concrete_material": ConcreteMaterial(name="C35", fc_MPa=35, beta1=0.80),
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400)],
        "prestress_materials": [PrestressSteelMaterial(name="15.2mm strand", steel_type="strand", fpu_MPa=1860)],
        "rebars": [rebar],
        "prestress_elements": [prestress],
        "load_cases": [
            LoadCase(name="ULS-01", Pu_N=1000, Mux_Nmm=2000, Muy_Nmm=3000, load_type="ULS"),
            LoadCase(name="SLS-01", Pu_N=500, Mux_Nmm=1000, Muy_Nmm=1000, load_type="SLS"),
        ],
        "rebars_valid_for_analysis": True,
        "prestress_valid_for_analysis": True,
        "analysis_settings": AnalysisSettings(),
    }


def test_analysis_settings_default_creation() -> None:
    settings = AnalysisSettings()

    assert settings.code == "ACI 318"
    assert settings.analysis_type == "PMM Surface"
    assert settings.strength_load_type == "ULS"


def test_analysis_settings_rejects_too_few_angle_steps() -> None:
    with pytest.raises(ValueError):
        AnalysisSettings(neutral_axis_angle_steps=11)


def test_analysis_settings_rejects_too_few_depth_steps() -> None:
    with pytest.raises(ValueError):
        AnalysisSettings(neutral_axis_depth_steps=9)


def test_analysis_settings_rejects_invalid_transverse_reinforcement() -> None:
    with pytest.raises(ValueError):
        AnalysisSettings(transverse_reinforcement="invalid")


def test_analysis_settings_rejects_invalid_prestress_stress_model() -> None:
    with pytest.raises(ValueError):
        AnalysisSettings(prestress_stress_model="invalid")


def test_analysis_input_can_be_created_from_valid_components() -> None:
    session = _valid_session()
    analysis_input = AnalysisInput(
        section_geometry=session["section_geometry"],
        concrete_material=session["concrete_material"],
        rebar_materials=session["rebar_materials"],
        prestress_materials=session["prestress_materials"],
        rebars=session["rebars"],
        prestress_elements=session["prestress_elements"],
        load_cases=session["load_cases"],
        settings=session["analysis_settings"],
    )

    assert analysis_input.section_geometry is not None
    assert len(analysis_input.rebars) == 1


def test_check_analysis_readiness_errors_when_section_geometry_missing() -> None:
    session = _valid_session()
    session["section_geometry"] = None

    result = check_analysis_readiness(session)

    assert result.ready is False
    assert any("Section geometry is missing" in error for error in result.errors)


def test_check_analysis_readiness_errors_when_no_uls_load_cases() -> None:
    session = _valid_session()
    session["load_cases"] = [LoadCase(name="SLS-01", load_type="SLS")]

    result = check_analysis_readiness(session)

    assert result.ready is False
    assert any("No active ULS load cases" in error for error in result.errors)


def test_check_analysis_readiness_keeps_sls_limitation_out_of_uls_warnings() -> None:
    result = check_analysis_readiness(_valid_session())

    assert not any("SLS load cases are present" in warning for warning in result.warnings)
    assert any("SLS load cases are stored" in item for item in result.info)
    assert any("not used in the ULS PMM" in item for item in result.info)


def test_check_analysis_readiness_reports_total_as() -> None:
    result = check_analysis_readiness(_valid_session())

    assert any("Total As = 490.9 mm^2" in info for info in result.info)


def test_check_analysis_readiness_reports_total_aps_and_total_pe() -> None:
    result = check_analysis_readiness(_valid_session())

    assert any("Total Aps = 200.0 mm^2" in info for info in result.info)
    assert any("Total Pe_eff = 100,000.0 N" in info for info in result.info)


def test_check_analysis_readiness_warns_about_unbonded_prestress() -> None:
    session = _valid_session()
    session["prestress_elements"] = [PrestressElement(x_mm=0, y_mm=0, area_mm2=100, steel_type="strand", bonded=False)]

    result = check_analysis_readiness(session)

    assert any("Unbonded prestress" in warning for warning in result.warnings)


def test_project_model_round_trip_preserves_analysis_settings() -> None:
    project = ProjectModel(
        analysis_settings=AnalysisSettings(
            neutral_axis_angle_steps=96,
            include_prestress=False,
            transverse_reinforcement="spiral",
            prestress_stress_model="linear_cap",
            subtract_rebar_displaced_concrete=False,
        )
    )

    loaded = project_from_json(project_to_json(project))

    assert loaded.analysis_settings is not None
    assert loaded.analysis_settings.neutral_axis_angle_steps == 96
    assert loaded.analysis_settings.include_prestress is False
    assert loaded.analysis_settings.transverse_reinforcement == "spiral"
    assert loaded.analysis_settings.prestress_stress_model == "linear_cap"
    assert loaded.analysis_settings.subtract_rebar_displaced_concrete is False


def test_build_analysis_input_from_session_state_returns_analysis_input_when_ready() -> None:
    analysis_input = build_analysis_input_from_session_state(_valid_session())

    assert analysis_input is not None
    assert len(analysis_input.load_cases) == 1
    assert analysis_input.load_cases[0].load_type == "ULS"


def test_apply_project_to_session_state_restores_analysis_settings() -> None:
    session: dict[str, object] = {}
    project = ProjectModel(analysis_settings=AnalysisSettings(neutral_axis_depth_steps=144))

    apply_project_to_session_state(project, session)

    assert isinstance(session["analysis_settings"], AnalysisSettings)
    assert session["analysis_settings"].neutral_axis_depth_steps == 144


def test_check_analysis_readiness_allows_rc_only_without_prestress_warning() -> None:
    session = _valid_session()
    session["prestress_elements"] = []

    result = check_analysis_readiness(session)

    assert result.ready is True
    assert not any("No prestress" in warning for warning in result.warnings)
    assert any("RC-only" in item for item in result.info)


def test_check_analysis_readiness_allows_prestress_only_without_rebar_warning() -> None:
    session = _valid_session()
    session["rebars"] = []

    result = check_analysis_readiness(session)

    assert result.ready is True
    assert not any("No rebars" in warning or "Rebars are missing" in warning for warning in result.warnings)
    assert not any("Rebars are missing" in error for error in result.errors)
    assert any("No active ordinary rebar" in item for item in result.info)


def test_check_analysis_readiness_errors_when_no_longitudinal_reinforcement() -> None:
    session = _valid_session()
    session["rebars"] = []
    session["prestress_elements"] = []

    result = check_analysis_readiness(session)

    assert result.ready is False
    assert any("No active longitudinal reinforcement" in error for error in result.errors)


def test_section_rebar_flag_disables_rebars_without_deleting_prestress() -> None:
    session = _valid_session()
    session["section_has_ordinary_rebar"] = False

    analysis_input = build_analysis_input_from_session_state(session)
    readiness = check_analysis_readiness(session)

    assert analysis_input is not None
    assert analysis_input.rebars == []
    assert len(analysis_input.prestress_elements) == 1
    assert any("Ordinary rebar is disabled" in item for item in readiness.info)


def test_section_prestress_flag_disables_prestress_without_deleting_rebars() -> None:
    session = _valid_session()
    session["section_has_prestressing_steel"] = False

    analysis_input = build_analysis_input_from_session_state(session)
    readiness = check_analysis_readiness(session)

    assert analysis_input is not None
    assert len(analysis_input.rebars) == 1
    assert analysis_input.prestress_elements == []
    assert any("Prestressing steel is disabled" in item for item in readiness.info)


def test_section_flags_can_make_pmm_not_ready_when_both_systems_disabled() -> None:
    session = _valid_session()
    session["section_has_ordinary_rebar"] = False
    session["section_has_prestressing_steel"] = False

    readiness = check_analysis_readiness(session)
    analysis_input = build_analysis_input_from_session_state(session)

    assert readiness.ready is False
    assert analysis_input is None
    assert any("No active longitudinal reinforcement" in error for error in readiness.errors)


def test_precast_girder_ignores_legacy_section_level_prestress_rows() -> None:
    session = _valid_session()
    session["analysis_mode_settings"] = {"member_type": "beam_girder"}
    session["girder_section_family"] = "precast_composite_girder"
    session["section_preset_key"] = "box_section_fillet"
    session["section_has_ordinary_rebar"] = True
    session["section_has_prestressing_steel"] = True

    analysis_input = build_analysis_input_from_session_state(session)
    readiness = check_analysis_readiness(session)

    assert analysis_input is not None
    assert len(analysis_input.rebars) == 1
    assert analysis_input.prestress_elements == []
    assert any("Section-level tendon/prestress rows are ignored" in item for item in readiness.info)


def test_column_workflow_still_uses_section_level_prestress_rows_when_enabled() -> None:
    session = _valid_session()
    session["analysis_mode_settings"] = {"member_type": "column_pier_pmm"}
    session["section_has_prestressing_steel"] = True

    analysis_input = build_analysis_input_from_session_state(session)

    assert analysis_input is not None
    assert len(analysis_input.prestress_elements) == 1


def test_preflight_reports_girder_sls_stage_pe_mapping_ready_when_force_states_applied() -> None:
    session = _valid_session()
    session["analysis_mode_settings"] = {"member_type": "beam_girder"}
    session["girder_section_family"] = "precast_composite_girder"
    session["section_preset_key"] = "precast_plank_girder_interior"
    session["section_has_prestressing_steel"] = True
    session["girder_strand_layout_table"] = [
        {
            "Active": True,
            "Group ID": "Row 1",
            "No. Strands": 4,
            "Pe_transfer/strand_kN": 120.0,
            "Pe_construction/strand_kN": 115.0,
            "Pe_eff_final/strand_kN": 105.0,
        }
    ]

    result = check_analysis_readiness(session)

    assert any("Girder SLS stage Pe mapping is ready" in item for item in result.info)
    assert not any("stage Pe mapping is incomplete" in warning for warning in result.warnings)


def test_preflight_warns_when_girder_sls_stage_pe_mapping_is_missing() -> None:
    session = _valid_session()
    session["analysis_mode_settings"] = {"member_type": "beam_girder"}
    session["girder_section_family"] = "precast_composite_girder"
    session["section_preset_key"] = "precast_plank_girder_interior"
    session["section_has_prestressing_steel"] = True
    session["girder_strand_layout_table"] = [
        {
            "Active": True,
            "Group ID": "Row 1",
            "No. Strands": 4,
            "Pe_transfer/strand_kN": 120.0,
            "Pe_construction/strand_kN": 115.0,
            "Pe_eff_final/strand_kN": 0.0,
        }
    ]

    result = check_analysis_readiness(session)

    assert any("stage Pe mapping is incomplete" in warning for warning in result.warnings)
    assert any("Final service" in warning for warning in result.warnings)
