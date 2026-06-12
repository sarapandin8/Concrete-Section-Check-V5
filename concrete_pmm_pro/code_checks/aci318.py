"""Small ACI 318 helper functions.

These helpers are data preparation utilities only. The RC PMM prototype uses beta1
and axial-cap helpers inside a prototype RC PMM solver; final ACI capacity
checks are future work.
"""

from __future__ import annotations

from concrete_pmm_pro.core.models import PrestressElement, Rebar, RebarMaterial


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


def _rebar_yield_strength_mpa(rebar: Rebar, default_material: RebarMaterial) -> float:
    """Return rebar yield stress with backward-compatible attribute handling."""

    return float(getattr(rebar, "fy_MPa", None) or getattr(rebar, "fy_mpa", None) or default_material.fy_MPa)


def prestress_axial_strength_reference_mpa(element: PrestressElement) -> float:
    """Return the prestressing steel stress reference used by Po.

    The axial compression cap helper is a nominal-strength helper, not an
    effective-prestress helper.  It therefore uses the prestressing steel proof
    stress ``fpy`` when available.  When catalog data provides only ``fpu``, a
    conservative ``0.90 fpu`` reference is used.  ``Pe_eff`` and breaking-load
    metadata must never be used here because they represent service/effective
    prestress or product reference data, not nominal axial strength.
    """

    if element.fpy_mpa is not None:
        return float(element.fpy_mpa)
    if element.fpu_mpa is not None:
        return 0.90 * float(element.fpu_mpa)
    raise ValueError(
        "Prestress element is missing both fpy_mpa and fpu_mpa; "
        "prestress contribution to nominal Po cannot be calculated."
    )


def nominal_po_rc(
    fc_MPa: float,
    Ag_mm2: float,
    rebars: list[Rebar],
    rebar_material_default: RebarMaterial | None = None,
) -> float:
    """Return nominal concentric axial strength for the RC prototype.

    ``Ag_mm2`` is gross section area from the active geometry, with any modeled
    holes/voids already removed by the geometry layer. Rebar yield stress comes
    from the rebar object when available; otherwise the supplied default
    material is used.
    """

    return nominal_po_rc_prestressed(
        fc_MPa=fc_MPa,
        Ag_mm2=Ag_mm2,
        rebars=rebars,
        rebar_material_default=rebar_material_default,
        prestress_elements=[],
    )


def nominal_po_rc_prestressed(
    fc_MPa: float,
    Ag_mm2: float,
    rebars: list[Rebar],
    rebar_material_default: RebarMaterial | None = None,
    prestress_elements: list[PrestressElement] | None = None,
) -> float:
    """Return nominal concentric axial strength for RC + bonded prestress.

    This is a narrow ACI-style helper for the PMM prototype axial cap.  It uses
    gross concrete area from geometry, subtracts ordinary rebar area and bonded
    prestressing steel area from the concrete compression term, then adds the
    nominal steel terms:

    ``Po = 0.85 fc (Ag - Ast - Aps) + fy Ast + fps_ref Aps``

    where ``fps_ref`` is ``fpy`` when provided, otherwise ``0.90 fpu``.  The
    helper expects the caller to pass only prestress elements that belong in the
    strain-compatible section model, normally bonded elements.  It intentionally
    does not use ``Pe_eff`` or product breaking load.
    """

    if fc_MPa <= 0:
        raise ValueError("fc_MPa must be positive.")
    if Ag_mm2 <= 0:
        raise ValueError("Ag_mm2 must be positive.")

    default_material = rebar_material_default or RebarMaterial(name="Default", fy_MPa=390.0, Es_MPa=200000.0)
    prestress_items = prestress_elements or []

    Ast_mm2 = sum(rebar.area_mm2 for rebar in rebars)
    Aps_mm2 = sum(element.area_mm2 * element.count for element in prestress_items)
    concrete_area_mm2 = Ag_mm2 - Ast_mm2 - Aps_mm2
    if concrete_area_mm2 < 0:
        raise ValueError("Ag_mm2 minus total rebar and prestress steel area must not be negative.")

    steel_force_N = 0.0
    for rebar in rebars:
        steel_force_N += _rebar_yield_strength_mpa(rebar, default_material) * rebar.area_mm2

    prestress_force_N = 0.0
    for element in prestress_items:
        prestress_force_N += prestress_axial_strength_reference_mpa(element) * element.area_mm2 * element.count

    return 0.85 * fc_MPa * concrete_area_mm2 + steel_force_N + prestress_force_N


def aci_max_phiPn(Po_N: float, phi_compression: float, transverse_reinforcement: str) -> float:
    """Return prototype ACI-style capped maximum factored axial strength."""

    if Po_N < 0:
        raise ValueError("Po_N must not be negative.")
    if phi_compression <= 0:
        raise ValueError("phi_compression must be positive.")
    cap_factor = aci_column_axial_cap_factor(transverse_reinforcement)
    return cap_factor * phi_compression * Po_N
