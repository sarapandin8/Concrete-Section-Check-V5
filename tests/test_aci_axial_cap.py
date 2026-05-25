from __future__ import annotations

import pytest

from concrete_pmm_pro.code_checks import aci_column_axial_cap_factor, aci_max_phiPn, nominal_po_rc
from concrete_pmm_pro.core.models import Rebar, RebarMaterial


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
