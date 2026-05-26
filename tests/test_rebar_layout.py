from __future__ import annotations

from pathlib import Path

from concrete_pmm_pro.core.models import Point2D, SectionGeometry
from concrete_pmm_pro.ui import rebar_page


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_rebar_page_professional_layout_sections_are_present() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "rebar_page.py").read_text(encoding="utf-8")

    assert "Rebar Input" in source
    assert "Rebar Status" in source
    assert "Rebar Summary" in source
    assert "cpmm-rebar-strip" in source
    assert "st.sidebar" not in source


def test_rebar_summary_strip_helper_escapes_values() -> None:
    html = rebar_page._strip_html([rebar_page.RebarMetric("Total <As>", "400 > 300", "safe & quiet")])

    assert "Total &lt;As&gt;" in html
    assert "400 &gt; 300" in html
    assert "safe &amp; quiet" in html


def test_rebar_validation_source_is_compact() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "rebar_page.py").read_text(encoding="utf-8")

    assert "No validation errors" not in source
    assert "WARNING: none" not in source
    assert "_kv_panel_html" in source


def test_rebar_ratio_uses_existing_section_area() -> None:
    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=-100.0, y=-100.0),
            Point2D(x=100.0, y=-100.0),
            Point2D(x=100.0, y=100.0),
            Point2D(x=-100.0, y=100.0),
        ]
    )

    assert rebar_page._reinforcement_ratio_label(400.0, geometry) == "1.000%"


def test_rebar_ratio_is_na_without_geometry() -> None:
    assert rebar_page._reinforcement_ratio_label(400.0, None) == "N/A"
