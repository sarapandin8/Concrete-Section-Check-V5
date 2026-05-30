import pytest

from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.serviceability.girder_stage import (
    GirderServiceStageCase,
    default_girder_service_stage_templates,
    girder_service_stage_result_rows,
    girder_service_stage_result_to_dict,
    run_girder_service_stage_stress,
)
from concrete_pmm_pro.serviceability.girder_stress import make_girder_basis_from_gross_summary
from concrete_pmm_pro.validation.girder_stage import validate_girder_service_stage_stress
from concrete_pmm_pro.validation.runner import run_all_validations


def _rect_basis():
    return make_girder_basis_from_gross_summary(summarize_geometry(rectangle(1000.0, 500.0)))


def test_service_stage_without_prestress_matches_hand_calculation():
    basis = _rect_basis()
    case = GirderServiceStageCase(
        stage_id="SVC",
        title="Service-only stage",
        basis_name="precast_gross",
        N_kN=1000.0,
        M_kNm=500.0,
        include_prestress=False,
    )
    result = run_girder_service_stage_stress(basis, case)

    area = 1000.0 * 500.0
    ix = 1000.0 * 500.0**3 / 12.0
    axial = -1000.0 * 1000.0 / area
    assert result.prestress_result is None
    assert result.top.total_stress_MPa == pytest.approx(axial + 500.0 * 1_000_000.0 * (250.0 - 500.0) / ix)
    assert result.bottom.total_stress_MPa == pytest.approx(axial + 500.0 * 1_000_000.0 * (250.0 - 0.0) / ix)
    assert result.top.service_total_stress_MPa == pytest.approx(result.top.total_stress_MPa)
    assert result.top.prestress_total_stress_MPa == pytest.approx(0.0)


def test_service_stage_combines_service_and_effective_prestress_components():
    basis = _rect_basis()
    case = GirderServiceStageCase(
        stage_id="FINAL",
        title="Final combined stress",
        basis_name="precast_gross",
        N_kN=0.0,
        M_kNm=500.0,
        include_prestress=True,
        Pe_eff_kN=2000.0,
        tendon_y_from_bottom_mm=100.0,
    )
    result = run_girder_service_stage_stress(basis, case)

    assert result.prestress_result is not None
    assert result.prestress_result.eccentricity_mm == pytest.approx(-150.0)
    assert result.top.total_stress_MPa == pytest.approx(result.top.service_total_stress_MPa + result.top.prestress_total_stress_MPa)
    assert result.bottom.total_stress_MPa == pytest.approx(result.bottom.service_total_stress_MPa + result.bottom.prestress_total_stress_MPa)
    assert result.bottom.prestress_total_stress_MPa < result.top.prestress_total_stress_MPa


def test_service_stage_warns_when_prestress_requested_without_centroid():
    result = run_girder_service_stage_stress(
        _rect_basis(),
        GirderServiceStageCase(
            stage_id="BAD_PS",
            title="Missing PS centroid",
            basis_name="precast_gross",
            include_prestress=True,
            Pe_eff_kN=1000.0,
        ),
    )

    assert result.prestress_result is None
    assert result.warnings
    assert any("tendon_y_from_bottom" in warning for warning in result.warnings)


def test_stage_case_basis_mismatch_is_warning_not_silent():
    result = run_girder_service_stage_stress(
        _rect_basis(),
        GirderServiceStageCase(
            stage_id="MISMATCH",
            title="Basis mismatch",
            basis_name="composite_transformed",
        ),
    )
    assert any("does not match" in warning for warning in result.warnings)


def test_default_stage_templates_are_guidance_only():
    templates = default_girder_service_stage_templates()

    assert [template.stage_id for template in templates] == [
        "TRANSFER_PRECAST",
        "DECK_CASTING_PRECOMPOSITE",
        "FINAL_SERVICE_COMPOSITE",
        "LIVE_LOAD_COMPOSITE",
    ]
    assert {template.recommended_basis_name for template in templates} == {"precast_gross", "composite_transformed"}
    assert any("explicitly" in template.engineering_note for template in templates)


def test_stage_result_rows_and_dict_are_ui_report_ready():
    result = run_girder_service_stage_stress(
        _rect_basis(),
        GirderServiceStageCase(
            stage_id="FINAL",
            title="Final combined stress",
            basis_name="precast_gross",
            M_kNm=500.0,
            include_prestress=True,
            Pe_eff_kN=2000.0,
            tendon_y_from_bottom_mm=100.0,
        ),
    )
    rows = girder_service_stage_result_rows(result)
    data = girder_service_stage_result_to_dict(result)

    assert [row["Fiber"] for row in rows] == ["Top", "Bottom"]
    assert "Total stress (MPa)" in rows[0]
    assert data["stage_id"] == "FINAL"
    assert data["includes_prestress"] is True
    assert data["Pe_eff_kN"] == pytest.approx(2000.0)


def test_invalid_stage_inputs_raise_clear_errors():
    with pytest.raises(ValueError, match="stage_id"):
        run_girder_service_stage_stress(
            _rect_basis(),
            GirderServiceStageCase(stage_id="", title="Bad", basis_name="precast_gross"),
        )
    with pytest.raises(ValueError, match="Pe_eff"):
        run_girder_service_stage_stress(
            _rect_basis(),
            GirderServiceStageCase(stage_id="NEG", title="Negative PS", basis_name="precast_gross", Pe_eff_kN=-1.0),
        )


def test_girder_service_stage_validation_suite_passes():
    results = validate_girder_service_stage_stress()
    assert results
    assert all(result.status == "PASS" for result in results)


def test_validation_runner_includes_girder_service_stage_suite():
    report = run_all_validations()
    summary = report.summary()
    case_ids = {result.case_id for result in report.results}
    assert "GIRDER.STAGE.COMBINED.BOTTOM" in case_ids
    assert summary["failed"] == 0
