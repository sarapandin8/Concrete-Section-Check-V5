from __future__ import annotations

import json

from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.core.analysis_modes import (
    analysis_mode_description,
    analysis_mode_label,
    analysis_mode_warnings,
    is_beam_girder_future_workflow,
    is_pmm_primary_workflow,
)
from concrete_pmm_pro.core.models import BeamGirderLoadCase
from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.io.project_io import project_from_json, project_to_json


def test_analysis_mode_settings_default_is_column_pier_pmm() -> None:
    settings = AnalysisModeSettings()

    assert settings.member_type == "column_pier_pmm"
    assert settings.analysis_workflow == "pmm_section"


def test_column_pier_pmm_maps_to_pmm_section_workflow() -> None:
    settings = AnalysisModeSettings(member_type="column_pier_pmm", analysis_workflow="beam_girder_future")

    assert settings.analysis_workflow == "pmm_section"
    assert settings.allow_pmm_workflow is True
    assert settings.allow_sls_workflow is True
    assert settings.allow_beam_girder_placeholder is False


def test_beam_girder_maps_to_future_workflow() -> None:
    settings = AnalysisModeSettings(member_type="beam_girder")

    assert settings.analysis_workflow == "beam_girder_future"
    assert settings.allow_pmm_workflow is False
    assert settings.allow_sls_workflow is True
    assert settings.allow_beam_girder_placeholder is True


def test_general_section_maps_to_general_section_workflow() -> None:
    settings = AnalysisModeSettings(member_type="general_section")

    assert settings.analysis_workflow == "general_section"
    assert settings.allow_pmm_workflow is True
    assert settings.allow_sls_workflow is True


def test_analysis_mode_label_returns_readable_label() -> None:
    assert "Column" in analysis_mode_label(AnalysisModeSettings())
    assert "Beam" in analysis_mode_label(AnalysisModeSettings(member_type="beam_girder"))


def test_analysis_mode_description_returns_non_empty_description() -> None:
    assert analysis_mode_description(AnalysisModeSettings())
    assert analysis_mode_description(AnalysisModeSettings(member_type="general_section"))


def test_is_pmm_primary_workflow_true_for_column_pier_pmm() -> None:
    assert is_pmm_primary_workflow(AnalysisModeSettings()) is True


def test_is_pmm_primary_workflow_false_for_beam_girder() -> None:
    assert is_pmm_primary_workflow(AnalysisModeSettings(member_type="beam_girder")) is False
    assert is_beam_girder_future_workflow(AnalysisModeSettings(member_type="beam_girder")) is True


def test_analysis_mode_warnings_for_beam_girder_include_double_count_warning() -> None:
    warnings = analysis_mode_warnings(AnalysisModeSettings(member_type="beam_girder"))

    assert any("double-count prestress" in warning for warning in warnings)
    assert any("not implemented" in warning for warning in warnings)


def test_general_section_warning_mentions_load_interpretation() -> None:
    warnings = analysis_mode_warnings(AnalysisModeSettings(member_type="general_section"))

    assert any("Pu, Mux, and Muy" in warning for warning in warnings)


def test_project_model_save_load_preserves_analysis_mode_settings() -> None:
    project = ProjectModel(analysis_mode_settings=AnalysisModeSettings(member_type="beam_girder", note="future beam workflow"))

    loaded = project_from_json(project_to_json(project))

    assert loaded.analysis_mode_settings is not None
    assert loaded.analysis_mode_settings.member_type == "beam_girder"
    assert loaded.analysis_mode_settings.analysis_workflow == "beam_girder_future"
    assert loaded.analysis_mode_settings.note == "future beam workflow"


def test_old_project_json_without_analysis_mode_settings_loads_default() -> None:
    loaded = project_from_json(json.dumps({"project_name": "Legacy"}))

    assert loaded.analysis_mode_settings is not None
    assert loaded.analysis_mode_settings.member_type == "column_pier_pmm"


def test_beam_girder_load_case_placeholder_defaults() -> None:
    load_case = BeamGirderLoadCase()

    assert load_case.stage == "service"
    assert load_case.Mu_Nmm == 0.0
    assert load_case.active is True


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")


def test_project_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.project_page as project_page

    assert hasattr(project_page, "render_project_page")
