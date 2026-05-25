from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_section_builder_does_not_render_geometry_parameters_in_sidebar() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "with st.sidebar" not in source
    assert "st.sidebar" not in source


def test_app_does_not_reintroduce_sidebar_geometry_parameters() -> None:
    source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")

    assert "Geometry Parameters" not in source
    assert "st.sidebar" not in source


def test_kaleido_dependency_pin_is_preserved() -> None:
    requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "kaleido==0.2.1" in requirements
