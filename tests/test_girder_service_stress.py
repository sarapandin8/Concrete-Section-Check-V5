import pytest

from concrete_pmm_pro.geometry.composite import CompositeDeckInput, calculate_composite_transformed_section
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.serviceability.girder_stress import (
    GirderSectionBasis,
    girder_service_stress_at_y,
    girder_service_stress_result_to_dict,
    make_girder_basis_from_composite,
    make_girder_basis_from_gross_summary,
    run_basic_girder_service_stress,
)
from concrete_pmm_pro.validation.girder_service_stress import validate_girder_service_stress
from concrete_pmm_pro.validation.runner import run_all_validations


def test_gross_rectangular_girder_stress_matches_hand_calculation():
    b = 1000.0
    h = 500.0
    area = b * h
    ix = b * h**3 / 12.0
    basis = make_girder_basis_from_gross_summary(summarize_geometry(rectangle(b, h)))
    result = run_basic_girder_service_stress(basis, N_kN=1000.0, M_kNm=500.0)

    axial = -1000.0 * 1000.0 / area
    assert basis.basis_name == "precast_gross"
    assert basis.c_top_mm == pytest.approx(250.0)
    assert basis.c_bottom_mm == pytest.approx(250.0)
    assert result.top.total_stress_MPa == pytest.approx(axial - 500.0 * 1_000_000.0 * 250.0 / ix)
    assert result.bottom.total_stress_MPa == pytest.approx(axial + 500.0 * 1_000_000.0 * 250.0 / ix)
    assert result.top.stress_type == "compression"
    assert result.bottom.stress_type == "tension"


def test_hogging_moment_reverses_stress_signs():
    basis = make_girder_basis_from_gross_summary(summarize_geometry(rectangle(1000.0, 500.0)))
    result = run_basic_girder_service_stress(basis, N_kN=0.0, M_kNm=-500.0)
    assert result.top.total_stress_MPa > 0.0
    assert result.bottom.total_stress_MPa < 0.0


def test_composite_basis_is_separate_and_uses_transformed_section_properties():
    gross = summarize_geometry(rectangle(1000.0, 450.0))
    deck = CompositeDeckInput(enabled=True, Tslab_mm=100.0, Be_mm=1000.0, Ebeam_MPa=30000.0, Edeck_MPa=30000.0)
    composite = calculate_composite_transformed_section(gross, deck)
    basis = make_girder_basis_from_composite(composite)
    result = run_basic_girder_service_stress(basis, N_kN=0.0, M_kNm=1000.0)

    assert basis.basis_name == "composite_transformed"
    assert basis.area_mm2 == pytest.approx(composite.area_mm2)
    assert basis.ix_mm4 == pytest.approx(composite.ix_mm4)
    assert result.top.total_stress_MPa < 0.0
    assert result.bottom.total_stress_MPa > 0.0


def test_point_stress_at_centroid_has_no_bending_component():
    basis = GirderSectionBasis(
        basis_name="precast_gross",
        area_mm2=500000.0,
        centroid_y_from_bottom_mm=250.0,
        ix_mm4=10_000_000_000.0,
        top_fiber_y_from_bottom_mm=500.0,
    )
    result = girder_service_stress_at_y(basis, N_kN=1000.0, M_kNm=500.0, y_from_bottom_mm=250.0)
    assert result.bending_stress_MPa == pytest.approx(0.0)
    assert result.total_stress_MPa == pytest.approx(-2.0)


def test_girder_stress_result_to_dict_is_report_friendly():
    basis = make_girder_basis_from_gross_summary(summarize_geometry(rectangle(1000.0, 500.0)))
    result = run_basic_girder_service_stress(basis, N_kN=0.0, M_kNm=500.0)
    data = girder_service_stress_result_to_dict(result)
    assert data["basis_name"] == "precast_gross"
    assert data["top_stress_type"] == "compression"
    assert data["bottom_stress_type"] == "tension"
    assert "top_stress_MPa" in data
    assert "bottom_stress_MPa" in data


def test_invalid_girder_basis_or_input_raises_clear_error():
    with pytest.raises(ValueError, match="area"):
        run_basic_girder_service_stress(
            GirderSectionBasis(
                basis_name="precast_gross",
                area_mm2=0.0,
                centroid_y_from_bottom_mm=250.0,
                ix_mm4=10_000_000_000.0,
                top_fiber_y_from_bottom_mm=500.0,
            ),
            M_kNm=100.0,
        )


def test_girder_service_stress_validation_suite_passes():
    results = validate_girder_service_stress()
    assert results
    assert all(result.status == "PASS" for result in results)


def test_validation_runner_includes_girder_service_stress_suite():
    report = run_all_validations()
    summary = report.summary()
    case_ids = {result.case_id for result in report.results}
    assert "GIRDER.SLS.RECT.TOP" in case_ids
    assert summary["failed"] == 0
