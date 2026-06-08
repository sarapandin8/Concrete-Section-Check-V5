"""Concrete PMM Pro Streamlit application."""

from __future__ import annotations

import streamlit as st

from concrete_pmm_pro.state.dirty_state import update_dirty_state_from_session
from concrete_pmm_pro.ui.analysis_page import render_analysis_page
from concrete_pmm_pro.ui.loads_page import render_loads_page
from concrete_pmm_pro.ui.materials_page import render_materials_page
from concrete_pmm_pro.ui.prestress_page import render_prestress_page
from concrete_pmm_pro.ui.project_page import render_project_page
from concrete_pmm_pro.ui.rebar_page import render_rebar_page
from concrete_pmm_pro.ui.section_builder import render_section_builder


WORKSPACE_NAVIGATION = {
    "Setup": ["Project", "Materials"],
    "Sections": ["Section Builder", "Rebar", "Prestress"],
    "Loads": ["Loads"],
    "Analysis": ["ULS / PMM", "SLS / Stress & Cracking", "SLS Deflection / Camber", "Report / QA"],
    "Results": ["Results"],
}

RESULTS_WORKSPACE_PLACEHOLDER = (
    "Future Results Workspace. Current result outputs remain available under Analysis. "
    "Future milestones will add Summary Table, Case Details, Interaction Diagram, Charts, and Report Preview."
)


def _safe_choice(label: str, options: list[str], *, key: str, horizontal: bool = True) -> str:
    """Return one selected option without rendering inactive pages.

    Streamlit tabs execute every tab body on each rerun.  PERF.RERUN1 uses a
    segmented/radio choice instead so only the selected workspace/subpage runs.
    This is the key performance gate for heavy Analysis and preview code.
    """

    if not options:
        raise ValueError("Navigation options must not be empty.")
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]
    # Prefer segmented_control when available; fall back to radio for older
    # Streamlit versions and for lightweight test stubs.
    segmented = getattr(st, "segmented_control", None)
    if callable(segmented):
        try:
            value = segmented(label, options, key=key, selection_mode="single")
            if value in options:
                return str(value)
        except TypeError:
            pass
    value = st.radio(label, options, key=key, horizontal=horizontal, label_visibility="collapsed")
    return str(value) if value in options else str(st.session_state.get(key, options[0]))


def render_setup_workspace() -> None:
    active = _safe_choice("Setup workspace", WORKSPACE_NAVIGATION["Setup"], key="_nav_setup_subpage")
    if active == "Project":
        render_project_page()
    elif active == "Materials":
        render_materials_page()


def render_sections_workspace() -> None:
    active = _safe_choice("Sections workspace", WORKSPACE_NAVIGATION["Sections"], key="_nav_sections_subpage")
    if active == "Section Builder":
        render_section_builder()
    elif active == "Rebar":
        render_rebar_page()
    elif active == "Prestress":
        render_prestress_page()


def render_loads_workspace() -> None:
    render_loads_page()


def render_analysis_workspace() -> None:
    render_analysis_page()


def render_results_workspace() -> None:
    st.info(RESULTS_WORKSPACE_PLACEHOLDER)


def main() -> None:
    st.set_page_config(page_title="Concrete PMM Pro", layout="wide")
    st.title("Concrete PMM Pro")
    st.caption(
        "Milestone P.1: Analysis performance audit and runtime control. "
        "Internal units: mm, MPa, N, N-mm."
    )

    update_dirty_state_from_session(st.session_state)

    active_workspace = _safe_choice(
        "Workspace",
        list(WORKSPACE_NAVIGATION.keys()),
        key="_nav_active_workspace",
    )
    if active_workspace == "Setup":
        render_setup_workspace()
    elif active_workspace == "Sections":
        render_sections_workspace()
    elif active_workspace == "Loads":
        render_loads_workspace()
    elif active_workspace == "Analysis":
        render_analysis_workspace()
    elif active_workspace == "Results":
        render_results_workspace()


if __name__ == "__main__":
    main()
