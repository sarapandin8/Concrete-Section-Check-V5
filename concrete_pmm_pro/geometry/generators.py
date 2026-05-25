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
        "u_girder": (u_girder, u_girder_dimensions),
        "single_cell_box_girder": (single_cell_box_girder, single_cell_box_girder_dimensions),
    }
    for name, (geometry_func, dimension_func) in entries.items():
        registry.register_geometry(name, geometry_func)
        registry.register_dimensions(name, dimension_func)
