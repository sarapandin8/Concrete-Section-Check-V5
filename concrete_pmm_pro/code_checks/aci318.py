"""Small ACI 318 helper functions.

These helpers are data preparation utilities only. The RC PMM prototype uses beta1
and axial-cap helpers inside a prototype RC PMM solver; final ACI capacity
checks are future work.
"""

from __future__ import annotations

from concrete_pmm_pro.core.models import Rebar, RebarMaterial


def aci_beta1(fc_MPa: float) -> float:
    """Return ACI-style rectangular stress block beta1 for concrete strength."""

    if fc_MPa <= 0:
        raise ValueError("fc_MPa must be positive.")
    if fc_MPa <= 28.0:
        return 0.85
    reduction_steps = (fc_MPa - 28.0) / 7.0
    return max(0.65, 0.85 - 0.05 * reduction_steps)


def aci_column_axial_cap_factor(transverse_reinforcement: str) -> float:
    """Return prototype ACI-style maximum axial strength factor."""

    if transverse_reinforcement == "tied":
        return 0.80
    if transverse_reinforcement == "spiral":
        return 0.85
    raise ValueError("transverse_reinforcement must be tied or spiral.")


def nominal_po_rc(
    fc_MPa: float,
    Ag_mm2: float,
    rebars: list[Rebar],
    rebar_material_default: RebarMaterial | None = None,
) -> float:
    """Return nominal concentric axial strength for the RC prototype.

    `Ag_mm2` is the net concrete section area, including holes removed. Rebar
    yield stress comes from the rebar object when available; otherwise the
    supplied default material is used.
    """

    if fc_MPa <= 0:
        raise ValueError("fc_MPa must be positive.")
    if Ag_mm2 <= 0:
        raise ValueError("Ag_mm2 must be positive.")

    default_material = rebar_material_default or RebarMaterial(name="Default", fy_MPa=400.0, Es_MPa=200000.0)
    Ast_mm2 = sum(rebar.area_mm2 for rebar in rebars)
    concrete_area_mm2 = Ag_mm2 - Ast_mm2
    if concrete_area_mm2 < 0:
        raise ValueError("Ag_mm2 minus total rebar area must not be negative.")

    steel_force_N = 0.0
    for rebar in rebars:
        fy_MPa = getattr(rebar, "fy_MPa", None) or getattr(rebar, "fy_mpa", None) or default_material.fy_MPa
        steel_force_N += float(fy_MPa) * rebar.area_mm2
    return 0.85 * fc_MPa * concrete_area_mm2 + steel_force_N


def aci_max_phiPn(Po_N: float, phi_compression: float, transverse_reinforcement: str) -> float:
    """Return prototype ACI-style capped maximum factored axial strength."""

    if Po_N < 0:
        raise ValueError("Po_N must not be negative.")
    if phi_compression <= 0:
        raise ValueError("phi_compression must be positive.")
    cap_factor = aci_column_axial_cap_factor(transverse_reinforcement)
    return cap_factor * phi_compression * Po_N
