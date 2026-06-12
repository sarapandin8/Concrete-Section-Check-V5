from __future__ import annotations

import pytest

from concrete_pmm_pro.code_checks import aci_beta1
from concrete_pmm_pro.core.concrete_materials import (
    DEFAULT_DECK_TOPPING_MATERIAL,
    DEFAULT_PRIMARY_CONCRETE_MATERIAL,
    aci_concrete_ec_mpa,
    default_concrete_materials,
    ensure_concrete_material_library,
)
from concrete_pmm_pro.core.models import ConcreteMaterial, PrestressSteelMaterial, RebarMaterial
from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.io.project_io import project_from_json, project_to_json
from concrete_pmm_pro.ui.materials_page import default_rebar_materials


def test_concrete_material_creation() -> None:
    material = ConcreteMaterial(name="C35", fc_MPa=35.0, ecu=0.003, density_kg_m3=2400.0, beta1=0.80)

    assert material.fc_MPa == pytest.approx(35.0)
    assert material.fc_mpa == pytest.approx(35.0)
    assert material.ecu == pytest.approx(0.003)


def test_aci_concrete_ec_values() -> None:
    assert aci_concrete_ec_mpa(45.0) == pytest.approx(31528.6, abs=0.1)
    assert aci_concrete_ec_mpa(35.0) == pytest.approx(27805.6, abs=0.1)


def test_concrete_material_effective_ec_auto_and_manual() -> None:
    auto = ConcreteMaterial(name="C45", fc_MPa=45.0)
    manual = ConcreteMaterial(name="C45M", fc_MPa=45.0, Ec_method="Manual", Ec_MPa=33000.0)
    old_style = ConcreteMaterial.model_validate({"name": "Old C35", "fc_MPa": 35.0})

    assert auto.effective_Ec_MPa == pytest.approx(31528.6, abs=0.1)
    assert manual.effective_Ec_MPa == pytest.approx(33000.0)
    assert old_style.effective_Ec_MPa == pytest.approx(27805.6, abs=0.1)


def test_default_concrete_material_library_contains_precast_and_topping() -> None:
    materials = {material.name: material for material in default_concrete_materials()}

    assert DEFAULT_PRIMARY_CONCRETE_MATERIAL in materials
    assert DEFAULT_DECK_TOPPING_MATERIAL in materials
    assert materials[DEFAULT_PRIMARY_CONCRETE_MATERIAL].fc_MPa == pytest.approx(45.0)
    assert materials[DEFAULT_DECK_TOPPING_MATERIAL].fc_MPa == pytest.approx(35.0)
    assert materials[DEFAULT_PRIMARY_CONCRETE_MATERIAL].effective_Ec_MPa == pytest.approx(31528.6, abs=0.1)
    assert materials[DEFAULT_DECK_TOPPING_MATERIAL].effective_Ec_MPa == pytest.approx(27805.6, abs=0.1)




def test_default_concrete_material_library_contains_standard_grades() -> None:
    materials = {material.name: material for material in default_concrete_materials()}

    for fc in (28, 30, 35, 40, 45, 50, 55, 60):
        material = materials[f"C{fc}"]
        assert material.fc_MPa == pytest.approx(float(fc))
        assert material.density_kg_m3 == pytest.approx(2400.0)
        assert material.ecu == pytest.approx(0.003)
        assert material.effective_Ec_MPa == pytest.approx(aci_concrete_ec_mpa(float(fc)), abs=0.1)


def test_rebar_material_creation() -> None:
    material = RebarMaterial(name="SD40", fy_MPa=390.0, Es_MPa=200000.0)

    assert material.fy_MPa == pytest.approx(390.0)
    assert material.Es_MPa == pytest.approx(200000.0)


def test_default_rebar_materials_use_project_sd40_sd50_yield_strengths() -> None:
    materials = {material.name: material for material in default_rebar_materials()}

    assert materials["SD40"].fy_MPa == pytest.approx(390.0)
    assert materials["SD50"].fy_MPa == pytest.approx(490.0)
    assert materials["SD40"].Es_MPa == pytest.approx(200000.0)
    assert materials["SD50"].Es_MPa == pytest.approx(200000.0)


def test_rebar_material_model_default_uses_sd40_project_yield_strength() -> None:
    material = RebarMaterial()

    assert material.name == "SD40"
    assert material.fy_MPa == pytest.approx(390.0)


def test_prestress_steel_material_supports_prestressing_bar() -> None:
    material = PrestressSteelMaterial(
        name="PT Bar 32",
        steel_type="prestressing_bar",
        diameter_mm=32.0,
        area_mm2=804.2,
        grade="1080/1230",
        fpy_MPa=1080.0,
        fpu_MPa=1230.0,
        Ep_MPa=200000.0,
    )

    assert material.steel_type == "prestressing_bar"
    assert material.fpu_MPa == pytest.approx(1230.0)
    assert material.Ep_MPa == pytest.approx(200000.0)


def test_prestress_steel_material_rejects_fpy_greater_than_or_equal_to_fpu() -> None:
    with pytest.raises(ValueError, match="fpy_MPa"):
        PrestressSteelMaterial(name="Bad PT Bar", steel_type="prestressing_bar", fpy_MPa=1230.0, fpu_MPa=1230.0)


def test_prestress_steel_material_rejects_nonpositive_ep() -> None:
    with pytest.raises(ValueError):
        PrestressSteelMaterial(name="Bad PT Bar", steel_type="prestressing_bar", fpu_MPa=1230.0, Ep_MPa=0.0)


def test_pt_bar_material_with_fpu_and_ep_is_valid() -> None:
    material = PrestressSteelMaterial(name="PT Bar", steel_type="prestressing_bar", fpu_MPa=1030.0, Ep_MPa=200000.0)

    assert material.fpu_MPa == pytest.approx(1030.0)
    assert material.Ep_MPa == pytest.approx(200000.0)


def test_aci_beta1_values() -> None:
    assert aci_beta1(28.0) == pytest.approx(0.85)
    assert aci_beta1(35.0) == pytest.approx(0.80)
    assert aci_beta1(42.0) == pytest.approx(0.75)
    assert aci_beta1(100.0) == pytest.approx(0.65)


def test_project_round_trip_preserves_concrete_material() -> None:
    project = ProjectModel(concrete_material=ConcreteMaterial(name="C40", fc_MPa=40.0, beta1=aci_beta1(40.0)))

    loaded = project_from_json(project_to_json(project))

    assert loaded.concrete_material.name == "C40"
    assert loaded.concrete_material.fc_MPa == pytest.approx(40.0)


def test_new_project_defaults_to_precast_primary_and_topping_deck() -> None:
    project = ProjectModel()

    assert project.concrete_material.name == DEFAULT_PRIMARY_CONCRETE_MATERIAL
    assert project.active_concrete_material_name == DEFAULT_PRIMARY_CONCRETE_MATERIAL
    assert project.deck_topping_material_name == DEFAULT_DECK_TOPPING_MATERIAL


def test_old_concrete_material_is_preserved_as_active_primary() -> None:
    old_material = ConcreteMaterial(name="Old C35", fc_MPa=35.0, beta1=aci_beta1(35.0))
    library_state = ensure_concrete_material_library(
        concrete_material=old_material,
        concrete_materials=[],
        preserve_existing_primary=True,
    )

    assert library_state.active_material.name == "Old C35"
    assert library_state.active_material.fc_MPa == pytest.approx(35.0)
    assert DEFAULT_PRIMARY_CONCRETE_MATERIAL in {material.name for material in library_state.materials}


def test_project_round_trip_preserves_prestressing_bar_material() -> None:
    project = ProjectModel(
        prestress_materials=[
            PrestressSteelMaterial(
                name="PS Bar 64 - 1080/1230",
                steel_type="prestressing_bar",
                diameter_mm=64.0,
                area_mm2=3217.0,
                grade="1080/1230",
                fpy_MPa=1080.0,
                fpu_MPa=1230.0,
                Ep_MPa=200000.0,
            )
        ],
        active_prestress_material_name="PS Bar 64 - 1080/1230",
    )

    loaded = project_from_json(project_to_json(project))

    assert loaded.prestress_materials[0].steel_type == "prestressing_bar"
    assert loaded.prestress_materials[0].diameter_mm == pytest.approx(64.0)
    assert loaded.active_prestress_material_name == "PS Bar 64 - 1080/1230"


def test_loading_old_project_without_materials_does_not_crash() -> None:
    loaded = project_from_json('{"project_name": "Old Project", "version": "1.6.1"}')

    assert loaded.project_name == "Old Project"
    assert loaded.concrete_material.fc_MPa > 0
    assert loaded.rebar_materials == []
    assert loaded.prestress_materials == []


def test_empty_material_library_preserves_existing_singleton_primary() -> None:
    old_material = ConcreteMaterial(name="Legacy Empty List C35", fc_MPa=35.0, beta1=aci_beta1(35.0))
    library_state = ensure_concrete_material_library(
        concrete_material=old_material,
        concrete_materials=[],
        active_concrete_material_name=None,
        deck_topping_material_name=None,
        preserve_existing_primary=False,
    )

    assert library_state.active_material.name == "Legacy Empty List C35"
    assert library_state.active_material.fc_MPa == pytest.approx(35.0)
    assert DEFAULT_PRIMARY_CONCRETE_MATERIAL in {material.name for material in library_state.materials}
    assert DEFAULT_DECK_TOPPING_MATERIAL in {material.name for material in library_state.materials}
