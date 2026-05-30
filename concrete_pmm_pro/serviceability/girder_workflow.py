"""Beam/Girder serviceability workflow helpers.

GIRDER.SLS1B connects the pure elastic girder-stress kernel to explicit section
basis selection without changing PMM, prestress, rebar, report, load, or geometry
logic.  The helpers remain Streamlit-free so they can be validation-tested and
reused later by the UI/report layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from concrete_pmm_pro.core.models import SectionGeometry
from concrete_pmm_pro.geometry.composite import (
    calculate_composite_transformed_section_from_geometry,
    composite_deck_input_from_parameters,
)
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.serviceability.girder_stress import (
    GirderSectionBasis,
    GirderServiceStressResult,
    make_girder_basis_from_composite,
    make_girder_basis_from_gross_summary,
)


@dataclass(frozen=True)
class GirderServiceStressBasisOptions:
    """Available section bases for one Beam/Girder service-stress preview."""

    bases: dict[str, GirderSectionBasis]
    labels: dict[str, str]
    warnings: tuple[str, ...] = ()
    info: tuple[str, ...] = ()

    @property
    def has_composite_basis(self) -> bool:
        return "composite_transformed" in self.bases


def build_girder_service_stress_basis_options(
    section_geometry: SectionGeometry | None,
    section_parameters: Mapping[str, Any] | None,
    *,
    member_type: str | None = "beam_girder",
) -> GirderServiceStressBasisOptions:
    """Return safe girder SLS section-basis options for UI/report consumers.

    A precast gross basis is available whenever section geometry is available.
    A composite transformed basis is available only when explicit composite
    metadata is active and valid.  This function does not infer composite action
    from a preset name and never modifies the section geometry.
    """

    if section_geometry is None:
        return GirderServiceStressBasisOptions(
            bases={},
            labels={},
            warnings=("Section geometry is required before Beam/Girder service-stress preview can run.",),
        )

    warnings: list[str] = []
    info: list[str] = []
    bases: dict[str, GirderSectionBasis] = {}
    labels: dict[str, str] = {}

    try:
        gross_summary = summarize_geometry(section_geometry)
        gross_basis = make_girder_basis_from_gross_summary(gross_summary)
        bases["precast_gross"] = gross_basis
        labels["precast_gross"] = "Precast gross section"
    except (TypeError, ValueError) as exc:
        warnings.append(f"Precast gross service-stress basis is unavailable: {exc}")
        return GirderServiceStressBasisOptions(bases=bases, labels=labels, warnings=tuple(warnings), info=tuple(info))

    params = dict(section_parameters or {})
    deck = composite_deck_input_from_parameters(params, member_type=member_type)
    if deck.enabled:
        try:
            composite = calculate_composite_transformed_section_from_geometry(section_geometry, deck)
            bases["composite_transformed"] = make_girder_basis_from_composite(composite)
            labels["composite_transformed"] = "Composite transformed section"
            if composite.warnings:
                warnings.extend(composite.warnings)
        except (TypeError, ValueError) as exc:
            warnings.append(f"Composite transformed service-stress basis is unavailable: {exc}")
    else:
        info.append(
            "Composite transformed service-stress basis is not active. Enable composite deck/topping metadata "
            "with positive Tslab, Be, Ebeam, and Edeck values to use the composite basis."
        )

    return GirderServiceStressBasisOptions(bases=bases, labels=labels, warnings=tuple(warnings), info=tuple(info))


def girder_service_stress_result_rows(result: GirderServiceStressResult) -> list[dict[str, Any]]:
    """Return stable table rows for top/bottom girder service stresses."""

    return [
        {
            "Fiber": "Top",
            "y from bottom (mm)": result.top.y_from_bottom_mm,
            "Axial stress (MPa)": result.top.axial_stress_MPa,
            "Bending stress (MPa)": result.top.bending_stress_MPa,
            "Total stress (MPa)": result.top.total_stress_MPa,
            "Stress type": result.top.stress_type,
        },
        {
            "Fiber": "Bottom",
            "y from bottom (mm)": result.bottom.y_from_bottom_mm,
            "Axial stress (MPa)": result.bottom.axial_stress_MPa,
            "Bending stress (MPa)": result.bottom.bending_stress_MPa,
            "Total stress (MPa)": result.bottom.total_stress_MPa,
            "Stress type": result.bottom.stress_type,
        },
    ]
