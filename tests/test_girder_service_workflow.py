from pathlib import Path

import pytest

from concrete_pmm_pro.geometry.composite import CompositeDeckInput, calculate_composite_transformed_section
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.serviceability.girder_workflow import (
    build_girder_service_stress_basis_options,
    girder_service_stress_result_rows,
)
from concrete_pmm_pro.serviceability.girder_stress import run_basic_girder_service_stress

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_girder_service_basis_options_include_gross_for_valid_geometry():
    options = build_girder_service_stress_basis_options(
        rectangle(1000.0, 500.0),
        {},
        member_type="beam_girder",
    )

    assert "precast_gross" in options.bases
    assert options.labels["precast_gross"] == "Precast gross section"
    assert options.has_composite_basis is False
    assert options.warnings == ()
    assert any("Composite transformed" in item for item in options.info)


def test_girder_service_basis_options_include_composite_only_when_explicitly_active():
    geometry = rectangle(1000.0, 450.0)
    params = {
        "composite_enabled": True,
        "Tslab_mm": 100.0,
        "Be_mm": 1000.0,
        "Ebeam_MPa": 30000.0,
        "Edeck_MPa": 30000.0,
    }

    options = build_girder_service_stress_basis_options(geometry, params, member_type="beam_girder")

    assert "precast_gross" in options.bases
    assert "composite_transformed" in options.bases
    assert options.has_composite_basis is True
    assert options.labels["composite_transformed"] == "Composite transformed section"
    assert options.bases["composite_transformed"].total_depth_mm == pytest.approx(550.0)


def test_girder_service_basis_options_block_composite_outside_beam_girder():
    geometry = rectangle(1000.0, 450.0)
    params = {
        "composite_enabled": True,
        "Tslab_mm": 100.0,
        "Be_mm": 1000.0,
        "Ebeam_MPa": 30000.0,
        "Edeck_MPa": 30000.0,
    }

    options = build_girder_service_stress_basis_options(geometry, params, member_type="column_pier_pmm")

    assert "precast_gross" in options.bases
    assert "composite_transformed" not in options.bases


def test_girder_service_basis_options_report_missing_geometry():
    options = build_girder_service_stress_basis_options(None, {}, member_type="beam_girder")

    assert options.bases == {}
    assert options.labels == {}
    assert options.warnings


def test_girder_service_stress_result_rows_are_ui_ready():
    geometry = rectangle(1000.0, 500.0)
    basis = build_girder_service_stress_basis_options(geometry, {}, member_type="beam_girder").bases["precast_gross"]
    result = run_basic_girder_service_stress(basis, N_kN=0.0, M_kNm=500.0)
    rows = girder_service_stress_result_rows(result)

    assert [row["Fiber"] for row in rows] == ["Top", "Bottom"]
    assert rows[0]["Stress type"] == "compression"
    assert rows[1]["Stress type"] == "tension"
    assert "Total stress (MPa)" in rows[0]


def test_analysis_page_includes_beam_girder_service_stress_preview_source():
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")

    assert "Beam/Girder Elastic Service Stress Preview" in source
    assert "girder_service_stress_basis_name" in source
    assert "run_basic_girder_service_stress" in source
    assert "Include effective prestress stress component" in source
    assert "run_girder_prestress_stress_effect" in source
    assert "summarize_girder_prestress_elements" in source
    assert "Section basis for stress preview" in source
