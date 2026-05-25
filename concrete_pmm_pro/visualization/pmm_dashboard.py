"""PMM dashboard visualization helpers."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from concrete_pmm_pro.analysis.capacity_check import DemandCapacitySummary
from concrete_pmm_pro.analysis.slice_envelope import SliceEnvelopeResult, build_slice_envelope
from concrete_pmm_pro.core.models import LoadCase
from concrete_pmm_pro.core.units import N_to_kN, Nmm_to_kNm

STATUS_COLORS = {
    "PASS": "#16a34a",
    "FAIL": "#dc2626",
    "OUT_OF_RANGE": "#f97316",
    "NOT_CHECKED": "#6b7280",
}

PMM_P_COLUMN_CANDIDATES = ("phiPn_kN", "phiPn_capped_kN", "P_kN", "Pu_kN", "P")
PMM_MX_COLUMN_CANDIDATES = ("phiMnx_kNm", "Mx_kNm", "Mux_kNm", "Mnx_kNm")
PMM_MY_COLUMN_CANDIDATES = ("phiMny_kNm", "My_kNm", "Muy_kNm", "Mny_kNm")


def get_active_uls_load_cases(load_cases: list[LoadCase]) -> list[LoadCase]:
    return [load_case for load_case in load_cases if load_case.active and load_case.load_type == "ULS"]


def demand_load_cases_to_display_dataframe(load_cases: list[LoadCase]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Combo Name": load_case.name,
                "Pu_kN": N_to_kN(load_case.Pu_N),
                "Mux_kNm": Nmm_to_kNm(load_case.Mux_Nmm),
                "Muy_kNm": Nmm_to_kNm(load_case.Muy_Nmm),
                "Mu_kNm": Nmm_to_kNm(math.hypot(load_case.Mux_Nmm, load_case.Muy_Nmm)),
                "Load Type": load_case.load_type,
                "Active": load_case.active,
            }
            for load_case in load_cases
        ]
    )


def get_selected_load_case(load_cases: list[LoadCase], combo_name: str) -> LoadCase | None:
    for load_case in load_cases:
        if load_case.name == combo_name:
            return load_case
    return None


def _slice_p_column(pmm_df: pd.DataFrame) -> str:
    if "phiPn_kN" in pmm_df.columns:
        return "phiPn_kN"
    if "phiPn_capped_kN" in pmm_df.columns:
        return "phiPn_capped_kN"
    raise ValueError("PMM dataframe must include phiPn_kN or phiPn_capped_kN.")


def _resolve_slice_p_column(pmm_df: pd.DataFrame, p_column: str) -> str:
    if p_column in pmm_df.columns:
        return p_column
    return _slice_p_column(pmm_df)


def _sort_slice_by_angle(slice_df: pd.DataFrame) -> pd.DataFrame:
    if slice_df.empty:
        return slice_df
    sorted_df = slice_df.copy()
    sorted_df["_slice_angle"] = sorted_df.apply(lambda row: math.atan2(row["phiMny_kNm"], row["phiMnx_kNm"]), axis=1)
    return sorted_df.sort_values("_slice_angle").drop(columns=["_slice_angle"])


def pmm_slice_at_pu_tolerance(
    pmm_df: pd.DataFrame,
    Pu_kN: float,
    tolerance_kN: float | None = None,
) -> pd.DataFrame:
    """Return PMM points near a selected axial load for Mux-Muy slicing."""

    if pmm_df.empty:
        result = pmm_df.copy()
        result.attrs["warnings"] = ["PMM dataframe is empty."]
        result.attrs["tolerance_kN"] = tolerance_kN
        result.attrs["method"] = "tolerance"
        return result

    p_column = _slice_p_column(pmm_df)
    p_values = pmm_df[p_column].astype(float)
    axial_range = float(p_values.max() - p_values.min())
    base_tolerance = tolerance_kN if tolerance_kN is not None else max(0.02 * axial_range, 50.0)
    max_tolerance = max(base_tolerance, 0.25 * axial_range, 250.0)
    warnings: list[str] = []

    selected = pd.DataFrame()
    selected_tolerance = base_tolerance
    multipliers = (1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 12.0)
    for multiplier in multipliers:
        selected_tolerance = min(base_tolerance * multiplier, max_tolerance)
        selected = pmm_df[(p_values - Pu_kN).abs() <= selected_tolerance].copy()
        if len(selected) >= 8 or selected_tolerance >= max_tolerance:
            if multiplier > 1.0:
                warnings.append(f"PMM Pu slice tolerance widened to {selected_tolerance:.1f} kN.")
            break

    if selected.empty:
        nearest_index = (p_values - Pu_kN).abs().idxmin()
        selected = pmm_df.loc[[nearest_index]].copy()
        warnings.append("No PMM points were inside the Pu slice tolerance; nearest PMM point is shown.")

    selected = _sort_slice_by_angle(selected)
    selected.attrs["warnings"] = warnings
    selected.attrs["tolerance_kN"] = selected_tolerance
    selected.attrs["p_column"] = p_column
    selected.attrs["method"] = "tolerance"
    return selected


def _with_fallback_attrs(fallback_df: pd.DataFrame, warnings: list[str]) -> pd.DataFrame:
    merged_warnings = warnings + list(fallback_df.attrs.get("warnings", []))
    fallback_df.attrs["warnings"] = merged_warnings
    fallback_df.attrs["method"] = "tolerance_fallback"
    return fallback_df


def _interpolate_between_rows(left: pd.Series, right: pd.Series, ratio: float, theta: float, Pu_kN: float, p_column: str) -> dict[str, Any]:
    interpolated: dict[str, Any] = {"theta_rad": theta}
    columns = set(left.index).union(set(right.index))
    for column in columns:
        left_value = left.get(column)
        right_value = right.get(column)
        if column == "theta_rad":
            interpolated[column] = theta
        elif column == p_column:
            interpolated[column] = Pu_kN
        elif column == "strain_condition":
            interpolated[column] = left_value if left_value == right_value else "interpolated"
        elif isinstance(left_value, Real) and isinstance(right_value, Real) and pd.notna(left_value) and pd.notna(right_value):
            interpolated[column] = float(left_value) + ratio * (float(right_value) - float(left_value))
        else:
            interpolated[column] = left_value if left_value == right_value else None
    if "phiPn_kN" in columns and p_column == "phiPn_kN":
        interpolated["phiPn_kN"] = Pu_kN
    if "phiPn_capped_kN" in columns and p_column == "phiPn_capped_kN":
        interpolated["phiPn_capped_kN"] = Pu_kN
    return interpolated


def pmm_slice_at_pu_interpolated(
    pmm_df: pd.DataFrame,
    Pu_kN: float,
    p_column: str = "phiPn_kN",
) -> pd.DataFrame:
    """Interpolate one PMM slice point per neutral-axis angle at a selected Pu."""

    warnings: list[str] = []
    required_columns = {"theta_rad", "c_mm", "phiMnx_kNm", "phiMny_kNm"}
    if pmm_df.empty:
        result = pmm_df.copy()
        result.attrs["method"] = "interpolated"
        result.attrs["warnings"] = ["PMM dataframe is empty."]
        result.attrs["skipped_theta_count"] = 0
        result.attrs["interpolated_theta_count"] = 0
        return result
    if not required_columns.issubset(pmm_df.columns):
        fallback = pmm_slice_at_pu_tolerance(pmm_df, Pu_kN)
        return _with_fallback_attrs(
            fallback,
            ["Interpolated PMM slice requires theta_rad and c_mm. Tolerance slice fallback used."],
        )

    resolved_p_column = _resolve_slice_p_column(pmm_df, p_column)
    rows: list[dict[str, Any]] = []
    skipped_theta_count = 0
    for theta, group in pmm_df.groupby("theta_rad", sort=False):
        working = group.copy()
        working = working[pd.notna(working[resolved_p_column])].copy()
        if len(working) < 2:
            skipped_theta_count += 1
            continue
        working["_radius"] = working.apply(lambda row: math.hypot(row["phiMnx_kNm"], row["phiMny_kNm"]), axis=1)
        working = working.sort_values([resolved_p_column, "_radius"]).drop_duplicates(subset=[resolved_p_column], keep="last")
        working = working.sort_values(resolved_p_column).drop(columns=["_radius"])
        p_values = working[resolved_p_column].astype(float).to_list()
        if Pu_kN < min(p_values) or Pu_kN > max(p_values):
            skipped_theta_count += 1
            continue

        exact = working[(working[resolved_p_column].astype(float) - Pu_kN).abs() <= 1.0e-9]
        if not exact.empty:
            row = exact.iloc[0].to_dict()
            row[resolved_p_column] = Pu_kN
            rows.append(row)
            continue

        interpolated_row: dict[str, Any] | None = None
        sorted_rows = list(working.iterrows())
        for (_, left), (_, right) in zip(sorted_rows[:-1], sorted_rows[1:]):
            p1 = float(left[resolved_p_column])
            p2 = float(right[resolved_p_column])
            if p1 == p2:
                continue
            if (p1 <= Pu_kN <= p2) or (p2 <= Pu_kN <= p1):
                ratio = (Pu_kN - p1) / (p2 - p1)
                interpolated_row = _interpolate_between_rows(left, right, ratio, float(theta), Pu_kN, resolved_p_column)
                break
        if interpolated_row is None:
            skipped_theta_count += 1
        else:
            rows.append(interpolated_row)

    if len(rows) < 8:
        fallback = pmm_slice_at_pu_tolerance(pmm_df, Pu_kN)
        return _with_fallback_attrs(
            fallback,
            [
                "Interpolated slice produced too few points; tolerance slice fallback used.",
                f"Interpolated theta count = {len(rows)}; skipped theta count = {skipped_theta_count}.",
            ],
        )

    result = _sort_slice_by_angle(pd.DataFrame(rows))
    result.attrs["method"] = "interpolated"
    result.attrs["skipped_theta_count"] = skipped_theta_count
    result.attrs["interpolated_theta_count"] = len(rows)
    result.attrs["warnings"] = warnings
    result.attrs["p_column"] = resolved_p_column
    return result.reset_index(drop=True)


def pmm_slice_at_pu(
    pmm_df: pd.DataFrame,
    Pu_kN: float,
    tolerance_kN: float | None = None,
) -> pd.DataFrame:
    """Return the preferred PMM slice, using interpolation with tolerance fallback."""

    if tolerance_kN is not None:
        return pmm_slice_at_pu_tolerance(pmm_df, Pu_kN, tolerance_kN)
    return pmm_slice_at_pu_interpolated(pmm_df, Pu_kN)


def _angle_0_to_2pi(angle_rad: float) -> float:
    return angle_rad % (2.0 * math.pi)


def estimate_directional_capacity_from_slice(
    slice_df: pd.DataFrame,
    Mux_kNm: float,
    Muy_kNm: float,
) -> dict[str, Any]:
    """Estimate directional capacity radius from a Mux-Muy PMM slice."""

    warnings: list[str] = []
    demand_Mu_kNm = math.hypot(Mux_kNm, Muy_kNm)
    alpha_rad = math.atan2(Muy_kNm, Mux_kNm)
    if demand_Mu_kNm <= 1.0e-12:
        return {
            "capacity_phiMn_kNm": None,
            "demand_Mu_kNm": demand_Mu_kNm,
            "dcr": None,
            "alpha_rad": alpha_rad,
            "method": "interpolated_slice",
            "status": "NOT_CHECKED",
            "warnings": ["Directional capacity from slice requires nonzero moment demand."],
        }
    if slice_df.empty or not {"phiMnx_kNm", "phiMny_kNm"}.issubset(slice_df.columns):
        return {
            "capacity_phiMn_kNm": None,
            "demand_Mu_kNm": demand_Mu_kNm,
            "dcr": None,
            "alpha_rad": alpha_rad,
            "method": "interpolated_slice",
            "status": "NOT_CHECKED",
            "warnings": ["PMM slice is empty or missing moment columns."],
        }

    polar_points: list[tuple[float, float]] = []
    for row in slice_df.itertuples():
        radius = math.hypot(float(row.phiMnx_kNm), float(row.phiMny_kNm))
        if radius <= 0.0:
            continue
        beta = _angle_0_to_2pi(math.atan2(float(row.phiMny_kNm), float(row.phiMnx_kNm)))
        polar_points.append((beta, radius))
    if len(polar_points) < 2:
        return {
            "capacity_phiMn_kNm": None,
            "demand_Mu_kNm": demand_Mu_kNm,
            "dcr": None,
            "alpha_rad": alpha_rad,
            "method": "interpolated_slice",
            "status": "NOT_CHECKED",
            "warnings": ["PMM slice has too few positive-radius points for directional interpolation."],
        }

    polar_points = sorted(polar_points, key=lambda item: item[0])
    alpha = _angle_0_to_2pi(alpha_rad)
    wrapped_points = polar_points + [(polar_points[0][0] + 2.0 * math.pi, polar_points[0][1])]
    if alpha < polar_points[0][0]:
        alpha += 2.0 * math.pi

    capacity_radius: float | None = None
    for (angle_1, radius_1), (angle_2, radius_2) in zip(wrapped_points[:-1], wrapped_points[1:]):
        if angle_1 <= alpha <= angle_2:
            if abs(angle_2 - angle_1) <= 1.0e-12:
                capacity_radius = max(radius_1, radius_2)
            else:
                ratio = (alpha - angle_1) / (angle_2 - angle_1)
                capacity_radius = radius_1 + ratio * (radius_2 - radius_1)
            break

    if capacity_radius is None or capacity_radius <= 0.0:
        return {
            "capacity_phiMn_kNm": None,
            "demand_Mu_kNm": demand_Mu_kNm,
            "dcr": None,
            "alpha_rad": alpha_rad,
            "method": "interpolated_slice",
            "status": "OUT_OF_RANGE",
            "warnings": warnings + ["Could not bracket demand angle on PMM slice."],
        }

    return {
        "capacity_phiMn_kNm": capacity_radius,
        "demand_Mu_kNm": demand_Mu_kNm,
        "dcr": demand_Mu_kNm / capacity_radius,
        "alpha_rad": alpha_rad,
        "method": "interpolated_slice",
        "status": "PASS",
        "warnings": warnings,
    }


def demand_capacity_result_to_display_dataframe(summary: DemandCapacitySummary) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Combo": result.combo_name,
                "Pu_kN": N_to_kN(result.Pu_N),
                "Mux_kNm": Nmm_to_kNm(result.Mux_Nmm),
                "Muy_kNm": Nmm_to_kNm(result.Muy_Nmm),
                "Mu_kNm": Nmm_to_kNm(result.Mu_Nmm),
                "Capacity_phiMn_kNm": None if result.capacity_phiMn_Nmm is None else Nmm_to_kNm(result.capacity_phiMn_Nmm),
                "D/C": result.dcr,
                "Status": result.status,
                "Capacity Method": result.capacity_method,
                "Slice Method": result.slice_method,
                "Envelope Method": result.envelope_method,
                "Used Fallback": result.used_fallback,
                "Warning Count": result.warning_count,
                "Message": result.message,
            }
            for result in summary.results
        ]
    )


def rank_load_cases_by_dcr(summary: DemandCapacitySummary) -> pd.DataFrame:
    df = demand_capacity_result_to_display_dataframe(summary)
    if df.empty:
        return df
    status_rank = {"FAIL": 0, "OUT_OF_RANGE": 1, "NOT_CHECKED": 2, "PASS": 3}
    ranked = df.copy()
    ranked["_status_rank"] = ranked["Status"].map(lambda value: status_rank.get(value, 4))
    ranked["_dcr_rank"] = ranked["D/C"].fillna(-1.0)
    ranked = ranked.sort_values(["_status_rank", "_dcr_rank"], ascending=[True, False])
    return ranked.drop(columns=["_status_rank", "_dcr_rank"]).reset_index(drop=True)


def _dc_lookup(dc_summary: DemandCapacitySummary | None) -> dict[str, tuple[str, float | None, float | None, str]]:
    if dc_summary is None:
        return {}
    return {
        item.combo_name: (item.status, item.dcr, item.capacity_phiMn_Nmm, item.message)
        for item in dc_summary.results
    }


def _status_for(combo_name: str, dc_summary: DemandCapacitySummary | None) -> str:
    return _dc_lookup(dc_summary).get(combo_name, ("NOT_CHECKED", None, None, ""))[0]


def _dcr_for(combo_name: str, dc_summary: DemandCapacitySummary | None) -> float | None:
    return _dc_lookup(dc_summary).get(combo_name, ("NOT_CHECKED", None, None, ""))[1]


def _capacity_for(combo_name: str, dc_summary: DemandCapacitySummary | None) -> float | None:
    capacity_nmm = _dc_lookup(dc_summary).get(combo_name, ("NOT_CHECKED", None, None, ""))[2]
    return None if capacity_nmm is None else Nmm_to_kNm(capacity_nmm)


def _message_for(combo_name: str, dc_summary: DemandCapacitySummary | None) -> str:
    return _dc_lookup(dc_summary).get(combo_name, ("NOT_CHECKED", None, None, ""))[3]


def _dc_result_for(combo_name: str, dc_summary: DemandCapacitySummary | None):
    if dc_summary is None:
        return None
    for result in dc_summary.results:
        if result.combo_name == combo_name:
            return result
    return None


def _resolve_numeric_column(pmm_df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for column in candidates:
        if column in pmm_df.columns and pd.to_numeric(pmm_df[column], errors="coerce").notna().any():
            return column
    return None


def pmm_surface_data_adapter(pmm_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Resolve stored PMM result data into canonical columns for 3D plotting."""

    diagnostics: dict[str, Any] = {
        "surface_generated": False,
        "surface_trace_type": "None",
        "valid_point_count": 0,
        "p_column": None,
        "mx_column": None,
        "my_column": None,
        "fallback_reason": "",
        "available_columns": list(pmm_df.columns),
    }
    p_column = _resolve_numeric_column(pmm_df, PMM_P_COLUMN_CANDIDATES)
    mx_column = _resolve_numeric_column(pmm_df, PMM_MX_COLUMN_CANDIDATES)
    my_column = _resolve_numeric_column(pmm_df, PMM_MY_COLUMN_CANDIDATES)
    diagnostics.update({"p_column": p_column, "mx_column": mx_column, "my_column": my_column})
    if p_column is None or mx_column is None or my_column is None:
        diagnostics["fallback_reason"] = "Could not resolve numeric P, Mx, and My columns from stored PMM data."
        return pd.DataFrame(columns=["phiPn_kN", "phiMnx_kNm", "phiMny_kNm"]), diagnostics

    adapted = pd.DataFrame(
        {
            "phiPn_kN": pd.to_numeric(pmm_df[p_column], errors="coerce"),
            "phiMnx_kNm": pd.to_numeric(pmm_df[mx_column], errors="coerce"),
            "phiMny_kNm": pd.to_numeric(pmm_df[my_column], errors="coerce"),
        }
    )
    for optional_column in ("theta_rad", "c_mm", "phi", "strain_condition"):
        if optional_column in pmm_df.columns:
            adapted[optional_column] = pmm_df[optional_column]
    adapted = adapted.dropna(subset=["phiPn_kN", "phiMnx_kNm", "phiMny_kNm"]).copy()
    diagnostics["valid_point_count"] = int(len(adapted))
    if adapted.empty:
        diagnostics["fallback_reason"] = "No valid numeric P/Mx/My PMM points were available after column resolution."
    return adapted, diagnostics


def _pmm_surface_grid(pmm_df: pd.DataFrame) -> tuple[list[list[float]], list[list[float]], list[list[float]]] | None:
    """Build a Plotly surface grid from stored PMM result points.

    The grid is only a visualization layer. It uses the existing theta/c rows
    from the stored PMM dataframe and does not trigger any capacity calculation.
    """

    required = {"theta_rad", "c_mm", "phiMnx_kNm", "phiMny_kNm"}
    if not required.issubset(pmm_df.columns):
        return None
    p_column = "phiPn_kN"
    surface_df = pmm_df[["theta_rad", "c_mm", "phiMnx_kNm", "phiMny_kNm", p_column]].dropna().copy()
    if surface_df.empty or surface_df["theta_rad"].nunique() < 3 or surface_df["c_mm"].nunique() < 2:
        return None

    surface_df = (
        surface_df.groupby(["theta_rad", "c_mm"], as_index=False)[["phiMnx_kNm", "phiMny_kNm", p_column]]
        .mean()
        .sort_values(["theta_rad", "c_mm"])
    )
    x_grid = surface_df.pivot(index="theta_rad", columns="c_mm", values="phiMnx_kNm").sort_index().sort_index(axis=1)
    y_grid = surface_df.pivot(index="theta_rad", columns="c_mm", values="phiMny_kNm").sort_index().sort_index(axis=1)
    z_grid = surface_df.pivot(index="theta_rad", columns="c_mm", values=p_column).sort_index().sort_index(axis=1)
    if x_grid.shape[0] < 3 or x_grid.shape[1] < 2:
        return None

    x_values = x_grid.to_numpy().tolist()
    y_values = y_grid.to_numpy().tolist()
    z_values = z_grid.to_numpy().tolist()
    theta_values = list(x_grid.index)
    if theta_values and abs((float(theta_values[-1]) - float(theta_values[0])) % (2.0 * math.pi)) > 1.0e-6:
        x_values.append(x_values[0])
        y_values.append(y_values[0])
        z_values.append(z_values[0])
    return x_values, y_values, z_values


def _add_pmm_surface_trace(fig: go.Figure, surface_df: pd.DataFrame, diagnostics: dict[str, Any]) -> None:
    """Add a visible PMM capacity body trace from stored PMM points.

    A light grid Surface is kept when theta/c data are available because it is
    useful for report/tests, but a Mesh3d capacity body is added as the primary
    visible object.  This avoids the real-app symptom where a Surface trace can
    render too faintly or not communicate a body, leaving only the Pu slice line.
    This function is visualization-only and never recomputes capacity.
    """
    if surface_df.empty:
        diagnostics.setdefault("fallback_reason", "No valid PMM points were available for surface generation.")
        diagnostics["surface_generated"] = False
        diagnostics["surface_trace_type"] = "None"
        return

    surface_grid = _pmm_surface_grid(surface_df)
    if surface_grid is not None:
        x_grid, y_grid, z_grid = surface_grid
        fig.add_trace(
            go.Surface(
                x=x_grid,
                y=y_grid,
                z=z_grid,
                opacity=0.20,
                colorscale=[[0.0, "#cbd7e6"], [0.5, "#7f9bbf"], [1.0, "#426799"]],
                showscale=False,
                name="PMM surface grid",
                showlegend=False,
                hovertemplate=(
                    "phiMnx=%{x:.2f} kN-m<br>phiMny=%{y:.2f} kN-m"
                    "<br>phiPn=%{z:.2f} kN<extra>PMM surface</extra>"
                ),
            )
        )

    mesh_df = surface_df[["phiMnx_kNm", "phiMny_kNm", "phiPn_kN"]].dropna().copy()
    diagnostics["valid_point_count"] = int(len(mesh_df))
    if len(mesh_df) >= 8:
        fig.add_trace(
            go.Mesh3d(
                x=mesh_df["phiMnx_kNm"],
                y=mesh_df["phiMny_kNm"],
                z=mesh_df["phiPn_kN"],
                alphahull=0,
                opacity=0.42,
                color="#6f8fb6",
                flatshading=False,
                lighting=dict(ambient=0.55, diffuse=0.75, specular=0.18, roughness=0.72, fresnel=0.05),
                lightposition=dict(x=100, y=200, z=400),
                name="PMM surface",
                showlegend=True,
                hovertemplate=(
                    "phiMnx=%{x:.2f} kN-m<br>phiMny=%{y:.2f} kN-m"
                    "<br>phiPn=%{z:.2f} kN<extra>PMM surface</extra>"
                ),
            )
        )
        diagnostics["surface_generated"] = True
        diagnostics["surface_trace_type"] = "Surface+Mesh3d" if surface_grid is not None else "Mesh3d"
        diagnostics["fallback_reason"] = "Mesh3d capacity body generated from stored PMM capacity points."
        return

    if surface_grid is not None:
        diagnostics["surface_generated"] = True
        diagnostics["surface_trace_type"] = "Surface"
        diagnostics["fallback_reason"] = "Surface generated from theta/c grid; insufficient points for Mesh3d body."
        return

    diagnostics["surface_generated"] = False
    diagnostics["surface_trace_type"] = "None"
    diagnostics["fallback_reason"] = (
        f"Only {len(mesh_df)} valid PMM points were available; at least 8 are required for Mesh3d."
    )

def _closed_pu_slice_dataframe(slice_df: pd.DataFrame) -> pd.DataFrame:
    if slice_df.empty:
        return slice_df
    ordered = _sort_slice_by_angle(slice_df)
    if len(ordered) > 2:
        return pd.concat([ordered, ordered.iloc[[0]]], ignore_index=True)
    return ordered


def _demand_hover_text(row: pd.Series, dc_summary: DemandCapacitySummary | None) -> str:
    combo_name = str(row["Combo Name"])
    status = _status_for(combo_name, dc_summary)
    dcr = _dcr_for(combo_name, dc_summary)
    dcr_label = "N/A" if dcr is None else f"{dcr:.3f}"
    return (
        f"{combo_name}<br>Status={status}<br>D/C={dcr_label}<br>"
        f"Pu={row['Pu_kN']:.2f} kN<br>Mux={row['Mux_kNm']:.2f} kN-m<br>Muy={row['Muy_kNm']:.2f} kN-m"
    )


def pmm_slice_export_dataframe(slice_df: pd.DataFrame) -> pd.DataFrame:
    """Return selected PMM slice data with stable review/export columns."""

    export = slice_df.copy()
    if export.empty:
        return export
    if "angle_rad" not in export.columns or "radius_kNm" not in export.columns:
        export["angle_rad"] = export.apply(lambda row: math.atan2(float(row["phiMny_kNm"]), float(row["phiMnx_kNm"])), axis=1)
        export["radius_kNm"] = export.apply(lambda row: math.hypot(float(row["phiMnx_kNm"]), float(row["phiMny_kNm"])), axis=1)
    export["slice_method"] = slice_df.attrs.get("method", "unknown")
    preferred = [
        "phiPn_kN",
        "phiMnx_kNm",
        "phiMny_kNm",
        "angle_rad",
        "radius_kNm",
        "theta_rad",
        "c_mm",
        "slice_method",
    ]
    return export[[column for column in preferred if column in export.columns]]


def slice_envelope_export_dataframe(envelope: SliceEnvelopeResult) -> pd.DataFrame:
    """Return selected slice envelope data with stable review/export columns."""

    export = envelope.envelope_df.copy()
    if export.empty:
        return export
    if "angle_rad" not in export.columns or "radius_kNm" not in export.columns:
        export["angle_rad"] = export.apply(lambda row: math.atan2(float(row["phiMny_kNm"]), float(row["phiMnx_kNm"])), axis=1)
        export["radius_kNm"] = export.apply(lambda row: math.hypot(float(row["phiMnx_kNm"]), float(row["phiMny_kNm"])), axis=1)
    export["envelope_method"] = envelope.method
    export["envelope_valid"] = envelope.is_valid
    export["used_convex_hull"] = envelope.used_convex_hull
    preferred = [
        "phiPn_kN",
        "phiMnx_kNm",
        "phiMny_kNm",
        "angle_rad",
        "radius_kNm",
        "theta_rad",
        "c_mm",
        "source_method",
        "envelope_method",
        "envelope_valid",
        "used_convex_hull",
    ]
    return export[[column for column in preferred if column in export.columns]]


def make_mux_muy_slice_figure(
    pmm_df: pd.DataFrame,
    selected_load_case: LoadCase,
    dc_summary: DemandCapacitySummary | None = None,
) -> go.Figure:
    Pu_kN = N_to_kN(selected_load_case.Pu_N)
    demand_x = Nmm_to_kNm(selected_load_case.Mux_Nmm)
    demand_y = Nmm_to_kNm(selected_load_case.Muy_Nmm)
    slice_df = pmm_slice_at_pu(pmm_df, Pu_kN)
    envelope = build_slice_envelope(slice_df)
    method_label = "Interpolated Slice" if slice_df.attrs.get("method") == "interpolated" else "Tolerance Fallback"
    if envelope.used_convex_hull:
        method_label += " / Convex Hull Envelope"
    status = _status_for(selected_load_case.name, dc_summary)
    dcr = _dcr_for(selected_load_case.name, dc_summary)
    color = STATUS_COLORS.get(status, STATUS_COLORS["NOT_CHECKED"])

    fig = go.Figure()
    if not slice_df.empty:
        fig.add_trace(
            go.Scatter(
                x=slice_df["phiMnx_kNm"],
                y=slice_df["phiMny_kNm"],
                mode="markers",
                marker=dict(size=5, color="#60a5fa", opacity=0.35),
                name="Raw Pu slice points",
                hovertemplate="phiMnx=%{x:.2f} kN-m<br>phiMny=%{y:.2f} kN-m<extra></extra>",
            )
        )
    if not envelope.envelope_df.empty:
        envelope_df = envelope.envelope_df
        closed = pd.concat([envelope_df, envelope_df.iloc[[0]]], ignore_index=True) if len(envelope_df) > 2 else envelope_df
        fig.add_trace(
            go.Scatter(
                x=closed["phiMnx_kNm"],
                y=closed["phiMny_kNm"],
                mode="lines+markers",
                marker=dict(size=5, color="#1d4ed8", opacity=0.9),
                line=dict(color="#1d4ed8", width=2),
                name="PMM slice envelope",
                hovertemplate="phiMnx=%{x:.2f} kN-m<br>phiMny=%{y:.2f} kN-m<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=[0.0, demand_x],
            y=[0.0, demand_y],
            mode="lines",
            line=dict(color=color, width=3),
            name="Demand vector",
            hoverinfo="skip",
        )
    )
    dcr_label = "N/A" if dcr is None else f"{dcr:.3f}"
    fig.add_trace(
        go.Scatter(
            x=[demand_x],
            y=[demand_y],
            mode="markers+text",
            marker=dict(size=14, color=color, symbol="diamond", line=dict(width=2, color="#111827")),
            text=[selected_load_case.name],
            textposition="top center",
            name="Selected demand",
            hovertemplate=(
                f"{selected_load_case.name}<br>Mux=%{{x:.2f}} kN-m<br>Muy=%{{y:.2f}} kN-m"
                f"<br>Pu={Pu_kN:.2f} kN<br>D/C={dcr_label}<br>Status={status}<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=0.0, line=dict(color="#6b7280", width=1, dash="dot"))
    fig.add_vline(x=0.0, line=dict(color="#6b7280", width=1, dash="dot"))
    fig.add_annotation(
        x=demand_x,
        y=demand_y,
        text=f"{selected_load_case.name}<br>D/C {dcr_label}<br>{status}",
        showarrow=True,
        arrowhead=2,
        ax=30,
        ay=-35,
        bgcolor="rgba(255,255,255,0.85)",
        bordercolor=color,
    )
    fig.update_layout(
        title=f"PMM Mux-Muy Slice at Pu = {Pu_kN:,.1f} kN ({method_label})",
        xaxis_title="phiMnx capacity / Mux demand (kN-m)",
        yaxis_title="phiMny capacity / Muy demand (kN-m)",
        legend=dict(orientation="h"),
    )
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


def make_pmm_3d_dashboard_figure(
    pmm_df: pd.DataFrame,
    demand_df: pd.DataFrame,
    selected_load_case: LoadCase | None = None,
    dc_summary: DemandCapacitySummary | None = None,
    *,
    show_surface: bool = True,
    show_current_pu_slice: bool = True,
    show_raw_points: bool = False,
    show_selected_load_point: bool = True,
    show_all_uls_load_points: bool = False,
) -> go.Figure:
    fig = go.Figure()
    surface_df, surface_diagnostics = pmm_surface_data_adapter(pmm_df)
    if show_surface:
        _add_pmm_surface_trace(fig, surface_df, surface_diagnostics)
    else:
        surface_diagnostics["fallback_reason"] = "Surface display option is disabled."

    if show_raw_points and not surface_df.empty:
        hover = [
            f"P={row.phiPn_kN:.2f} kN<br>Mx={row.phiMnx_kNm:.2f} kN-m<br>My={row.phiMny_kNm:.2f} kN-m"
            f"<br>phi={getattr(row, 'phi', float('nan')):.3f}<br>{getattr(row, 'strain_condition', '')}"
            for row in surface_df.itertuples()
        ]
        fig.add_trace(
            go.Scatter3d(
                x=surface_df["phiMnx_kNm"],
                y=surface_df["phiMny_kNm"],
                z=surface_df["phiPn_kN"],
                mode="markers",
                marker=dict(size=2.5, color="#475467", opacity=0.34),
                text=hover,
                hoverinfo="text",
                name="PMM raw points",
            )
    )

    if show_current_pu_slice and selected_load_case is not None:
        slice_df = pmm_slice_at_pu(surface_df, N_to_kN(selected_load_case.Pu_N)) if not surface_df.empty else surface_df
        if not slice_df.empty:
            slice_line_df = _closed_pu_slice_dataframe(slice_df)
            fig.add_trace(
                go.Scatter3d(
                    x=slice_line_df["phiMnx_kNm"],
                    y=slice_line_df["phiMny_kNm"],
                    z=slice_line_df["phiPn_kN"],
                    mode="lines",
                    line=dict(color="#d97706", width=5),
                    name="Current Pu slice",
                    hovertemplate=(
                        "phiMnx=%{x:.2f} kN-m<br>phiMny=%{y:.2f} kN-m"
                        "<br>phiPn=%{z:.2f} kN<extra>Current Pu slice</extra>"
                    ),
                )
            )

    if show_all_uls_load_points and not demand_df.empty:
        visible_demand_df = demand_df
        if selected_load_case is not None and "Combo Name" in demand_df:
            visible_demand_df = demand_df[demand_df["Combo Name"] != selected_load_case.name]
        if not visible_demand_df.empty:
            colors = [
                STATUS_COLORS.get(_status_for(str(row["Combo Name"]), dc_summary), STATUS_COLORS["NOT_CHECKED"])
                for _, row in visible_demand_df.iterrows()
            ]
            hover = [_demand_hover_text(row, dc_summary) for _, row in visible_demand_df.iterrows()]
            fig.add_trace(
                go.Scatter3d(
                    x=visible_demand_df["Mux_kNm"],
                    y=visible_demand_df["Muy_kNm"],
                    z=visible_demand_df["Pu_kN"],
                    mode="markers",
                    marker=dict(size=4, color=colors, symbol="circle", opacity=0.62, line=dict(width=0.8, color="#344054")),
                    text=hover,
                    hoverinfo="text",
                    name="All ULS load points",
                )
            )

    if show_selected_load_point and selected_load_case is not None:
        status = _status_for(selected_load_case.name, dc_summary)
        dcr = _dcr_for(selected_load_case.name, dc_summary)
        dc_result = _dc_result_for(selected_load_case.name, dc_summary)
        color = STATUS_COLORS.get(status, STATUS_COLORS["NOT_CHECKED"])
        dcr_label = "N/A" if dcr is None else f"{dcr:.3f}"
        capacity_method = "N/A" if dc_result is None or dc_result.capacity_method is None else dc_result.capacity_method
        slice_method = "N/A" if dc_result is None or dc_result.slice_method is None else dc_result.slice_method
        selected_hover = (
            f"{selected_load_case.name}<br>Status={status}<br>D/C={dcr_label}<br>"
            f"Pu={N_to_kN(selected_load_case.Pu_N):.2f} kN<br>"
            f"Mux={Nmm_to_kNm(selected_load_case.Mux_Nmm):.2f} kN-m<br>"
            f"Muy={Nmm_to_kNm(selected_load_case.Muy_Nmm):.2f} kN-m<br>"
            f"Capacity method={capacity_method}<br>Slice method={slice_method}"
        )
        fig.add_trace(
            go.Scatter3d(
                x=[Nmm_to_kNm(selected_load_case.Mux_Nmm)],
                y=[Nmm_to_kNm(selected_load_case.Muy_Nmm)],
                z=[N_to_kN(selected_load_case.Pu_N)],
                mode="markers+text",
                marker=dict(size=7, color=color, symbol="circle", line=dict(width=2, color="#111827")),
                text=[selected_load_case.name],
                textposition="top center",
                hovertext=[selected_hover],
                hoverinfo="text",
                name="Selected load point",
            )
        )

    fig.update_layout(
        title="3D PMM Interaction View",
        scene=dict(
            xaxis_title="Mux / phiMnx (kN-m)",
            yaxis_title="Muy / phiMny (kN-m)",
            zaxis_title="P / phiPn (kN)",
        ),
        legend=dict(orientation="h"),
        margin=dict(l=0, r=0, t=45, b=0),
        meta={"pmm_surface_diagnostics": surface_diagnostics},
    )
    return fig


def build_selected_load_case_summary(
    selected_load_case: LoadCase,
    dc_summary: DemandCapacitySummary | None,
    mode_label: str,
    include_prestress: bool,
    envelope: SliceEnvelopeResult | None = None,
) -> dict[str, Any]:
    status = _status_for(selected_load_case.name, dc_summary)
    dcr = _dcr_for(selected_load_case.name, dc_summary)
    message = _message_for(selected_load_case.name, dc_summary)
    dc_result = _dc_result_for(selected_load_case.name, dc_summary)
    dcr_method = "N/A" if dc_result is None or dc_result.capacity_method is None else dc_result.capacity_method
    slice_method = "N/A" if dc_result is None or dc_result.slice_method is None else dc_result.slice_method
    return {
        "selected_combo": selected_load_case.name,
        "status": status,
        "dcr": dcr,
        "Pu_kN": N_to_kN(selected_load_case.Pu_N),
        "Mux_kNm": Nmm_to_kNm(selected_load_case.Mux_Nmm),
        "Muy_kNm": Nmm_to_kNm(selected_load_case.Muy_Nmm),
        "Mu_kNm": Nmm_to_kNm(math.hypot(selected_load_case.Mux_Nmm, selected_load_case.Muy_Nmm)),
        "capacity_phiMn_kNm": _capacity_for(selected_load_case.name, dc_summary),
        "analysis_mode": mode_label,
        "prestress_included": include_prestress,
        "slice_method": slice_method,
        "dcr_method": dcr_method,
        "envelope_method": "N/A" if envelope is None else envelope.method,
        "envelope_valid": None if envelope is None else envelope.is_valid,
        "convex_hull_fallback": None if envelope is None else envelope.used_convex_hull,
        "boundary_warning_count": 0 if envelope is None else len(envelope.warnings),
        "used_fallback": False if dc_result is None else dc_result.used_fallback,
        "capacity_method": dcr_method,
        "message": message,
    }
