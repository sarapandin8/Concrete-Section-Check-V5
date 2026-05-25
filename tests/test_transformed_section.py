from __future__ import annotations

import math

import pytest

from concrete_pmm_pro.core.analysis import AnalysisInput
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
from concrete_pmm_pro.io.project_io import project_from_json, project_to_json
from concrete_pmm_pro.serviceability import (
    ServiceabilitySettings,
    compute_gross_section_properties,
    compute_uncracked_transformed_section_properties,
    estimate_concrete_ec_mpa,
    modular_ratio,
    transformed_section_properties_to_dataframe,
)
from concrete_pmm_pro.serviceability.preflight import build_serviceability_summary_from_analysis_input


def _gross_props():
    return compute_gross_section_properties(rectangle(width_mm=400, height_mm=600))


def _settings(**kwargs) -> ServiceabilitySettings:
    return ServiceabilitySettings(use_transformed_section=True, concrete_Ec_MPa=30_000, **kwargs)


def _concrete() -> ConcreteMaterial:
    return ConcreteMaterial(name="C40", fc_MPa=40, density_kg_m3=2400)


def test_estimate_concrete_ec_mpa_aci_normal_weight() -> None:
    assert estimate_concrete_ec_mpa(40) == pytest.approx(4700 * math.sqrt(40))


def test_estimate_concrete_ec_mpa_rejects_invalid_fc() -> None:
    with pytest.raises(ValueError):
        estimate_concrete_ec_mpa(0)


def test_modular_ratio_returns_es_over_ec() -> None:
    assert modular_ratio(200_000, 25_000) == pytest.approx(8.0)


def test_modular_ratio_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        modular_ratio(200_000, 0)


def test_serviceability_settings_round_trip_preserves_use_transformed_section() -> None:
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


def test_transformed_section_concrete_only_equals_gross_properties() -> None:
    gross = _gross_props()
    transformed = compute_uncracked_transformed_section_properties(
        gross,
        _concrete(),
        [],
        [],
        [],
        [],
        _settings(),
    )

    assert transformed.area_mm2 == pytest.approx(gross.area_mm2)
    assert transformed.centroid_x_mm == pytest.approx(gross.centroid_x_mm)
    assert transformed.centroid_y_mm == pytest.approx(gross.centroid_y_mm)
    assert transformed.Ix_mm4 == pytest.approx(gross.Ix_mm4)
    assert transformed.Iy_mm4 == pytest.approx(gross.Iy_mm4)


def test_symmetric_rebar_increases_transformed_area() -> None:
    gross = _gross_props()
    rebars = [Rebar(x_mm=-100, y_mm=0, diameter_mm=25), Rebar(x_mm=100, y_mm=0, diameter_mm=25)]

    transformed = compute_uncracked_transformed_section_properties(
        gross,
        _concrete(),
        rebars,
        [RebarMaterial(name="SD40", fy_MPa=400, Es_MPa=200_000)],
        [],
        [],
        _settings(),
    )

    assert transformed.area_mm2 > gross.area_mm2
    assert transformed.transformed_rebar_area_mm2 > 0


def test_symmetric_rebar_does_not_shift_centroid_significantly() -> None:
    gross = _gross_props()
    rebars = [
        Rebar(x_mm=-100, y_mm=-250, diameter_mm=25),
        Rebar(x_mm=100, y_mm=-250, diameter_mm=25),
        Rebar(x_mm=-100, y_mm=250, diameter_mm=25),
        Rebar(x_mm=100, y_mm=250, diameter_mm=25),
    ]

    transformed = compute_uncracked_transformed_section_properties(
        gross,
        _concrete(),
        rebars,
        [RebarMaterial(name="SD40", fy_MPa=400, Es_MPa=200_000)],
        [],
        [],
        _settings(),
    )

    assert transformed.centroid_x_mm == pytest.approx(gross.centroid_x_mm, abs=1.0e-9)
    assert transformed.centroid_y_mm == pytest.approx(gross.centroid_y_mm, abs=1.0e-9)


def test_eccentric_rebar_shifts_centroid_toward_rebar() -> None:
    transformed = compute_uncracked_transformed_section_properties(
        _gross_props(),
        _concrete(),
        [Rebar(x_mm=150, y_mm=0, diameter_mm=40)],
        [RebarMaterial(name="SD40", fy_MPa=400, Es_MPa=200_000)],
        [],
        [],
        _settings(),
    )

    assert transformed.centroid_x_mm > 0


def test_rebar_increases_transformed_inertia_about_relevant_axis() -> None:
    gross = _gross_props()
    rebars = [Rebar(x_mm=0, y_mm=-250, diameter_mm=32), Rebar(x_mm=0, y_mm=250, diameter_mm=32)]

    transformed = compute_uncracked_transformed_section_properties(
        gross,
        _concrete(),
        rebars,
        [RebarMaterial(name="SD40", fy_MPa=400, Es_MPa=200_000)],
        [],
        [],
        _settings(),
    )

    assert transformed.Ix_mm4 > gross.Ix_mm4


def test_bonded_prestress_contributes_transformed_area_when_enabled() -> None:
    element = PrestressElement(x_mm=0, y_mm=-200, area_mm2=300, steel_type="prestressing_bar", ep_mpa=195_000, bonded=True)

    transformed = compute_uncracked_transformed_section_properties(
        _gross_props(),
        _concrete(),
        [],
        [],
        [element],
        [PrestressSteelMaterial(name="PT", steel_type="prestressing_bar", fpu_MPa=1230, Ep_MPa=195_000)],
        _settings(),
    )

    assert transformed.prestress_count == 1
    assert transformed.transformed_prestress_area_mm2 > 0


def test_unbonded_prestress_is_ignored_with_warning() -> None:
    element = PrestressElement(x_mm=0, y_mm=-200, area_mm2=300, steel_type="strand", bonded=False)

    transformed = compute_uncracked_transformed_section_properties(
        _gross_props(),
        _concrete(),
        [],
        [],
        [element],
        [],
        _settings(),
    )

    assert transformed.prestress_count == 0
    assert any("Unbonded prestress" in warning for warning in transformed.warnings)


def test_transformed_section_properties_to_dataframe_contains_required_fields() -> None:
    transformed = compute_uncracked_transformed_section_properties(
        _gross_props(),
        _concrete(),
        [Rebar(x_mm=0, y_mm=250, diameter_mm=25)],
        [RebarMaterial(name="SD40", fy_MPa=400, Es_MPa=200_000)],
        [],
        [],
        _settings(),
    )

    df = transformed_section_properties_to_dataframe(transformed)

    assert {
        "Ec_MPa",
        "Area_mm2",
        "Centroid x_mm",
        "Centroid y_mm",
        "Ix_mm4",
        "Iy_mm4",
        "Ixy_mm4",
        "Gross Concrete Area_mm2",
        "Transformed Rebar Area_mm2",
        "Transformed Prestress Area_mm2",
        "Rebar Count",
        "Prestress Count",
        "Warnings",
    }.issubset(df.columns)


def test_serviceability_preflight_includes_transformed_section_info_when_enabled() -> None:
    analysis_input = AnalysisInput(
        section_geometry=rectangle(width_mm=400, height_mm=600),
        concrete_material=_concrete(),
        rebar_materials=[RebarMaterial(name="SD40", fy_MPa=400, Es_MPa=200_000)],
        rebars=[Rebar(x_mm=0, y_mm=250, diameter_mm=25)],
        load_cases=[LoadCase(name="SLS-01", load_type="SLS")],
    )

    summary = build_serviceability_summary_from_analysis_input(analysis_input, _settings())

    assert summary.transformed_section_properties is not None
    assert any("Transformed section properties are available" in item for item in summary.info)


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
