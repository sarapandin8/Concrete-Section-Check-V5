from __future__ import annotations

import json
from pathlib import Path

from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.core.design_code import (
    PROJECT_CODE_AASHTO_LRFD,
    PROJECT_CODE_ACI318,
    default_code_edition_for,
    girder_sls_code_for_project_code,
    normalize_project_code_edition,
    normalize_project_design_code,
    project_code_capability_cards,
)
from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.io.project_io import apply_project_to_session_state, project_from_session_state, project_to_json
from concrete_pmm_pro.ui.project_page import _project_design_code_cards

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")
PRESTRESS_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "prestress_page.py").read_text(encoding="utf-8")
PROJECT_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "project_page.py").read_text(encoding="utf-8")


def test_project_design_code_normalization_and_girder_profile_mapping() -> None:
    assert normalize_project_design_code("AASHTO LRFD Bridge") == PROJECT_CODE_AASHTO_LRFD
    assert normalize_project_design_code("ACI318") == PROJECT_CODE_ACI318
    assert girder_sls_code_for_project_code("AASHTO LRFD") == "AASHTO LRFD Bridge"
    assert girder_sls_code_for_project_code("ACI 318") == "ACI 318"
    assert default_code_edition_for("AASHTO") == "AASHTO LRFD 9th Edition"
    assert normalize_project_code_edition("AASHTO LRFD", "bad edition") == "AASHTO LRFD 9th Edition"


def test_project_model_and_io_preserve_code_and_edition() -> None:
    project = ProjectModel(code="AASHTO LRFD Bridge", code_edition="AASHTO LRFD 9th Edition")
    assert project.code == PROJECT_CODE_AASHTO_LRFD
    assert project.code_edition == "AASHTO LRFD 9th Edition"

    parsed = json.loads(project_to_json(project))
    assert parsed["code"] == PROJECT_CODE_AASHTO_LRFD
    assert parsed["code_edition"] == "AASHTO LRFD 9th Edition"

    session: dict[str, object] = {"design_code": "AASHTO LRFD", "code_edition": "AASHTO LRFD 9th Edition"}
    saved = project_from_session_state(session)
    assert saved.code == PROJECT_CODE_AASHTO_LRFD
    assert saved.code_edition == "AASHTO LRFD 9th Edition"

    restored: dict[str, object] = {}
    apply_project_to_session_state(saved, restored)
    assert restored["design_code"] == PROJECT_CODE_AASHTO_LRFD
    assert restored["code_edition"] == "AASHTO LRFD 9th Edition"


def test_project_design_code_cards_flag_aashto_pmm_as_planned() -> None:
    cards = _project_design_code_cards(
        ProjectModel(code="AASHTO LRFD", code_edition="AASHTO LRFD 9th Edition"),
        AnalysisModeSettings(member_type="column_pier_pmm"),
    )
    by_title = {card.title: card for card in cards}

    assert by_title["Design Code"].value == PROJECT_CODE_AASHTO_LRFD
    assert by_title["Column/Pier PMM"].value == "PLANNED / REVIEW"
    assert by_title["Column/Pier PMM"].status == "warning"


def test_code_capability_helper_does_not_overclaim_aashto_pmm() -> None:
    cards = project_code_capability_cards("AASHTO LRFD", "column_pier_pmm")
    by_title = {card["title"]: card for card in cards}

    assert by_title["Column/Pier PMM"]["value"] == "PLANNED / REVIEW"
    assert "future solver milestone" in by_title["Column/Pier PMM"]["detail"]


def test_code_setup1_source_files_have_project_code_guardrails() -> None:
    assert "Project-level source of truth" in PROJECT_SOURCE
    assert "Project Design Code / Capability Guard" in PROJECT_SOURCE
    assert "Project code profile" in ANALYSIS_SOURCE
    assert "project-code preview stress-limit profile" in ANALYSIS_SOURCE
    assert "Workflow-enforced from active Analysis Mode" in ANALYSIS_SOURCE
    assert "_girder_sls_project_design_code_from_session" in ANALYSIS_SOURCE
    assert "Project Design Code is AASHTO LRFD" in ANALYSIS_SOURCE
    assert "AASHTO LRFD PMM is planned" in ANALYSIS_SOURCE
    assert "Prestress loss code basis" in PRESTRESS_SOURCE
    assert "Prestress loss basis differs from Project Design Code" in PRESTRESS_SOURCE
    assert "ACI 318 / PCI-style approximate loss basis selected" in PRESTRESS_SOURCE


def test_workflow_type2_filters_project_design_code_by_workflow() -> None:
    bridge = ProjectModel(
        code="ACI 318",
        code_edition="ACI 318-19",
        analysis_mode_settings=AnalysisModeSettings(member_type="beam_girder"),
    )
    assert bridge.code == PROJECT_CODE_AASHTO_LRFD
    assert bridge.code_edition == "AASHTO LRFD 9th Edition"

    building = ProjectModel(
        code="AASHTO LRFD",
        code_edition="AASHTO LRFD 9th Edition",
        analysis_mode_settings=AnalysisModeSettings(member_type="building_beam_girder"),
    )
    assert building.code == PROJECT_CODE_ACI318
    assert building.code_edition == "ACI 318-19"

    column = ProjectModel(
        code="AASHTO LRFD",
        code_edition="AASHTO LRFD 9th Edition",
        analysis_mode_settings=AnalysisModeSettings(member_type="column_pier_pmm"),
    )
    assert column.code == PROJECT_CODE_AASHTO_LRFD


def test_project_page_source_has_workflow_aware_design_code_routing() -> None:
    assert "allowed_project_design_codes_for_workflow" in PROJECT_SOURCE
    assert "Bridge Beam/Girder is AASHTO LRFD only" in PROJECT_SOURCE
    assert "Building Beam/Girder is ACI 318 only" in PROJECT_SOURCE
    assert 'if analysis_mode.member_type == "beam_girder"' in PROJECT_SOURCE
    assert 'elif analysis_mode.member_type == "building_beam_girder"' in PROJECT_SOURCE
