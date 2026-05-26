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
    assert "Key Properties" in source
    assert "Geometry Context" in source
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


def test_section_builder_validation_summary_is_compact_source() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "No validation errors" not in source
    assert "WARNING: none" not in source
    assert "_status_panel_html" in source
