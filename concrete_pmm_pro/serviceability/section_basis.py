"""Section-basis helpers for elastic serviceability stress checks."""

from __future__ import annotations

import math
from typing import Any

from concrete_pmm_pro.serviceability.models import GrossSectionProperties, ServiceabilitySettings
from concrete_pmm_pro.serviceability.transformed import TransformedSectionProperties


def _section_basis_warning_for_i_xy(ix_mm4: float, iy_mm4: float, ixy_mm4: float, basis_name: str) -> str | None:
    reference = math.sqrt(ix_mm4 * iy_mm4)
    if reference <= 0:
        return None
    if abs(ixy_mm4) > 1.0e-6 * reference:
        return f"Ixy is nonzero; {basis_name} SLS stress check currently uses simplified Ix/Iy uncoupled formula."
    return None


def get_serviceability_section_basis(
    gross_props: GrossSectionProperties,
    transformed_props: TransformedSectionProperties | None,
    settings: ServiceabilitySettings,
) -> dict[str, Any]:
    """Return the active section basis for elastic SLS stress checks.

    The returned coordinates stay in the global section coordinate system.
    Stress check points can therefore be evaluated directly against either
    gross or uncracked transformed centroid/inertia values.
    """

    warnings: list[str] = []
    info: list[str] = []
    if settings.use_transformed_section:
        if transformed_props is not None:
            basis = {
                "basis_name": "transformed_uncracked",
                "area_mm2": transformed_props.area_mm2,
                "centroid_x_mm": transformed_props.centroid_x_mm,
                "centroid_y_mm": transformed_props.centroid_y_mm,
                "Ix_mm4": transformed_props.Ix_mm4,
                "Iy_mm4": transformed_props.Iy_mm4,
                "Ixy_mm4": transformed_props.Ixy_mm4,
                "warnings": warnings,
                "info": info,
            }
            info.append("Uncracked transformed section basis used.")
            info.append("Transformed section is uncracked. Cracked section analysis is future work.")
            ixy_warning = _section_basis_warning_for_i_xy(
                transformed_props.Ix_mm4,
                transformed_props.Iy_mm4,
                transformed_props.Ixy_mm4,
                "transformed uncracked",
            )
            if ixy_warning:
                warnings.append(ixy_warning)
            return basis
        warnings.append("Transformed section requested but unavailable; gross section properties used.")

    ixy_warning = _section_basis_warning_for_i_xy(gross_props.Ix_mm4, gross_props.Iy_mm4, gross_props.Ixy_mm4, "gross")
    if ixy_warning:
        warnings.append(ixy_warning)
    info.append("Gross section basis used.")
    return {
        "basis_name": "gross",
        "area_mm2": gross_props.area_mm2,
        "centroid_x_mm": gross_props.centroid_x_mm,
        "centroid_y_mm": gross_props.centroid_y_mm,
        "Ix_mm4": gross_props.Ix_mm4,
        "Iy_mm4": gross_props.Iy_mm4,
        "Ixy_mm4": gross_props.Ixy_mm4,
        "warnings": warnings,
        "info": info,
    }
