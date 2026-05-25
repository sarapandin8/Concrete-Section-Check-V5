"""Standard engineering terminology for future report generation."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class EngineeringTerm:
    key: str
    label: str
    description: str
    unit: str | None = None
    category: str = "General"


def get_standard_terminology() -> dict[str, EngineeringTerm]:
    """Return a stable glossary for UI tables and future reports."""

    terms = [
        EngineeringTerm("Pu", "Pu", "Factored axial demand, compression positive.", "kN", "Demand / ULS"),
        EngineeringTerm("Mux", "Mux", "Factored moment demand about the x-axis.", "kN-m", "Demand / ULS"),
        EngineeringTerm("Muy", "Muy", "Factored moment demand about the y-axis.", "kN-m", "Demand / ULS"),
        EngineeringTerm("Mu", "Mu", "Resultant factored moment demand.", "kN-m", "Demand / ULS"),
        EngineeringTerm("Pn", "Pn", "Nominal axial resistance from PMM analysis.", "kN", "Capacity / PMM"),
        EngineeringTerm("Mnx", "Mnx", "Nominal moment resistance about the x-axis.", "kN-m", "Capacity / PMM"),
        EngineeringTerm("Mny", "Mny", "Nominal moment resistance about the y-axis.", "kN-m", "Capacity / PMM"),
        EngineeringTerm("phiPn", "phiPn", "Strength-reduced axial resistance.", "kN", "Capacity / PMM"),
        EngineeringTerm("phiMnx", "phiMnx", "Strength-reduced moment resistance about the x-axis.", "kN-m", "Capacity / PMM"),
        EngineeringTerm("phiMny", "phiMny", "Strength-reduced moment resistance about the y-axis.", "kN-m", "Capacity / PMM"),
        EngineeringTerm("D/C Ratio", "D/C Ratio", "Demand divided by available capacity.", None, "Capacity / PMM"),
        EngineeringTerm("External Stress", "External Stress", "Elastic SLS stress from applied service load effects.", "MPa", "SLS"),
        EngineeringTerm("Prestress Stress", "Prestress Stress", "Elastic SLS stress contribution from effective bonded prestress.", "MPa", "SLS"),
        EngineeringTerm("Total Stress", "Total Stress", "Combined SLS stress used for serviceability judgement.", "MPa", "SLS"),
        EngineeringTerm("Compression Negative", "Compression Negative", "SLS display convention: compression stress is negative.", "MPa", "SLS"),
        EngineeringTerm("Tension Positive", "Tension Positive", "SLS display convention: tension stress is positive.", "MPa", "SLS"),
        EngineeringTerm("Gross Section", "Gross Section", "Gross concrete section basis for elastic SLS stress.", None, "SLS"),
        EngineeringTerm(
            "Transformed Uncracked Section",
            "Transformed Uncracked Section",
            "Uncracked transformed section basis using modular ratios.",
            None,
            "SLS",
        ),
        EngineeringTerm("No-Tension", "No-Tension", "Serviceability requirement that checked concrete stress remains non-tensile.", None, "SLS"),
        EngineeringTerm("Decompression", "Decompression", "Prototype no-tension-style decompression check at selected stress points.", None, "SLS"),
        EngineeringTerm("Cracking Classification", "Cracking Classification", "Tension-zone classification from existing SLS stress results.", None, "SLS"),
        EngineeringTerm("Pe_eff", "Pe_eff", "Effective prestressing force stored on prestress elements.", "kN", "Prestress"),
        EngineeringTerm("Bonded Prestress", "Bonded Prestress", "Prestress element included by current bonded prototype workflows.", None, "Prestress"),
        EngineeringTerm("Unbonded Prestress", "Unbonded Prestress", "Prestress element type ignored by current solver and SLS checks.", None, "Prestress"),
        EngineeringTerm("PT Bar", "PT Bar", "Prestressing bar / post-tensioning bar element type.", None, "Prestress"),
        EngineeringTerm("Prestress Action", "Prestress Action", "Internal prestress/reinforcement action, not an external Pu demand.", None, "Prestress"),
        EngineeringTerm("Not External Pu", "Not External Pu", "Reminder not to double-count prestress by entering Pe as Pu.", None, "Prestress"),
        EngineeringTerm("Column/Pier PMM Mode", "Column/Pier PMM Mode", "Current PMM workflow using Pu, Mux, and Muy.", None, "Analysis Mode"),
        EngineeringTerm("Beam/Girder Future Mode", "Beam/Girder Future Mode", "Placeholder for future beam/girder checks.", None, "Analysis Mode"),
        EngineeringTerm("General Section Mode", "General Section Mode", "General section review workflow with PMM and SLS tools available.", None, "Analysis Mode"),
    ]
    return {term.key: term for term in terms}


def terminology_to_dataframe() -> pd.DataFrame:
    """Return standard terminology as a dataframe for UI/CSV export."""

    return pd.DataFrame(
        [
            {
                "Key": term.key,
                "Label": term.label,
                "Description": term.description,
                "Unit": term.unit or "",
                "Category": term.category,
            }
            for term in get_standard_terminology().values()
        ],
        columns=["Key", "Label", "Description", "Unit", "Category"],
    )
