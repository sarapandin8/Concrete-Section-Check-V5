from __future__ import annotations

import pytest

from concrete_pmm_pro.code_checks import (
    aci_column_axial_cap_factor,
    aci_max_phiPn,
    nominal_po_rc,
    nominal_po_rc_prestressed,
    prestress_axial_strength_reference_mpa,
)
from concrete_pmm_pro.core.models import PrestressElement, Rebar, RebarMaterial


def test_aci_column_axial_cap_factor_tied() -> None:
    assert aci_column_axial_cap_factor("tied") == pytest.approx(0.80)


def test_aci_column_axial_cap_factor_spiral() -> None:
    assert aci_column_axial_cap_factor("spiral") == pytest.approx(0.85)


def test_aci_column_axial_cap_factor_rejects_invalid_type() -> None:
    with pytest.raises(ValueError):
        aci_column_axial_cap_factor("invalid")


def test_nominal_po_rc_computes_expected_simple_value() -> None:
    rebars = [Rebar(x_mm=0, y_mm=0, diameter_mm=20), Rebar(x_mm=100, y_mm=0, diameter_mm=20)]
    material = RebarMaterial(name="SD40", fy_MPa=400)
    Ast = sum(rebar.area_mm2 for rebar in rebars)

    po = nominal_po_rc(fc_MPa=30, Ag_mm2=100_000, rebars=rebars, rebar_material_default=material)

    assert po == pytest.approx(0.85 * 30 * (100_000 - Ast) + 400 * Ast)


def test_aci_max_phipn_tied_uses_expected_factor() -> None:
    assert aci_max_phiPn(1_000_000, 0.65, "tied") == pytest.approx(0.80 * 0.65 * 1_000_000)


def test_aci_max_phipn_spiral_uses_expected_factor() -> None:
    assert aci_max_phiPn(1_000_000, 0.75, "spiral") == pytest.approx(0.85 * 0.75 * 1_000_000)


def test_nominal_po_rc_prestressed_includes_bonded_prestress_area_and_fpy() -> None:
    rebars = [Rebar(x_mm=0, y_mm=0, diameter_mm=20)]
    prestress = [
        PrestressElement(
            x_mm=0,
            y_mm=-100,
            area_mm2=140.0,
            count=12,
            fpy_mpa=1580.0,
            fpu_mpa=1860.0,
            pe_eff_n=1_000_000.0,
            bonded=True,
        )
    ]
    material = RebarMaterial(name="SD40", fy_MPa=400)
    Ast = sum(rebar.area_mm2 for rebar in rebars)
    Aps = 140.0 * 12

    po = nominal_po_rc_prestressed(
        fc_MPa=40,
        Ag_mm2=200_000,
        rebars=rebars,
        rebar_material_default=material,
        prestress_elements=prestress,
    )

    assert po == pytest.approx(0.85 * 40 * (200_000 - Ast - Aps) + 400 * Ast + 1580 * Aps)


def test_nominal_po_rc_prestressed_uses_fpu_fallback_not_pe_eff() -> None:
    prestress = [
        PrestressElement(
            x_mm=0,
            y_mm=-100,
            area_mm2=100.0,
            count=2,
            fpy_mpa=None,
            fpu_mpa=1860.0,
            pe_eff_n=999_999_999.0,
            bonded=True,
        )
    ]

    assert prestress_axial_strength_reference_mpa(prestress[0]) == pytest.approx(0.9 * 1860.0)

    po = nominal_po_rc_prestressed(
        fc_MPa=30,
        Ag_mm2=100_000,
        rebars=[],
        prestress_elements=prestress,
    )

    assert po == pytest.approx(0.85 * 30 * (100_000 - 200.0) + 0.9 * 1860.0 * 200.0)


def test_nominal_po_rc_prestressed_rejects_missing_prestress_strength_reference() -> None:
    prestress = [
        PrestressElement(
            x_mm=0,
            y_mm=-100,
            area_mm2=100.0,
            count=1,
            fpy_mpa=None,
            fpu_mpa=None,
            bonded=True,
        )
    ]

    with pytest.raises(ValueError, match="missing both fpy_mpa and fpu_mpa"):
        nominal_po_rc_prestressed(fc_MPa=30, Ag_mm2=100_000, rebars=[], prestress_elements=prestress)
