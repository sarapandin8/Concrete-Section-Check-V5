from __future__ import annotations

from types import SimpleNamespace

from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.ui.project_page import (
    DashboardCard,
    _analysis_configuration_cards,
    _compact_panel_html,
    _dashboard_card_html,
    _pre_report_readiness_cards,
    _project_overview_cards,
    _report_foundation_cards,
    _sls_stress_point_cards,
    _summary_item_html,
    status_style_for_value,
)


def test_status_style_for_value_maps_key_project_states() -> None:
    assert status_style_for_value("READY") == "ready"
    assert status_style_for_value("Yes") == "ready"
    assert status_style_for_value("Caution") == "warning"
    assert status_style_for_value("NOT_READY") == "danger"
    assert status_style_for_value("No") == "danger"
    assert status_style_for_value("N/A") == "neutral"


def test_dashboard_card_html_escapes_text_and_marks_status() -> None:
    html = _dashboard_card_html(DashboardCard("Overall <Status>", "NOT_READY", "Review > results", "danger", strong=True))

    assert "cpmm-dashboard-card danger primary" in html
    assert "Overall &lt;Status&gt;" in html
    assert "Review &gt; results" in html
    assert "NOT_READY" in html
    assert "DANGER" in html


def test_dashboard_card_html_omits_badge_for_quiet_cards() -> None:
    html = _dashboard_card_html(DashboardCard("Version", "PS.DB1.2", "", "neutral"))

    assert "cpmm-dashboard-card neutral" in html
    assert "cpmm-status-badge" not in html


def test_summary_item_and_compact_panel_html_are_quiet() -> None:
    summary = _summary_item_html(DashboardCard("Load Cases", "2", "Stored load combinations", "neutral"))
    panel = _compact_panel_html([DashboardCard("Member Type", "General", "Active analysis context", "info")])

    assert "cpmm-summary-strip" in summary
    assert "cpmm-status-badge" not in summary
    assert "cpmm-compact-panel" in panel
    assert "cpmm-kv-row" in panel
    assert "cpmm-status-badge" not in panel


def test_compact_panel_accepts_columns_layout_hint() -> None:
    panel = _compact_panel_html(
        [
            DashboardCard("Member Type", "Beam / Girder", "Active analysis context", "info"),
            DashboardCard("PMM Workflow", "Caution", "ULS/PMM workspace availability", "warning", strong=True),
        ],
        columns=2,
    )

    assert "cpmm-compact-panel" in panel
    assert "cpmm-kv-grid-row" in panel
    assert "Beam / Girder" in panel
    assert "cpmm-status-badge warning" in panel


def test_project_overview_cards_keep_existing_summary_values() -> None:
    cards = _project_overview_cards(
        ProjectModel(version="PS.DB1.2"),
        section_geometry=object(),
        load_cases=[object(), object()],
        rebars=[object()],
        prestress_elements=[],
        rebar_valid=True,
        prestress_valid=None,
    )
    by_title = {card.title: card for card in cards}

    assert by_title["Geometry"].value == "Yes"
    assert by_title["Load Cases"].value == "2"
    assert by_title["Rebars"].detail == "Valid for analysis: Yes"
    assert by_title["Prestress Elements"].detail == "Valid for analysis: N/A"
    assert by_title["Version"].value == "PS.DB1.2"
    assert by_title["Version"].status == "neutral"


def test_analysis_configuration_cards_show_workflow_statuses() -> None:
    settings = AnalysisModeSettings(
        member_type="beam_girder",
    )
    cards = _analysis_configuration_cards(settings)
    by_title = {card.title: card for card in cards}

    assert by_title["Analysis Workflow"].value == "beam_girder_future"
    assert by_title["PMM Workflow"].value == "Caution"
    assert by_title["PMM Workflow"].status == "warning"
    assert by_title["PMM Workflow"].strong is True
    assert by_title["SLS Workflow"].value == "Yes"
    assert by_title["SLS Workflow"].strong is False
    assert by_title["Beam/Girder Workflow"].value == "Future / not implemented"


def test_sls_stress_point_cards_count_custom_and_active_points() -> None:
    cards = _sls_stress_point_cards(
        [SimpleNamespace(active=True), SimpleNamespace(active=False), SimpleNamespace(active=True)],
        include_default_stress_points=False,
    )
    by_title = {card.title: card for card in cards}

    assert by_title["Custom Points"].value == "3"
    assert by_title["Active Custom Points"].value == "2"
    assert by_title["Include Default Stress Points"].value == "No"


def test_pre_report_readiness_cards_preserve_snapshot_values() -> None:
    snapshot = SimpleNamespace(
        pmm_result_available=False,
        sls_result_available=True,
        warning_count=4,
        high_or_critical_limitation_count=2,
    )
    readiness = SimpleNamespace(overall_status="NOT_READY")
    cards = _pre_report_readiness_cards(snapshot, readiness)
    by_title = {card.title: card for card in cards}

    assert by_title["Overall Status"].value == "NOT_READY"
    assert by_title["Overall Status"].status == "danger"
    assert by_title["Overall Status"].strong is True
    assert by_title["ULS PMM Result"].value == "No"
    assert by_title["ULS PMM Result"].strong is True
    assert by_title["SLS Result"].value == "Yes"
    assert by_title["Warning Count"].value == "4"
    assert by_title["Warning Count"].strong is True
    assert by_title["High/Critical Limitations"].value == "2"
    assert by_title["High/Critical Limitations"].status == "danger"
    assert by_title["High/Critical Limitations"].strong is True


def test_report_foundation_cards_count_manifest_items_or_snapshot_fallback() -> None:
    manifest = SimpleNamespace(
        tables=[SimpleNamespace(available=True), SimpleNamespace(available=False)],
        figures=[SimpleNamespace(available=True), SimpleNamespace(available=True)],
        engineering_limitations=[object(), object(), object()],
    )
    snapshot = SimpleNamespace(limitation_count=9)

    cards = _report_foundation_cards(manifest, snapshot)
    by_title = {card.title: card for card in cards}

    assert by_title["Report Manifest"].value == "Yes"
    assert by_title["Available Tables"].value == "1"
    assert by_title["Available Tables"].strong is False
    assert by_title["Available Figures"].value == "2"
    assert by_title["Engineering Limitations"].value == "3"
    assert by_title["Engineering Limitations"].strong is True

    fallback = {card.title: card for card in _report_foundation_cards(None, snapshot)}
    assert fallback["Report Manifest"].value == "No"
    assert fallback["Report Manifest"].strong is True
    assert fallback["Engineering Limitations"].value == "9"


def test_project_page_member_type_selector_source_is_present() -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "concrete_pmm_pro" / "ui" / "project_page.py").read_text(encoding="utf-8")

    assert "Analysis Mode / Member Type" in source
    assert "Beam / Girder - Future Design Workflow" in source
    assert "MEMBER.TYPE1.3 removes ambiguous General Section mode" in source
    assert "project_analysis_mode_member_type_label" in source
    assert '"General Section": "general_section"' not in source
