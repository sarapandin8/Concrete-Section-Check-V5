"""Project design-code source-of-truth helpers.

CODE.SETUP1 centralizes the design-code names used by the UI/project model.
It intentionally does not implement new ACI/AASHTO solver formulas.  Workflow
pages use these helpers to display capability status and to select existing
preview profiles without pretending that planned code-specific engines already
exist.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

PROJECT_CODE_ACI318 = "ACI 318"
PROJECT_CODE_AASHTO_LRFD = "AASHTO LRFD"
DEFAULT_PROJECT_DESIGN_CODE = PROJECT_CODE_ACI318
PROJECT_DESIGN_CODE_OPTIONS: tuple[str, ...] = (PROJECT_CODE_ACI318, PROJECT_CODE_AASHTO_LRFD)

DEFAULT_CODE_EDITION_BY_CODE: dict[str, str] = {
    PROJECT_CODE_ACI318: "ACI 318-19",
    PROJECT_CODE_AASHTO_LRFD: "AASHTO LRFD 9th Edition",
}
CODE_EDITION_OPTIONS_BY_CODE: dict[str, tuple[str, ...]] = {
    PROJECT_CODE_ACI318: ("ACI 318-19", "ACI 318-14", "Project-specified ACI 318 edition"),
    PROJECT_CODE_AASHTO_LRFD: (
        "AASHTO LRFD 9th Edition",
        "AASHTO LRFD 8th Edition",
        "Project-specified AASHTO LRFD edition",
    ),
}

GirderSLSProfileCode = Literal["AASHTO LRFD Bridge", "ACI 318"]


def normalize_project_design_code(value: object | None) -> str:
    """Return the canonical project design-code name used by Setup.

    Legacy UI labels are accepted so older project JSON and session state load
    safely.  Unknown labels fall back to ACI 318 rather than creating a third
    unsupported code path silently.
    """

    text = str(value or "").strip()
    compact = text.casefold().replace("-", " ").replace("_", " ")
    if not compact:
        return DEFAULT_PROJECT_DESIGN_CODE
    if "aashto" in compact or "lrfd" in compact or "bridge" in compact:
        return PROJECT_CODE_AASHTO_LRFD
    if "aci" in compact or "318" in compact:
        return PROJECT_CODE_ACI318
    return DEFAULT_PROJECT_DESIGN_CODE




def allowed_project_design_codes_for_workflow(member_type: object | None) -> tuple[str, ...]:
    """Return design-code options allowed by the active member workflow.

    WORKFLOW.TYPE2 makes code selection workflow-aware:
    Bridge Beam/Girder uses AASHTO LRFD only; Building Beam/Girder uses
    ACI 318 only; Column/Pier/Wall/Pylon can choose either code.
    """

    member = str(member_type or "column_pier_pmm")
    if member == "beam_girder":
        return (PROJECT_CODE_AASHTO_LRFD,)
    if member == "building_beam_girder":
        return (PROJECT_CODE_ACI318,)
    return PROJECT_DESIGN_CODE_OPTIONS


def default_project_design_code_for_workflow(member_type: object | None, current_code: object | None = None) -> str:
    """Return the workflow-compatible project design code.

    If ``current_code`` is allowed for the selected workflow it is preserved;
    otherwise the workflow's required/default code is returned.
    """

    allowed = allowed_project_design_codes_for_workflow(member_type)
    canonical = normalize_project_design_code(current_code)
    if canonical in allowed:
        return canonical
    return allowed[0]


def workflow_code_policy_message(member_type: object | None) -> str:
    member = str(member_type or "column_pier_pmm")
    if member == "beam_girder":
        return "Bridge Beam/Girder workflow uses AASHTO LRFD design basis only."
    if member == "building_beam_girder":
        return "Building Beam/Girder workflow uses ACI 318 design basis only."
    return "Column / Pier / Wall / Pylon workflow may use ACI 318 or AASHTO LRFD, with capability guards where engines are not yet implemented."


def code_edition_options_for(code: object | None) -> tuple[str, ...]:
    canonical = normalize_project_design_code(code)
    return CODE_EDITION_OPTIONS_BY_CODE.get(canonical, CODE_EDITION_OPTIONS_BY_CODE[DEFAULT_PROJECT_DESIGN_CODE])


def default_code_edition_for(code: object | None) -> str:
    canonical = normalize_project_design_code(code)
    return DEFAULT_CODE_EDITION_BY_CODE.get(canonical, DEFAULT_CODE_EDITION_BY_CODE[DEFAULT_PROJECT_DESIGN_CODE])


def normalize_project_code_edition(code: object | None, edition: object | None) -> str:
    """Return a valid edition label for the canonical project code."""

    options = code_edition_options_for(code)
    text = str(edition or "").strip()
    if text in options:
        return text
    return default_code_edition_for(code)


def project_design_code_from_session(session_state: Mapping[str, Any] | Any) -> str:
    getter = session_state.get if hasattr(session_state, "get") else lambda key, default=None: getattr(session_state, key, default)
    return normalize_project_design_code(getter("design_code", getter("code", DEFAULT_PROJECT_DESIGN_CODE)))


def project_code_edition_from_session(session_state: Mapping[str, Any] | Any) -> str:
    getter = session_state.get if hasattr(session_state, "get") else lambda key, default=None: getattr(session_state, key, default)
    code = project_design_code_from_session(session_state)
    return normalize_project_code_edition(code, getter("code_edition", None))


def girder_sls_code_for_project_code(code: object | None) -> GirderSLSProfileCode:
    """Map project code to the existing girder SLS preview profile namespace."""

    canonical = normalize_project_design_code(code)
    if canonical == PROJECT_CODE_AASHTO_LRFD:
        return "AASHTO LRFD Bridge"
    return "ACI 318"


def project_code_capability_cards(code: object | None, member_type: str | None = None) -> list[dict[str, str]]:
    """Return compact capability/status rows for project-level code routing.

    These are UI status guards only.  They do not authorize solver behavior.
    WORKFLOW.TYPE2 makes the project design-code selector workflow-aware.
    """

    member = str(member_type or "column_pier_pmm")
    canonical = default_project_design_code_for_workflow(member, code)
    if member == "beam_girder":
        workflow_note = "Active Bridge Beam/Girder workflow"
        pmm_status = "NOT APPLICABLE"
        pmm_note = "Column/Pier PMM is hidden in the Bridge Beam/Girder workflow."
        girder_status = "PREVIEW AVAILABLE"
        girder_note = "Bridge Beam/Girder uses AASHTO LRFD. Current implemented girder SLS/prestress tools remain preview / engineering-review workflows until full bridge ULS/SLS engines are completed."
    elif member == "building_beam_girder":
        workflow_note = "Active Building Beam/Girder workflow"
        pmm_status = "NOT APPLICABLE"
        pmm_note = "Column/Pier PMM is hidden in the Building Beam/Girder workflow."
        girder_status = "PLANNED / REVIEW"
        girder_note = "Building Beam/Girder uses ACI 318. Building beam/girder ULS and SLS engines are planned; bridge-specific tools are intentionally hidden."
    elif canonical == PROJECT_CODE_AASHTO_LRFD:
        workflow_note = "Active Column/Pier/Wall/Pylon workflow"
        pmm_status = "PLANNED / REVIEW"
        pmm_note = "AASHTO LRFD PMM for Column/Pier/Wall/Pylon is a future solver milestone. Current PMM remains ACI-oriented."
        girder_status = "NOT ACTIVE"
        girder_note = "Bridge/Building beam-girder checks are hidden because the active workflow is Column/Pier/Wall/Pylon."
    else:
        workflow_note = "Active Column/Pier/Wall/Pylon workflow"
        pmm_status = "AVAILABLE"
        pmm_note = "Current Column/Pier/Wall/Pylon PMM workflow is ACI-oriented."
        girder_status = "NOT ACTIVE"
        girder_note = "Bridge/Building beam-girder checks are hidden because the active workflow is Column/Pier/Wall/Pylon."
    return [
        {"title": "Project Design Code", "value": canonical, "detail": workflow_code_policy_message(member), "status": "info"},
        {"title": "Active Workflow", "value": workflow_note, "detail": "Tabs read this project basis; unsupported engines show REVIEW", "status": "info"},
        {"title": "Column/Pier PMM", "value": pmm_status, "detail": pmm_note, "status": "ready" if pmm_status == "AVAILABLE" else ("neutral" if pmm_status in {"NOT APPLICABLE", "NOT ACTIVE"} else "warning")},
        {"title": "Beam/Girder Checks", "value": girder_status, "detail": girder_note, "status": "neutral" if girder_status in {"NOT APPLICABLE", "NOT ACTIVE"} else "warning"},
    ]
