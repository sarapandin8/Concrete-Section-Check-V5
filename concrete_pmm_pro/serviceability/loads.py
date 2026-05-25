"""SLS load filtering and display helpers."""

from __future__ import annotations

import pandas as pd

from concrete_pmm_pro.core.models import LoadCase
from concrete_pmm_pro.core.units import N_to_kN, Nmm_to_kNm


def get_active_sls_load_cases(load_cases: list[LoadCase]) -> list[LoadCase]:
    """Return active SLS load cases only."""

    return [load_case for load_case in load_cases if load_case.active and load_case.load_type == "SLS"]


def sls_load_cases_to_display_dataframe(load_cases: list[LoadCase]) -> pd.DataFrame:
    """Return active SLS load cases in engineering display units."""

    return pd.DataFrame(
        [
            {
                "Combo Name": load_case.name,
                "Pu_kN": N_to_kN(load_case.Pu_N),
                "Mux_kNm": Nmm_to_kNm(load_case.Mux_Nmm),
                "Muy_kNm": Nmm_to_kNm(load_case.Muy_Nmm),
                "Active": load_case.active,
                "Note": load_case.note or "",
            }
            for load_case in get_active_sls_load_cases(load_cases)
        ]
    )
