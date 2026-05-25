"""Concrete PMM Pro Streamlit application."""

from __future__ import annotations

import streamlit as st

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
    "Analysis": ["ULS / PMM", "SLS / Stress & Cracking", "Report / QA"],
    "Results": ["Results"],
}

RESULTS_WORKSPACE_PLACEHOLDER = (
    "Future Results Workspace. Current result outputs remain available under Analysis. "
    "Future milestones will add Summary Table, Case Details, Interaction Diagram, Charts, and Report Preview."
)


def render_setup_workspace() -> None:
    project_tab, materials_tab = st.tabs(WORKSPACE_NAVIGATION["Setup"])
    with project_tab:
        render_project_page()
    with materials_tab:
        render_materials_page()


def render_sections_workspace() -> None:
    section_tab, rebar_tab, prestress_tab = st.tabs(WORKSPACE_NAVIGATION["Sections"])
    with section_tab:
        render_section_builder()
    with rebar_tab:
        render_rebar_page()
    with prestress_tab:
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

    setup_tab, sections_tab, loads_tab, analysis_tab, results_tab = st.tabs(list(WORKSPACE_NAVIGATION.keys()))
    with setup_tab:
        render_setup_workspace()
    with sections_tab:
        render_sections_workspace()
    with loads_tab:
        render_loads_workspace()
    with analysis_tab:
        render_analysis_workspace()
    with results_tab:
        render_results_workspace()


if __name__ == "__main__":
    main()
