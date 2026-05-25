"""Plotly section preview."""

from __future__ import annotations

import math

import plotly.graph_objects as go

from concrete_pmm_pro.core.models import DimensionItem, DimensionLabelMode, Point2D, PrestressElement, Rebar, SectionGeometry
from concrete_pmm_pro.geometry.summary import summarize_geometry


def _closed_xy(points: list[Point2D]) -> tuple[list[float], list[float]]:
    closed = points + [points[0]]
    return [point.x for point in closed], [point.y for point in closed]


def equivalent_diameter_from_area(area_mm2: float | None) -> float | None:
    if area_mm2 is None or area_mm2 <= 0.0:
        return None
    return math.sqrt(4.0 * area_mm2 / math.pi)


def display_diameter_for_prestress_element(element: PrestressElement) -> float | None:
    if element.steel_type == "tendon_group":
        return equivalent_diameter_from_area(element.total_area_mm2)
    if element.diameter_mm is not None and element.diameter_mm > 0.0:
        return element.diameter_mm
    return equivalent_diameter_from_area(element.area_mm2)


def _prestress_display_group(element: PrestressElement) -> tuple[str, str, str]:
    if element.steel_type == "prestressing_bar":
        return "PT bar", "#c2410c", "#fff7ed"
    if element.steel_type in {"strand", "tendon_group", "wire"}:
        return "Prestressing strand/tendon", "#2563eb", "#eff6ff"
    return "Prestress steel", "#0f766e", "#ecfeff"


def _add_prestress_circle_shape(fig: go.Figure, element: PrestressElement, diameter_mm: float, color: str, outline: str) -> None:
    radius = diameter_mm / 2.0
    fig.add_shape(
        type="circle",
        xref="x",
        yref="y",
        x0=element.x_mm - radius,
        x1=element.x_mm + radius,
        y0=element.y_mm - radius,
        y1=element.y_mm + radius,
        fillcolor=color,
        opacity=0.34,
        line=dict(color=outline, width=1.4),
        layer="above",
    )


def create_section_preview(
    geometry: SectionGeometry,
    dimensions: list[DimensionItem] | None = None,
    dimension_label_mode: DimensionLabelMode = "symbol_value",
    rebars: list[Rebar] | None = None,
    prestress_elements: list[PrestressElement] | None = None,
) -> go.Figure:
    fig = go.Figure()
    outer_x, outer_y = _closed_xy(geometry.outer_polygon)
    fig.add_trace(
        go.Scatter(
            x=outer_x,
            y=outer_y,
            mode="lines",
            fill="toself",
            fillcolor="rgba(88, 120, 152, 0.38)",
            line=dict(color="#2d4059", width=2),
            name="Concrete",
        )
    )

    for index, hole in enumerate(geometry.holes, start=1):
        hole_x, hole_y = _closed_xy(hole)
        fig.add_trace(
            go.Scatter(
                x=hole_x,
                y=hole_y,
                mode="lines",
                fill="toself",
                fillcolor="rgba(255, 255, 255, 1.0)",
                line=dict(color="#5b6470", width=1.5, dash="dot"),
                name=f"Hole {index}",
            )
        )

    for dimension in dimensions or []:
        fig.add_trace(
            go.Scatter(
                x=[dimension.start.x, dimension.end.x],
                y=[dimension.start.y, dimension.end.y],
                mode="lines+markers",
                line=dict(color="#9a3412", width=1),
                marker=dict(size=4, color="#9a3412"),
                showlegend=False,
                hoverinfo="skip",
            )
        )
        fig.add_annotation(
            x=dimension.text_position.x,
            y=dimension.text_position.y,
            text=dimension.display_label(dimension_label_mode),
            showarrow=False,
            font=dict(size=11, color="#9a3412"),
            bgcolor="rgba(255,255,255,0.72)",
            borderpad=2,
        )

    if rebars:
        fig.add_trace(
            go.Scatter(
                x=[rebar.x_mm for rebar in rebars],
                y=[rebar.y_mm for rebar in rebars],
                mode="markers",
                marker=dict(
                    symbol="circle",
                    size=[max(8.0, min(24.0, rebar.diameter_mm * 0.7)) for rebar in rebars],
                    color="#111827",
                    line=dict(color="#f8fafc", width=1.5),
                ),
                text=[
                    f"{rebar.label or 'Rebar'}<br>x={rebar.x_mm:g} mm<br>y={rebar.y_mm:g} mm<br>D={rebar.diameter_mm:g} mm<br>As={rebar.area_mm2:.1f} mm^2"
                    for rebar in rebars
                ],
                hoverinfo="text",
                name="Rebar",
            )
        )

    if prestress_elements:
        grouped: dict[str, list[PrestressElement]] = {}
        group_styles: dict[str, tuple[str, str]] = {}
        for element in prestress_elements:
            group_name, color, outline = _prestress_display_group(element)
            grouped.setdefault(group_name, []).append(element)
            group_styles[group_name] = (color, outline)
        for group_name, elements in grouped.items():
            color, outline = group_styles[group_name]
            display_diameters = [display_diameter_for_prestress_element(element) for element in elements]
            display_sources = [
                "total steel area equivalent diameter" if element.steel_type == "tendon_group" or element.diameter_mm is None else "nominal steel diameter"
                for element in elements
            ]
            hover_text = []
            for element, display_diameter, display_source in zip(elements, display_diameters, display_sources):
                display_diameter_text = "N/A" if display_diameter is None else f"{display_diameter:.2f} mm"
                nominal_diameter_text = "N/A" if element.diameter_mm is None else f"{element.diameter_mm:g} mm"
                hover_text.append(
                    f"{element.label or group_name}<br>"
                    f"type={element.steel_type}<br>"
                    f"x={element.x_mm:g} mm<br>"
                    f"y={element.y_mm:g} mm<br>"
                    f"count={element.count}<br>"
                    f"nominal steel D={nominal_diameter_text}<br>"
                    f"display steel D={display_diameter_text}<br>"
                    f"display basis={display_source}<br>"
                    f"Aps per element={element.area_mm2:.1f} mm^2<br>"
                    f"total Aps={element.total_area_mm2:.1f} mm^2<br>"
                    f"Pe_eff per element={element.pe_eff_n:.1f} N<br>"
                    f"total Pe_eff={element.pe_eff_n * element.count:.1f} N<br>"
                    f"f_init={(element.initial_stress_mpa or 0.0):.1f} MPa<br>"
                    f"{'bonded' if element.bonded else 'unbonded'}"
                )
                if display_diameter is not None:
                    _add_prestress_circle_shape(fig, element, display_diameter, color, outline)
            fig.add_trace(
                go.Scatter(
                    x=[element.x_mm for element in elements],
                    y=[element.y_mm for element in elements],
                    mode="markers",
                    marker=dict(
                        symbol="circle",
                        # The true steel area is drawn with coordinate-unit circle
                        # shapes; this small marker preserves hover and legend.
                        size=7,
                        color=color,
                        line=dict(color=outline, width=1.5),
                    ),
                    text=hover_text,
                    hoverinfo="text",
                    name=group_name,
                )
            )

    summary = summarize_geometry(geometry)
    fig.add_trace(
        go.Scatter(
            x=[summary.centroid_x_mm],
            y=[summary.centroid_y_mm],
            mode="markers+text",
            marker=dict(symbol="cross", size=12, color="#be123c"),
            text=["Centroid"],
            textposition="top center",
            name="Centroid",
        )
    )

    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        height=560,
        paper_bgcolor="white",
        plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(title="x (mm)", scaleanchor="y", scaleratio=1, showgrid=True, zeroline=True)
    fig.update_yaxes(title="y (mm)", showgrid=True, zeroline=True)
    return fig
