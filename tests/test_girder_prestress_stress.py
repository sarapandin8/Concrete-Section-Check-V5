import pytest

from concrete_pmm_pro.core.models import PrestressElement
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.serviceability.girder_prestress import (
    girder_prestress_stress_at_y,
    girder_prestress_stress_result_rows,
    girder_prestress_stress_result_to_dict,
    run_girder_prestress_stress_effect,
    summarize_girder_prestress_elements,
)
from concrete_pmm_pro.serviceability.girder_stress import make_girder_basis_from_gross_summary
from concrete_pmm_pro.validation.girder_prestress import validate_girder_prestress_stress
from concrete_pmm_pro.validation.runner import run_all_validations


def _rect_basis():
    return make_girder_basis_from_gross_summary(summarize_geometry(rectangle(1000.0, 500.0)))


def test_low_tendon_prestress_matches_hand_calculation_and_compresses_bottom():
    basis = _rect_basis()
    result = run_girder_prestress_stress_effect(basis, Pe_eff_kN=2000.0, tendon_y_from_bottom_mm=100.0)

    area = 1000.0 * 500.0
    ix = 1000.0 * 500.0**3 / 12.0
    axial = -2000.0 * 1000.0 / area
    mps = 2000.0 * (100.0 - 250.0) / 1000.0

    assert result.eccentricity_mm == pytest.approx(-150.0)
    assert result.equivalent_moment_kNm == pytest.approx(-300.0)
    assert result.top.axial_stress_MPa == pytest.approx(axial)
    assert result.bottom.axial_stress_MPa == pytest.approx(axial)
    assert result.top.total_stress_MPa == pytest.approx(axial + mps * 1_000_000.0 * (250.0 - 500.0) / ix)
    assert result.bottom.total_stress_MPa == pytest.approx(axial + mps * 1_000_000.0 * (250.0 - 0.0) / ix)
    assert result.bottom.total_stress_MPa < result.top.total_stress_MPa
    assert result.bottom.stress_type == "compression"


def test_centroidal_prestress_has_no_eccentric_bending_component():
    basis = _rect_basis()
    result = run_girder_prestress_stress_effect(basis, Pe_eff_kN=1000.0, tendon_y_from_bottom_mm=250.0)

    assert result.eccentricity_mm == pytest.approx(0.0)
    assert result.equivalent_moment_kNm == pytest.approx(0.0)
    assert result.top.eccentric_bending_stress_MPa == pytest.approx(0.0)
    assert result.bottom.eccentric_bending_stress_MPa == pytest.approx(0.0)
    assert result.top.total_stress_MPa == pytest.approx(-2.0)
    assert result.bottom.total_stress_MPa == pytest.approx(-2.0)


def test_high_tendon_increases_top_compression():
    basis = _rect_basis()
    result = run_girder_prestress_stress_effect(basis, Pe_eff_kN=2000.0, tendon_y_from_bottom_mm=400.0)

    assert result.eccentricity_mm == pytest.approx(150.0)
    assert result.equivalent_moment_kNm == pytest.approx(300.0)
    assert result.top.total_stress_MPa < result.bottom.total_stress_MPa
    assert result.top.stress_type == "compression"


def test_zero_prestress_is_allowed_and_returns_zero_stress():
    basis = _rect_basis()
    stress = girder_prestress_stress_at_y(basis, Pe_eff_kN=0.0, tendon_y_from_bottom_mm=100.0, y_from_bottom_mm=500.0)

    assert stress.axial_stress_MPa == pytest.approx(0.0)
    assert stress.eccentric_bending_stress_MPa == pytest.approx(0.0)
    assert stress.total_stress_MPa == pytest.approx(0.0)
    assert stress.stress_type == "zero"


def test_prestress_centroid_outside_basis_adds_warning_but_does_not_crash():
    basis = _rect_basis()
    result = run_girder_prestress_stress_effect(basis, Pe_eff_kN=1000.0, tendon_y_from_bottom_mm=-50.0)

    assert result.warnings
    assert "outside" in result.warnings[-1]


def test_invalid_negative_prestress_raises_clear_error():
    basis = _rect_basis()
    with pytest.raises(ValueError, match="Pe_eff_kN"):
        run_girder_prestress_stress_effect(basis, Pe_eff_kN=-1.0, tendon_y_from_bottom_mm=100.0)


def test_prestress_element_summary_uses_pe_eff_only_and_count_once():
    elements = [
        PrestressElement(x_mm=0.0, y_mm=-150.0, area_mm2=140.0, pe_eff_n=100_000.0, count=2, label="PS1"),
        PrestressElement(x_mm=0.0, y_mm=-50.0, area_mm2=140.0, pe_eff_n=200_000.0, count=1, label="PS2"),
        PrestressElement(x_mm=0.0, y_mm=0.0, area_mm2=140.0, pe_eff_n=0.0, count=1, label="Passive"),
    ]
    summary = summarize_girder_prestress_elements(elements, section_bottom_y_mm=-250.0)

    assert summary.total_pe_eff_kN == pytest.approx(400.0)
    assert summary.tendon_y_from_bottom_mm == pytest.approx(150.0)
    assert summary.included_element_count == 2
    assert summary.ignored_element_count == 1
    assert any("pe_eff_n only" in item for item in summary.info)
    assert any("no positive Pe_eff" in item for item in summary.warnings)


def test_prestress_element_summary_can_ignore_unbonded_when_requested():
    elements = [
        PrestressElement(x_mm=0.0, y_mm=-150.0, area_mm2=140.0, pe_eff_n=100_000.0, count=1, bonded=True, label="Bonded"),
        PrestressElement(x_mm=0.0, y_mm=-50.0, area_mm2=140.0, pe_eff_n=200_000.0, count=1, bonded=False, label="Unbonded"),
    ]
    summary = summarize_girder_prestress_elements(elements, section_bottom_y_mm=-250.0, include_unbonded=False)

    assert summary.total_pe_eff_kN == pytest.approx(100.0)
    assert summary.tendon_y_from_bottom_mm == pytest.approx(100.0)
    assert summary.ignored_element_count == 1
    assert any("Unbonded" in item for item in summary.warnings)


def test_prestress_result_helpers_are_ui_report_ready():
    result = run_girder_prestress_stress_effect(_rect_basis(), Pe_eff_kN=2000.0, tendon_y_from_bottom_mm=100.0)
    rows = girder_prestress_stress_result_rows(result)
    data = girder_prestress_stress_result_to_dict(result)

    assert [row["Fiber"] for row in rows] == ["Top", "Bottom"]
    assert "Total prestress stress (MPa)" in rows[0]
    assert data["Pe_eff_kN"] == pytest.approx(2000.0)
    assert data["equivalent_moment_kNm"] == pytest.approx(-300.0)
    assert "bottom_prestress_stress_MPa" in data


def test_girder_prestress_validation_suite_passes():
    results = validate_girder_prestress_stress()
    assert results
    assert all(result.status == "PASS" for result in results)


def test_validation_runner_includes_girder_prestress_suite():
    report = run_all_validations()
    summary = report.summary()
    case_ids = {result.case_id for result in report.results}
    assert "GIRDER.PS.LOW.BOTTOM" in case_ids
    assert summary["failed"] == 0
