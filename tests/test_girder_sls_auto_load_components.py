from __future__ import annotations

import json
from pathlib import Path

import pytest

from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.io.project_io import apply_project_to_session_state, project_from_session_state, project_to_json
from concrete_pmm_pro.serviceability.girder_sls_load_components import (
    BEAM_GIRDER_SYSTEM_SETTINGS_KEY,
    BEAM_GIRDER_SLS_AUTO_LOAD_SETTINGS_KEY,
    BeamGirderSLSAutoLoadSettings,
    BeamGirderSystemSettings,
    auto_load_breakdown_for_stage,
    barrier_sidewalk_load_per_girder_kN_m,
    default_sls_station_grid,
    simple_span_udl_moment_kNm,
    wearing_surface_load_per_girder_kN_m,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "project_page.py").read_text(encoding="utf-8")
LOADS_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "loads_page.py").read_text(encoding="utf-8")
ANALYSIS_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")


def test_barrier_parapet_sidewalk_default_area_is_total_for_both_sides() -> None:
    system = BeamGirderSystemSettings(number_of_girders=6)
    settings = BeamGirderSLSAutoLoadSettings()

    assert settings.barrier_sidewalk_total_area_both_sides_m2 == pytest.approx(1.50)
    assert settings.barrier_sidewalk_area_per_side_m2 == pytest.approx(0.75)
    assert barrier_sidewalk_load_per_girder_kN_m(system, settings) == pytest.approx(6.0)


def test_wearing_surface_uses_tributary_width_not_be() -> None:
    system = BeamGirderSystemSettings(girder_spacing_m=1.0, tributary_width_m=1.2)
    settings = BeamGirderSLSAutoLoadSettings(wearing_thickness_mm=80.0, wearing_unit_weight_kN_m3=24.0)

    assert wearing_surface_load_per_girder_kN_m(system, settings) == pytest.approx(0.08 * 1.2 * 24.0)


def test_simple_span_udl_moment_and_auto_stage_breakdown() -> None:
    system = BeamGirderSystemSettings(span_length_m=20.0, girder_spacing_m=1.0, number_of_girders=6)
    settings = BeamGirderSLSAutoLoadSettings()
    transfer = auto_load_breakdown_for_stage(
        stage_label="Transfer stage",
        system=system,
        settings=settings,
        precast_area_mm2=700_000.0,
        topping_thickness_mm=100.0,
    )
    construction = auto_load_breakdown_for_stage(
        stage_label="Construction stage",
        system=system,
        settings=settings,
        precast_area_mm2=700_000.0,
        topping_thickness_mm=100.0,
    )
    service = auto_load_breakdown_for_stage(
        stage_label="Service stage",
        system=system,
        settings=settings,
        precast_area_mm2=700_000.0,
        topping_thickness_mm=100.0,
    )

    assert transfer.total_kN_m == pytest.approx(0.7 * 24.0)
    assert construction.total_kN_m == pytest.approx(0.7 * 24.0 + 0.1 * 1.0 * 24.0)
    assert service.total_kN_m == pytest.approx(6.0 + 0.08 * 1.0 * 24.0)
    assert simple_span_udl_moment_kNm(10.0, 10.0, 20.0) == pytest.approx(500.0)


def test_default_station_grid_has_full_span_points() -> None:
    grid = default_sls_station_grid(20.0, extra_stations_m=[1.0, 19.0], divisions=20)
    assert grid[0] == pytest.approx(0.0)
    assert grid[-1] == pytest.approx(20.0)
    assert 10.0 in grid
    assert 1.0 in grid
    assert 19.0 in grid
    assert len(grid) >= 21


def test_project_io_preserves_beam_girder_system_and_auto_load_settings() -> None:
    session: dict[str, object] = {
        BEAM_GIRDER_SYSTEM_SETTINGS_KEY: {
            "span_length_m": 30.0,
            "girder_spacing_m": 1.5,
            "number_of_girders": 8,
            "concrete_unit_weight_kN_m3": 24.0,
            "tributary_width_m": 1.5,
        },
        BEAM_GIRDER_SLS_AUTO_LOAD_SETTINGS_KEY: {
            "barrier_sidewalk_total_area_both_sides_m2": 1.50,
            "wearing_thickness_mm": 80.0,
            "include_service_other_sdl": True,
            "other_sdl_area_load_kN_m2": 2.0,
        },
    }
    project = project_from_session_state(session)
    raw = json.loads(project_to_json(project))
    assert raw["metadata"][BEAM_GIRDER_SYSTEM_SETTINGS_KEY]["number_of_girders"] == 8
    assert raw["metadata"][BEAM_GIRDER_SLS_AUTO_LOAD_SETTINGS_KEY]["wearing_thickness_mm"] == 80.0

    restored: dict[str, object] = {}
    apply_project_to_session_state(ProjectModel.model_validate(raw), restored)
    assert restored[BEAM_GIRDER_SYSTEM_SETTINGS_KEY]["span_length_m"] == pytest.approx(30.0)
    assert restored["girder_prestress_system_settings"]["span_length_m"] == pytest.approx(30.0)
    assert restored[BEAM_GIRDER_SLS_AUTO_LOAD_SETTINGS_KEY]["include_service_other_sdl"] is True


def test_source_files_have_sls5a_ui_and_analysis_guardrails() -> None:
    assert "Beam/Girder System Settings" in PROJECT_SOURCE
    assert "Number of girders" in PROJECT_SOURCE
    assert "Tributary width for load take-down" in PROJECT_SOURCE
    assert "Beam/Girder SLS Auto Load Components" in LOADS_SOURCE
    assert "Barrier / Parapet / Sidewalk total area for both sides" in LOADS_SOURCE
    assert "Import LL+IM only from CSiBridge" in LOADS_SOURCE
    assert "GIRDER.SLS5A generates a span station grid" in ANALYSIS_SOURCE
    assert "Service auto load = SDL after composite only" in ANALYSIS_SOURCE
    assert "Auto Mx (kN-m)" in ANALYSIS_SOURCE
