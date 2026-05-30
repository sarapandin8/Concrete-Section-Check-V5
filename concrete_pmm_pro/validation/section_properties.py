"""Section property validation cases.

Closed-form benchmark values are computed independently of the polygon summary
implementation.  Parametric girder checks protect accepted geometry signatures.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from concrete_pmm_pro.core.models import Point2D, SectionGeometry
from concrete_pmm_pro.geometry import default_registry
from concrete_pmm_pro.geometry.generators import circle, rectangle, rectangular_hollow
from concrete_pmm_pro.geometry.summary import GeometrySummary, summarize_geometry
from concrete_pmm_pro.geometry.validation import validate_section_geometry
from concrete_pmm_pro.validation.models import ValidationResult, boolean_validation_result, numeric_validation_result

CATEGORY = "Section Properties"


def _interior_plank_params() -> dict[str, float]:
    return {
        "B_mm": 990.0,
        "b1_mm": 45.0,
        "b2_mm": 70.0,
        "b3_mm": 850.0,
        "H_mm": 450.0,
        "h1_mm": 80.0,
        "h2_mm": 140.0,
        "Tslab_mm": 100.0,
        "Be_mm": 1000.0,
        "Ebeam_MPa": 35000.0,
        "Edeck_MPa": 28560.0,
        "girder_length_mm": 12000.0,
    }


def _exterior_plank_params() -> dict[str, float]:
    params = _interior_plank_params()
    params.update({"b3_mm": 920.0, "overhang_mm": 500.0})
    return params


def _default_i_girder_params() -> dict[str, float]:
    return {
        "B1_mm": 800.0,
        "B2_mm": 500.0,
        "D1_mm": 1400.0,
        "D2_mm": 200.0,
        "D3_mm": 150.0,
        "D5_mm": 250.0,
        "D6_mm": 150.0,
        "T1_mm": 200.0,
        "T2_mm": 200.0,
        "C1_mm": 0.0,
    }


def _finite_positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0.0


def _summary_common_sanity(case_prefix: str, geometry: SectionGeometry, summary: GeometrySummary) -> list[ValidationResult]:
    validation = validate_section_geometry(geometry)
    return [
        boolean_validation_result(
            case_id=f"{case_prefix}.GEOM_VALID",
            category=CATEGORY,
            title=f"{geometry.name} geometry is valid",
            passed=validation.is_valid and not validation.errors,
            expected="valid geometry",
            actual={"is_valid": validation.is_valid, "errors": validation.errors},
        ),
        boolean_validation_result(
            case_id=f"{case_prefix}.AREA_POSITIVE",
            category=CATEGORY,
            title=f"{geometry.name} area is positive",
            passed=_finite_positive(summary.area_mm2),
            expected="area > 0",
            actual=summary.area_mm2,
            units="mm^2",
        ),
        boolean_validation_result(
            case_id=f"{case_prefix}.IX_POSITIVE",
            category=CATEGORY,
            title=f"{geometry.name} Ix is positive",
            passed=_finite_positive(summary.ix_nmm4),
            expected="Ix > 0",
            actual=summary.ix_nmm4,
            units="mm^4",
        ),
        boolean_validation_result(
            case_id=f"{case_prefix}.IY_POSITIVE",
            category=CATEGORY,
            title=f"{geometry.name} Iy is positive",
            passed=_finite_positive(summary.iy_nmm4),
            expected="Iy > 0",
            actual=summary.iy_nmm4,
            units="mm^4",
        ),
    ]


def _centroid_inside_bounds(summary: GeometrySummary) -> bool:
    if summary.x_min_mm is None or summary.x_max_mm is None or summary.y_min_mm is None or summary.y_max_mm is None:
        return False
    return summary.x_min_mm <= summary.centroid_x_mm <= summary.x_max_mm and summary.y_min_mm <= summary.centroid_y_mm <= summary.y_max_mm


def validate_rectangle_properties() -> list[ValidationResult]:
    b = 400.0
    h = 600.0
    summary = summarize_geometry(rectangle(b, h))
    ix = b * h**3 / 12.0
    iy = h * b**3 / 12.0
    return [
        numeric_validation_result(case_id="SEC.RECT.AREA", category=CATEGORY, title="Rectangle area", expected=b * h, actual=summary.area_mm2, abs_tolerance=1.0e-6, units="mm^2"),
        numeric_validation_result(case_id="SEC.RECT.CX", category=CATEGORY, title="Rectangle centroid x", expected=0.0, actual=summary.centroid_x_mm, abs_tolerance=1.0e-9, units="mm"),
        numeric_validation_result(case_id="SEC.RECT.CY_FROM_BOTTOM", category=CATEGORY, title="Rectangle centroid from bottom", expected=h / 2.0, actual=summary.centroid_y_from_bottom_mm or float("nan"), abs_tolerance=1.0e-9, units="mm"),
        numeric_validation_result(case_id="SEC.RECT.IX", category=CATEGORY, title="Rectangle Ix", expected=ix, actual=summary.ix_nmm4 or float("nan"), abs_tolerance=1.0e-3, units="mm^4"),
        numeric_validation_result(case_id="SEC.RECT.IY", category=CATEGORY, title="Rectangle Iy", expected=iy, actual=summary.iy_nmm4 or float("nan"), abs_tolerance=1.0e-3, units="mm^4"),
        numeric_validation_result(case_id="SEC.RECT.CTOP", category=CATEGORY, title="Rectangle ctop", expected=h / 2.0, actual=summary.top_fiber_distance_mm or float("nan"), abs_tolerance=1.0e-9, units="mm"),
        numeric_validation_result(case_id="SEC.RECT.CBOTTOM", category=CATEGORY, title="Rectangle cbottom", expected=h / 2.0, actual=summary.bottom_fiber_distance_mm or float("nan"), abs_tolerance=1.0e-9, units="mm"),
        numeric_validation_result(case_id="SEC.RECT.ZTOP", category=CATEGORY, title="Rectangle Ztop", expected=ix / (h / 2.0), actual=summary.z_top_mm3 or float("nan"), abs_tolerance=1.0e-3, units="mm^3"),
        numeric_validation_result(case_id="SEC.RECT.ZBOTTOM", category=CATEGORY, title="Rectangle Zbottom", expected=ix / (h / 2.0), actual=summary.z_bottom_mm3 or float("nan"), abs_tolerance=1.0e-3, units="mm^3"),
    ]


def validate_circle_properties() -> list[ValidationResult]:
    diameter = 600.0
    summary = summarize_geometry(circle(diameter, segments=4096))
    area = math.pi * diameter**2 / 4.0
    inertia = math.pi * diameter**4 / 64.0
    return [
        numeric_validation_result(case_id="SEC.CIRCLE.AREA", category=CATEGORY, title="Circle area", expected=area, actual=summary.area_mm2, abs_tolerance=1.0, units="mm^2", engineering_note="Polygon circle uses dense segmentation; benchmark is closed form."),
        numeric_validation_result(case_id="SEC.CIRCLE.IX", category=CATEGORY, title="Circle Ix", expected=inertia, actual=summary.ix_nmm4 or float("nan"), rel_tolerance=1.0e-5, units="mm^4"),
        numeric_validation_result(case_id="SEC.CIRCLE.IY", category=CATEGORY, title="Circle Iy", expected=inertia, actual=summary.iy_nmm4 or float("nan"), rel_tolerance=1.0e-5, units="mm^4"),
        numeric_validation_result(case_id="SEC.CIRCLE.CTOP", category=CATEGORY, title="Circle ctop", expected=diameter / 2.0, actual=summary.top_fiber_distance_mm or float("nan"), abs_tolerance=1.0e-6, units="mm"),
        numeric_validation_result(case_id="SEC.CIRCLE.CBOTTOM", category=CATEGORY, title="Circle cbottom", expected=diameter / 2.0, actual=summary.bottom_fiber_distance_mm or float("nan"), abs_tolerance=1.0e-6, units="mm"),
    ]


def validate_hollow_rectangle_properties() -> list[ValidationResult]:
    width = 600.0
    height = 800.0
    wall = 100.0
    inner_width = width - 2.0 * wall
    inner_height = height - 2.0 * wall
    summary = summarize_geometry(rectangular_hollow(width, height, wall_thickness_mm=wall))
    area = width * height - inner_width * inner_height
    ix = width * height**3 / 12.0 - inner_width * inner_height**3 / 12.0
    iy = height * width**3 / 12.0 - inner_height * inner_width**3 / 12.0
    return [
        numeric_validation_result(case_id="SEC.HRECT.AREA", category=CATEGORY, title="Hollow rectangle area", expected=area, actual=summary.area_mm2, abs_tolerance=1.0e-6, units="mm^2"),
        numeric_validation_result(case_id="SEC.HRECT.IX", category=CATEGORY, title="Hollow rectangle Ix", expected=ix, actual=summary.ix_nmm4 or float("nan"), abs_tolerance=1.0e-3, units="mm^4"),
        numeric_validation_result(case_id="SEC.HRECT.IY", category=CATEGORY, title="Hollow rectangle Iy", expected=iy, actual=summary.iy_nmm4 or float("nan"), abs_tolerance=1.0e-3, units="mm^4"),
    ]


def validate_interior_plank_signature() -> list[ValidationResult]:
    geometry = default_registry.geometry("parametric_plank_girder_interior")(**_interior_plank_params())
    summary = summarize_geometry(geometry)
    return [
        *(_summary_common_sanity("SEC.PLANK.INT", geometry, summary)),
        numeric_validation_result(case_id="SEC.PLANK.INT.AREA", category=CATEGORY, title="Accepted interior plank area", expected=405650.0, actual=summary.area_mm2, abs_tolerance=1.0, units="mm^2"),
        numeric_validation_result(case_id="SEC.PLANK.INT.CY_BOTTOM", category=CATEGORY, title="Accepted interior plank centroid from bottom", expected=220.92, actual=summary.centroid_y_from_bottom_mm or float("nan"), abs_tolerance=0.05, units="mm"),
        numeric_validation_result(case_id="SEC.PLANK.INT.CTOP", category=CATEGORY, title="Accepted interior plank ctop", expected=229.08, actual=summary.top_fiber_distance_mm or float("nan"), abs_tolerance=0.05, units="mm"),
        numeric_validation_result(case_id="SEC.PLANK.INT.CBOTTOM", category=CATEGORY, title="Accepted interior plank cbottom", expected=220.92, actual=summary.bottom_fiber_distance_mm or float("nan"), abs_tolerance=0.05, units="mm"),
        numeric_validation_result(case_id="SEC.PLANK.INT.IX", category=CATEGORY, title="Accepted interior plank Ix", expected=7.060e9, actual=summary.ix_nmm4 or float("nan"), rel_tolerance=1.0e-3, units="mm^4"),
        numeric_validation_result(case_id="SEC.PLANK.INT.IY", category=CATEGORY, title="Accepted interior plank Iy", expected=27.705e9, actual=summary.iy_nmm4 or float("nan"), rel_tolerance=1.0e-3, units="mm^4"),
    ]


def _points_at_x(points: Iterable[Point2D], x_value: float, tolerance: float = 1.0e-6) -> list[Point2D]:
    return [point for point in points if abs(point.x - x_value) <= tolerance]


def validate_exterior_plank_signature() -> list[ValidationResult]:
    params = _exterior_plank_params()
    geometry = default_registry.geometry("parametric_plank_girder_exterior")(**params)
    summary = summarize_geometry(geometry)
    x_right = params["B_mm"] / 2.0
    right_points = _points_at_x(geometry.outer_polygon, x_right)
    right_y_values = {round(point.y, 6) for point in right_points}
    bottom_y = -params["H_mm"] / 2.0
    top_y = params["H_mm"] / 2.0
    return [
        *_summary_common_sanity("SEC.PLANK.EXT", geometry, summary),
        boolean_validation_result(
            case_id="SEC.PLANK.EXT.CENTROID_INSIDE",
            category=CATEGORY,
            title="Exterior plank centroid lies inside bounds",
            passed=_centroid_inside_bounds(summary),
            expected="centroid inside generated polygon bounds",
            actual={"x": summary.centroid_x_mm, "y": summary.centroid_y_mm, "bounds": (summary.x_min_mm, summary.y_min_mm, summary.x_max_mm, summary.y_max_mm)},
        ),
        boolean_validation_result(
            case_id="SEC.PLANK.EXT.RIGHT_VERTICAL",
            category=CATEGORY,
            title="Exterior plank right side remains full-height vertical",
            passed=round(bottom_y, 6) in right_y_values and round(top_y, 6) in right_y_values,
            expected={"x": x_right, "y": [bottom_y, top_y]},
            actual={"x": x_right, "y_values_at_right": sorted(right_y_values)},
            engineering_note="Protects accepted exterior plank rule: right side is vertical full height.",
        ),
    ]


def validate_i_girder_signature() -> list[ValidationResult]:
    geometry = default_registry.geometry("parametric_i_girder")(**_default_i_girder_params())
    summary = summarize_geometry(geometry)
    return [
        *_summary_common_sanity("SEC.IGIRDER", geometry, summary),
        boolean_validation_result(
            case_id="SEC.IGIRDER.CENTROID_DEPTH",
            category=CATEGORY,
            title="I-Girder centroid lies within section depth",
            passed=_centroid_inside_bounds(summary),
            expected="centroid inside generated section bounds",
            actual={"x": summary.centroid_x_mm, "y": summary.centroid_y_mm, "bounds": (summary.x_min_mm, summary.y_min_mm, summary.x_max_mm, summary.y_max_mm)},
        ),
        boolean_validation_result(
            case_id="SEC.IGIRDER.FIBER_DISTANCES",
            category=CATEGORY,
            title="I-Girder top and bottom fiber distances are positive",
            passed=_finite_positive(summary.top_fiber_distance_mm) and _finite_positive(summary.bottom_fiber_distance_mm),
            expected="ctop > 0 and cbottom > 0",
            actual={"ctop": summary.top_fiber_distance_mm, "cbottom": summary.bottom_fiber_distance_mm},
            units="mm",
        ),
    ]


def validate_section_properties() -> list[ValidationResult]:
    return [
        *validate_rectangle_properties(),
        *validate_circle_properties(),
        *validate_hollow_rectangle_properties(),
        *validate_interior_plank_signature(),
        *validate_exterior_plank_signature(),
        *validate_i_girder_signature(),
    ]
