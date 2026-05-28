"""Result models for PMM analysis prototypes."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from concrete_pmm_pro.core.models import LoadCase
from concrete_pmm_pro.core.units import N_to_kN, Nmm_to_kNm


class PMMPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    theta_rad: float
    c_mm: float
    Pn_N: float
    Mnx_Nmm: float
    Mny_Nmm: float
    phi: float
    phiPn_N: float
    phiPn_capped_N: float | None = None
    phiMnx_Nmm: float
    phiMny_Nmm: float
    eps_t: float | None
    strain_condition: str
    concrete_area_mm2: float
    concrete_force_N: float
    prestress_force_N: float = 0.0
    prestress_count: int = 0
    bonded_prestress_count: int = 0
    active_prestress_count: int = 0
    passive_prestress_count: int = 0
    unbonded_prestress_ignored_count: int = 0
    prestress_stress_model: str | None = None
    prestress_stress_warning_count: int = 0
    max_prestress_stress_MPa: float = 0.0
    prestress_reached_fpu_cap_count: int = 0
    prestress_compression_reversal_count: int = 0
    rebar_displaced_concrete_subtracted_N: float = 0.0
    rebar_inside_compression_count: int = 0


class PMMSolverResult(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    points: list[PMMPoint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    info: list[str] = Field(default_factory=list)

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([point.model_dump() for point in self.points])


def pmm_result_to_display_dataframe(result: PMMSolverResult) -> pd.DataFrame:
    """Return PMM result data with internal and engineering display units.

    Internal solver units remain N and N-mm. The added display columns use kN
    and kN-m for engineering review in the UI.
    """

    df = result.to_dataframe()
    if df.empty:
        for column in [
            "phiPn_capped_N",
            "Pn_kN",
            "Mnx_kNm",
            "Mny_kNm",
            "phiPn_kN",
            "phiPn_capped_kN",
            "phiMnx_kNm",
            "phiMny_kNm",
            "prestress_force_N",
            "prestress_force_kN",
            "prestress_count",
            "bonded_prestress_count",
            "active_prestress_count",
            "passive_prestress_count",
            "unbonded_prestress_ignored_count",
            "prestress_stress_model",
            "prestress_stress_warning_count",
            "max_prestress_stress_MPa",
            "prestress_reached_fpu_cap_count",
            "prestress_compression_reversal_count",
            "rebar_displaced_concrete_subtracted_N",
            "rebar_displaced_concrete_subtracted_kN",
            "rebar_inside_compression_count",
        ]:
            df[column] = []
        return df

    if "phiPn_capped_N" not in df.columns:
        df["phiPn_capped_N"] = df["phiPn_N"]
    df["phiPn_N"] = pd.to_numeric(df["phiPn_N"], errors="coerce").astype(float)
    df["phiPn_capped_N"] = pd.to_numeric(df["phiPn_capped_N"], errors="coerce")
    df["phiPn_capped_N"] = df["phiPn_capped_N"].where(df["phiPn_capped_N"].notna(), df["phiPn_N"]).astype(float)
    df["Pn_kN"] = df["Pn_N"].map(N_to_kN)
    df["Mnx_kNm"] = df["Mnx_Nmm"].map(Nmm_to_kNm)
    df["Mny_kNm"] = df["Mny_Nmm"].map(Nmm_to_kNm)
    df["phiPn_kN"] = df["phiPn_N"].map(N_to_kN)
    df["phiPn_capped_kN"] = df["phiPn_capped_N"].map(N_to_kN)
    df["phiMnx_kNm"] = df["phiMnx_Nmm"].map(Nmm_to_kNm)
    df["phiMny_kNm"] = df["phiMny_Nmm"].map(Nmm_to_kNm)
    if "prestress_force_N" not in df.columns:
        df["prestress_force_N"] = 0.0
    if "prestress_count" not in df.columns:
        df["prestress_count"] = 0
    if "bonded_prestress_count" not in df.columns:
        df["bonded_prestress_count"] = 0
    if "active_prestress_count" not in df.columns:
        df["active_prestress_count"] = df["bonded_prestress_count"]
    if "passive_prestress_count" not in df.columns:
        df["passive_prestress_count"] = 0
    if "unbonded_prestress_ignored_count" not in df.columns:
        df["unbonded_prestress_ignored_count"] = 0
    if "prestress_stress_model" not in df.columns:
        df["prestress_stress_model"] = None
    if "prestress_stress_warning_count" not in df.columns:
        df["prestress_stress_warning_count"] = 0
    if "max_prestress_stress_MPa" not in df.columns:
        df["max_prestress_stress_MPa"] = 0.0
    if "prestress_reached_fpu_cap_count" not in df.columns:
        df["prestress_reached_fpu_cap_count"] = 0
    if "prestress_compression_reversal_count" not in df.columns:
        df["prestress_compression_reversal_count"] = 0
    if "rebar_displaced_concrete_subtracted_N" not in df.columns:
        df["rebar_displaced_concrete_subtracted_N"] = 0.0
    if "rebar_inside_compression_count" not in df.columns:
        df["rebar_inside_compression_count"] = 0
    df["prestress_force_kN"] = df["prestress_force_N"].map(N_to_kN)
    df["rebar_displaced_concrete_subtracted_kN"] = df["rebar_displaced_concrete_subtracted_N"].map(N_to_kN)
    return df


def summarize_pmm_result(result: PMMSolverResult) -> dict[str, float | int | bool | None]:
    df = result.to_dataframe()
    if df.empty:
        return {
            "point_count": 0,
            "max_phiPn_N": None,
            "max_phiPn_capped_N": None,
            "min_phiPn_N": None,
            "max_abs_phiMnx_Nmm": None,
            "max_abs_phiMny_Nmm": None,
            "has_nan": False,
            "has_inf": False,
            "phi_min": None,
            "phi_max": None,
        }

    numeric_df = df.select_dtypes(include=["number"])
    required_numeric_df = numeric_df.drop(columns=["eps_t"], errors="ignore")
    numeric_array = required_numeric_df.to_numpy(dtype=float) if not required_numeric_df.empty else np.empty((0, 0), dtype=float)
    capped_series = pd.to_numeric(df["phiPn_capped_N"], errors="coerce")
    capped_series = capped_series.where(capped_series.notna(), pd.to_numeric(df["phiPn_N"], errors="coerce"))
    return {
        "point_count": int(len(df)),
        "max_phiPn_N": float(df["phiPn_N"].max()),
        "max_phiPn_capped_N": float(capped_series.max()),
        "min_phiPn_N": float(df["phiPn_N"].min()),
        "max_abs_phiMnx_Nmm": float(df["phiMnx_Nmm"].abs().max()),
        "max_abs_phiMny_Nmm": float(df["phiMny_Nmm"].abs().max()),
        "has_nan": bool(required_numeric_df.isna().any().any()),
        "has_inf": bool(np.isinf(numeric_array).any()) if numeric_array.size else False,
        "phi_min": float(df["phi"].min()),
        "phi_max": float(df["phi"].max()),
    }


def active_load_cases_to_display_dataframe(load_cases: Iterable[LoadCase], load_type: str = "ULS") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Combo Name": load_case.name,
                "Pu_kN": N_to_kN(load_case.Pu_N),
                "Mux_kNm": Nmm_to_kNm(load_case.Mux_Nmm),
                "Muy_kNm": Nmm_to_kNm(load_case.Muy_Nmm),
            }
            for load_case in load_cases
            if load_case.active and load_case.load_type == load_type
        ]
    )


def check_pmm_dataframe_numerics(df: pd.DataFrame) -> dict[str, object]:
    """Return lightweight numeric sanity information for PMM display data."""

    numeric_df = df.select_dtypes(include=["number"])
    nan_columns = [column for column in numeric_df.columns if numeric_df[column].isna().any()]
    inf_columns = []
    if not numeric_df.empty:
        for column in numeric_df.columns:
            values = pd.to_numeric(numeric_df[column], errors="coerce").to_numpy(dtype=float)
            if np.isinf(values).any():
                inf_columns.append(column)
    warnings: list[str] = []
    if nan_columns:
        warnings.append(f"NaN values detected in PMM dataframe columns: {', '.join(nan_columns)}.")
    if inf_columns:
        warnings.append(f"Inf values detected in PMM dataframe columns: {', '.join(inf_columns)}.")
    return {
        "row_count": int(len(df)),
        "has_nan": bool(nan_columns),
        "has_inf": bool(inf_columns),
        "nan_columns": nan_columns,
        "inf_columns": inf_columns,
        "max_abs_phiPn_kN": None if "phiPn_kN" not in df else float(df["phiPn_kN"].abs().max()),
        "max_abs_phiMnx_kNm": None if "phiMnx_kNm" not in df else float(df["phiMnx_kNm"].abs().max()),
        "max_abs_phiMny_kNm": None if "phiMny_kNm" not in df else float(df["phiMny_kNm"].abs().max()),
        "warnings": warnings,
    }
