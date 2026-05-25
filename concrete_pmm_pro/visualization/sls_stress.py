"""SLS stress result visualization helpers.

These helpers visualize existing elastic SLS stress results at selected check
points. They intentionally do not perform stress redistribution, contouring, or
cracked-section analysis.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go

from concrete_pmm_pro.core.models import Point2D, SectionGeometry
from concrete_pmm_pro.serviceability.cracking import CrackClassificationPoint, CrackClassificationSummary
from concrete_pmm_pro.serviceability.models import ServiceStressPointResult, ServiceabilitySummary


def _closed_xy(points: list[Point2D]) -> tuple[list[float], list[float]]:
    if not points:
        return [], []
    closed = points + [points[0]]
    return [point.x for point in closed], [point.y for point in closed]


def service_stress_results_for_combo(
    summary: ServiceabilitySummary,
    combo_name: str,
) -> list[ServiceStressPointResult]:
    """Return stress point results for one SLS combo."""

    return [result for result in summary.stress_results if result.combo_name == combo_name]


def crack_classification_for_combo(
    crack_summary: CrackClassificationSummary | None,
    combo_name: str,
) -> list[CrackClassificationPoint]:
    """Return crack/tension classifications for one SLS combo."""

    if crack_summary is None:
        return []
    return [point for point in crack_summary.points if point.combo_name == combo_name]


def _classification_lookup(
    crack_summary: CrackClassificationSummary | None,
) -> dict[tuple[str, str], CrackClassificationPoint]:
    if crack_summary is None:
        return {}
    return {(point.combo_name, point.point_name): point for point in crack_summary.points}


def service_stress_results_to_plot_dataframe(
    summary: ServiceabilitySummary,
    crack_summary: CrackClassificationSummary | None = None,
    combo_name: str | None = None,
) -> pd.DataFrame:
    """Return SLS stress results with crack classification fields for plotting."""

    columns = [
        "Combo",
        "Point",
        "x_mm",
        "y_mm",
        "Stress_MPa",
        "External Stress_MPa",
        "Prestress Stress_MPa",
        "Total Stress_MPa",
        "Stress Type",
        "Status",
        "Utilization",
        "Section Basis",
        "Point Type",
        "Source",
        "Include in Governing",
        "Crack Classification",
        "Is Tension",
        "No-Tension Violation",
        "Decompression Violation",
        "Message",
    ]
    lookup = _classification_lookup(crack_summary)
    rows: list[dict[str, Any]] = []
    for result in summary.stress_results:
        if combo_name is not None and result.combo_name != combo_name:
            continue
        crack_point = lookup.get((result.combo_name, result.point_name))
        stress = result.stress_MPa
        is_tension = bool(stress is not None and stress > 0.0)
        rows.append(
            {
                "Combo": result.combo_name,
                "Point": result.point_name,
                "x_mm": result.x_mm,
                "y_mm": result.y_mm,
                "Stress_MPa": stress,
                "External Stress_MPa": result.external_stress_MPa,
                "Prestress Stress_MPa": result.prestress_stress_MPa,
                "Total Stress_MPa": result.total_stress_MPa,
                "Stress Type": result.stress_type,
                "Status": result.status,
                "Utilization": result.utilization,
                "Section Basis": result.section_basis,
                "Point Type": result.point_type,
                "Source": result.point_source,
                "Include in Governing": result.include_in_governing,
                "Crack Classification": None if crack_point is None else crack_point.classification,
                "Is Tension": is_tension if crack_point is None else crack_point.is_tension,
                "No-Tension Violation": False if crack_point is None else crack_point.no_tension_violation,
                "Decompression Violation": False if crack_point is None else crack_point.decompression_violation,
                "Message": result.message if crack_point is None else f"{result.message} {crack_point.message}".strip(),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def sls_status_color(
    status: str | None,
    stress_type: str | None = None,
    crack_classification: str | None = None,
) -> str:
    """Return a stable semantic color for SLS stress point status."""

    if status == "FAIL" or crack_classification in {
        "NO_TENSION_VIOLATION",
        "DECOMPRESSION_VIOLATION",
        "TENSION_EXCEEDS_LIMIT",
    }:
        return "#dc2626"
    if status == "WARNING":
        return "#f97316"
    if stress_type == "Compression":
        return "#2563eb"
    if stress_type == "Tension":
        return "#f59e0b"
    if stress_type == "Zero":
        return "#6b7280"
    if status == "PASS":
        return "#16a34a"
    return "#6b7280"


def _marker_sizes(stress_df: pd.DataFrame) -> list[float]:
    sizes: list[float] = []
    for value in stress_df.get("Utilization", pd.Series(dtype=float)):
        if pd.isna(value):
            sizes.append(13.0)
        else:
            sizes.append(max(11.0, min(24.0, 11.0 + float(value) * 7.0)))
    return sizes


def _empty_figure(title: str, message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(title=title, height=520, margin=dict(l=10, r=10, t=50, b=10))
    fig.add_annotation(text=message, showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5)
    return fig


def make_sls_section_stress_figure(
    section_geometry: SectionGeometry | None,
    stress_df: pd.DataFrame,
    combo_name: str,
    show_labels: bool = True,
) -> go.Figure:
    """Plot section outline and SLS stress check points for a selected combo."""

    title = f"SLS Stress Check Points - {combo_name}"
    if section_geometry is None:
        return _empty_figure(title, "Section geometry is not available.")

    fig = go.Figure()
    outer_x, outer_y = _closed_xy(section_geometry.outer_polygon)
    fig.add_trace(
        go.Scatter(
            x=outer_x,
            y=outer_y,
            mode="lines",
            fill="toself",
            fillcolor="rgba(148, 163, 184, 0.26)",
            line=dict(color="#334155", width=2),
            name="Concrete boundary",
            hoverinfo="skip",
        )
    )
    for index, hole in enumerate(section_geometry.holes, start=1):
        hole_x, hole_y = _closed_xy(hole)
        fig.add_trace(
            go.Scatter(
                x=hole_x,
                y=hole_y,
                mode="lines",
                fill="toself",
                fillcolor="rgba(255, 255, 255, 1.0)",
                line=dict(color="#64748b", width=1.5, dash="dot"),
                name=f"Hole {index}",
                hoverinfo="skip",
            )
        )

    plot_df = stress_df[stress_df["Combo"] == combo_name].copy() if "Combo" in stress_df.columns else stress_df.copy()
    if plot_df.empty:
        fig.add_annotation(text="No SLS stress point results are available for this combo.", showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5)
    else:
        colors = [
            sls_status_color(row.get("Status"), row.get("Stress Type"), row.get("Crack Classification"))
            for _, row in plot_df.iterrows()
        ]
        customdata = plot_df[
            [
                "Combo",
                "Point",
                "Total Stress_MPa",
                "External Stress_MPa",
                "Prestress Stress_MPa",
                "Stress Type",
                "Status",
                "Utilization",
                "Crack Classification",
                "Point Type",
                "Source",
                "Include in Governing",
                "Message",
            ]
        ].to_numpy()
        fig.add_trace(
            go.Scatter(
                x=plot_df["x_mm"],
                y=plot_df["y_mm"],
                mode="markers+text" if show_labels else "markers",
                marker=dict(size=_marker_sizes(plot_df), color=colors, line=dict(color="white", width=1.4)),
                text=plot_df["Point"] if show_labels else None,
                textposition="top center",
                customdata=customdata,
                hovertemplate=(
                    "Combo=%{customdata[0]}<br>"
                    "Point=%{customdata[1]}<br>"
                    "x=%{x:.2f} mm<br>"
                    "y=%{y:.2f} mm<br>"
                    "Total stress=%{customdata[2]:.3f} MPa<br>"
                    "External stress=%{customdata[3]:.3f} MPa<br>"
                    "Prestress stress=%{customdata[4]:.3f} MPa<br>"
                    "Stress type=%{customdata[5]}<br>"
                    "Status=%{customdata[6]}<br>"
                    "Utilization=%{customdata[7]}<br>"
                    "Crack classification=%{customdata[8]}<br>"
                    "Point type=%{customdata[9]}<br>"
                    "Source=%{customdata[10]}<br>"
                    "Include in governing=%{customdata[11]}<br>"
                    "%{customdata[12]}<extra></extra>"
                ),
                name="SLS stress points",
            )
        )

    fig.update_layout(
        title=title,
        height=560,
        margin=dict(l=10, r=10, t=50, b=10),
        paper_bgcolor="white",
        plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(title="x (mm)", scaleanchor="y", scaleratio=1, showgrid=True, zeroline=True)
    fig.update_yaxes(title="y (mm)", showgrid=True, zeroline=True)
    return fig


def make_sls_stress_bar_figure(
    stress_df: pd.DataFrame,
    combo_name: str,
) -> go.Figure:
    """Plot selected-combo SLS stress point values as a bar diagram."""

    title = f"SLS Stress Diagram - {combo_name}"
    plot_df = stress_df[stress_df["Combo"] == combo_name].copy() if "Combo" in stress_df.columns else stress_df.copy()
    if plot_df.empty:
        return _empty_figure(title, "No SLS stress point results are available for this combo.")

    colors = [
        sls_status_color(row.get("Status"), row.get("Stress Type"), row.get("Crack Classification"))
        for _, row in plot_df.iterrows()
    ]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=plot_df["Point"],
            y=plot_df["Total Stress_MPa"],
            marker=dict(color=colors),
            customdata=plot_df[["Status", "Stress Type", "Crack Classification", "Message"]].to_numpy(),
            hovertemplate=(
                "Point=%{x}<br>"
                "Total stress=%{y:.3f} MPa<br>"
                "Status=%{customdata[0]}<br>"
                "Stress type=%{customdata[1]}<br>"
                "Crack classification=%{customdata[2]}<br>"
                "%{customdata[3]}<extra></extra>"
            ),
            name="Total stress",
        )
    )
    fig.add_shape(type="line", xref="paper", x0=0, x1=1, y0=0, y1=0, line=dict(color="#111827", width=1))
    fig.update_layout(
        title=title,
        height=420,
        margin=dict(l=10, r=10, t=50, b=60),
        paper_bgcolor="white",
        plot_bgcolor="white",
    )
    fig.update_xaxes(title="Stress check point")
    fig.update_yaxes(title="Total stress (MPa)")
    return fig
