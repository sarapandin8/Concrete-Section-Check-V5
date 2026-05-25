"""Effective prestress contribution for gross-section SLS stress checks."""

from __future__ import annotations

import math

import pandas as pd

from concrete_pmm_pro.core.models import PrestressElement
from concrete_pmm_pro.core.units import N_to_kN, Nmm_to_kNm
from concrete_pmm_pro.serviceability.models import GrossSectionProperties, PrestressServiceContribution


def _effective_pe_from_element(element: PrestressElement) -> tuple[float, str | None]:
    if element.pe_eff_n > 0:
        return element.pe_eff_n * element.count, "pe_eff_n"
    if element.initial_stress_mpa is not None and element.initial_stress_mpa > 0:
        return element.initial_stress_mpa * element.area_mm2 * element.count, "initial_stress_mpa"
    if element.initial_strain is not None and element.initial_strain > 0:
        return element.initial_strain * element.ep_mpa * element.area_mm2 * element.count, "initial_strain"
    return 0.0, None


def summarize_effective_prestress_for_sls(
    prestress_elements: list[PrestressElement],
    section_props: GrossSectionProperties | None = None,
    include_unbonded: bool = False,
    *,
    centroid_x_mm: float | None = None,
    centroid_y_mm: float | None = None,
    Ix_mm4: float | None = None,
    Iy_mm4: float | None = None,
    Ixy_mm4: float = 0.0,
    basis_name: str = "gross",
) -> PrestressServiceContribution:
    """Summarize bonded effective prestress forces for elastic SLS stress checks.

    ``Pe_eff`` is a compressive action on concrete. The equivalent prestress
    moments are referenced to the same centroid used by the selected section
    basis, so transformed-section stress checks use the transformed centroid.
    """

    warnings: list[str] = []
    info: list[str] = []
    if section_props is not None:
        centroid_x_mm = section_props.centroid_x_mm if centroid_x_mm is None else centroid_x_mm
        centroid_y_mm = section_props.centroid_y_mm if centroid_y_mm is None else centroid_y_mm
        Ix_mm4 = section_props.Ix_mm4 if Ix_mm4 is None else Ix_mm4
        Iy_mm4 = section_props.Iy_mm4 if Iy_mm4 is None else Iy_mm4
        Ixy_mm4 = section_props.Ixy_mm4
    if centroid_x_mm is None or centroid_y_mm is None or Ix_mm4 is None or Iy_mm4 is None:
        raise ValueError("Prestress SLS summary requires a section basis centroid and inertia.")

    total_pe = 0.0
    total_area = 0.0
    weighted_x = 0.0
    weighted_y = 0.0
    mpe_x = 0.0
    mpe_y = 0.0
    bonded_count = 0
    unbonded_ignored_count = 0

    for element in prestress_elements:
        label = element.label or element.id
        if not element.bonded and not include_unbonded:
            unbonded_ignored_count += element.count
            warnings.append(f"Unbonded prestress element {label} is ignored in {basis_name} SLS stress check.")
            continue

        pe_i, source = _effective_pe_from_element(element)
        if pe_i <= 0:
            warnings.append(f"Prestress element {label} has no positive effective prestress force and is ignored.")
            continue

        bonded_count += element.count
        area_i = element.area_mm2 * element.count
        total_area += area_i
        total_pe += pe_i
        weighted_x += pe_i * element.x_mm
        weighted_y += pe_i * element.y_mm
        # Pe_eff is a compressive action on the concrete. Under the SLS
        # convention compression is negative, so equivalent prestress bending
        # moments have the opposite sign of Pe * eccentricity in the displayed
        # stress formula.
        mpe_x += -pe_i * (element.y_mm - centroid_y_mm)
        mpe_y += -pe_i * (element.x_mm - centroid_x_mm)
        info.append(f"Prestress element {label} uses {source} for effective SLS prestress.")

    centroid_x = weighted_x / total_pe if total_pe > 0 else None
    centroid_y = weighted_y / total_pe if total_pe > 0 else None
    if total_pe <= 0:
        info.append("No positive bonded effective prestress force is available for elastic SLS stress.")
    else:
        info.append(f"Total bonded effective prestress = {N_to_kN(total_pe):,.3f} kN.")

    reference = math.sqrt(Ix_mm4 * Iy_mm4)
    if reference > 0 and abs(Ixy_mm4) > 1.0e-6 * reference:
        warnings.append("Ixy is nonzero; prestress SLS stress contribution uses simplified Ix/Iy uncoupled formula.")

    return PrestressServiceContribution(
        bonded_count=bonded_count,
        unbonded_ignored_count=unbonded_ignored_count,
        total_pe_eff_N=total_pe,
        total_area_mm2=total_area,
        centroid_x_mm=centroid_x,
        centroid_y_mm=centroid_y,
        Mpe_x_Nmm=mpe_x,
        Mpe_y_Nmm=mpe_y,
        warnings=warnings,
        info=info,
    )


def elastic_prestress_stress_gross(
    x_mm: float,
    y_mm: float,
    props: GrossSectionProperties,
    contribution: PrestressServiceContribution,
) -> float:
    """Return gross-section effective prestress stress contribution in MPa.

    Compression is negative and tension is positive. Effective prestress is
    treated as compressive action on the concrete/member. With the signed
    Mpe values stored in ``contribution``, a tendon near a fiber increases
    compression at that same fiber.
    """

    return elastic_prestress_stress_section_basis(
        x_mm=x_mm,
        y_mm=y_mm,
        area_mm2=props.area_mm2,
        centroid_x_mm=props.centroid_x_mm,
        centroid_y_mm=props.centroid_y_mm,
        Ix_mm4=props.Ix_mm4,
        Iy_mm4=props.Iy_mm4,
        contribution=contribution,
    )


def elastic_prestress_stress_section_basis(
    x_mm: float,
    y_mm: float,
    area_mm2: float,
    centroid_x_mm: float,
    centroid_y_mm: float,
    Ix_mm4: float,
    Iy_mm4: float,
    contribution: PrestressServiceContribution,
) -> float:
    """Return effective prestress stress contribution for a selected basis."""

    if contribution.total_pe_eff_N <= 0:
        return 0.0
    dx_point = x_mm - centroid_x_mm
    dy_point = y_mm - centroid_y_mm
    return (
        -contribution.total_pe_eff_N / area_mm2
        + contribution.Mpe_x_Nmm * dy_point / Ix_mm4
        + contribution.Mpe_y_Nmm * dx_point / Iy_mm4
    )


def prestress_service_contribution_to_dataframe(contribution: PrestressServiceContribution) -> pd.DataFrame:
    """Return a one-row engineering-unit prestress contribution summary."""

    return pd.DataFrame(
        [
            {
                "Bonded Count": contribution.bonded_count,
                "Unbonded Ignored Count": contribution.unbonded_ignored_count,
                "Total Pe_kN": N_to_kN(contribution.total_pe_eff_N),
                "Centroid x_mm": contribution.centroid_x_mm,
                "Centroid y_mm": contribution.centroid_y_mm,
                "Mpe_x_kNm": Nmm_to_kNm(contribution.Mpe_x_Nmm),
                "Mpe_y_kNm": Nmm_to_kNm(contribution.Mpe_y_Nmm),
                "Warnings": "; ".join(contribution.warnings),
            }
        ]
    )
