"""Built-in metadata-addressable section geometry generators."""

from __future__ import annotations

import math

from shapely.geometry import Polygon
from shapely.validation import explain_validity

from concrete_pmm_pro.core.models import DimensionItem, Point2D, SectionGeometry
from concrete_pmm_pro.geometry.registry import GeometryRegistry


def _point(x: float, y: float) -> Point2D:
    return Point2D(x=float(x), y=float(y))


def _rectangle_points(width_mm: float, height_mm: float) -> list[Point2D]:
    w = width_mm / 2.0
    h = height_mm / 2.0
    return [_point(-w, -h), _point(w, -h), _point(w, h), _point(-w, h)]


def _rectangle_from_bounds(left: float, bottom: float, right: float, top: float) -> list[Point2D]:
    return [_point(left, bottom), _point(right, bottom), _point(right, top), _point(left, top)]


def _circle_points(radius_mm: float, segments: int = 96) -> list[Point2D]:
    return [
        _point(radius_mm * math.cos(2.0 * math.pi * i / segments), radius_mm * math.sin(2.0 * math.pi * i / segments))
        for i in range(segments)
    ]


def _rounded_rectangle_from_bounds(
    left: float,
    bottom: float,
    right: float,
    top: float,
    radius_mm: float,
    segments_per_corner: int = 12,
) -> list[Point2D]:
    width = right - left
    height = top - bottom
    radius = float(radius_mm)
    if radius <= 0:
        return _rectangle_from_bounds(left, bottom, right, top)
    if radius * 2.0 > min(width, height):
        raise ValueError("Invalid geometry: fillet radius is too large for the selected rectangle dimensions.")

    n = max(1, int(segments_per_corner))
    corners = [
        ((right - radius, bottom + radius), -math.pi / 2, 0.0),
        ((right - radius, top - radius), 0.0, math.pi / 2),
        ((left + radius, top - radius), math.pi / 2, math.pi),
        ((left + radius, bottom + radius), math.pi, 3 * math.pi / 2),
    ]
    points: list[Point2D] = []
    for (cx, cy), start_angle, end_angle in corners:
        for index in range(n + 1):
            if points and index == 0:
                continue
            angle = start_angle + (end_angle - start_angle) * index / n
            points.append(_point(cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


def _rounded_rectangle_points(width_mm: float, height_mm: float, radius_mm: float, segments_per_corner: int = 12) -> list[Point2D]:
    return _rounded_rectangle_from_bounds(
        -width_mm / 2.0,
        -height_mm / 2.0,
        width_mm / 2.0,
        height_mm / 2.0,
        radius_mm,
        segments_per_corner,
    )


def _require_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"Invalid geometry: {name} must be greater than zero.")


def _require_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"Invalid geometry: {name} must be zero or greater.")


def _resolve_wall_thicknesses(
    *,
    t_top_mm: float | None = None,
    t_bottom_mm: float | None = None,
    t_left_mm: float | None = None,
    t_right_mm: float | None = None,
    wall_thickness_mm: float | None = None,
) -> tuple[float, float, float, float]:
    if wall_thickness_mm is not None:
        t_top_mm = wall_thickness_mm if t_top_mm is None else t_top_mm
        t_bottom_mm = wall_thickness_mm if t_bottom_mm is None else t_bottom_mm
        t_left_mm = wall_thickness_mm if t_left_mm is None else t_left_mm
        t_right_mm = wall_thickness_mm if t_right_mm is None else t_right_mm

    missing = [
        name
        for name, value in {
            "t_top_mm": t_top_mm,
            "t_bottom_mm": t_bottom_mm,
            "t_left_mm": t_left_mm,
            "t_right_mm": t_right_mm,
        }.items()
        if value is None
    ]
    if missing:
        raise ValueError(f"Invalid geometry: missing wall thickness parameter(s): {', '.join(missing)}.")

    values = (float(t_top_mm), float(t_bottom_mm), float(t_left_mm), float(t_right_mm))
    for name, value in zip(("t_top_mm", "t_bottom_mm", "t_left_mm", "t_right_mm"), values):
        _require_positive(name, value)
    return values


def _inner_rect_bounds(
    *,
    width_mm: float,
    height_mm: float,
    t_top_mm: float,
    t_bottom_mm: float,
    t_left_mm: float,
    t_right_mm: float,
) -> tuple[float, float, float, float]:
    _require_positive("width_mm", width_mm)
    _require_positive("height_mm", height_mm)
    inner_width = width_mm - t_left_mm - t_right_mm
    inner_height = height_mm - t_top_mm - t_bottom_mm
    if inner_width <= 0:
        raise ValueError("Invalid geometry: t_left + t_right must be less than B.")
    if inner_height <= 0:
        raise ValueError("Invalid geometry: t_top + t_bottom must be less than H.")
    return (
        -width_mm / 2.0 + t_left_mm,
        -height_mm / 2.0 + t_bottom_mm,
        width_mm / 2.0 - t_right_mm,
        height_mm / 2.0 - t_top_mm,
    )


def _ensure_valid_simple_polygon(points: list[Point2D], name: str) -> None:
    polygon = Polygon([point.as_tuple() for point in points])
    if not polygon.is_valid:
        raise ValueError(f"Invalid geometry: {name} polygon is self-intersecting ({explain_validity(polygon)}).")
    if polygon.area <= 0:
        raise ValueError(f"Invalid geometry: {name} polygon area must be positive.")


def rectangle(width_mm: float, height_mm: float, name: str = "Rectangle") -> SectionGeometry:
    _require_positive("B", width_mm)
    _require_positive("H", height_mm)
    return SectionGeometry(name=name, outer_polygon=_rectangle_points(width_mm, height_mm), holes=[], metadata={"preset": "rectangle"})


def rectangular_chamfered(width_mm: float, height_mm: float, chamfer_mm: float, name: str = "Rectangular chamfered") -> SectionGeometry:
    _require_positive("B", width_mm)
    _require_positive("H", height_mm)
    _require_non_negative("chamfer_mm", chamfer_mm)
    w = width_mm / 2.0
    h = height_mm / 2.0
    c = min(chamfer_mm, width_mm / 2.0, height_mm / 2.0)
    points = [
        _point(-w + c, -h),
        _point(w - c, -h),
        _point(w, -h + c),
        _point(w, h - c),
        _point(w - c, h),
        _point(-w + c, h),
        _point(-w, h - c),
        _point(-w, -h + c),
    ]
    return SectionGeometry(name=name, outer_polygon=points, holes=[], metadata={"preset": "rectangular_chamfered"})


def circle(diameter_mm: float, segments: int = 128, name: str = "Circle") -> SectionGeometry:
    _require_positive("D", diameter_mm)
    return SectionGeometry(name=name, outer_polygon=_circle_points(diameter_mm / 2.0, segments), holes=[], metadata={"preset": "circle"})


def circular_hollow(outer_diameter_mm: float, inner_diameter_mm: float, segments: int = 128, name: str = "Circular hollow") -> SectionGeometry:
    _require_positive("D_outer", outer_diameter_mm)
    _require_positive("D_inner", inner_diameter_mm)
    if inner_diameter_mm >= outer_diameter_mm:
        raise ValueError("Invalid geometry: D_inner must be smaller than D_outer.")
    return SectionGeometry(
        name=name,
        outer_polygon=_circle_points(outer_diameter_mm / 2.0, segments),
        holes=[list(reversed(_circle_points(inner_diameter_mm / 2.0, segments)))],
        metadata={"preset": "circular_hollow"},
    )


def rectangular_hollow(
    width_mm: float,
    height_mm: float,
    t_top_mm: float | None = None,
    t_bottom_mm: float | None = None,
    t_left_mm: float | None = None,
    t_right_mm: float | None = None,
    wall_thickness_mm: float | None = None,
    name: str = "Rectangular hollow",
) -> SectionGeometry:
    top, bottom, left, right = _resolve_wall_thicknesses(
        t_top_mm=t_top_mm,
        t_bottom_mm=t_bottom_mm,
        t_left_mm=t_left_mm,
        t_right_mm=t_right_mm,
        wall_thickness_mm=wall_thickness_mm,
    )
    inner_bounds = _inner_rect_bounds(
        width_mm=width_mm,
        height_mm=height_mm,
        t_top_mm=top,
        t_bottom_mm=bottom,
        t_left_mm=left,
        t_right_mm=right,
    )
    return SectionGeometry(
        name=name,
        outer_polygon=_rectangle_points(width_mm, height_mm),
        holes=[list(reversed(_rectangle_from_bounds(*inner_bounds)))],
        metadata={"preset": "rectangular_hollow", "wall_thicknesses_mm": {"top": top, "bottom": bottom, "left": left, "right": right}},
    )


def box_section_fillet(
    width_mm: float,
    height_mm: float,
    t_top_mm: float | None = None,
    t_bottom_mm: float | None = None,
    t_left_mm: float | None = None,
    t_right_mm: float | None = None,
    r_inner_mm: float | None = None,
    r_outer_mm: float = 0.0,
    n_fillet: int = 12,
    wall_thickness_mm: float | None = None,
    fillet_radius_mm: float | None = None,
    name: str = "Box section with fillet",
) -> SectionGeometry:
    top, bottom, left, right = _resolve_wall_thicknesses(
        t_top_mm=t_top_mm,
        t_bottom_mm=t_bottom_mm,
        t_left_mm=t_left_mm,
        t_right_mm=t_right_mm,
        wall_thickness_mm=wall_thickness_mm,
    )
    inner_radius = float(fillet_radius_mm if r_inner_mm is None and fillet_radius_mm is not None else r_inner_mm or 0.0)
    outer_radius = float(r_outer_mm)
    _require_non_negative("r_inner_mm", inner_radius)
    _require_non_negative("r_outer_mm", outer_radius)
    if n_fillet < 4:
        raise ValueError("Invalid geometry: n_fillet must be at least 4.")
    inner_bounds = _inner_rect_bounds(
        width_mm=width_mm,
        height_mm=height_mm,
        t_top_mm=top,
        t_bottom_mm=bottom,
        t_left_mm=left,
        t_right_mm=right,
    )
    inner_width = inner_bounds[2] - inner_bounds[0]
    inner_height = inner_bounds[3] - inner_bounds[1]
    if outer_radius * 2.0 > min(width_mm, height_mm):
        raise ValueError("Invalid geometry: outer fillet radius is too large for the section dimensions.")
    if inner_radius * 2.0 > min(inner_width, inner_height):
        raise ValueError("Invalid geometry: fillet radius is too large for inner void.")

    return SectionGeometry(
        name=name,
        outer_polygon=_rounded_rectangle_points(width_mm, height_mm, outer_radius, n_fillet),
        holes=[list(reversed(_rounded_rectangle_from_bounds(*inner_bounds, inner_radius, n_fillet)))],
        metadata={
            "preset": "box_section_fillet",
            "wall_thicknesses_mm": {"top": top, "bottom": bottom, "left": left, "right": right},
            "r_inner_mm": inner_radius,
            "r_outer_mm": outer_radius,
            "n_fillet": n_fillet,
        },
    )


def psc_i_girder(
    depth_mm: float,
    top_flange_width_mm: float,
    top_flange_thickness_mm: float,
    web_width_mm: float,
    bottom_flange_width_mm: float,
    bottom_flange_thickness_mm: float,
    name: str = "PSC I-girder",
) -> SectionGeometry:
    _require_positive("total depth", depth_mm)
    _require_positive("top flange width", top_flange_width_mm)
    _require_positive("bottom flange width", bottom_flange_width_mm)
    _require_positive("web thickness", web_width_mm)
    _require_positive("top flange thickness", top_flange_thickness_mm)
    _require_positive("bottom flange thickness", bottom_flange_thickness_mm)
    if top_flange_thickness_mm + bottom_flange_thickness_mm >= depth_mm:
        raise ValueError("Invalid geometry: top flange thickness + bottom flange thickness must be less than total depth.")
    if web_width_mm > top_flange_width_mm or web_width_mm > bottom_flange_width_mm:
        raise ValueError("Invalid geometry: web thickness must not exceed top or bottom flange width.")
    d = depth_mm / 2.0
    tw = top_flange_width_mm / 2.0
    bw = bottom_flange_width_mm / 2.0
    ww = web_width_mm / 2.0
    y_top_web = d - top_flange_thickness_mm
    y_bot_web = -d + bottom_flange_thickness_mm
    points = [
        _point(-bw, -d),
        _point(bw, -d),
        _point(bw, y_bot_web),
        _point(ww, y_bot_web),
        _point(ww, y_top_web),
        _point(tw, y_top_web),
        _point(tw, d),
        _point(-tw, d),
        _point(-tw, y_top_web),
        _point(-ww, y_top_web),
        _point(-ww, y_bot_web),
        _point(-bw, y_bot_web),
    ]
    _ensure_valid_simple_polygon(points, "PSC I-girder")
    return SectionGeometry(name=name, outer_polygon=points, holes=[], metadata={"preset": "psc_i_girder"})


def parametric_i_girder(
    B1_mm: float,
    B2_mm: float,
    D1_mm: float,
    D2_mm: float,
    D3_mm: float,
    D5_mm: float,
    D6_mm: float,
    T1_mm: float,
    T2_mm: float,
    C1_mm: float = 0.0,
    name: str = "Parametric I-Girder",
) -> SectionGeometry:
    """Generate a symmetric parametric bridge I-girder section.

    Parameter naming intentionally follows the user's bridge-girder drafting
    convention rather than generic geometry names:
      B1 = top flange width, B2 = bottom flange width, D1 = total depth,
      D2 = top flange thickness, D3 = top haunch depth,
      D5 = bottom flange thickness, D6 = bottom haunch depth,
      T1 = upper web width, T2 = lower/main web width, C1 = corner chamfer.

    The first implementation is a left-right symmetric solid concrete polygon.
    It is intended as an analysis-ready section definition for PMM / future
    prestressed-girder checks, not merely a preview sketch.
    """
    for label, value in {
        "B1": B1_mm,
        "B2": B2_mm,
        "D1": D1_mm,
        "T1": T1_mm,
        "T2": T2_mm,
    }.items():
        _require_positive(label, value)
    for label, value in {"D2": D2_mm, "D3": D3_mm, "D5": D5_mm, "D6": D6_mm, "C1": C1_mm}.items():
        _require_non_negative(label, value)

    if T1_mm > B1_mm:
        raise ValueError("Invalid geometry: T1 must not exceed B1.")
    if T2_mm > B2_mm:
        raise ValueError("Invalid geometry: T2 must not exceed B2.")
    if T1_mm > B2_mm:
        raise ValueError("Invalid geometry: T1 must not exceed B2 so the web can connect through the section depth.")
    if T2_mm > B1_mm:
        raise ValueError("Invalid geometry: T2 must not exceed B1 so the web can connect through the section depth.")

    web_zone_mm = D1_mm - D2_mm - D3_mm - D5_mm - D6_mm
    if web_zone_mm <= 0:
        raise ValueError("Invalid geometry: D1 must be greater than D2 + D3 + D5 + D6.")

    chamfer_limit = max(0.0, min(B1_mm, B2_mm, D1_mm) / 2.0)
    if C1_mm > chamfer_limit:
        raise ValueError("Invalid geometry: C1 is too large for the selected girder dimensions.")

    top_y = D1_mm / 2.0
    bottom_y = -D1_mm / 2.0
    y_top_flange_bottom = top_y - D2_mm
    y_top_haunch_bottom = y_top_flange_bottom - D3_mm
    y_bottom_flange_top = bottom_y + D5_mm
    y_bottom_haunch_top = y_bottom_flange_top + D6_mm

    b1 = B1_mm / 2.0
    b2 = B2_mm / 2.0
    t1 = T1_mm / 2.0
    t2 = T2_mm / 2.0
    c = float(C1_mm)

    def add(points: list[Point2D], x: float, y: float) -> None:
        if points and abs(points[-1].x - x) < 1e-9 and abs(points[-1].y - y) < 1e-9:
            return
        points.append(_point(x, y))

    points: list[Point2D] = []
    # Clockwise/counter-clockwise orientation is not important to Shapely for
    # a solid polygon, but we keep an ordered perimeter without duplicate points.
    if c > 0:
        add(points, -b2 + c, bottom_y)
        add(points, b2 - c, bottom_y)
        add(points, b2, bottom_y + c)
    else:
        add(points, -b2, bottom_y)
        add(points, b2, bottom_y)
    add(points, b2, y_bottom_flange_top)
    add(points, t2, y_bottom_haunch_top)
    add(points, t1, y_top_haunch_bottom)
    add(points, b1, y_top_flange_bottom)
    if c > 0:
        add(points, b1, top_y - c)
        add(points, b1 - c, top_y)
        add(points, -b1 + c, top_y)
        add(points, -b1, top_y - c)
    else:
        add(points, b1, top_y)
        add(points, -b1, top_y)
    add(points, -b1, y_top_flange_bottom)
    add(points, -t1, y_top_haunch_bottom)
    add(points, -t2, y_bottom_haunch_top)
    add(points, -b2, y_bottom_flange_top)
    if c > 0:
        add(points, -b2, bottom_y + c)

    _ensure_valid_simple_polygon(points, "Parametric I-Girder")
    return SectionGeometry(
        name=name,
        outer_polygon=points,
        holes=[],
        metadata={
            "preset": "parametric_i_girder",
            "girder_type": "I-Girder",
            "units": "mm",
            "parameters": {
                "B1_mm": B1_mm,
                "B2_mm": B2_mm,
                "D1_mm": D1_mm,
                "D2_mm": D2_mm,
                "D3_mm": D3_mm,
                "D5_mm": D5_mm,
                "D6_mm": D6_mm,
                "T1_mm": T1_mm,
                "T2_mm": T2_mm,
                "C1_mm": C1_mm,
            },
            "zone_depths_mm": {
                "top_flange": D2_mm,
                "top_haunch": D3_mm,
                "web_clear_zone": web_zone_mm,
                "bottom_haunch": D6_mm,
                "bottom_flange": D5_mm,
            },
            "analysis_compatibility": {
                "uls_pmm": "supported",
                "sls_stress": "planned",
                "beam_girder_assignment": "planned",
                "shear_torsion": "planned",
            },
        },
    )



def _plank_transformed_metadata(
    *,
    Tslab_mm: float,
    Be_mm: float,
    Ebeam_MPa: float,
    Edeck_MPa: float,
    girder_length_mm: float,
    overhang_mm: float = 0.0,
) -> dict[str, float | str]:
    _require_non_negative("Tslab", Tslab_mm)
    _require_positive("Be", Be_mm)
    _require_positive("Ebeam", Ebeam_MPa)
    _require_positive("Edeck", Edeck_MPa)
    _require_positive("Girder length", girder_length_mm)
    _require_non_negative("overhang", overhang_mm)
    n = Edeck_MPa / Ebeam_MPa
    return {
        "Tslab_mm": float(Tslab_mm),
        "Be_mm": float(Be_mm),
        "Ebeam_MPa": float(Ebeam_MPa),
        "Edeck_MPa": float(Edeck_MPa),
        "n_Edeck_over_Ebeam": float(n),
        "Btransformed_mm": float(n * Be_mm),
        "girder_length_mm": float(girder_length_mm),
        "overhang_mm": float(overhang_mm),
        "Be_calculation_mode": "manual_current__auto_aashto_planned",
    }


def parametric_plank_girder_interior(
    B_mm: float,
    b1_mm: float,
    b2_mm: float,
    b3_mm: float,
    H_mm: float,
    h1_mm: float,
    h2_mm: float,
    Tslab_mm: float = 100.0,
    Be_mm: float = 1000.0,
    Ebeam_MPa: float = 35000.0,
    Edeck_MPa: float = 28560.0,
    girder_length_mm: float = 12000.0,
    name: str = "Parametric Plank Girder — Interior",
) -> SectionGeometry:
    """Generate a symmetric interior precast plank-girder polygon.

    The polygon represents the precast plank only. Composite deck metadata is
    retained for future AASHTO SLS/transformed-section checks, but the slab is
    not merged into the concrete polygon in this milestone.
    """
    for label, value in {"B": B_mm, "b3": b3_mm, "H": H_mm}.items():
        _require_positive(label, value)
    for label, value in {"b1": b1_mm, "b2": b2_mm, "h1": h1_mm, "h2": h2_mm}.items():
        _require_non_negative(label, value)
    if b3_mm >= B_mm:
        raise ValueError("Invalid geometry: b3 must be smaller than B for an interior plank with side offsets.")
    if h1_mm > h2_mm:
        raise ValueError("Invalid geometry: h1 must not exceed h2.")
    if h2_mm >= H_mm:
        raise ValueError("Invalid geometry: h2 must be less than H.")
    expected_b2 = (B_mm - b3_mm) / 2.0
    if abs(expected_b2 - b2_mm) > max(2.0, 0.05 * B_mm):
        raise ValueError("Invalid geometry: for interior plank, B should approximately equal b3 + 2*b2.")
    if b1_mm > (B_mm - b3_mm) / 2.0 + b1_mm + B_mm:
        raise ValueError("Invalid geometry: b1 is not compatible with the selected plank width.")

    top_y = H_mm / 2.0
    bottom_y = -H_mm / 2.0
    y1 = bottom_y + h1_mm
    y2 = bottom_y + h2_mm

    # Drawing convention for the user-supplied plank:
    #   B is the overall reference width.
    #   The solid top face is inset by b1 from both sides.
    #   The solid bottom/reference face has width b3, leaving b2 each side.
    # Earlier versions incorrectly used B as the physical top face, which made
    # the plank an inverted wide-top trapezoid.  The physical section is built
    # from the visible precast outline, while B remains the dimension guide.
    x_ref = B_mm / 2.0
    x_top = max(0.0, x_ref - b1_mm)
    x_bottom = b3_mm / 2.0
    x_lower_ref = max(x_bottom, x_ref - b2_mm)

    if x_top <= 0.0:
        raise ValueError("Invalid geometry: B must be greater than 2*b1 for an interior plank.")
    if x_bottom <= 0.0:
        raise ValueError("Invalid geometry: b3 must be greater than zero.")

    points = [
        _point(-x_top, top_y),
        _point(x_top, top_y),
        _point(x_top, y2),
        _point(x_lower_ref, y1),
        _point(x_bottom, bottom_y),
        _point(-x_bottom, bottom_y),
        _point(-x_lower_ref, y1),
        _point(-x_top, y2),
    ]
    _ensure_valid_simple_polygon(points, "Parametric interior plank girder")
    transformed = _plank_transformed_metadata(
        Tslab_mm=Tslab_mm,
        Be_mm=Be_mm,
        Ebeam_MPa=Ebeam_MPa,
        Edeck_MPa=Edeck_MPa,
        girder_length_mm=girder_length_mm,
        overhang_mm=0.0,
    )
    return SectionGeometry(
        name=name,
        outer_polygon=points,
        holes=[],
        metadata={
            "preset": "parametric_plank_girder_interior",
            "girder_type": "Plank Girder",
            "plank_position": "Interior",
            "units": "mm",
            "parameters": {
                "B_mm": B_mm,
                "b1_mm": b1_mm,
                "b2_mm": b2_mm,
                "b3_mm": b3_mm,
                "H_mm": H_mm,
                "h1_mm": h1_mm,
                "h2_mm": h2_mm,
            },
            "composite_metadata": transformed,
            "analysis_compatibility": {
                "uls_pmm": "supported_precast_only",
                "sls_stress": "planned_composite_metadata_ready",
                "beam_girder_assignment": "planned",
                "aashto_effective_width_auto": "planned",
                "shear_torsion": "planned",
            },
        },
    )


def parametric_plank_girder_exterior(
    B_mm: float,
    b1_mm: float,
    b2_mm: float,
    b3_mm: float,
    H_mm: float,
    h1_mm: float,
    h2_mm: float,
    Tslab_mm: float = 100.0,
    Be_mm: float = 1000.0,
    Ebeam_MPa: float = 35000.0,
    Edeck_MPa: float = 28560.0,
    girder_length_mm: float = 12000.0,
    overhang_mm: float = 500.0,
    name: str = "Parametric Plank Girder — Exterior",
) -> SectionGeometry:
    """Generate an asymmetric exterior precast plank-girder polygon.

    The exterior side is kept vertical; the interior side follows the stepped
    plank profile. The polygon is precast-only. Effective slab width data are
    retained as metadata for future AASHTO composite checks.
    """
    for label, value in {"B": B_mm, "b3": b3_mm, "H": H_mm}.items():
        _require_positive(label, value)
    for label, value in {"b1": b1_mm, "b2": b2_mm, "h1": h1_mm, "h2": h2_mm, "overhang": overhang_mm}.items():
        _require_non_negative(label, value)
    if b3_mm >= B_mm:
        raise ValueError("Invalid geometry: b3 must be smaller than B for an exterior plank with one side offset.")
    if h1_mm > h2_mm:
        raise ValueError("Invalid geometry: h1 must not exceed h2.")
    if h2_mm >= H_mm:
        raise ValueError("Invalid geometry: h2 must be less than H.")
    expected_b2 = B_mm - b3_mm
    if abs(expected_b2 - b2_mm) > max(2.0, 0.05 * B_mm):
        raise ValueError("Invalid geometry: for exterior plank, B should approximately equal b3 + b2.")

    top_y = H_mm / 2.0
    bottom_y = -H_mm / 2.0
    y1 = bottom_y + h1_mm
    y2 = bottom_y + h2_mm

    # Exterior plank drawing convention:
    #   one exterior side is kept vertical/full-depth;
    #   the interior side is inset by b1 at the top and by b2/b3 at the bottom.
    # This matches the supplied exterior-girder sketch instead of using the
    # full reference width as the physical top face.
    x_right = B_mm / 2.0
    x_left_ref = -B_mm / 2.0
    x_top_left = x_left_ref + b1_mm
    x_bottom_left = x_right - b3_mm
    x_lower_ref = min(x_bottom_left, x_left_ref + b2_mm)

    if x_top_left >= x_right:
        raise ValueError("Invalid geometry: B must be greater than b1 for an exterior plank.")
    if x_bottom_left >= x_right:
        raise ValueError("Invalid geometry: b3 must be smaller than B for an exterior plank.")

    points = [
        _point(x_top_left, top_y),
        _point(x_right, top_y),
        _point(x_right, bottom_y),
        _point(x_bottom_left, bottom_y),
        _point(x_lower_ref, y1),
        _point(x_top_left, y2),
    ]
    _ensure_valid_simple_polygon(points, "Parametric exterior plank girder")
    transformed = _plank_transformed_metadata(
        Tslab_mm=Tslab_mm,
        Be_mm=Be_mm,
        Ebeam_MPa=Ebeam_MPa,
        Edeck_MPa=Edeck_MPa,
        girder_length_mm=girder_length_mm,
        overhang_mm=overhang_mm,
    )
    return SectionGeometry(
        name=name,
        outer_polygon=points,
        holes=[],
        metadata={
            "preset": "parametric_plank_girder_exterior",
            "girder_type": "Plank Girder",
            "plank_position": "Exterior",
            "units": "mm",
            "parameters": {
                "B_mm": B_mm,
                "b1_mm": b1_mm,
                "b2_mm": b2_mm,
                "b3_mm": b3_mm,
                "H_mm": H_mm,
                "h1_mm": h1_mm,
                "h2_mm": h2_mm,
            },
            "composite_metadata": transformed,
            "analysis_compatibility": {
                "uls_pmm": "supported_precast_only",
                "sls_stress": "planned_composite_metadata_ready",
                "beam_girder_assignment": "planned",
                "aashto_effective_width_auto": "planned",
                "shear_torsion": "planned",
            },
        },
    )

def u_girder(
    depth_mm: float,
    top_width_mm: float,
    bottom_width_mm: float,
    wall_thickness_mm: float,
    bottom_slab_thickness_mm: float,
    name: str = "U-girder",
) -> SectionGeometry:
    _require_positive("total depth", depth_mm)
    _require_positive("top width", top_width_mm)
    _require_positive("bottom width", bottom_width_mm)
    _require_positive("web thickness", wall_thickness_mm)
    _require_positive("bottom slab thickness", bottom_slab_thickness_mm)
    if bottom_slab_thickness_mm >= depth_mm:
        raise ValueError("Invalid geometry: bottom slab thickness must be less than total depth.")
    if top_width_mm <= bottom_width_mm:
        raise ValueError("Invalid geometry: top width must be greater than bottom width for this U-girder generator.")
    if 2.0 * wall_thickness_mm >= top_width_mm or 2.0 * wall_thickness_mm >= bottom_width_mm:
        raise ValueError("Invalid geometry: web thickness is too large for the selected girder widths.")
    top_y = depth_mm / 2.0
    bot_y = -depth_mm / 2.0
    inner_bot_y = bot_y + bottom_slab_thickness_mm
    points = [
        _point(-top_width_mm / 2.0, top_y),
        _point(-top_width_mm / 2.0 + wall_thickness_mm, top_y),
        _point(-bottom_width_mm / 2.0 + wall_thickness_mm, inner_bot_y),
        _point(bottom_width_mm / 2.0 - wall_thickness_mm, inner_bot_y),
        _point(top_width_mm / 2.0 - wall_thickness_mm, top_y),
        _point(top_width_mm / 2.0, top_y),
        _point(bottom_width_mm / 2.0, bot_y),
        _point(-bottom_width_mm / 2.0, bot_y),
    ]
    _ensure_valid_simple_polygon(points, "U-girder")
    return SectionGeometry(name=name, outer_polygon=points, holes=[], metadata={"preset": "u_girder"})


def single_cell_box_girder(
    width_mm: float,
    depth_mm: float,
    top_slab_thickness_mm: float,
    bottom_slab_thickness_mm: float,
    web_thickness_mm: float,
    name: str = "Single cell box girder",
) -> SectionGeometry:
    _require_positive("B", width_mm)
    _require_positive("D", depth_mm)
    _require_positive("top slab thickness", top_slab_thickness_mm)
    _require_positive("bottom slab thickness", bottom_slab_thickness_mm)
    _require_positive("web thickness", web_thickness_mm)
    if top_slab_thickness_mm + bottom_slab_thickness_mm >= depth_mm:
        raise ValueError("Invalid geometry: top slab + bottom slab must be less than total depth.")
    if 2.0 * web_thickness_mm >= width_mm:
        raise ValueError("Invalid geometry: web thickness is too large; inner width must be positive.")
    inner_w = width_mm - 2.0 * web_thickness_mm
    inner_h = depth_mm - top_slab_thickness_mm - bottom_slab_thickness_mm
    if inner_w <= 0:
        raise ValueError("Invalid geometry: inner width must be greater than zero.")
    if inner_h <= 0:
        raise ValueError("Invalid geometry: inner height must be greater than zero.")
    cy = (bottom_slab_thickness_mm - top_slab_thickness_mm) / 2.0
    hole = [_point(p.x, p.y + cy) for p in _rectangle_points(inner_w, inner_h)]
    return SectionGeometry(
        name=name,
        outer_polygon=_rectangle_points(width_mm, depth_mm),
        holes=[list(reversed(hole))],
        metadata={"preset": "single_cell_box_girder"},
    )


def _dim(
    symbol: str,
    start: Point2D,
    end: Point2D,
    text: Point2D,
    kind: str = "aligned",
    value: float | None = None,
    unit: str = "mm",
) -> DimensionItem:
    label = f"{symbol} = {value:g} {unit}" if value is not None else symbol
    return DimensionItem(label=label, symbol=symbol, start=start, end=end, text_position=text, kind=kind, value_mm=value, unit=unit)


def rectangle_dimensions(width_mm: float, height_mm: float, **_: object) -> list[DimensionItem]:
    w = width_mm / 2.0
    h = height_mm / 2.0
    offset = max(width_mm, height_mm) * 0.08
    return [
        _dim("B", _point(-w, -h - offset), _point(w, -h - offset), _point(0, -h - 1.6 * offset), "horizontal", width_mm),
        _dim("H", _point(w + offset, -h), _point(w + offset, h), _point(w + 1.8 * offset, 0), "vertical", height_mm),
    ]


def rectangular_chamfered_dimensions(width_mm: float, height_mm: float, chamfer_mm: float, **kwargs: object) -> list[DimensionItem]:
    dims = rectangle_dimensions(width_mm, height_mm, **kwargs)
    w = width_mm / 2.0
    h = height_mm / 2.0
    dims.append(_dim("c", _point(w - chamfer_mm, h), _point(w, h - chamfer_mm), _point(w + chamfer_mm, h + chamfer_mm), "aligned", chamfer_mm))
    return dims


def circle_dimensions(diameter_mm: float, **_: object) -> list[DimensionItem]:
    r = diameter_mm / 2.0
    return [_dim("D", _point(-r, 0), _point(r, 0), _point(0, -0.18 * diameter_mm), "diameter", diameter_mm)]


def circular_hollow_dimensions(outer_diameter_mm: float, inner_diameter_mm: float, **_: object) -> list[DimensionItem]:
    r_outer = outer_diameter_mm / 2.0
    r_inner = inner_diameter_mm / 2.0
    return [
        _dim("D_outer", _point(-r_outer, 0), _point(r_outer, 0), _point(0, -0.18 * outer_diameter_mm), "diameter", outer_diameter_mm),
        _dim("D_inner", _point(-r_inner, 0), _point(r_inner, 0), _point(0, 0.18 * outer_diameter_mm), "diameter", inner_diameter_mm),
    ]


def rectangular_hollow_dimensions(
    width_mm: float,
    height_mm: float,
    t_top_mm: float | None = None,
    t_bottom_mm: float | None = None,
    t_left_mm: float | None = None,
    t_right_mm: float | None = None,
    wall_thickness_mm: float | None = None,
    **kwargs: object,
) -> list[DimensionItem]:
    top, bottom, left, right = _resolve_wall_thicknesses(
        t_top_mm=t_top_mm,
        t_bottom_mm=t_bottom_mm,
        t_left_mm=t_left_mm,
        t_right_mm=t_right_mm,
        wall_thickness_mm=wall_thickness_mm,
    )
    dims = rectangle_dimensions(width_mm, height_mm, **kwargs)
    dims.extend(
        [
            _dim("t_left", _point(-width_mm / 2.0, 0), _point(-width_mm / 2.0 + left, 0), _point(-width_mm / 2.0, height_mm * 0.18), "horizontal", left),
            _dim("t_right", _point(width_mm / 2.0 - right, 0), _point(width_mm / 2.0, 0), _point(width_mm / 2.0, height_mm * 0.18), "horizontal", right),
            _dim("t_top", _point(0, height_mm / 2.0 - top), _point(0, height_mm / 2.0), _point(-width_mm * 0.18, height_mm / 2.0), "vertical", top),
            _dim("t_bottom", _point(0, -height_mm / 2.0), _point(0, -height_mm / 2.0 + bottom), _point(width_mm * 0.18, -height_mm / 2.0), "vertical", bottom),
        ]
    )
    return dims


def box_section_fillet_dimensions(
    width_mm: float,
    height_mm: float,
    t_top_mm: float | None = None,
    t_bottom_mm: float | None = None,
    t_left_mm: float | None = None,
    t_right_mm: float | None = None,
    r_inner_mm: float | None = None,
    r_outer_mm: float = 0.0,
    n_fillet: int = 12,
    wall_thickness_mm: float | None = None,
    fillet_radius_mm: float | None = None,
    **kwargs: object,
) -> list[DimensionItem]:
    # n_fillet is intentionally kept in the dimension-helper signature to
    # mirror the geometry generator; dimension annotations do not discretize arcs.
    _ = n_fillet
    top, bottom, left, right = _resolve_wall_thicknesses(
        t_top_mm=t_top_mm,
        t_bottom_mm=t_bottom_mm,
        t_left_mm=t_left_mm,
        t_right_mm=t_right_mm,
        wall_thickness_mm=wall_thickness_mm,
    )
    inner_radius = float(fillet_radius_mm if r_inner_mm is None and fillet_radius_mm is not None else r_inner_mm or 0.0)
    dims = rectangular_hollow_dimensions(width_mm, height_mm, top, bottom, left, right, **kwargs)
    if inner_radius > 0:
        dims.append(
            _dim(
                "Ri",
                _point(width_mm / 2.0 - right - inner_radius, height_mm / 2.0 - top),
                _point(width_mm / 2.0 - right, height_mm / 2.0 - top - inner_radius),
                _point(width_mm / 2.0 - right, height_mm / 2.0 - top),
                "radial",
                inner_radius,
            )
        )
    dims.append(
        _dim(
            "Ro",
            _point(width_mm / 2.0 - r_outer_mm, height_mm / 2.0),
            _point(width_mm / 2.0, height_mm / 2.0 - r_outer_mm),
            _point(width_mm / 2.0, height_mm / 2.0),
            "radial",
            r_outer_mm,
        )
    )
    return dims


def parametric_i_girder_dimensions(
    B1_mm: float,
    B2_mm: float,
    D1_mm: float,
    D2_mm: float,
    D3_mm: float,
    D5_mm: float,
    D6_mm: float,
    T1_mm: float,
    T2_mm: float,
    C1_mm: float = 0.0,
    **_: object,
) -> list[DimensionItem]:
    top_y = D1_mm / 2.0
    bottom_y = -D1_mm / 2.0
    y_top_flange_bottom = top_y - D2_mm
    y_top_haunch_bottom = y_top_flange_bottom - D3_mm
    y_bottom_flange_top = bottom_y + D5_mm
    y_bottom_haunch_top = y_bottom_flange_top + D6_mm
    offset = max(B1_mm, B2_mm, D1_mm) * 0.08
    right = max(B1_mm, B2_mm) / 2.0
    dims = [
        _dim("D1", _point(right + offset, bottom_y), _point(right + offset, top_y), _point(right + 2.0 * offset, 0.0), "vertical", D1_mm),
        _dim("B1", _point(-B1_mm / 2.0, top_y + offset), _point(B1_mm / 2.0, top_y + offset), _point(0.0, top_y + 1.6 * offset), "horizontal", B1_mm),
        _dim("B2", _point(-B2_mm / 2.0, bottom_y - offset), _point(B2_mm / 2.0, bottom_y - offset), _point(0.0, bottom_y - 1.6 * offset), "horizontal", B2_mm),
        _dim("T1", _point(-T1_mm / 2.0, y_top_haunch_bottom), _point(T1_mm / 2.0, y_top_haunch_bottom), _point(0.0, y_top_haunch_bottom + offset), "horizontal", T1_mm),
        _dim("T2", _point(-T2_mm / 2.0, y_bottom_haunch_top), _point(T2_mm / 2.0, y_bottom_haunch_top), _point(0.0, y_bottom_haunch_top - offset), "horizontal", T2_mm),
        _dim("D2", _point(-right - offset, y_top_flange_bottom), _point(-right - offset, top_y), _point(-right - 2.0 * offset, top_y - D2_mm / 2.0), "vertical", D2_mm),
        _dim("D3", _point(-right - offset, y_top_haunch_bottom), _point(-right - offset, y_top_flange_bottom), _point(-right - 2.0 * offset, y_top_flange_bottom - D3_mm / 2.0), "vertical", D3_mm),
        _dim("D5", _point(-right - offset, bottom_y), _point(-right - offset, y_bottom_flange_top), _point(-right - 2.0 * offset, bottom_y + D5_mm / 2.0), "vertical", D5_mm),
        _dim("D6", _point(-right - offset, y_bottom_flange_top), _point(-right - offset, y_bottom_haunch_top), _point(-right - 2.0 * offset, y_bottom_flange_top + D6_mm / 2.0), "vertical", D6_mm),
    ]
    if C1_mm > 0:
        dims.append(
            _dim(
                "C1",
                _point(B2_mm / 2.0 - C1_mm, bottom_y),
                _point(B2_mm / 2.0, bottom_y + C1_mm),
                _point(B2_mm / 2.0 + offset * 0.7, bottom_y + offset * 0.35),
                "aligned",
                C1_mm,
            )
        )
    return dims



def parametric_plank_girder_interior_dimensions(
    B_mm: float,
    b1_mm: float,
    b2_mm: float,
    b3_mm: float,
    H_mm: float,
    h1_mm: float,
    h2_mm: float,
    **_: object,
) -> list[DimensionItem]:
    x_outer = B_mm / 2.0
    x_bottom = b3_mm / 2.0
    top_y = H_mm / 2.0
    bottom_y = -H_mm / 2.0
    offset = max(B_mm, H_mm) * 0.07
    return [
        _dim("B", _point(-x_outer, top_y + offset), _point(x_outer, top_y + offset), _point(0, top_y + 1.6 * offset), "horizontal", B_mm),
        _dim("b3", _point(-x_bottom, bottom_y - offset), _point(x_bottom, bottom_y - offset), _point(0, bottom_y - 1.6 * offset), "horizontal", b3_mm),
        _dim("H", _point(x_outer + offset, bottom_y), _point(x_outer + offset, top_y), _point(x_outer + 1.8 * offset, 0), "vertical", H_mm),
        _dim("h1", _point(-x_outer - offset, bottom_y), _point(-x_outer - offset, bottom_y + h1_mm), _point(-x_outer - 1.8 * offset, bottom_y + h1_mm / 2.0), "vertical", h1_mm),
        _dim("h2", _point(-x_outer - 2.1 * offset, bottom_y), _point(-x_outer - 2.1 * offset, bottom_y + h2_mm), _point(-x_outer - 2.9 * offset, bottom_y + h2_mm / 2.0), "vertical", h2_mm),
        _dim("b1", _point(x_outer - b1_mm, top_y + 0.35 * offset), _point(x_outer, top_y + 0.35 * offset), _point(x_outer - b1_mm / 2.0, top_y + 0.9 * offset), "horizontal", b1_mm),
        _dim("b2", _point(x_bottom, bottom_y - 0.35 * offset), _point(x_outer, bottom_y - 0.35 * offset), _point((x_bottom + x_outer) / 2.0, bottom_y - 0.9 * offset), "horizontal", b2_mm),
    ]


def parametric_plank_girder_exterior_dimensions(
    B_mm: float,
    b1_mm: float,
    b2_mm: float,
    b3_mm: float,
    H_mm: float,
    h1_mm: float,
    h2_mm: float,
    **_: object,
) -> list[DimensionItem]:
    x_left = -B_mm / 2.0
    x_right = B_mm / 2.0
    x_bottom_left = x_right - b3_mm
    top_y = H_mm / 2.0
    bottom_y = -H_mm / 2.0
    offset = max(B_mm, H_mm) * 0.07
    return [
        _dim("B", _point(x_left, top_y + offset), _point(x_right, top_y + offset), _point(0, top_y + 1.6 * offset), "horizontal", B_mm),
        _dim("b3", _point(x_bottom_left, bottom_y - offset), _point(x_right, bottom_y - offset), _point((x_bottom_left + x_right) / 2.0, bottom_y - 1.6 * offset), "horizontal", b3_mm),
        _dim("H", _point(x_right + offset, bottom_y), _point(x_right + offset, top_y), _point(x_right + 1.8 * offset, 0), "vertical", H_mm),
        _dim("h1", _point(x_left - offset, bottom_y), _point(x_left - offset, bottom_y + h1_mm), _point(x_left - 1.8 * offset, bottom_y + h1_mm / 2.0), "vertical", h1_mm),
        _dim("h2", _point(x_left - 2.1 * offset, bottom_y), _point(x_left - 2.1 * offset, bottom_y + h2_mm), _point(x_left - 2.9 * offset, bottom_y + h2_mm / 2.0), "vertical", h2_mm),
        _dim("b1", _point(x_left, top_y + 0.35 * offset), _point(x_left + b1_mm, top_y + 0.35 * offset), _point(x_left + b1_mm / 2.0, top_y + 0.9 * offset), "horizontal", b1_mm),
        _dim("b2", _point(x_left, bottom_y - 0.35 * offset), _point(x_bottom_left, bottom_y - 0.35 * offset), _point((x_left + x_bottom_left) / 2.0, bottom_y - 0.9 * offset), "horizontal", b2_mm),
    ]

def psc_i_girder_dimensions(depth_mm: float, top_flange_width_mm: float, bottom_flange_width_mm: float, web_width_mm: float, **_: object) -> list[DimensionItem]:
    d = depth_mm / 2.0
    offset = depth_mm * 0.08
    return [
        _dim("D", _point(max(top_flange_width_mm, bottom_flange_width_mm) / 2.0 + offset, -d), _point(max(top_flange_width_mm, bottom_flange_width_mm) / 2.0 + offset, d), _point(max(top_flange_width_mm, bottom_flange_width_mm) / 2.0 + 2 * offset, 0), "vertical", depth_mm),
        _dim("B_top", _point(-top_flange_width_mm / 2.0, d + offset), _point(top_flange_width_mm / 2.0, d + offset), _point(0, d + 1.6 * offset), "horizontal", top_flange_width_mm),
        _dim("t_web", _point(-web_width_mm / 2.0, 0), _point(web_width_mm / 2.0, 0), _point(0, -offset), "horizontal", web_width_mm),
    ]


def u_girder_dimensions(depth_mm: float, top_width_mm: float, bottom_width_mm: float, wall_thickness_mm: float, **_: object) -> list[DimensionItem]:
    d = depth_mm / 2.0
    offset = depth_mm * 0.08
    return [
        _dim("D", _point(top_width_mm / 2.0 + offset, -d), _point(top_width_mm / 2.0 + offset, d), _point(top_width_mm / 2.0 + 2 * offset, 0), "vertical", depth_mm),
        _dim("B_top", _point(-top_width_mm / 2.0, d + offset), _point(top_width_mm / 2.0, d + offset), _point(0, d + 1.6 * offset), "horizontal", top_width_mm),
        _dim("B_bot", _point(-bottom_width_mm / 2.0, -d - offset), _point(bottom_width_mm / 2.0, -d - offset), _point(0, -d - 1.6 * offset), "horizontal", bottom_width_mm),
        _dim("t_web", _point(top_width_mm / 2.0 - wall_thickness_mm, d - offset), _point(top_width_mm / 2.0, d - offset), _point(top_width_mm / 2.0, d - 2 * offset), "horizontal", wall_thickness_mm),
    ]


def single_cell_box_girder_dimensions(width_mm: float, depth_mm: float, web_thickness_mm: float, top_slab_thickness_mm: float, **kwargs: object) -> list[DimensionItem]:
    dims = rectangle_dimensions(width_mm, depth_mm, **kwargs)
    dims.append(_dim("t_web", _point(width_mm / 2.0 - web_thickness_mm, 0), _point(width_mm / 2.0, 0), _point(width_mm / 2.0, depth_mm * 0.18), "horizontal", web_thickness_mm))
    dims.append(_dim("t_top", _point(0, depth_mm / 2.0 - top_slab_thickness_mm), _point(0, depth_mm / 2.0), _point(-width_mm * 0.18, depth_mm / 2.0), "vertical", top_slab_thickness_mm))
    return dims


def register_builtin_generators(registry: GeometryRegistry) -> None:
    entries = {
        "rectangle": (rectangle, rectangle_dimensions),
        "rectangular_chamfered": (rectangular_chamfered, rectangular_chamfered_dimensions),
        "circle": (circle, circle_dimensions),
        "circular_hollow": (circular_hollow, circular_hollow_dimensions),
        "rectangular_hollow": (rectangular_hollow, rectangular_hollow_dimensions),
        "box_section_fillet": (box_section_fillet, box_section_fillet_dimensions),
        "psc_i_girder": (psc_i_girder, psc_i_girder_dimensions),
        "parametric_i_girder": (parametric_i_girder, parametric_i_girder_dimensions),
        "parametric_plank_girder_interior": (parametric_plank_girder_interior, parametric_plank_girder_interior_dimensions),
        "parametric_plank_girder_exterior": (parametric_plank_girder_exterior, parametric_plank_girder_exterior_dimensions),
        "u_girder": (u_girder, u_girder_dimensions),
        "single_cell_box_girder": (single_cell_box_girder, single_cell_box_girder_dimensions),
    }
    for name, (geometry_func, dimension_func) in entries.items():
        registry.register_geometry(name, geometry_func)
        registry.register_dimensions(name, dimension_func)
