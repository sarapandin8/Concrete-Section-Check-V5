from __future__ import annotations

import json
from pathlib import Path

import pytest

from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.io.project_io import apply_project_to_session_state, project_from_session_state, project_to_json
from concrete_pmm_pro.serviceability.girder_sls_load_components import (
    BEAM_GIRDER_SYSTEM_SETTINGS_KEY,
    BUILDING_BEAM_GIRDER_SERVICE_LOAD_SETTINGS_KEY,
    BeamGirderSystemSettings,
    BuildingBeamGirderServiceLoadSettings,
    building_service_load_components_kN_m,
    building_service_load_settings_from_mapping,
    building_service_moment_rows,
    building_service_total_load_kN_m,
    simple_span_udl_moment_kNm,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "project_page.py").read_text(encoding="utf-8")
LOADS_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "loads_page.py").read_text(encoding="utf-8")
ANALYSIS_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")


def test_building_service_area_loads_convert_to_line_load_and_moment() -> None:
    system = BeamGirderSystemSettings(span_length_m=8.0, girder_spacing_m=2.5, use_girder_spacing_as_tributary_width=True)
    settings = BuildingBeamGirderServiceLoadSettings(
        service_sdl_kN_m2=2.0,
        service_ll_kN_m2=3.0,
        include_additional_sdl=True,
        additional_sdl_kN_m2=1.0,
    )

    components = dict(building_service_load_components_kN_m(system, settings))
    assert components["Building SDL"] == pytest.approx(5.0)
    assert components["Additional SDL"] == pytest.approx(2.5)
    assert components["Building LL"] == pytest.approx(7.5)
    assert building_service_total_load_kN_m(system, settings) == pytest.approx(15.0)
    assert simple_span_udl_moment_kNm(15.0, 4.0, 8.0) == pytest.approx(120.0)

    rows = building_service_moment_rows(system, settings, stations_m=[0.0, 4.0, 8.0])
    assert rows[0]["Mx service (kN-m)"] == pytest.approx(0.0)
    assert rows[1]["Mx service (kN-m)"] == pytest.approx(120.0)
    assert rows[2]["Mx service (kN-m)"] == pytest.approx(0.0)


def test_building_system_can_use_spacing_as_tributary_width() -> None:
    system = BeamGirderSystemSettings(
        girder_spacing_m=3.2,
        tributary_width_m=1.1,
        use_girder_spacing_as_tributary_width=True,
    )
    assert system.effective_tributary_width_m == pytest.approx(3.2)
    assert system.as_metadata()["use_girder_spacing_as_tributary_width"] is True

def test_building_service_direct_line_load_mode_is_supported() -> None:
    system = BeamGirderSystemSettings(span_length_m=10.0, tributary_width_m=3.0)
    settings = BuildingBeamGirderServiceLoadSettings(
        include_service_sdl=False,
        include_service_ll=False,
        include_additional_sdl=True,
        additional_sdl_mode="Direct kN/m",
        additional_sdl_line_load_kN_m=4.2,
        additional_sdl_kN_m2=99.0,
    )
    assert building_service_total_load_kN_m(system, settings) == pytest.approx(4.2)


def test_building_service_settings_round_trip_project_io() -> None:
    session: dict[str, object] = {
        BEAM_GIRDER_SYSTEM_SETTINGS_KEY: {
            "span_length_m": 9.0,
            "girder_spacing_m": 2.4,
            "tributary_width_m": 2.2,
            "use_girder_spacing_as_tributary_width": False,
            "concrete_unit_weight_kN_m3": 24.0,
        },
        BUILDING_BEAM_GIRDER_SERVICE_LOAD_SETTINGS_KEY: {
            "include_service_sdl": True,
            "service_sdl_kN_m2": 1.5,
            "include_service_ll": True,
            "service_ll_kN_m2": 2.5,
            "include_additional_sdl": True,
            "additional_sdl_mode": "Direct kN/m",
            "additional_sdl_line_load_kN_m": 0.75,
        },
    }

    project = project_from_session_state(session)
    raw = json.loads(project_to_json(project))
    saved = raw["metadata"][BUILDING_BEAM_GIRDER_SERVICE_LOAD_SETTINGS_KEY]
    assert saved["service_sdl_kN_m2"] == pytest.approx(1.5)
    assert saved["service_ll_kN_m2"] == pytest.approx(2.5)

    restored: dict[str, object] = {}
    apply_project_to_session_state(ProjectModel.model_validate(raw), restored)
    assert restored[BEAM_GIRDER_SYSTEM_SETTINGS_KEY]["girder_spacing_m"] == pytest.approx(2.4)
    assert restored[BEAM_GIRDER_SYSTEM_SETTINGS_KEY]["use_girder_spacing_as_tributary_width"] is False
    normalized = building_service_load_settings_from_mapping(restored[BUILDING_BEAM_GIRDER_SERVICE_LOAD_SETTINGS_KEY])
    assert normalized.service_ll_kN_m2 == pytest.approx(2.5)
    assert normalized.additional_sdl_line_load_kN_m == pytest.approx(0.75)



def test_building_auto_load_breakdown_uses_building_loads_not_bridge_sdl() -> None:
    from concrete_pmm_pro.serviceability.girder_sls_load_components import building_auto_load_breakdown_for_stage

    system = BeamGirderSystemSettings(span_length_m=10.0, girder_spacing_m=2.0, use_girder_spacing_as_tributary_width=True)
    settings = BuildingBeamGirderServiceLoadSettings(service_sdl_kN_m2=1.0, service_ll_kN_m2=2.0)

    transfer = building_auto_load_breakdown_for_stage(
        stage_label="Transfer stage",
        system=system,
        service_settings=settings,
        precast_area_mm2=500_000.0,
        topping_thickness_mm=120.0,
    )
    construction = building_auto_load_breakdown_for_stage(
        stage_label="Construction stage",
        system=system,
        service_settings=settings,
        precast_area_mm2=500_000.0,
        topping_thickness_mm=120.0,
    )
    service = building_auto_load_breakdown_for_stage(
        stage_label="Service stage",
        system=system,
        service_settings=settings,
        precast_area_mm2=500_000.0,
        topping_thickness_mm=120.0,
    )

    assert dict(transfer.component_loads_kN_m)["Precast girder self-weight"] == pytest.approx(12.0)
    assert dict(construction.component_loads_kN_m)["Wet topping/slab"] == pytest.approx(5.76)
    service_components = dict(service.component_loads_kN_m)
    assert service_components["Building SDL"] == pytest.approx(2.0)
    assert service_components["Building LL"] == pytest.approx(4.0)
    assert "Barrier/Parapet/Sidewalk" not in service_components
    assert "Wearing surface" not in service_components

def test_building_workflow_ui_hides_bridge_sdl_and_exposes_building_sdl() -> None:
    assert "Building Beam/Girder System Settings" in PROJECT_SOURCE
    assert "Beam / Girder spacing" in PROJECT_SOURCE
    assert "Use beam/girder spacing as tributary width" in PROJECT_SOURCE
    assert "Tributary width for SDL/LL load take-down" in PROJECT_SOURCE
    assert "Beam/Girder spacing" in LOADS_SOURCE
    assert "Bridge SDL" in PROJECT_SOURCE
    assert "Building Beam/Girder ACI Service Load Components" in LOADS_SOURCE
    assert "SDL (kN/m²)" in LOADS_SOURCE
    assert "LL (kN/m²)" in LOADS_SOURCE
    assert "bridge barrier/parapet/sidewalk, wearing surface" in LOADS_SOURCE
    assert "Building Beam/Girder ACI SLS Stress Workspace" in ANALYSIS_SOURCE
    assert "Building ACI preview active" in ANALYSIS_SOURCE
    assert "Building Service auto load = Building SDL/LL from Loads" in ANALYSIS_SOURCE
