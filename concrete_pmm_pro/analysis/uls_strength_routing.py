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
        shear_engine_label="AASHTO LRFD-compatible shear route",
        shear_basis_note=(
            "Bridge shear uses a provided-stirrup sectional φVn check with an AASHTO LRFD-compatible "
            "basis for first-pass girder ULS review. Detailed MCFT calibration, maximum spacing, minimum "
            "transverse reinforcement, and benchmark certification remain follow-up QA milestones."
        ),
        torsion_engine_label="AASHTO LRFD torsion route",
        torsion_basis_note=(
            "Bridge torsion uses an AASHTO LRFD-compatible first-pass closed-stirrup φTn route. "
            "Detailed LRFD torsion calibration, longitudinal torsion reinforcement, closed-hoop detailing, "
            "and shear+tortion interaction remain follow-up QA/design milestones."
        ),
        overall_guard_note=(
            "No overall Bridge ULS certification is issued until AASHTO LRFD torsion detailing, "
            "combined shear+tortion interaction, development, and benchmark checks are implemented; "
            "flexure, first-pass sectional shear, and first-pass transverse torsion can be reviewed separately."
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
        shear_engine_label="ACI 318 shear route",
        shear_basis_note=(
            "Building shear uses a provided-stirrup sectional φVn check with ACI 318 one-way shear "
            "basis for first-pass beam/girder ULS review. Maximum spacing, minimum shear reinforcement, "
            "and benchmark certification remain follow-up QA milestones."
        ),
        torsion_engine_label="ACI 318 torsion route",
        torsion_basis_note=(
            "Building torsion uses an ACI 318 first-pass closed-stirrup φTn route. "
            "Longitudinal torsion reinforcement, closed-hoop detailing, and shear+tortion interaction "
            "remain follow-up QA/design milestones."
        ),
        overall_guard_note=(
            "No overall Building ULS certification is issued until ACI 318 torsion detailing, "
            "combined shear+tortion interaction, development, and benchmark checks are implemented; "
            "flexure, first-pass sectional shear, and first-pass transverse torsion can be reviewed separately."
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
