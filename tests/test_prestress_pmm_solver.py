from __future__ import annotations

import pytest

from concrete_pmm_pro.analysis.pmm_solver import (
    neutral_axis_depth_range,
    prestress_tensile_stress_mpa,
    prestress_total_tensile_strain,
    run_rc_pmm_solver,
)
from concrete_pmm_pro.analysis.prestress_stress import (
    PRESTRESS_COMPRESSION_REVERSAL_WARNING,
    PRESTRESS_FPU_CAP_WARNING,
    PRESTRESS_LINEAR_CAP_FALLBACK_WARNING,
    prestress_stress_mpa,
)
from concrete_pmm_pro.analysis.result_models import pmm_result_to_display_dataframe
from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, PrestressElement, Rebar, RebarMaterial
from concrete_pmm_pro.geometry.generators import rectangle


def _analysis_input(element: PrestressElement, include_prestress: bool = True) -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400, height_mm=600),
        concrete_material=ConcreteMaterial(name="C35", fc_MPa=35, ecu=0.003, beta1=0.80),
        rebar_materials=[RebarMaterial(name="SD40", fy_MPa=400, Es_MPa=200000)],
        rebars=[
            Rebar(x_mm=-150, y_mm=-250, diameter_mm=25, material_name="SD40", label="B1"),
            Rebar(x_mm=150, y_mm=250, diameter_mm=25, material_name="SD40", label="B2"),
        ],
        prestress_elements=[element],
        load_cases=[LoadCase(name="ULS-01", Pu_N=500_000, Mux_Nmm=80_000_000, Muy_Nmm=0, load_type="ULS")],
        settings=AnalysisSettings(
            include_prestress=include_prestress,
            neutral_axis_angle_steps=12,
            neutral_axis_depth_steps=10,
        ),
    )


def _analysis_input_with_model(element: PrestressElement, model: str) -> AnalysisInput:
    analysis_input = _analysis_input(element)
    analysis_input.settings = analysis_input.settings.model_copy(update={"prestress_stress_model": model})
    return analysis_input


def _prestress_only_analysis_input(element: PrestressElement) -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400, height_mm=600),
        concrete_material=ConcreteMaterial(name="C35", fc_MPa=35, ecu=0.003, beta1=0.80),
        rebar_materials=[],
        rebars=[],
        prestress_elements=[element],
        load_cases=[LoadCase(name="ULS-01", Pu_N=500_000, Mux_Nmm=80_000_000, Muy_Nmm=0, load_type="ULS")],
        settings=AnalysisSettings(
            include_prestress=True,
            neutral_axis_angle_steps=12,
            neutral_axis_depth_steps=10,
        ),
    )


def _bonded_strand(**updates: object) -> PrestressElement:
    data = {
        "x_mm": 0.0,
        "y_mm": -180.0,
        "area_mm2": 100.0,
        "steel_type": "strand",
        "fpu_mpa": 1860.0,
        "ep_mpa": 195000.0,
        "initial_strain": 0.005,
        "bonded": True,
        "count": 2,
        "label": "PS1",
    }
    data.update(updates)
    return PrestressElement(**data)


def test_prestress_total_tensile_strain_reduced_by_section_compression() -> None:
    assert prestress_total_tensile_strain(0.005, 0.001) == pytest.approx(0.004)


def test_prestress_total_tensile_strain_increased_by_section_tension() -> None:
    assert prestress_total_tensile_strain(0.005, -0.001) == pytest.approx(0.006)


def test_passive_prestress_compression_strain_clamps_stress_to_zero() -> None:
    element = _bonded_strand(initial_strain=0.0, fpu_mpa=1860.0)

    assert prestress_total_tensile_strain(0.0, 0.001) == pytest.approx(-0.001)
    assert prestress_tensile_stress_mpa(element, 0.0, 0.001) == pytest.approx(0.0)


def test_passive_prestress_tension_strain_creates_positive_tensile_stress() -> None:
    element = _bonded_strand(initial_strain=0.0, ep_mpa=195000.0, fpu_mpa=1860.0)

    assert prestress_total_tensile_strain(0.0, -0.001) == pytest.approx(0.001)
    assert prestress_tensile_stress_mpa(element, 0.0, -0.001) == pytest.approx(195.0)


def test_prestress_stress_linear_cap_caps_at_fpu() -> None:
    stress, warnings = prestress_stress_mpa(0.02, Ep_MPa=195000.0, fpu_MPa=1860.0, model="linear_cap")

    assert stress == pytest.approx(1860.0)
    assert PRESTRESS_FPU_CAP_WARNING in warnings


def test_prestress_stress_bilinear_uses_fpy_and_post_yield_slope() -> None:
    stress, warnings = prestress_stress_mpa(0.006, Ep_MPa=200000.0, fpu_MPa=1200.0, fpy_MPa=1000.0, model="bilinear")

    assert stress == pytest.approx(1000.0 + 0.02 * 200000.0 * (0.006 - 0.005))
    assert warnings == []


def test_prestress_stress_bilinear_caps_at_fpu() -> None:
    stress, warnings = prestress_stress_mpa(0.08, Ep_MPa=195000.0, fpu_MPa=1230.0, fpy_MPa=1080.0, model="bilinear")

    assert stress == pytest.approx(1230.0)
    assert PRESTRESS_FPU_CAP_WARNING in warnings


def test_prestress_stress_missing_fpy_falls_back_to_linear_cap() -> None:
    stress, warnings = prestress_stress_mpa(0.004, Ep_MPa=195000.0, fpu_MPa=1860.0, model="bilinear")

    assert stress == pytest.approx(780.0)
    assert PRESTRESS_LINEAR_CAP_FALLBACK_WARNING in warnings


def test_prestress_stress_negative_strain_clamps_with_warning() -> None:
    stress, warnings = prestress_stress_mpa(-0.001, Ep_MPa=195000.0, fpu_MPa=1860.0, fpy_MPa=1600.0)

    assert stress == pytest.approx(0.0)
    assert PRESTRESS_COMPRESSION_REVERSAL_WARNING in warnings


def test_prestress_stress_rejects_invalid_fpy() -> None:
    with pytest.raises(ValueError):
        prestress_stress_mpa(0.004, Ep_MPa=195000.0, fpu_MPa=1000.0, fpy_MPa=1000.0)


def test_bonded_prestress_element_is_included_when_enabled() -> None:
    result = run_rc_pmm_solver(_analysis_input(_bonded_strand()))

    assert result.points
    assert all(point.bonded_prestress_count == 2 for point in result.points)
    assert any(abs(point.prestress_force_N) > 0 for point in result.points)
    assert any("Bonded prestress is included" in warning for warning in result.warnings)


def test_bonded_prestress_tracks_eps_t_for_phi_when_no_rebar_exists() -> None:
    result = run_rc_pmm_solver(
        _prestress_only_analysis_input(
            _bonded_strand(
                y_mm=-250.0,
                area_mm2=140.0,
                fpy_mpa=1580.0,
                initial_strain=0.0,
                count=1,
            )
        )
    )

    tension_points = [point for point in result.points if point.eps_t is not None]

    assert tension_points
    assert any(point.phi > 0.65 for point in tension_points)
    assert any(point.strain_condition in {"transition", "tension-controlled"} for point in tension_points)


def test_prestress_element_is_ignored_when_include_prestress_false() -> None:
    result = run_rc_pmm_solver(_analysis_input(_bonded_strand(), include_prestress=False))

    assert all(point.bonded_prestress_count == 0 for point in result.points)
    assert all(point.prestress_force_N == pytest.approx(0.0) for point in result.points)
    assert any("excluded by analysis settings" in warning for warning in result.warnings)


def test_unbonded_prestress_element_is_ignored_with_warning() -> None:
    result = run_rc_pmm_solver(_analysis_input(_bonded_strand(bonded=False)))

    assert all(point.bonded_prestress_count == 0 for point in result.points)
    assert all(point.unbonded_prestress_ignored_count == 2 for point in result.points)
    assert any("Unbonded prestress is not included" in warning for warning in result.warnings)


def test_initial_strain_is_used_when_provided() -> None:
    result = run_rc_pmm_solver(_analysis_input(_bonded_strand(initial_strain=0.004, initial_stress_mpa=1200.0)))

    assert any(point.prestress_force_N < 0 for point in result.points)


def test_initial_stress_is_converted_to_initial_strain_when_needed() -> None:
    strain_result = run_rc_pmm_solver(_analysis_input(_bonded_strand(initial_strain=0.005, initial_stress_mpa=None)))
    stress_result = run_rc_pmm_solver(_analysis_input(_bonded_strand(initial_strain=None, initial_stress_mpa=975.0)))

    assert [point.prestress_force_N for point in stress_result.points] == pytest.approx(
        [point.prestress_force_N for point in strain_result.points]
    )


def test_pe_eff_is_converted_to_initial_stress_and_strain_when_needed() -> None:
    strain_result = run_rc_pmm_solver(_analysis_input(_bonded_strand(initial_strain=0.005, initial_stress_mpa=None, pe_eff_n=0.0)))
    pe_result = run_rc_pmm_solver(_analysis_input(_bonded_strand(initial_strain=None, initial_stress_mpa=None, pe_eff_n=97_500.0)))

    assert [point.prestress_force_N for point in pe_result.points] == pytest.approx(
        [point.prestress_force_N for point in strain_result.points]
    )


def test_passive_high_strength_prestressing_bar_does_not_crash() -> None:
    result = run_rc_pmm_solver(
        _analysis_input(
            _bonded_strand(
                steel_type="prestressing_bar",
                initial_strain=None,
                initial_stress_mpa=None,
                pe_eff_n=0.0,
                fpy_mpa=1080.0,
                fpu_mpa=1230.0,
                label="PT1",
            )
        )
    )

    assert result.points
    assert any("Passive bonded prestressing steel is included" in item for item in result.info)
    assert not any("compression reversal" in warning.lower() for warning in result.warnings)
    assert not any("reached fpu cap" in warning.lower() for warning in result.warnings)


def test_passive_bonded_prestress_uses_signed_passive_steel_without_active_warnings() -> None:
    result = run_rc_pmm_solver(
        _prestress_only_analysis_input(
            _bonded_strand(
                y_mm=-250.0,
                area_mm2=804.2,
                steel_type="prestressing_bar",
                initial_strain=None,
                initial_stress_mpa=None,
                pe_eff_n=0.0,
                fpy_mpa=1080.0,
                fpu_mpa=1230.0,
                ep_mpa=200000.0,
                count=1,
                label="PS Bar Passive",
            )
        )
    )

    assert result.points
    assert any(point.prestress_force_N < 0.0 for point in result.points)
    assert any(point.prestress_force_N > 0.0 for point in result.points)
    assert any(point.eps_t is not None for point in result.points)
    assert not any("compression reversal" in warning.lower() for warning in result.warnings)
    assert not any("reached fpu cap" in warning.lower() for warning in result.warnings)


def test_pt_bar_prestressing_bar_type_is_included_when_bonded() -> None:
    result = run_rc_pmm_solver(_analysis_input(_bonded_strand(steel_type="prestressing_bar", fpy_mpa=1080.0, fpu_mpa=1230.0)))

    assert all(point.bonded_prestress_count == 2 for point in result.points)


def test_bonded_pt_bar_with_fpy_uses_bilinear_model() -> None:
    result = run_rc_pmm_solver(
        _analysis_input_with_model(
            _bonded_strand(steel_type="prestressing_bar", fpy_mpa=1080.0, fpu_mpa=1230.0, initial_strain=0.02),
            "bilinear",
        )
    )

    assert result.points
    assert any(point.max_prestress_stress_MPa > 1080.0 for point in result.points)
    assert all(point.prestress_stress_model == "bilinear" for point in result.points)


def test_bonded_pt_bar_without_fpy_warns_and_uses_fallback() -> None:
    result = run_rc_pmm_solver(
        _analysis_input_with_model(
            _bonded_strand(steel_type="prestressing_bar", fpy_mpa=None, fpu_mpa=1230.0, initial_strain=0.004),
            "bilinear",
        )
    )

    assert any("missing fpy" in warning or "linear capped prestress model used" in warning for warning in result.warnings)


def test_solver_runs_bonded_prestress_with_linear_cap_model() -> None:
    result = run_rc_pmm_solver(_analysis_input_with_model(_bonded_strand(fpy_mpa=1600.0), "linear_cap"))

    assert result.points
    assert all(point.prestress_stress_model == "linear_cap" for point in result.points)


def test_neutral_axis_depth_range_uses_relative_minimum_for_large_section() -> None:
    c_min, c_max = neutral_axis_depth_range(5000.0)

    assert c_min == pytest.approx(5.0)
    assert c_max == pytest.approx(25_000.0)


def test_neutral_axis_depth_range_keeps_one_mm_minimum_for_small_section() -> None:
    c_min, c_max = neutral_axis_depth_range(100.0)

    assert c_min == pytest.approx(1.0)
    assert c_max == pytest.approx(500.0)


def test_pmm_display_dataframe_includes_prestress_summary_columns() -> None:
    df = pmm_result_to_display_dataframe(run_rc_pmm_solver(_analysis_input(_bonded_strand())))

    assert {
        "prestress_force_N",
        "prestress_force_kN",
        "prestress_count",
        "bonded_prestress_count",
        "unbonded_prestress_ignored_count",
        "prestress_stress_model",
        "prestress_stress_warning_count",
        "max_prestress_stress_MPa",
        "prestress_reached_fpu_cap_count",
    }.issubset(df.columns)


def test_solver_reports_prestress_aware_axial_cap_when_bonded_prestress_exists() -> None:
    result = run_rc_pmm_solver(_analysis_input(_bonded_strand(fpy_mpa=1580.0, fpu_mpa=1860.0)))

    assert any("bonded prestress steel" in item for item in result.info)
    assert any("QA.PO1-validated prestress-aware Po helper" in warning for warning in result.warnings)
    assert not any("Prestress contribution to axial cap is future work" in warning for warning in result.warnings)


def test_bonded_prestress_result_differs_from_rc_only_result() -> None:
    element = _bonded_strand()
    with_prestress = run_rc_pmm_solver(_analysis_input(element, include_prestress=True))
    rc_only = run_rc_pmm_solver(_analysis_input(element, include_prestress=False))

    assert any(
        prestress_point.Pn_N != pytest.approx(rc_point.Pn_N)
        for prestress_point, rc_point in zip(with_prestress.points, rc_only.points)
    )


def test_active_prestress_fpu_cap_is_metadata_not_global_warning() -> None:
    result = run_rc_pmm_solver(
        _analysis_input_with_model(
            _bonded_strand(fpy_mpa=1080.0, fpu_mpa=1230.0, initial_strain=0.08, steel_type="prestressing_bar"),
            "bilinear",
        )
    )
    df = pmm_result_to_display_dataframe(result)

    assert int(df["prestress_reached_fpu_cap_count"].sum()) > 0
    assert any("retained as PMM stress-state metadata" in item for item in result.info)
    assert not any("reached fpu cap" in warning.lower() for warning in result.warnings)


def test_active_prestress_compression_reversal_is_metadata_not_global_warning() -> None:
    result = run_rc_pmm_solver(
        _analysis_input_with_model(
            _bonded_strand(initial_strain=0.0001, fpy_mpa=1580.0, fpu_mpa=1860.0),
            "bilinear",
        )
    )
    df = pmm_result_to_display_dataframe(result)

    assert int(df["prestress_compression_reversal_count"].sum()) > 0
    assert any("compression reversal" in item.lower() and "metadata" in item.lower() for item in result.info)
    assert not any("compression reversal" in warning.lower() for warning in result.warnings)
