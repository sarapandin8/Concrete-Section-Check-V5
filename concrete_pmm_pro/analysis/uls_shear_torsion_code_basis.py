"""Code-basis audit metadata for Beam/Girder ULS shear and torsion.

This module is deliberately not a calculation engine.  It is a QA gate used by
Analysis/UI tests so future shear, torsion, and V+T milestones do not silently
promote first-pass formulas to final code-certified checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Route = Literal["ACI_RC", "ACI_PSC", "AASHTO_RC", "AASHTO_PSC"]
AuditStatus = Literal["OK", "PARTIAL", "MISSING", "DO_NOT_USE"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@dataclass(frozen=True)
class ShearTorsionFormulaAuditItem:
    route: Route
    check_item: str
    code_edition: str
    code_location: str
    implementation_status: AuditStatus
    risk_level: RiskLevel
    current_app_status: str
    required_action: str


ACI_318_19_CHAPTER_BASIS = {
    "strength_reduction_factors": "ACI 318-19 Chapter 21",
    "sectional_strength": "ACI 318-19 Chapter 22",
    "one_way_shear": "ACI 318-19 Section 22.5",
    "torsional_strength": "ACI 318-19 Section 22.7",
}

AASHTO_LRFD_9_BASIS = {
    "edition": "AASHTO LRFD Bridge Design Specifications, 9th Edition, 2020",
    "route_owner": "Bridge Beam/Girder workflow",
    "implementation_gate": "Use project-specified 9th Edition + errata; do not mix 10th Edition concrete revisions unless the project code basis changes.",
}

# Unit-sensitive coefficients used as QA guards for the current SI/mm/MPa app.
# The app stores concrete strength in MPa and dimensions in mm, so US customary
# coefficients such as 2*sqrt(fc) are not allowed in metric formulas.
ACI_METRIC_SIMPLIFIED_ONE_WAY_VC_FACTOR = 0.17
ACI_US_SIMPLIFIED_ONE_WAY_VC_FACTOR = 2.0

FORMULA_AUDIT_ITEMS: tuple[ShearTorsionFormulaAuditItem, ...] = (
    ShearTorsionFormulaAuditItem(
        route="ACI_RC",
        check_item="One-way shear concrete contribution Vc",
        code_edition="ACI 318-19",
        code_location="Chapter 22 sectional strength; Section 22.5 one-way shear",
        implementation_status="PARTIAL",
        risk_level="MEDIUM",
        current_app_status="Uses SI coefficient 0.17 for simplified Vc in the provided-stirrup shear check.",
        required_action="Add ACI 318-19 size-effect / reinforcement-condition route before calling the shear engine final.",
    ),
    ShearTorsionFormulaAuditItem(
        route="ACI_PSC",
        check_item="Prestressed one-way shear Vc / Vp",
        code_edition="ACI 318-19",
        code_location="Chapter 22; prestressed one-way shear provisions",
        implementation_status="MISSING",
        risk_level="HIGH",
        current_app_status="Current shear route does not compute detailed prestressed Vci/Vcw or Vp as a final ACI PSC route.",
        required_action="Implement Vci/Vcw/Vp input path and benchmark before certifying Building PSC shear.",
    ),
    ShearTorsionFormulaAuditItem(
        route="ACI_RC",
        check_item="Torsional transverse strength φTn",
        code_edition="ACI 318-19",
        code_location="Chapter 22; Section 22.7 torsional strength",
        implementation_status="PARTIAL",
        risk_level="HIGH",
        current_app_status="TORSION1 computes first-pass transverse closed-hoop φTn only; longitudinal torsion and V+T interaction are review items.",
        required_action="Add threshold, section sizing, longitudinal torsion steel, hoop detailing, and V+T checks before final PASS.",
    ),
    ShearTorsionFormulaAuditItem(
        route="ACI_PSC",
        check_item="Prestressed torsion",
        code_edition="ACI 318-19",
        code_location="Chapter 22 torsional strength with prestressed member applicability review",
        implementation_status="MISSING",
        risk_level="HIGH",
        current_app_status="No dedicated PSC torsion route or prestress contribution certification exists.",
        required_action="Create a PSC-specific torsion data owner and benchmark against validated examples.",
    ),
    ShearTorsionFormulaAuditItem(
        route="AASHTO_RC",
        check_item="MCFT shear β/θ and Vc/Vs",
        code_edition="AASHTO LRFD 9th Edition, 2020",
        code_location="Concrete shear/torsion articles for the selected section type",
        implementation_status="PARTIAL",
        risk_level="HIGH",
        current_app_status="Uses first-pass simplified sectional shear language and θ=45° placeholder; MCFT β/θ calibration is pending.",
        required_action="Implement section-type-specific AASHTO LRFD 9th + errata β/θ route and benchmark before final PASS.",
    ),
    ShearTorsionFormulaAuditItem(
        route="AASHTO_PSC",
        check_item="Prestressed bridge shear including dv, Vp, end region",
        code_edition="AASHTO LRFD 9th Edition, 2020",
        code_location="Concrete shear/torsion articles for prestressed girders",
        implementation_status="PARTIAL",
        risk_level="CRITICAL",
        current_app_status="Effective d/dv is visible and user-controllable, but prestress shear effects and end-region certification are not final.",
        required_action="Implement PSC-specific dv/strain/prestress/end-region checks and benchmark against bridge examples.",
    ),
    ShearTorsionFormulaAuditItem(
        route="AASHTO_RC",
        check_item="Torsional transverse strength φTn",
        code_edition="AASHTO LRFD 9th Edition, 2020",
        code_location="Concrete torsion / combined shear-torsion articles for section type",
        implementation_status="PARTIAL",
        risk_level="HIGH",
        current_app_status="TORSION1 computes first-pass closed-hoop φTn with θ=45°; detailed LRFD torsion calibration is pending.",
        required_action="Add θ consistency with shear, section-size/crushing, longitudinal steel, and V+T checks before final PASS.",
    ),
    ShearTorsionFormulaAuditItem(
        route="AASHTO_PSC",
        check_item="Prestressed bridge torsion and Combined V+T",
        code_edition="AASHTO LRFD 9th Edition, 2020",
        code_location="Concrete torsion / combined shear-torsion articles for prestressed girders",
        implementation_status="MISSING",
        risk_level="CRITICAL",
        current_app_status="Combined V+T is intentionally not implemented; separate shear and torsion checks must not be read as a combined PASS.",
        required_action="Implement code-specific combined V+T after shear and torsion formula routes pass benchmark tests.",
    ),
)


def audit_items_for_route(route: Route) -> tuple[ShearTorsionFormulaAuditItem, ...]:
    return tuple(item for item in FORMULA_AUDIT_ITEMS if item.route == route)


def aci_metric_vc_is_unit_safe(coefficient: float) -> bool:
    """Return True only for the SI/mm/MPa simplified ACI Vc coefficient.

    This guard prevents accidental reintroduction of the US customary 2.0
    coefficient into metric calculations.
    """

    return abs(float(coefficient) - ACI_METRIC_SIMPLIFIED_ONE_WAY_VC_FACTOR) <= 1.0e-12
