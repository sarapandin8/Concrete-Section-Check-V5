"""Unit convention registry for report-readiness review."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class UnitConvention:
    quantity: str
    internal_unit: str
    display_unit: str
    report_unit: str
    conversion_note: str


def get_unit_conventions() -> list[UnitConvention]:
    return [
        UnitConvention("Force", "N", "kN", "kN", "Divide internal N values by 1,000 for display/report."),
        UnitConvention("Moment", "N-mm", "kN-m", "kN-m", "Divide internal N-mm values by 1,000,000."),
        UnitConvention("Stress", "MPa", "MPa", "MPa", "MPa is N/mm2."),
        UnitConvention("Length", "mm", "mm", "mm", "Geometry and coordinates use mm."),
        UnitConvention("Area", "mm2", "mm2", "mm2", "Concrete and steel areas use mm2."),
        UnitConvention("Inertia", "mm4", "mm4", "mm4", "Section inertias use mm4."),
        UnitConvention("Strain", "dimensionless", "dimensionless", "dimensionless", "Concrete and steel strains are unitless."),
        UnitConvention("Angle", "rad", "rad / deg", "deg optional", "Radians internally; degrees may be shown in reports."),
        UnitConvention("Reinforcement area", "mm2", "mm2", "mm2", "Ordinary and prestress steel areas use mm2."),
        UnitConvention("Prestress force", "N", "kN", "kN", "Effective prestress is stored in N and displayed in kN."),
    ]


def unit_conventions_to_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Quantity": item.quantity,
                "Internal Unit": item.internal_unit,
                "Display Unit": item.display_unit,
                "Report Unit": item.report_unit,
                "Conversion Note": item.conversion_note,
            }
            for item in get_unit_conventions()
        ],
        columns=["Quantity", "Internal Unit", "Display Unit", "Report Unit", "Conversion Note"],
    )
