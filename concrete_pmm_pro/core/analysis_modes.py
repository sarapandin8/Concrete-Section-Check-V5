"""Analysis mode/member type helper functions."""

from __future__ import annotations

from concrete_pmm_pro.core.analysis import AnalysisModeSettings

COLUMN_PIER_WORKFLOW = "column_pier_pmm"
BRIDGE_BEAM_GIRDER_WORKFLOW = "beam_girder"
BUILDING_BEAM_GIRDER_WORKFLOW = "building_beam_girder"


def analysis_mode_label(settings: AnalysisModeSettings) -> str:
    if settings.member_type == COLUMN_PIER_WORKFLOW:
        return "Column / Pier / Wall / Pylon — RC / Prestressed Member"
    if settings.member_type == BRIDGE_BEAM_GIRDER_WORKFLOW:
        return "Bridge Beam / Girder — RC / Prestressed Member"
    if settings.member_type == BUILDING_BEAM_GIRDER_WORKFLOW:
        return "Building Beam / Girder — RC / Prestressed Member"
    if settings.member_type == "general_section":
        return "Column / Pier / Wall / Pylon — RC / Prestressed Member"
    return "Unknown Analysis Mode"


def analysis_mode_description(settings: AnalysisModeSettings) -> str:
    if settings.description:
        return settings.description
    if settings.member_type == COLUMN_PIER_WORKFLOW:
        return (
            "Workflow for column-type members primarily reviewed with Pu, Mux, and Muy. "
            "ACI 318 is available in the current PMM engine; AASHTO LRFD PMM is a planned capability guard."
        )
    if settings.member_type == BRIDGE_BEAM_GIRDER_WORKFLOW:
        return (
            "Bridge Beam/Girder workflow for RC/prestressed bridge members. AASHTO LRFD is the project code basis; "
            "current implemented tools focus on staged SLS stress preview, prestress, debonding, and bridge load components."
        )
    if settings.member_type == BUILDING_BEAM_GIRDER_WORKFLOW:
        return (
            "Building Beam/Girder workflow for RC/prestressed building members. ACI 318 is the project code basis; "
            "building beam ULS/SLS engines are planned and bridge-specific tools remain hidden."
        )
    if settings.member_type == "general_section":
        return (
            "Legacy General Section mode is migrated to the explicit Column / Pier / Wall / Pylon "
            "PMM workflow to avoid ambiguous design interpretation."
        )
    return "Analysis mode is not recognized."


def is_pmm_primary_workflow(settings: AnalysisModeSettings) -> bool:
    return settings.member_type == COLUMN_PIER_WORKFLOW


def is_beam_girder_future_workflow(settings: AnalysisModeSettings) -> bool:
    """Return True for the active Bridge Beam/Girder workflow.

    The function name is preserved for backward compatibility with existing UI
    code; WORKFLOW.TYPE2 narrows this helper to bridge girders only, not building
    beam/girder workflows.
    """

    return settings.member_type == BRIDGE_BEAM_GIRDER_WORKFLOW


def is_bridge_beam_girder_workflow(settings: AnalysisModeSettings) -> bool:
    return settings.member_type == BRIDGE_BEAM_GIRDER_WORKFLOW


def is_building_beam_girder_workflow(settings: AnalysisModeSettings) -> bool:
    return settings.member_type == BUILDING_BEAM_GIRDER_WORKFLOW


def analysis_mode_warnings(settings: AnalysisModeSettings) -> list[str]:
    warnings: list[str] = []
    if settings.member_type == BRIDGE_BEAM_GIRDER_WORKFLOW:
        warnings.extend(
            [
                "Bridge Beam/Girder uses AASHTO LRFD project code basis. Current implemented tools are preview/engineering-review workflows and full bridge ULS/SLS engines are not implemented yet.",
                "Do not double-count prestress by entering Pe as Pu when prestress elements are defined.",
                "Bridge-specific inputs such as girder spacing, number of girders, barrier/parapet/sidewalk, wearing surface, and CSiBridge LL+IM are hidden outside this workflow.",
            ]
        )
    elif settings.member_type == BUILDING_BEAM_GIRDER_WORKFLOW:
        warnings.extend(
            [
                "Building Beam/Girder uses ACI 318 project code basis.",
                "Building beam/girder ULS and SLS engines are planned; bridge-specific staged girder assumptions are intentionally hidden.",
            ]
        )
    elif settings.member_type == "general_section":
        warnings.append(
            "Legacy General Section mode has been removed from the active workflow list; use Column/Pier PMM, Bridge Beam/Girder, or Building Beam/Girder."
        )
    return warnings
