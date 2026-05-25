from __future__ import annotations

import pytest

from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, PrestressElement
from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.io.project_io import project_from_json, project_to_json
from concrete_pmm_pro.serviceability import (
    ServiceabilitySettings,
    compute_gross_section_properties,
    elastic_concrete_stress_gross_with_prestress,
    elastic_prestress_stress_gross,
    prestress_service_contribution_to_dataframe,
    run_gross_section_sls_stress_check,
    service_stress_results_to_dataframe,
    summarize_effective_prestress_for_sls,
)


def _props():
    return compute_gross_section_properties(rectangle(width_mm=400, height_mm=600))


def _analysis_input(prestress_elements: list[PrestressElement], load_cases: list[LoadCase] | None = None) -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400, height_mm=600),
        concrete_material=ConcreteMaterial(fc_MPa=40),
        prestress_elements=prestress_elements,
        load_cases=load_cases or [LoadCase(name="SLS-01", Pu_N=0, Mux_Nmm=0, Muy_Nmm=0, load_type="SLS")],
    )


def test_summarize_effective_prestress_for_sls_includes_bonded_pe_eff() -> None:
    element = PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=120_000, bonded=True, label="PS1")

    contribution = summarize_effective_prestress_for_sls([element], _props())

    assert contribution.bonded_count == 1
    assert contribution.total_pe_eff_N == pytest.approx(120_000)


def test_summarize_effective_prestress_for_sls_ignores_unbonded_with_warning() -> None:
    element = PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=120_000, bonded=False, label="UB")

    contribution = summarize_effective_prestress_for_sls([element], _props())

    assert contribution.unbonded_ignored_count == 1
    assert contribution.total_pe_eff_N == pytest.approx(0)
    assert any("Unbonded" in warning for warning in contribution.warnings)


def test_summarize_effective_prestress_for_sls_computes_total_pe_from_sources() -> None:
    elements = [
        PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=100_000, bonded=True),
        PrestressElement(x_mm=0, y_mm=0, area_mm2=200, initial_stress_mpa=500, bonded=True, count=2),
        PrestressElement(x_mm=0, y_mm=0, area_mm2=100, initial_strain=0.002, ep_mpa=200_000, bonded=True),
    ]

    contribution = summarize_effective_prestress_for_sls(elements, _props())

    assert contribution.total_pe_eff_N == pytest.approx(100_000 + 200 * 500 * 2 + 0.002 * 200_000 * 100)


def test_summarize_effective_prestress_for_sls_computes_centroid() -> None:
    elements = [
        PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=100_000, bonded=True),
        PrestressElement(x_mm=100, y_mm=40, area_mm2=100, pe_eff_n=300_000, bonded=True),
    ]

    contribution = summarize_effective_prestress_for_sls(elements, _props())

    assert contribution.centroid_x_mm == pytest.approx(75.0)
    assert contribution.centroid_y_mm == pytest.approx(30.0)


def test_summarize_effective_prestress_for_sls_computes_mpe_x_and_y() -> None:
    elements = [PrestressElement(x_mm=100, y_mm=50, area_mm2=100, pe_eff_n=200_000, bonded=True)]

    contribution = summarize_effective_prestress_for_sls(elements, _props())

    assert contribution.Mpe_x_Nmm == pytest.approx(-200_000 * 50)
    assert contribution.Mpe_y_Nmm == pytest.approx(-200_000 * 100)


def test_elastic_prestress_stress_gross_concentric_negative_at_centroid() -> None:
    props = _props()
    contribution = summarize_effective_prestress_for_sls(
        [PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=240_000, bonded=True)],
        props,
    )

    stress = elastic_prestress_stress_gross(0, 0, props, contribution)

    assert stress == pytest.approx(-1.0)


def test_prestress_above_centroid_increases_top_compression() -> None:
    props = _props()
    contribution = summarize_effective_prestress_for_sls(
        [PrestressElement(x_mm=0, y_mm=100, area_mm2=100, pe_eff_n=240_000, bonded=True)],
        props,
    )

    top = elastic_prestress_stress_gross(0, props.y_max_mm, props, contribution)
    bottom = elastic_prestress_stress_gross(0, props.y_min_mm, props, contribution)

    assert top < bottom
    assert top != pytest.approx(bottom)


def test_prestress_below_centroid_increases_bottom_compression() -> None:
    props = _props()
    contribution = summarize_effective_prestress_for_sls(
        [PrestressElement(x_mm=0, y_mm=-100, area_mm2=100, pe_eff_n=240_000, bonded=True)],
        props,
    )

    top = elastic_prestress_stress_gross(0, props.y_max_mm, props, contribution)
    bottom = elastic_prestress_stress_gross(0, props.y_min_mm, props, contribution)

    assert bottom < top
    assert bottom != pytest.approx(top)


def test_prestress_right_of_centroid_increases_right_compression() -> None:
    props = _props()
    contribution = summarize_effective_prestress_for_sls(
        [PrestressElement(x_mm=100, y_mm=0, area_mm2=100, pe_eff_n=240_000, bonded=True)],
        props,
    )

    right = elastic_prestress_stress_gross(props.x_max_mm, 0, props, contribution)
    left = elastic_prestress_stress_gross(props.x_min_mm, 0, props, contribution)

    assert right < left
    assert right != pytest.approx(left)


def test_prestress_left_of_centroid_increases_left_compression() -> None:
    props = _props()
    contribution = summarize_effective_prestress_for_sls(
        [PrestressElement(x_mm=-100, y_mm=0, area_mm2=100, pe_eff_n=240_000, bonded=True)],
        props,
    )

    right = elastic_prestress_stress_gross(props.x_max_mm, 0, props, contribution)
    left = elastic_prestress_stress_gross(props.x_min_mm, 0, props, contribution)

    assert left < right
    assert left != pytest.approx(right)


def test_elastic_concrete_stress_gross_with_prestress_returns_parts() -> None:
    props = _props()
    contribution = summarize_effective_prestress_for_sls(
        [PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=240_000, bonded=True)],
        props,
    )

    parts = elastic_concrete_stress_gross_with_prestress(240_000, 0, 0, 0, 0, props, contribution)

    assert parts["external_stress_MPa"] == pytest.approx(-1.0)
    assert parts["prestress_stress_MPa"] == pytest.approx(-1.0)
    assert parts["total_stress_MPa"] == pytest.approx(-2.0)


def test_run_gross_section_sls_stress_check_without_prestress_matches_external_stress() -> None:
    summary = run_gross_section_sls_stress_check(
        _analysis_input([PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=240_000, bonded=True)]),
        ServiceabilitySettings(include_prestress_effective_force=False),
    )

    assert summary.prestress_included is False
    assert all(result.prestress_stress_MPa == pytest.approx(0.0) for result in summary.stress_results)
    assert all(result.total_stress_MPa == pytest.approx(result.external_stress_MPa) for result in summary.stress_results)


def test_run_gross_section_sls_stress_check_with_prestress_changes_total_stress() -> None:
    summary = run_gross_section_sls_stress_check(
        _analysis_input([PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=240_000, bonded=True)]),
        ServiceabilitySettings(include_prestress_effective_force=True),
    )

    assert summary.prestress_included is True
    assert any(result.prestress_stress_MPa != pytest.approx(0.0) for result in summary.stress_results)
    assert any(result.total_stress_MPa != pytest.approx(result.external_stress_MPa) for result in summary.stress_results)


def test_status_check_uses_total_stress_when_prestress_is_included() -> None:
    summary = run_gross_section_sls_stress_check(
        _analysis_input([PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=2_400_000, bonded=True)]),
        ServiceabilitySettings(
            include_prestress_effective_force=True,
            concrete_compression_limit_ratio=0.10,
        ),
    )

    assert summary.overall_status == "FAIL"
    assert any(result.status == "FAIL" and result.total_stress_MPa < 0 for result in summary.stress_results)


def test_service_stress_results_dataframe_includes_stress_parts() -> None:
    summary = run_gross_section_sls_stress_check(
        _analysis_input([PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=240_000, bonded=True)]),
        ServiceabilitySettings(include_prestress_effective_force=True),
    )

    df = service_stress_results_to_dataframe(summary)

    assert {"External Stress_MPa", "Prestress Stress_MPa", "Total Stress_MPa", "Stress_MPa"}.issubset(df.columns)


def test_prestress_service_contribution_dataframe_has_total_pe_and_mpe_columns() -> None:
    contribution = summarize_effective_prestress_for_sls(
        [PrestressElement(x_mm=100, y_mm=50, area_mm2=100, pe_eff_n=200_000, bonded=True)],
        _props(),
    )

    df = prestress_service_contribution_to_dataframe(contribution)

    assert {"Total Pe_kN", "Mpe_x_kNm", "Mpe_y_kNm"}.issubset(df.columns)


def test_serviceability_settings_round_trip_preserves_include_prestress_effective_force() -> None:
    project = ProjectModel(serviceability_settings=ServiceabilitySettings(include_prestress_effective_force=True))

    loaded = project_from_json(project_to_json(project))

    assert loaded.serviceability_settings is not None
    assert loaded.serviceability_settings.include_prestress_effective_force is True


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
