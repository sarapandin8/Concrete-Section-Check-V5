from __future__ import annotations

import pytest

from concrete_pmm_pro.serviceability import (
    ServiceStressPointResult,
    ServiceabilitySettings,
    ServiceabilitySummary,
    classify_service_stress_results_for_cracking,
    crack_classification_to_dataframe,
)
from concrete_pmm_pro.verification.sls_benchmarks import run_sls_verification_suite


def _summary(
    stresses: list[tuple[str, str, float, float | None]],
    settings: ServiceabilitySettings | None = None,
) -> ServiceabilitySummary:
    active_settings = settings or ServiceabilitySettings(enabled=True, concrete_tension_limit_MPa=5.0)
    return ServiceabilitySummary(
        enabled=True,
        settings=active_settings,
        section_properties=None,
        stress_results=[
            ServiceStressPointResult(
                combo_name=combo,
                point_name=point,
                x_mm=0.0,
                y_mm=0.0,
                section_basis="gross",
                total_stress_MPa=stress,
                stress_MPa=stress,
                limit_MPa=limit,
                status="PASS",
                message="",
            )
            for combo, point, stress, limit in stresses
        ],
    )


def _first_classification(stress: float, settings: ServiceabilitySettings | None = None, limit: float | None = 5.0):
    summary = _summary([("SLS-1", "Top fiber", stress, limit)], settings)
    return classify_service_stress_results_for_cracking(summary, summary.settings).points[0]


def test_classify_compression_stress_as_compression() -> None:
    point = _first_classification(-2.0)

    assert point.classification == "COMPRESSION"
    assert point.is_tension is False


def test_classify_near_zero_stress_as_zero() -> None:
    point = _first_classification(1.0e-8, ServiceabilitySettings(stress_zero_tolerance_MPa=1.0e-6))

    assert point.classification == "ZERO"


def test_classify_positive_stress_within_limit() -> None:
    point = _first_classification(2.0, limit=5.0)

    assert point.classification == "TENSION_WITHIN_LIMIT"
    assert point.is_tension is True
    assert point.exceeds_tension_limit is False


def test_classify_positive_stress_exceeds_tension_limit() -> None:
    point = _first_classification(6.0, limit=5.0)

    assert point.classification == "TENSION_EXCEEDS_LIMIT"
    assert point.exceeds_tension_limit is True


def test_no_tension_check_classifies_tension_as_violation() -> None:
    point = _first_classification(0.5, ServiceabilitySettings(no_tension_check=True), limit=0.0)

    assert point.classification == "NO_TENSION_VIOLATION"
    assert point.no_tension_violation is True


def test_decompression_check_classifies_tension_as_violation() -> None:
    point = _first_classification(0.5, ServiceabilitySettings(decompression_check=True), limit=0.0)

    assert point.classification == "DECOMPRESSION_VIOLATION"
    assert point.decompression_violation is True


def test_overall_priority_gives_decompression_over_tension_present() -> None:
    settings = ServiceabilitySettings(decompression_check=True)
    summary = _summary(
        [
            ("SLS-1", "Top fiber", 0.5, 0.0),
            ("SLS-1", "Bottom fiber", -2.0, 18.0),
        ],
        settings,
    )

    classification = classify_service_stress_results_for_cracking(summary, settings)

    assert classification.overall_classification == "DECOMPRESSION_VIOLATED"


def test_overall_priority_gives_no_tension_over_tension_present() -> None:
    settings = ServiceabilitySettings(no_tension_check=True)
    summary = _summary([("SLS-1", "Top fiber", 0.5, 0.0)], settings)

    classification = classify_service_stress_results_for_cracking(summary, settings)

    assert classification.overall_classification == "NO_TENSION_VIOLATED"


def test_pure_compression_summary_returns_uncracked_by_check_points() -> None:
    summary = _summary(
        [
            ("SLS-1", "Top fiber", -2.0, 18.0),
            ("SLS-1", "Bottom fiber", -1.0, 18.0),
        ]
    )

    classification = classify_service_stress_results_for_cracking(summary, summary.settings)

    assert classification.overall_classification == "UNCRACKED_BY_CHECK_POINTS"
    assert classification.tension_point_count == 0


def test_max_tension_is_reported_correctly() -> None:
    summary = _summary(
        [
            ("SLS-1", "Top fiber", 2.0, 5.0),
            ("SLS-2", "Top fiber", 4.0, 5.0),
        ]
    )

    classification = classify_service_stress_results_for_cracking(summary, summary.settings)

    assert classification.max_tension_MPa == pytest.approx(4.0)
    assert classification.tension_point_count == 2


def test_governing_combo_and_point_selected_from_most_severe_violation() -> None:
    summary = _summary(
        [
            ("SLS-LOW", "Top fiber", 2.0, 5.0),
            ("SLS-HIGH", "Bottom fiber", 8.0, 5.0),
        ]
    )

    classification = classify_service_stress_results_for_cracking(summary, summary.settings)

    assert classification.governing_combo == "SLS-HIGH"
    assert classification.governing_point == "Bottom fiber"


def test_critical_point_filter_extreme_fibers_only_excludes_centroid() -> None:
    settings = ServiceabilitySettings(critical_point_filter="extreme_fibers_only", concrete_tension_limit_MPa=5.0)
    summary = _summary(
        [
            ("SLS-1", "Centroid", 10.0, 5.0),
            ("SLS-1", "Top fiber", -2.0, 18.0),
        ],
        settings,
    )

    classification = classify_service_stress_results_for_cracking(summary, settings)

    assert {point.point_name for point in classification.points} == {"Centroid", "Top fiber"}
    assert classification.overall_classification == "UNCRACKED_BY_CHECK_POINTS"
    assert classification.governing_point is None


def test_crack_classification_to_dataframe_contains_required_columns() -> None:
    summary = _summary([("SLS-1", "Top fiber", 2.0, 5.0)])
    classification = classify_service_stress_results_for_cracking(summary, summary.settings)
    df = crack_classification_to_dataframe(classification)

    assert {
        "Combo",
        "Point",
        "x_mm",
        "y_mm",
        "Stress_MPa",
        "Section Basis",
        "Is Tension",
        "Exceeds Tension Limit",
        "No-Tension Violation",
        "Decompression Violation",
        "Classification",
        "Message",
    }.issubset(df.columns)


def test_crack_classification_csv_export_dataframe_can_be_generated() -> None:
    summary = _summary([("SLS-1", "Top fiber", 2.0, 5.0)])
    classification = classify_service_stress_results_for_cracking(summary, summary.settings)
    csv_text = crack_classification_to_dataframe(classification).to_csv(index=False)

    assert "Classification" in csv_text


def test_sls_verification_suite_includes_crack_classification_checks() -> None:
    summary = run_sls_verification_suite()

    assert any("Crack classification" in check.name for check in summary.checks)


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
