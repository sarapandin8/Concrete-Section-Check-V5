"""Workflow-aware ULS strength routing for Beam/Girder checks.

ULS.CODE.ROUTE1 intentionally separates *routing and reporting basis* from
strength equations.  Bridge Beam/Girder routes to an AASHTO LRFD ULS basis;
Building Beam/Girder routes to an ACI 318 ULS basis.  Formula-specific flexure
and shear engines can be plugged into these route slots in later milestones
without changing the UI contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from concrete_pmm_pro.core.design_code import (
    PROJECT_CODE_AASHTO_LRFD,
    PROJECT_CODE_ACI318,
    normalize_project_code_edition,
    normalize_project_design_code,
)


WORKFLOW_BRIDGE_BEAM_GIRDER = "bridge_beam_girder"
WORKFLOW_BUILDING_BEAM_GIRDER = "building_beam_girder"


@dataclass(frozen=True)
class BeamGirderUlsStrengthRoute:
    """Code-basis route used by Beam/Girder ULS strength workspaces."""

    workflow_key: str
    workflow_label: str
    project_design_code: str
    code_edition: str
    display_code_label: str
    solver_code_label: str
    uls_load_source_label: str
    default_combo_label: str
    flexure_engine_label: str
    flexure_basis_note: str
    shear_engine_label: str
    shear_basis_note: str
    torsion_engine_label: str
    torsion_basis_note: str
    overall_guard_note: str
    is_code_specific_flexure_final: bool = False
    is_code_specific_flexure_layer_ready: bool = True
    is_code_specific_shear_ready: bool = False
    is_code_specific_torsion_ready: bool = False

    @property
    def is_bridge(self) -> bool:
        return self.workflow_key == WORKFLOW_BRIDGE_BEAM_GIRDER

    @property
    def is_building(self) -> bool:
        return self.workflow_key == WORKFLOW_BUILDING_BEAM_GIRDER


def bridge_beam_girder_uls_strength_route(code_edition: object | None = None) -> BeamGirderUlsStrengthRoute:
    """Return the ULS route for Bridge Beam/Girder checks."""

    code = PROJECT_CODE_AASHTO_LRFD
    edition = normalize_project_code_edition(code, code_edition)
    return BeamGirderUlsStrengthRoute(
        workflow_key=WORKFLOW_BRIDGE_BEAM_GIRDER,
        workflow_label="Bridge Beam/Girder",
        project_design_code=code,
        code_edition=edition,
        display_code_label=edition,
        solver_code_label=code,
        uls_load_source_label="Loads → ULS Bridge Beam/Girder Design Loads",
        default_combo_label="Strength I",
        flexure_engine_label="AASHTO LRFD flexure route",
        flexure_basis_note=(
            "Bridge route selected. φMn uses an AASHTO LRFD-compatible strain-compatibility "
            "basis with workflow-specific resistance-factor policy. Detailing/development "
            "checks remain separate ULS milestones."
        ),
        shear_engine_label="AASHTO LRFD shear strength/detailing gate",
        shear_basis_note=(
            "Bridge shear uses the SHEAR.CODE2 provided-stirrup sectional gate: Vc = 0.083β√f'c bv dv "
            "with β=2.0, θ=45°, provided Av/s, Vn capped by 0.25f'c bv dv, minimum Av/s, maximum spacing, "
            "critical shear sections, and active-zone coverage. Development length, anchorage, bearing/end-zone, "
            "and shop-drawing details remain project review items."
        ),
        torsion_engine_label="AASHTO LRFD torsion route",
        torsion_basis_note=(
            "Bridge torsion uses TORSION.CODE2: closed-hoop φTn, torsion threshold screen, longitudinal Al from ordinary rebar, "
            "At/s, closed-hoop spacing, and active-zone coverage gates. Anchorage, hook geometry, bearing/end-zone detailing, "
            "and shop-drawing checks remain project review items."
        ),
        overall_guard_note=(
            "Bridge ULS calculated gates may report PASS when flexure, SHEAR.CODE2, TORSION.CODE2, and combined V+T pass. "
            "Development length, anchorage, bearing/end-zone, shop-drawing detailing, and independent benchmark packages remain project review items."
        ),
        is_code_specific_shear_ready=True,
        is_code_specific_torsion_ready=True,
    )


def building_beam_girder_uls_strength_route(code_edition: object | None = None) -> BeamGirderUlsStrengthRoute:
    """Return the ULS route for Building Beam/Girder checks."""

    code = PROJECT_CODE_ACI318
    edition = normalize_project_code_edition(code, code_edition)
    return BeamGirderUlsStrengthRoute(
        workflow_key=WORKFLOW_BUILDING_BEAM_GIRDER,
        workflow_label="Building Beam/Girder",
        project_design_code=code,
        code_edition=edition,
        display_code_label=edition,
        solver_code_label=code,
        uls_load_source_label="Loads → ULS Building Beam/Girder Design Loads",
        default_combo_label="ACI19-ULS-2" if edition == "ACI 318-19" else "ACI-ULS gravity combo",
        flexure_engine_label="ACI 318 flexure route",
        flexure_basis_note=(
            "Building route selected. φMn uses an ACI 318-compatible strain-compatibility "
            "basis with ACI strain-based strength-reduction factor logic. Detailing/development "
            "checks remain separate ULS milestones."
        ),
        shear_engine_label="ACI 318 shear strength/detailing gate",
        shear_basis_note=(
            "Building shear uses the SHEAR.CODE2 provided-stirrup sectional gate: Vc = 0.17√f'c bw d, "
            "provided Av/s, ACI minimum Av/s, maximum spacing, a Vs maximum screen, critical shear sections, "
            "and active-zone coverage. Development length, anchorage, and shop-drawing details remain project review items."
        ),
        torsion_engine_label="ACI 318 torsion route",
        torsion_basis_note=(
            "Building torsion uses TORSION.CODE2: closed-hoop φTn, torsion threshold screen, longitudinal Al from ordinary rebar, "
            "At/s, closed-hoop spacing, and active-zone coverage gates. Anchorage, hook geometry, and shop-drawing checks remain project review items."
        ),
        overall_guard_note=(
            "Building ULS calculated gates may report PASS when flexure, SHEAR.CODE2, TORSION.CODE2, and combined V+T pass. "
            "Development length, anchorage, shop-drawing detailing, and independent benchmark packages remain project review items."
        ),
        is_code_specific_shear_ready=True,
        is_code_specific_torsion_ready=True,
    )


def beam_girder_uls_strength_route(
    *,
    is_bridge: bool,
    is_building: bool,
    project_design_code: object | None = None,
    code_edition: object | None = None,
) -> BeamGirderUlsStrengthRoute:
    """Return the workflow-compatible Beam/Girder ULS strength route.

    The active workflow is the source of truth.  Incoming project code labels are
    normalized only to avoid stale session/project data; they do not override the
    workflow-locked routing policy.
    """

    if is_bridge:
        return bridge_beam_girder_uls_strength_route(code_edition)
    if is_building:
        return building_beam_girder_uls_strength_route(code_edition)

    code = normalize_project_design_code(project_design_code)
    if code == PROJECT_CODE_AASHTO_LRFD:
        return bridge_beam_girder_uls_strength_route(code_edition)
    return building_beam_girder_uls_strength_route(code_edition)
