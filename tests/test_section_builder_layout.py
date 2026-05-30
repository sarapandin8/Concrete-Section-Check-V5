from __future__ import annotations

from pathlib import Path

from concrete_pmm_pro.geometry.presets import preset_by_key
from concrete_pmm_pro.ui import section_builder


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_section_builder_professional_layout_sections_are_present() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "Section Definition" in source
    assert "Live Section Preview" in source
    assert "Section Properties" in source
    assert "cpmm-section-property-grid" in source
    assert "Geometry Parameters" in source
    assert "st.sidebar" not in source


def test_section_builder_keeps_rectangle_geometry_generation_path() -> None:
    preset = preset_by_key("rectangle")

    geometry, dimensions, validation = section_builder._build_geometry(preset, {"width_mm": 400.0, "height_mm": 600.0})

    assert validation.is_valid
    assert validation.errors == []
    assert geometry is not None
    assert geometry.name == "Rectangle"
    assert len(dimensions) > 0


def test_rectangle_width_height_remain_section_builder_parameters() -> None:
    rectangle = preset_by_key("rectangle")
    labels = [parameter["label"] for parameter in rectangle["parameters"]]

    assert "Width B (mm)" in labels
    assert "Height H (mm)" in labels


def test_section_builder_status_panel_helper_escapes_values() -> None:
    html = section_builder._status_panel_html(
        [section_builder.SectionMetric("Area <gross>", "400 > 300", "safe & escaped", "info", strong=True)]
    )

    assert "Area &lt;gross&gt;" in html
    assert "400 &gt; 300" in html


def test_section_builder_property_strip_helper_escapes_values() -> None:
    html = section_builder._property_strip_html(
        [section_builder.SectionMetric("Preset <A>", "Rect > Box", "quiet & compact")]
    )

    assert "cpmm-section-property-grid" in html
    assert "Preset &lt;A&gt;" in html
    assert "Rect &gt; Box" in html
    assert "quiet &amp; compact" in html


def test_section_builder_properties_are_compact_strip_source() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "_property_strip_html" in source
    assert "Gross Area" in source
    assert "Centroid" in source
    assert "Holes / Voids" in source
    assert "Readiness" in source
    assert "Key Properties" not in source
    assert "Geometry Context" not in source


def test_section_builder_validation_summary_is_compact_source() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "No validation errors" not in source
    assert "WARNING: none" not in source
    assert "_status_panel_html" in source


def test_section_property_clarity_labels_are_present() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "Precast Gross Section Properties" in source
    assert "Composite slab/topping properties are metadata" in source
    assert "Centroid yb" in source
    assert "from bottom fiber" in source
    assert "ctop" in source
    assert "cbottom" in source
    assert "Section property convention" in source
    assert "Tslab, Be, n, and Btransformed are not merged" in source

