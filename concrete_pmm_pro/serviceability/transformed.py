"""Uncracked transformed section property foundation."""

from __future__ import annotations

import math

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from concrete_pmm_pro.core.models import (
    ConcreteMaterial,
    PrestressElement,
    PrestressSteelMaterial,
    Rebar,
    RebarMaterial,
)
from concrete_pmm_pro.serviceability.materials import estimate_concrete_ec_mpa, estimate_concrete_ec_warnings, modular_ratio
from concrete_pmm_pro.serviceability.models import GrossSectionProperties, ServiceabilitySettings


class TransformedSectionProperties(BaseModel):
    """Uncracked transformed section properties in concrete-equivalent units."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    basis: str = "uncracked_transformed"
    Ec_MPa: float = Field(gt=0)
    area_mm2: float = Field(gt=0)
    centroid_x_mm: float
    centroid_y_mm: float
    Ix_mm4: float = Field(gt=0)
    Iy_mm4: float = Field(gt=0)
    Ixy_mm4: float
    gross_concrete_area_mm2: float
    transformed_rebar_area_mm2: float = 0.0
    transformed_prestress_area_mm2: float = 0.0
    rebar_count: int = 0
    prestress_count: int = 0
    x_min_mm: float
    x_max_mm: float
    y_min_mm: float
    y_max_mm: float
    section_modulus_top_mm3: float | None = None
    section_modulus_bottom_mm3: float | None = None
    section_modulus_left_mm3: float | None = None
    section_modulus_right_mm3: float | None = None
    warnings: list[str] = Field(default_factory=list)
    info: list[str] = Field(default_factory=list)


def _section_modulus(inertia_mm4: float, distance_mm: float) -> float | None:
    if distance_mm <= 0:
        return None
    return inertia_mm4 / distance_mm


def _rebar_material_for(rebar: Rebar, materials: list[RebarMaterial]) -> RebarMaterial:
    by_name = {material.name: material for material in materials}
    if rebar.material_name in by_name:
        return by_name[rebar.material_name]
    if materials:
        return materials[0]
    return RebarMaterial(name=rebar.material_name)


def _prestress_material_for(element: PrestressElement, materials: list[PrestressSteelMaterial]) -> PrestressSteelMaterial | None:
    if element.material_name is None:
        return None
    by_name = {material.name: material for material in materials}
    return by_name.get(element.material_name)


def _concrete_ec(concrete_material: ConcreteMaterial, settings: ServiceabilitySettings) -> float:
    if settings.concrete_Ec_MPa is not None and settings.concrete_Ec_MPa > 0:
        return settings.concrete_Ec_MPa
    return estimate_concrete_ec_mpa(concrete_material.fc_MPa, concrete_material.density_kg_m3, settings.Ec_method)


def _warn_if_centroid_outside_bounds(props: TransformedSectionProperties, warnings: list[str]) -> None:
    if not (props.x_min_mm <= props.centroid_x_mm <= props.x_max_mm) or not (props.y_min_mm <= props.centroid_y_mm <= props.y_max_mm):
        warnings.append("Transformed centroid lies outside the gross section bounds; review reinforcement layout and modular ratios.")


def _warn_if_i_xy_significant(ix_mm4: float, iy_mm4: float, ixy_mm4: float, warnings: list[str], info: list[str]) -> None:
    reference = math.sqrt(ix_mm4 * iy_mm4)
    if reference > 0 and abs(ixy_mm4) > 1.0e-6 * reference:
        message = (
            "Ixy is nonzero; current service stress checks use simplified uncoupled Ix/Iy formulation. "
            "Review unsymmetric bending effects."
        )
        warnings.append(message)
        info.append("Future transformed stress checks should include full unsymmetric bending formulation.")


def compute_uncracked_transformed_section_properties(
    gross_props: GrossSectionProperties,
    concrete_material: ConcreteMaterial,
    rebars: list[Rebar],
    rebar_materials: list[RebarMaterial],
    prestress_elements: list[PrestressElement],
    prestress_materials: list[PrestressSteelMaterial],
    settings: ServiceabilitySettings,
) -> TransformedSectionProperties:
    """Compute uncracked concrete-equivalent transformed section properties."""

    warnings: list[str] = []
    info: list[str] = []
    ec = _concrete_ec(concrete_material, settings)
    warnings.extend(estimate_concrete_ec_warnings(concrete_material.fc_MPa, concrete_material.density_kg_m3, settings.Ec_method))
    area_terms: list[tuple[float, float, float, str]] = []
    transformed_rebar_area = 0.0
    transformed_prestress_area = 0.0
    rebar_count = 0
    prestress_count = 0

    if settings.transformed_include_rebar:
        for rebar in rebars:
            material = _rebar_material_for(rebar, rebar_materials)
            n = modular_ratio(material.Es_MPa, ec)
            count = int(getattr(rebar, "count", 1) or 1)
            area = rebar.area_mm2 * count
            a_add = (n - 1.0) * area
            if a_add <= 0:
                warnings.append(f"Rebar {rebar.label or rebar.material_name} has nonpositive transformed area contribution.")
            area_terms.append((a_add, rebar.x_mm, rebar.y_mm, "rebar"))
            transformed_rebar_area += a_add
            rebar_count += count
        if rebars:
            info.append(f"Included {rebar_count} ordinary rebar object(s) using net_steel transformed area convention.")

    if settings.transformed_include_prestress:
        for element in prestress_elements:
            label = element.label or element.material_name or element.id
            if not element.bonded:
                warnings.append(f"Unbonded prestress element {label} is ignored in transformed section properties.")
                continue
            material = _prestress_material_for(element, prestress_materials)
            ep = element.ep_mpa if element.ep_mpa > 0 else (material.Ep_MPa if material is not None else 195000.0)
            n = modular_ratio(ep, ec)
            area = element.area_mm2 * element.count
            a_add = (n - 1.0) * area
            if a_add <= 0:
                warnings.append(f"Prestress element {label} has nonpositive transformed area contribution.")
            area_terms.append((a_add, element.x_mm, element.y_mm, "prestress"))
            transformed_prestress_area += a_add
            prestress_count += element.count
        if prestress_count:
            info.append(f"Included {prestress_count} bonded prestress element count(s) using net_steel transformed area convention.")

    area_0 = gross_props.area_mm2
    x_0 = gross_props.centroid_x_mm
    y_0 = gross_props.centroid_y_mm
    area_transformed = area_0 + sum(term[0] for term in area_terms)
    if area_transformed <= 0:
        raise ValueError("Transformed section area must be positive.")

    x_tr = (area_0 * x_0 + sum(a * x for a, x, _, _ in area_terms)) / area_transformed
    y_tr = (area_0 * y_0 + sum(a * y for a, _, y, _ in area_terms)) / area_transformed

    ix_tr = gross_props.Ix_mm4 + area_0 * (y_0 - y_tr) ** 2
    iy_tr = gross_props.Iy_mm4 + area_0 * (x_0 - x_tr) ** 2
    ixy_tr = gross_props.Ixy_mm4 + area_0 * (x_0 - x_tr) * (y_0 - y_tr)
    for a_add, x_i, y_i, _kind in area_terms:
        ix_tr += a_add * (y_i - y_tr) ** 2
        iy_tr += a_add * (x_i - x_tr) ** 2
        ixy_tr += a_add * (x_i - x_tr) * (y_i - y_tr)
    if ix_tr <= 0 or iy_tr <= 0:
        raise ValueError("Transformed section inertia must be positive.")

    props = TransformedSectionProperties(
        Ec_MPa=ec,
        area_mm2=area_transformed,
        centroid_x_mm=x_tr,
        centroid_y_mm=y_tr,
        Ix_mm4=ix_tr,
        Iy_mm4=iy_tr,
        Ixy_mm4=ixy_tr,
        gross_concrete_area_mm2=gross_props.area_mm2,
        transformed_rebar_area_mm2=transformed_rebar_area,
        transformed_prestress_area_mm2=transformed_prestress_area,
        rebar_count=rebar_count,
        prestress_count=prestress_count,
        x_min_mm=gross_props.x_min_mm,
        x_max_mm=gross_props.x_max_mm,
        y_min_mm=gross_props.y_min_mm,
        y_max_mm=gross_props.y_max_mm,
        section_modulus_top_mm3=_section_modulus(ix_tr, gross_props.y_max_mm - y_tr),
        section_modulus_bottom_mm3=_section_modulus(ix_tr, y_tr - gross_props.y_min_mm),
        section_modulus_left_mm3=_section_modulus(iy_tr, x_tr - gross_props.x_min_mm),
        section_modulus_right_mm3=_section_modulus(iy_tr, gross_props.x_max_mm - x_tr),
        warnings=warnings,
        info=info,
    )
    _warn_if_centroid_outside_bounds(props, props.warnings)
    _warn_if_i_xy_significant(props.Ix_mm4, props.Iy_mm4, props.Ixy_mm4, props.warnings, props.info)
    return props


def transformed_section_properties_to_dataframe(props: TransformedSectionProperties) -> pd.DataFrame:
    """Return transformed section properties as a one-row dataframe."""

    return pd.DataFrame(
        [
            {
                "Basis": props.basis,
                "Ec_MPa": props.Ec_MPa,
                "Area_mm2": props.area_mm2,
                "Centroid x_mm": props.centroid_x_mm,
                "Centroid y_mm": props.centroid_y_mm,
                "Ix_mm4": props.Ix_mm4,
                "Iy_mm4": props.Iy_mm4,
                "Ixy_mm4": props.Ixy_mm4,
                "Gross Concrete Area_mm2": props.gross_concrete_area_mm2,
                "Transformed Rebar Area_mm2": props.transformed_rebar_area_mm2,
                "Transformed Prestress Area_mm2": props.transformed_prestress_area_mm2,
                "Rebar Count": props.rebar_count,
                "Prestress Count": props.prestress_count,
                "x_min_mm": props.x_min_mm,
                "x_max_mm": props.x_max_mm,
                "y_min_mm": props.y_min_mm,
                "y_max_mm": props.y_max_mm,
                "S_top_mm3": props.section_modulus_top_mm3,
                "S_bottom_mm3": props.section_modulus_bottom_mm3,
                "S_left_mm3": props.section_modulus_left_mm3,
                "S_right_mm3": props.section_modulus_right_mm3,
                "Warnings": "; ".join(props.warnings),
                "Info": "; ".join(props.info),
            }
        ]
    )
