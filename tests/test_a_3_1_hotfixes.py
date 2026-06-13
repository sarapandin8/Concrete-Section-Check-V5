from __future__ import annotations

import pandas as pd
from shapely.geometry import Polygon

from concrete_pmm_pro.analysis.slice_envelope import build_convex_hull_envelope, detect_self_crossing_boundary
from concrete_pmm_pro.analysis.strain_compatibility import is_point_inside_compression_block
from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.reporting import (
    build_result_traceability_snapshot,
    collect_engineering_warnings,
    collect_limitations_for_report,
    deduplicate_limitations_by_key,
    engineering_limitations_to_dataframe,
    get_engineering_limitations,
)
from concrete_pmm_pro.reporting.limitations import _is_truthy_context_value
from concrete_pmm_pro.serviceability import (
    ServiceabilitySettings,
    StressCheckPoint,
    compute_gross_section_properties,
    estimate_concrete_ec_warnings,
    validate_stress_check_points_against_geometry,
)
from concrete_pmm_pro.serviceability.transformed import compute_uncracked_transformed_section_properties


class BoolRaisesTypeError:
    def __bool__(self) -> bool:
        raise TypeError("cannot evaluate truthiness")


class BoolRaisesValueError:
    def __bool__(self) -> bool:
        raise ValueError("cannot evaluate truthiness")


def _gross_rectangle():
    return compute_gross_section_properties(rectangle(width_mm=400.0, height_mm=600.0))


def test_significant_ixy_appends_warning() -> None:
    props = compute_uncracked_transformed_section_properties(
        _gross_rectangle(),
        ConcreteMaterial(name="LW", fc_MPa=40.0),
        [Rebar(x_mm=150.0, y_mm=200.0, diameter_mm=32.0, material_name="SD40", label="B1")],
        [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        [],
        [],
        ServiceabilitySettings(use_transformed_section=True),
    )

    assert any("Ixy is nonzero" in warning for warning in props.warnings)


def test_near_zero_ixy_does_not_append_warning() -> None:
    props = compute_uncracked_transformed_section_properties(
        _gross_rectangle(),
        ConcreteMaterial(name="C40", fc_MPa=40.0),
        [],
        [],
        [],
        [],
        ServiceabilitySettings(use_transformed_section=True),
    )

    assert not any("Ixy is nonzero" in warning for warning in props.warnings)


def test_get_engineering_limitations_contains_required_keys() -> None:
    keys = {item.key for item in get_engineering_limitations()}

    assert {
        "ixy_coupling_sls",
        "dc_directional_slice_envelope",
        "convex_hull_slice_envelope",
        "cracked_section_sls",
        "prestress_axial_cap",
        "unbonded_prestress",
    }.issubset(keys)


def test_engineering_limitations_to_dataframe_contains_required_columns() -> None:
    df = engineering_limitations_to_dataframe(get_engineering_limitations())

    assert {
        "Key",
        "Title",
        "Status",
        "Risk Level",
        "Category",
        "User Note",
        "Engineering Note",
        "Recommended Action",
    }.issubset(df.columns)


def test_limitations_include_expected_risk_levels_and_notes() -> None:
    by_key = {item.key: item for item in get_engineering_limitations()}

    assert by_key["convex_hull_slice_envelope"].risk_level == "CRITICAL"
    assert by_key["dc_directional_slice_envelope"].risk_level == "HIGH"
    assert by_key["ixy_coupling_sls"].risk_level == "HIGH"
    assert "lightweight" in by_key["lightweight_concrete_ec"].engineering_note.lower()
    assert "ecu" in by_key["ultimate_concrete_strain_ecu"].title.lower()


def test_collect_limitations_for_report_returns_registry() -> None:
    limitations = collect_limitations_for_report({})

    assert len(limitations) >= 10


def test_collect_limitations_include_all_false_includes_critical() -> None:
    keys = {item.key for item in collect_limitations_for_report({}, include_all=False)}

    assert "convex_hull_slice_envelope" in keys


def test_collect_limitations_include_all_false_includes_high_risk_items() -> None:
    keys = {item.key for item in collect_limitations_for_report({}, include_all=False)}

    assert {"ixy_coupling_sls", "dc_directional_slice_envelope", "prestress_axial_cap"}.issubset(keys)


def test_collect_limitations_include_all_false_keeps_all_high_and_critical() -> None:
    all_limitations = get_engineering_limitations()
    filtered_keys = {item.key for item in collect_limitations_for_report({}, include_all=False)}

    for item in all_limitations:
        if item.risk_level in {"HIGH", "CRITICAL"}:
            assert item.key in filtered_keys


def test_collect_limitations_include_all_false_has_no_duplicate_keys() -> None:
    keys = [item.key for item in collect_limitations_for_report({}, include_all=False)]

    assert len(keys) == len(set(keys))


def test_collect_limitations_include_all_true_still_returns_all_limitations() -> None:
    assert collect_limitations_for_report({}, include_all=True) == get_engineering_limitations()


def test_collect_limitations_include_all_false_adds_beam_girder_limitation() -> None:
    settings = AnalysisModeSettings(member_type="beam_girder")
    limitations = collect_limitations_for_report({"analysis_mode_settings": settings}, include_all=False)
    keys = [item.key for item in limitations]

    assert "beam_girder_shear_torsion" in keys
    assert len(keys) == len(set(keys))
    for item in get_engineering_limitations():
        if item.risk_level in {"HIGH", "CRITICAL"}:
            assert item.key in keys


def test_collect_limitations_include_all_false_adds_column_pier_vt_scope_limitation() -> None:
    settings = AnalysisModeSettings(member_type="column_pier_pmm")
    limitations = collect_limitations_for_report({"analysis_mode_settings": settings}, include_all=False)
    keys = [item.key for item in limitations]

    assert "column_pier_vt_scope" in keys
    assert len(keys) == len(set(keys))
    by_key = {item.key: item for item in limitations}
    assert "ACI RC nonprestressed" in by_key["column_pier_vt_scope"].user_note
    assert "AASHTO LRFD" in by_key["column_pier_vt_scope"].engineering_note


def test_collect_limitations_include_all_false_excludes_neutral_axis_without_pmm_context() -> None:
    keys = {item.key for item in collect_limitations_for_report({}, include_all=False)}

    assert "neutral_axis_sweep_resolution" not in keys


def test_collect_limitations_include_all_false_includes_neutral_axis_with_pmm_context() -> None:
    keys = {item.key for item in collect_limitations_for_report({"pmm_result": object()}, include_all=False)}

    assert "neutral_axis_sweep_resolution" in keys


def test_pmm_context_detected_via_dc_summary() -> None:
    keys = {item.key for item in collect_limitations_for_report({"dc_summary": object()}, include_all=False)}

    assert "neutral_axis_sweep_resolution" in keys


def test_pmm_context_detected_via_demand_capacity_summary() -> None:
    keys = {
        item.key
        for item in collect_limitations_for_report({"demand_capacity_summary": object()}, include_all=False)
    }

    assert "neutral_axis_sweep_resolution" in keys


def test_pmm_context_detected_via_rc_demand_capacity_result() -> None:
    keys = {
        item.key
        for item in collect_limitations_for_report({"rc_demand_capacity_result": object()}, include_all=False)
    }

    assert "neutral_axis_sweep_resolution" in keys


def test_collect_limitations_include_all_false_includes_prestress_reversal_with_prestress() -> None:
    keys = {item.key for item in collect_limitations_for_report({"prestress_elements": [object()]}, include_all=False)}

    assert "prestress_compression_reversal" in keys


def test_collect_limitations_include_all_false_includes_crack_width_with_sls_context() -> None:
    keys = {
        item.key
        for item in collect_limitations_for_report({"serviceability_summary": object()}, include_all=False)
    }

    assert "crack_width_check" in keys


def test_sls_context_detected_via_crack_classification_summary() -> None:
    keys = {
        item.key
        for item in collect_limitations_for_report({"crack_classification_summary": object()}, include_all=False)
    }

    assert "crack_width_check" in keys


def test_is_truthy_context_value_returns_false_when_bool_raises_type_error() -> None:
    assert _is_truthy_context_value(BoolRaisesTypeError()) is False


def test_is_truthy_context_value_returns_false_when_bool_raises_value_error() -> None:
    assert _is_truthy_context_value(BoolRaisesValueError()) is False


def test_deduplicate_limitations_by_key_preserves_first_occurrence() -> None:
    first, second = get_engineering_limitations()[:2]
    deduped = deduplicate_limitations_by_key([first, second, first])

    assert deduped == [first, second]


def test_collect_engineering_warnings_can_combine_with_limitations_without_duplicates() -> None:
    limitation_warnings = [item.user_note for item in get_engineering_limitations()[:2]]
    warnings = collect_engineering_warnings(additional_warnings=[*limitation_warnings, *limitation_warnings])

    assert warnings.count(limitation_warnings[0]) == 1


def test_pre_report_traceability_includes_limitation_count() -> None:
    snapshot = build_result_traceability_snapshot({})

    assert snapshot.limitation_count >= 10
    assert snapshot.high_or_critical_limitation_count >= 1


def test_lightweight_concrete_density_warning_helper_warns_for_low_density() -> None:
    warnings = estimate_concrete_ec_warnings(40.0, density_kg_m3=1850.0, method="aci_normal_weight")

    assert any("below normal-weight" in warning for warning in warnings)


def test_normal_weight_density_has_no_lightweight_warning() -> None:
    warnings = estimate_concrete_ec_warnings(40.0, density_kg_m3=2400.0, method="aci_normal_weight")

    assert not warnings


def test_reporting_limitations_module_imports_without_error() -> None:
    import concrete_pmm_pro.reporting.limitations as limitations

    assert hasattr(limitations, "get_engineering_limitations")


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")


def test_invalid_compression_polygon_does_not_crash_membership_check() -> None:
    invalid_polygon = Polygon([(0.0, 0.0), (2.0, 2.0), (0.0, 2.0), (2.0, 0.0)])

    assert is_point_inside_compression_block(1.0, 1.0, invalid_polygon) is False


def test_invalid_slice_envelope_geometry_does_not_crash_self_crossing_detection() -> None:
    bad_df = pd.DataFrame([{"phiMnx_kNm": "bad", "phiMny_kNm": 0.0}])

    assert detect_self_crossing_boundary(bad_df) is False


def test_convex_hull_fallback_handles_bad_input_without_crashing() -> None:
    bad_df = pd.DataFrame([{"phiMnx_kNm": "bad", "phiMny_kNm": 0.0}])

    result = build_convex_hull_envelope(bad_df)

    assert result.used_convex_hull is True
    assert result.is_valid is False
    assert result.warnings


def test_stress_check_point_validation_handles_missing_geometry() -> None:
    errors, warnings = validate_stress_check_points_against_geometry(
        [StressCheckPoint(name="P1", x_mm=0.0, y_mm=0.0)],
        None,
    )

    assert not errors
    assert warnings


def test_stress_check_point_validation_handles_invalid_geometry_without_crashing() -> None:
    invalid_geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=2.0, y=2.0),
            Point2D(x=0.0, y=2.0),
            Point2D(x=2.0, y=0.0),
        ],
    )

    errors, _warnings = validate_stress_check_points_against_geometry(
        [StressCheckPoint(name="P1", x_mm=1.0, y_mm=1.0)],
        invalid_geometry,
    )

    assert errors
