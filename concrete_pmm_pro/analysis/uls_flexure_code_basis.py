"""Code-specific flexure resistance basis for Beam/Girder ULS checks.

This module is intentionally a *thin code-routing layer* above the existing
strain-compatibility section engine.  It separates the resistance-factor basis
used for Bridge Beam/Girder and Building Beam/Girder checks without changing the
underlying section strain-compatibility solver.
"""

from __future__ import annotations

from dataclasses import dataclass

from concrete_pmm_pro.analysis.uls_strength_routing import BeamGirderUlsStrengthRoute


@dataclass(frozen=True)
class BeamGirderFlexureCodeBasis:
    """Resistance-factor basis used for one Beam/Girder flexure check."""

    route_label: str
    display_label: str
    capacity_label: str
    method_label: str
    basis_note: str
    strain_compatibility_basis: str
    resistance_factor_policy: str
    solver_audit_label: str
    material_model_scope: str
    benchmark_readiness_note: str
    resistance_factor: float | None = None
    requires_nominal_capacity: bool = False
    is_code_specific_layer_active: bool = True

    @property
    def resistance_factor_text(self) -> str:
        if self.resistance_factor is None:
            return "strain-based φ"
        return f"φ = {self.resistance_factor:.2f}"


def beam_girder_flexure_code_basis(
    strength_route: BeamGirderUlsStrengthRoute,
    *,
    has_bonded_prestress: bool,
) -> BeamGirderFlexureCodeBasis:
    """Return the routed flexure resistance basis for the active workflow.

    Building Beam/Girder keeps the existing ACI strain-based φ from the shared
    PMM engine.  Bridge Beam/Girder uses a code-specific AASHTO resistance-factor
    layer on nominal section capacity so Bridge and Building no longer silently
    report the same φMn merely because they share the same section solver.
    """

    if strength_route.is_bridge:
        if has_bonded_prestress:
            return BeamGirderFlexureCodeBasis(
                route_label="AASHTO LRFD flexure route — prestressed concrete",
                display_label="AASHTO LRFD flexure φ layer",
                capacity_label="φMn — AASHTO LRFD",
                method_label="AASHTO LRFD φ × nominal strain-compatibility Mn",
                basis_note=(
                    "Bridge prestressed concrete route: nominal Mn is solved from AASHTO LRFD-compatible "
                    "section strain compatibility, then the AASHTO LRFD prestressed flexure resistance "
                    "factor φ = 1.00 is applied."
                ),
                strain_compatibility_basis="AASHTO LRFD-compatible strain compatibility",
                resistance_factor_policy="AASHTO LRFD prestressed flexure: φ = 1.00 applied to nominal Mn",
                solver_audit_label="Nominal Mn from section equilibrium / strain compatibility",
                material_model_scope="Concrete, ordinary rebar, and bonded prestress use the current section material models",
                benchmark_readiness_note="Benchmark against AASHTO/PCI or commercial girder software using Mn, φ, φMn, and D/C",
                resistance_factor=1.00,
                requires_nominal_capacity=True,
            )
        return BeamGirderFlexureCodeBasis(
            route_label="AASHTO LRFD flexure route — reinforced concrete",
            display_label="AASHTO LRFD flexure φ layer",
            capacity_label="φMn — AASHTO LRFD",
            method_label="AASHTO LRFD / strain-compatible φMn",
            basis_note=(
                "Bridge nonprestressed concrete route: φMn is solved using an AASHTO LRFD-compatible "
                "strain-compatibility basis with the current reinforced-concrete φ logic."
            ),
            strain_compatibility_basis="AASHTO LRFD-compatible strain compatibility",
            resistance_factor_policy="AASHTO LRFD reinforced-concrete flexure: strain-compatible φ basis",
            solver_audit_label="φMn from section equilibrium / strain compatibility",
            material_model_scope="Concrete and ordinary rebar use the current section material models",
            benchmark_readiness_note="Benchmark against AASHTO reinforced-concrete flexure examples before certification",
            resistance_factor=None,
            requires_nominal_capacity=False,
        )

    return BeamGirderFlexureCodeBasis(
        route_label="ACI 318 flexure route — strain-compatible",
        display_label="ACI 318 strain-based φ",
        capacity_label="φMn — ACI 318",
        method_label="ACI 318 strain-based φ from PMM engine",
        basis_note=(
            "Building route: φMn is solved using an ACI 318-compatible strain-compatibility basis "
            "with the ACI strain-based strength-reduction factor logic."
        ),
        strain_compatibility_basis="ACI 318-compatible strain compatibility",
        resistance_factor_policy="ACI 318 flexure: strain-based φ from section response",
        solver_audit_label="φMn from section equilibrium / strain compatibility",
        material_model_scope="Concrete, ordinary rebar, and prestress use the current section material models",
        benchmark_readiness_note="Benchmark against ACI/prestressed concrete examples before certification",
        resistance_factor=None,
        requires_nominal_capacity=False,
    )


def apply_flexure_code_basis(
    *,
    phi_capacity_nmm: float | None,
    nominal_capacity_nmm: float | None,
    basis: BeamGirderFlexureCodeBasis,
) -> tuple[float | None, str]:
    """Return code-routed φMn and a short note describing the selected basis."""

    if basis.requires_nominal_capacity:
        if nominal_capacity_nmm is not None and nominal_capacity_nmm > 0.0 and basis.resistance_factor is not None:
            return float(basis.resistance_factor) * float(nominal_capacity_nmm), basis.basis_note
        return phi_capacity_nmm, basis.basis_note + " Nominal-capacity fallback was unavailable; reported value uses the current φ-reduced engine result."
    return phi_capacity_nmm, basis.basis_note
