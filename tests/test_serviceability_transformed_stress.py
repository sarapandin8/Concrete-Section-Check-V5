from __future__ import annotations

import pytest

from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, PrestressElement, Rebar, RebarMaterial
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.io.project_io import project_from_json, project_to_json
from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.serviceability import (
    ServiceabilitySettings,
    compute_gross_section_properties,
    compute_uncracked_transformed_section_properties,
    elastic_concrete_stress_gross,
    elastic_concrete_stress_section_basis,
    elastic_prestress_stress_section_basis,
    get_serviceability_section_basis,
    run_elastic_sls_stress_check,
    run_gross_section_sls_stress_check,
    service_stress_results_to_dataframe,
    summarize_effective_prestress_for_sls,
)


def _geometry():
    return rectangle(width_mm=400, height_mm=600)


def _gross_props():
    return compute_gross_section_properties(_geometry())


def _settings(**kwargs) -> ServiceabilitySettings:
    defaults = {
        "enabled": True,
        "concrete_Ec_MPa": 30_000.0,
        "concrete_tension_limit_MPa": 10.0,
    }
    defaults.update(kwargs)
    return ServiceabilitySettings(**defaults)


def _analysis_input(
    *,
    rebars: list[Rebar] | None = None,
    prestress_elements: list[PrestressElement] | None = None,
    load_cases: list[LoadCase] | None = None,
) -> AnalysisInput:
    return AnalysisInput(
        section_geometry=_geometry(),
        concrete_material=ConcreteMaterial(fc_MPa=40),
        rebar_materials=[RebarMaterial(name="SD40", fy_MPa=400, Es_MPa=200_000)],
        rebars=rebars or [],
        prestress_elements=prestress_elements or [],
        load_cases=load_cases
        or [LoadCase(name="SLS-01", Pu_N=0, Mux_Nmm=100_000_000, Muy_Nmm=0, load_type="SLS")],
    )


def test_elastic_concrete_stress_section_basis_axial_compression_is_negative() -> None:
    props = _gross_props()

    stress = elastic_concrete_stress_section_basis(
        240_000,
        0,
        0,
        0,
        0,
        props.area_mm2,
        props.centroid_x_mm,
        props.centroid_y_mm,
        props.Ix_mm4,
        props.Iy_mm4,
    )

    assert stress == pytest.approx(-1.0)


def test_elastic_concrete_stress_section_basis_bending_opposite_top_bottom() -> None:
    props = _gross_props()

    top = elastic_concrete_stress_section_basis(
        0,
        100_000_000,
        0,
        0,
        props.y_max_mm,
        props.area_mm2,
        props.centroid_x_mm,
        props.centroid_y_mm,
        props.Ix_mm4,
        props.Iy_mm4,
    )
    bottom = elastic_concrete_stress_section_basis(
        0,
        100_000_000,
        0,
        0,
        props.y_min_mm,
        props.area_mm2,
        props.centroid_x_mm,
        props.centroid_y_mm,
        props.Ix_mm4,
        props.Iy_mm4,
    )

    assert top > 0
    assert bottom < 0
    assert top == pytest.approx(-bottom)


def test_elastic_concrete_stress_gross_matches_generic_function() -> None:
    props = _gross_props()

    gross = elastic_concrete_stress_gross(240_000, 100_000_000, 50_000_000, 120, 200, props)
    generic = elastic_concrete_stress_section_basis(
        240_000,
        100_000_000,
        50_000_000,
        120,
        200,
        props.area_mm2,
        props.centroid_x_mm,
        props.centroid_y_mm,
        props.Ix_mm4,
        props.Iy_mm4,
        props.Ixy_mm4,
    )

    assert gross == pytest.approx(generic)


def test_get_serviceability_section_basis_returns_gross_when_transformed_disabled() -> None:
    props = _gross_props()

    basis = get_serviceability_section_basis(props, None, _settings(use_transformed_section=False))

    assert basis["basis_name"] == "gross"
    assert basis["area_mm2"] == pytest.approx(props.area_mm2)


def test_get_serviceability_section_basis_returns_transformed_when_available() -> None:
    props = _gross_props()
    transformed = compute_uncracked_transformed_section_properties(
        props,
        ConcreteMaterial(fc_MPa=40),
        [Rebar(x_mm=0, y_mm=250, diameter_mm=32)],
        [RebarMaterial(name="SD40", fy_MPa=400, Es_MPa=200_000)],
        [],
        [],
        _settings(use_transformed_section=True),
    )

    basis = get_serviceability_section_basis(props, transformed, _settings(use_transformed_section=True))

    assert basis["basis_name"] == "transformed_uncracked"
    assert basis["area_mm2"] == pytest.approx(transformed.area_mm2)


def test_get_serviceability_section_basis_falls_back_to_gross_with_warning() -> None:
    props = _gross_props()

    basis = get_serviceability_section_basis(props, None, _settings(use_transformed_section=True))

    assert basis["basis_name"] == "gross"
    assert any("unavailable" in warning for warning in basis["warnings"])


def test_transformed_concrete_only_stress_equals_gross_stress() -> None:
    analysis_input = _analysis_input()

    gross = run_elastic_sls_stress_check(analysis_input, _settings(use_transformed_section=False))
    transformed = run_elastic_sls_stress_check(
        analysis_input,
        _settings(use_transformed_section=True, transformed_include_rebar=False, transformed_include_prestress=False),
    )

    assert transformed.section_basis_used == "transformed_uncracked"
    for gross_result, transformed_result in zip(gross.stress_results, transformed.stress_results, strict=True):
        assert transformed_result.stress_MPa == pytest.approx(gross_result.stress_MPa)


def test_symmetric_transformed_rebar_increases_inertia_and_reduces_bending_stress() -> None:
    rebars = [
        Rebar(x_mm=-120, y_mm=250, diameter_mm=32),
        Rebar(x_mm=120, y_mm=250, diameter_mm=32),
        Rebar(x_mm=-120, y_mm=-250, diameter_mm=32),
        Rebar(x_mm=120, y_mm=-250, diameter_mm=32),
    ]
    analysis_input = _analysis_input(rebars=rebars)
    gross = run_elastic_sls_stress_check(analysis_input, _settings(use_transformed_section=False))
    transformed = run_elastic_sls_stress_check(analysis_input, _settings(use_transformed_section=True))

    assert transformed.transformed_section_properties is not None
    assert transformed.transformed_section_properties.Ix_mm4 > gross.section_properties.Ix_mm4
    gross_top = next(result for result in gross.stress_results if result.point_name == "Top fiber")
    transformed_top = next(result for result in transformed.stress_results if result.point_name == "Top fiber")
    assert abs(transformed_top.external_stress_MPa) < abs(gross_top.external_stress_MPa)


def test_eccentric_transformed_rebar_shifts_centroid_and_stress_uses_transformed_centroid() -> None:
    rebar = Rebar(x_mm=0, y_mm=250, diameter_mm=40)
    analysis_input = _analysis_input(rebars=[rebar])
    summary = run_elastic_sls_stress_check(analysis_input, _settings(use_transformed_section=True))

    assert summary.transformed_section_properties is not None
    assert summary.transformed_section_properties.centroid_y_mm > summary.section_properties.centroid_y_mm
    top = next(result for result in summary.stress_results if result.point_name == "Top fiber")
    manual = elastic_concrete_stress_section_basis(
        0,
        100_000_000,
        0,
        top.x_mm,
        top.y_mm,
        summary.transformed_section_properties.area_mm2,
        summary.transformed_section_properties.centroid_x_mm,
        summary.transformed_section_properties.centroid_y_mm,
        summary.transformed_section_properties.Ix_mm4,
        summary.transformed_section_properties.Iy_mm4,
        summary.transformed_section_properties.Ixy_mm4,
    )

    assert top.external_stress_MPa == pytest.approx(manual)


def test_run_elastic_sls_stress_check_gross_basis_matches_wrapper_behavior() -> None:
    analysis_input = _analysis_input()

    direct = run_elastic_sls_stress_check(analysis_input, _settings(use_transformed_section=False))
    wrapper = run_gross_section_sls_stress_check(analysis_input, _settings(use_transformed_section=False))

    assert direct.section_basis_used == "gross"
    assert wrapper.section_basis_used == "gross"
    assert [r.stress_MPa for r in direct.stress_results] == pytest.approx([r.stress_MPa for r in wrapper.stress_results])


def test_run_elastic_sls_stress_check_transformed_basis_marks_results() -> None:
    summary = run_elastic_sls_stress_check(
        _analysis_input(rebars=[Rebar(x_mm=0, y_mm=250, diameter_mm=32)]),
        _settings(use_transformed_section=True),
    )

    assert summary.section_basis_used == "transformed_uncracked"
    assert {result.section_basis for result in summary.stress_results} == {"transformed_uncracked"}


def test_transformed_stress_results_dataframe_includes_section_basis_columns() -> None:
    summary = run_elastic_sls_stress_check(
        _analysis_input(rebars=[Rebar(x_mm=0, y_mm=250, diameter_mm=32)]),
        _settings(use_transformed_section=True),
    )

    df = service_stress_results_to_dataframe(summary)

    assert {"Section Basis", "Section Area_mm2", "Section cx_mm", "Section cy_mm"}.issubset(df.columns)
    assert set(df["Section Basis"]) == {"transformed_uncracked"}


def test_effective_prestress_contribution_works_with_transformed_basis() -> None:
    summary = run_elastic_sls_stress_check(
        _analysis_input(
            rebars=[Rebar(x_mm=0, y_mm=250, diameter_mm=32)],
            prestress_elements=[PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=240_000, bonded=True)],
            load_cases=[LoadCase(name="SLS-01", Pu_N=0, Mux_Nmm=0, Muy_Nmm=0, load_type="SLS")],
        ),
        _settings(use_transformed_section=True, include_prestress_effective_force=True),
    )

    assert summary.section_basis_used == "transformed_uncracked"
    assert summary.prestress_included is True
    assert any(result.prestress_stress_MPa != pytest.approx(0.0) for result in summary.stress_results)


def test_top_eccentric_prestress_increases_top_compression_with_transformed_basis() -> None:
    analysis_input = _analysis_input(
        rebars=[Rebar(x_mm=0, y_mm=-250, diameter_mm=32)],
        prestress_elements=[PrestressElement(x_mm=0, y_mm=100, area_mm2=100, pe_eff_n=240_000, bonded=True)],
        load_cases=[LoadCase(name="SLS-01", Pu_N=0, Mux_Nmm=0, Muy_Nmm=0, load_type="SLS")],
    )
    summary = run_elastic_sls_stress_check(
        analysis_input,
        _settings(use_transformed_section=True, include_prestress_effective_force=True),
    )
    top = next(result for result in summary.stress_results if result.point_name == "Top fiber")
    bottom = next(result for result in summary.stress_results if result.point_name == "Bottom fiber")

    assert top.prestress_stress_MPa < bottom.prestress_stress_MPa


def test_bottom_eccentric_prestress_increases_bottom_compression_with_transformed_basis() -> None:
    analysis_input = _analysis_input(
        rebars=[Rebar(x_mm=0, y_mm=250, diameter_mm=32)],
        prestress_elements=[PrestressElement(x_mm=0, y_mm=-100, area_mm2=100, pe_eff_n=240_000, bonded=True)],
        load_cases=[LoadCase(name="SLS-01", Pu_N=0, Mux_Nmm=0, Muy_Nmm=0, load_type="SLS")],
    )
    summary = run_elastic_sls_stress_check(
        analysis_input,
        _settings(use_transformed_section=True, include_prestress_effective_force=True),
    )
    top = next(result for result in summary.stress_results if result.point_name == "Top fiber")
    bottom = next(result for result in summary.stress_results if result.point_name == "Bottom fiber")

    assert bottom.prestress_stress_MPa < top.prestress_stress_MPa


def test_elastic_prestress_stress_section_basis_matches_selected_centroid() -> None:
    props = _gross_props()
    contribution = summarize_effective_prestress_for_sls(
        [PrestressElement(x_mm=0, y_mm=100, area_mm2=100, pe_eff_n=240_000, bonded=True)],
        centroid_x_mm=0,
        centroid_y_mm=50,
        Ix_mm4=props.Ix_mm4,
        Iy_mm4=props.Iy_mm4,
        basis_name="transformed_uncracked",
    )

    assert contribution.Mpe_x_Nmm == pytest.approx(-240_000 * 50)
    top = elastic_prestress_stress_section_basis(
        0,
        props.y_max_mm,
        props.area_mm2,
        0,
        50,
        props.Ix_mm4,
        props.Iy_mm4,
        contribution,
    )
    bottom = elastic_prestress_stress_section_basis(
        0,
        props.y_min_mm,
        props.area_mm2,
        0,
        50,
        props.Ix_mm4,
        props.Iy_mm4,
        contribution,
    )

    assert top < bottom


def test_serviceability_settings_round_trip_preserves_transformed_stress_settings() -> None:
    project = ProjectModel(
        serviceability_settings=ServiceabilitySettings(
            use_transformed_section=True,
            concrete_Ec_MPa=31_000,
            transformed_include_rebar=False,
            transformed_include_prestress=True,
        )
    )

    loaded = project_from_json(project_to_json(project))

    assert loaded.serviceability_settings is not None
    assert loaded.serviceability_settings.use_transformed_section is True
    assert loaded.serviceability_settings.concrete_Ec_MPa == pytest.approx(31_000)
    assert loaded.serviceability_settings.transformed_include_rebar is False


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
