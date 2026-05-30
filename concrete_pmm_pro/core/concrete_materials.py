"""Concrete material library helpers.

The PMM solver continues to consume ``project.concrete_material``. These
helpers keep the richer library and section assignment metadata synchronized
without changing solver-facing material semantics.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import sqrt

from concrete_pmm_pro.core.models import ConcreteMaterial

CONCRETE_EC_METHOD_ACI = "ACI auto"
CONCRETE_EC_METHOD_MANUAL = "Manual"
CONCRETE_EC_METHOD_OPTIONS = [CONCRETE_EC_METHOD_ACI, CONCRETE_EC_METHOD_MANUAL]
DEFAULT_PRIMARY_CONCRETE_MATERIAL = "C45_PRECAST"
DEFAULT_DECK_TOPPING_MATERIAL = "C35_TOPPING"


@dataclass(frozen=True)
class ConcreteMaterialLibraryState:
    materials: list[ConcreteMaterial]
    active_concrete_material_name: str
    deck_topping_material_name: str
    active_material: ConcreteMaterial
    deck_topping_material: ConcreteMaterial


def aci_concrete_ec_mpa(fc_MPa: float) -> float:
    """ACI normal-weight concrete modulus in MPa."""
    return 4700.0 * sqrt(float(fc_MPa))


def c45_precast_material() -> ConcreteMaterial:
    return ConcreteMaterial(
        name=DEFAULT_PRIMARY_CONCRETE_MATERIAL,
        fc_MPa=45.0,
        density_kg_m3=2400.0,
        ecu=0.003,
        beta1=None,
        Ec_method=CONCRETE_EC_METHOD_ACI,
        Ec_MPa=None,
        note="Precast prestressed girder / beam concrete",
    )


def c35_topping_material() -> ConcreteMaterial:
    return ConcreteMaterial(
        name=DEFAULT_DECK_TOPPING_MATERIAL,
        fc_MPa=35.0,
        density_kg_m3=2400.0,
        ecu=0.003,
        beta1=None,
        Ec_method=CONCRETE_EC_METHOD_ACI,
        Ec_MPa=None,
        note="Cast-in-place deck / topping concrete",
    )


def concrete_grade_material(fc_MPa: float) -> ConcreteMaterial:
    """Return a standard normal-weight concrete grade material."""
    grade = int(fc_MPa) if float(fc_MPa).is_integer() else fc_MPa
    return ConcreteMaterial(
        name=f"C{grade}",
        fc_MPa=float(fc_MPa),
        density_kg_m3=2400.0,
        ecu=0.003,
        beta1=None,
        Ec_method=CONCRETE_EC_METHOD_ACI,
        Ec_MPa=None,
        note=f"Normal-weight concrete, f'c = {float(fc_MPa):g} MPa",
    )


def standard_concrete_grade_materials() -> list[ConcreteMaterial]:
    return [concrete_grade_material(fc) for fc in (28.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0)]


def default_concrete_materials() -> list[ConcreteMaterial]:
    return [c45_precast_material(), c35_topping_material(), *standard_concrete_grade_materials()]


def concrete_materials_by_name(materials: Iterable[ConcreteMaterial]) -> dict[str, ConcreteMaterial]:
    return {material.name: material for material in materials}


def _upsert_material(materials: list[ConcreteMaterial], material: ConcreteMaterial) -> list[ConcreteMaterial]:
    if material.name in {item.name for item in materials}:
        return materials
    return [*materials, material]


def _coerce_materials(materials: Iterable[ConcreteMaterial | dict] | None) -> list[ConcreteMaterial]:
    coerced: list[ConcreteMaterial] = []
    for material in materials or []:
        coerced.append(material if isinstance(material, ConcreteMaterial) else ConcreteMaterial.model_validate(material))
    return coerced


def ensure_concrete_material_library(
    *,
    concrete_material: ConcreteMaterial | dict | None = None,
    concrete_materials: Iterable[ConcreteMaterial | dict] | None = None,
    active_concrete_material_name: str | None = None,
    deck_topping_material_name: str | None = None,
    preserve_existing_primary: bool = True,
) -> ConcreteMaterialLibraryState:
    """Return a normalized concrete library and synchronized active names."""
    materials = _coerce_materials(concrete_materials)
    existing_primary = (
        concrete_material
        if isinstance(concrete_material, ConcreteMaterial)
        else ConcreteMaterial.model_validate(concrete_material)
        if isinstance(concrete_material, dict)
        else None
    )

    # Preserve an existing singleton concrete material whenever the library is empty.
    # This protects legacy projects/sessions that carry project.concrete_material but
    # have an empty concrete_materials list from being silently converted to C45_PRECAST.
    if not materials and existing_primary is not None:
        materials.append(existing_primary)

    for default_material in default_concrete_materials():
        materials = _upsert_material(materials, default_material)

    if not materials:
        materials = default_concrete_materials()

    material_map = concrete_materials_by_name(materials)

    if active_concrete_material_name not in material_map:
        if existing_primary is not None and existing_primary.name in material_map:
            active_concrete_material_name = existing_primary.name
        elif DEFAULT_PRIMARY_CONCRETE_MATERIAL in material_map:
            active_concrete_material_name = DEFAULT_PRIMARY_CONCRETE_MATERIAL
        else:
            active_concrete_material_name = materials[0].name

    if deck_topping_material_name not in material_map:
        deck_topping_material_name = (
            DEFAULT_DECK_TOPPING_MATERIAL
            if DEFAULT_DECK_TOPPING_MATERIAL in material_map
            else active_concrete_material_name
        )

    active_material = material_map[active_concrete_material_name]
    deck_topping_material = material_map[deck_topping_material_name]
    return ConcreteMaterialLibraryState(
        materials=materials,
        active_concrete_material_name=active_concrete_material_name,
        deck_topping_material_name=deck_topping_material_name,
        active_material=active_material,
        deck_topping_material=deck_topping_material,
    )
