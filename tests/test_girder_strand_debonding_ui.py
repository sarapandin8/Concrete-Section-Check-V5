from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESTRESS_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "prestress_page.py").read_text(encoding="utf-8")
PROJECT_IO_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "io" / "project_io.py").read_text(encoding="utf-8")


def test_prestress_page_contains_strand_layout_debonding_workflow() -> None:
    assert "Simple-Supported Girder Strand Layout & Debonding" in PRESTRESS_SOURCE
    assert "girder_strand_layout_table" in PRESTRESS_SOURCE
    assert "Left debond m" in PRESTRESS_SOURCE
    assert "Right debond m" in PRESTRESS_SOURCE
    assert "Effective prestress preview" in PRESTRESS_SOURCE
    assert "12.7 mm low-relaxation strand" in PRESTRESS_SOURCE
    assert "15.2 mm low-relaxation strand" in PRESTRESS_SOURCE
    assert "PS6A supports optional individual bonded/unbonded strand selection within a row" in PRESTRESS_SOURCE
    assert "Computed spacing_mm" in PRESTRESS_SOURCE
    assert "3db minimum spacing" in PRESTRESS_SOURCE
    assert "reduce the number of strands in this row" in PRESTRESS_SOURCE
    assert "Transfer/development length transition is not modeled" in PRESTRESS_SOURCE
    assert "does not change current Analysis results" in PRESTRESS_SOURCE
    assert "Rebuild default strand layout from current section" in PRESTRESS_SOURCE
    assert "Box/Plank presets use practical BP1 layouts" in PRESTRESS_SOURCE
    assert "Strand x positions mm" in PRESTRESS_SOURCE
    assert '"Strand x positions mm",\n    "y_mm_from_bottom"' in PRESTRESS_SOURCE
    assert "🟨 x coordinates (mm)" in PRESTRESS_SOURCE
    assert "_format_mm_compact" in PRESTRESS_SOURCE
    assert 'format="%.0f"' in PRESTRESS_SOURCE
    assert "_auto_strand_x_positions_text" in PRESTRESS_SOURCE
    assert "Option 2 spaced symmetric pairs" in PRESTRESS_SOURCE
    assert 'line={"color": section_line_color, "width": 2.0, "dash": "solid"}' in PRESTRESS_SOURCE
    assert 'name="Bonded"' in PRESTRESS_SOURCE
    assert 'name="Debonded"' in PRESTRESS_SOURCE
    assert "diamond-open" in PRESTRESS_SOURCE
    assert 'xanchor="left"' in PRESTRESS_SOURCE
    assert "label_gap = max(340.0" in PRESTRESS_SOURCE
    assert "on_change=_sync_girder_strand_layout_editor_to_table" in PRESTRESS_SOURCE
    assert "Row 1 at the bottom" in PRESTRESS_SOURCE
    assert "_girder_debonding_schedule_dataframe" in PRESTRESS_SOURCE
    assert "Advisory recommendation" in PRESTRESS_SOURCE
    assert "Apply advisory layout to strand table" in PRESTRESS_SOURCE
    assert "girder_advisory_debonding_recommendation_dataframe" in PRESTRESS_SOURCE
    assert "Debonding QA" in PRESTRESS_SOURCE
    assert "_render_girder_debonding_rule_dashboard" in PRESTRESS_SOURCE
    assert "Debonding rule audit — individual preview" in PRESTRESS_SOURCE
    assert "Critical transfer station audit" in PRESTRESS_SOURCE
    assert "Stage Pe mapping audit" in PRESTRESS_SOURCE
    assert "SLS feed" in PRESTRESS_SOURCE
    assert "girder_stage_pe_mapping_dataframe" in PRESTRESS_SOURCE
    assert 'type="primary"' in PRESTRESS_SOURCE
    assert "Select one loss input mode at a time" in PRESTRESS_SOURCE
    assert "Apply manual / percentage force states to strand table" in PRESTRESS_SOURCE
    assert "Approximate code-based loss" in PRESTRESS_SOURCE
    assert "Only this manual/percentage workspace is active in the current mode" in PRESTRESS_SOURCE
    assert "The Calculate-and-use action is the single source of truth for this mode" in PRESTRESS_SOURCE
    assert "No separate Apply button is required in this mode" in PRESTRESS_SOURCE
    assert "Code-Based Loss Estimate" in PRESTRESS_SOURCE
    assert "Calculate and use approximate losses" in PRESTRESS_SOURCE
    assert "Refined AASHTO time-dependent loss" in PRESTRESS_SOURCE
    assert "Calculate and use refined AASHTO losses" in PRESTRESS_SOURCE
    assert "🟨 fpj / fpu" in PRESTRESS_SOURCE
    assert "DEFAULT_CODE_LOSS_FPJ_RATIO = 0.75" in PRESTRESS_SOURCE
    assert "Jacking stress assumption: fpj" in PRESTRESS_SOURCE
    assert "derive Pjack per strand from fpj ratio" in PRESTRESS_SOURCE
    assert "auto-estimated refined AASHTO coefficients" in PRESTRESS_SOURCE or "auto-estimates creep/shrinkage/Kid/Kdf" in PRESTRESS_SOURCE
    assert "Thailand high humidity typical (RH ≈ 75%)" in PRESTRESS_SOURCE
    assert "Moderate humidity (RH ≈ 60%)" in PRESTRESS_SOURCE
    assert "Dry climate conservative (RH ≈ 45%)" in PRESTRESS_SOURCE
    assert "Preset coefficient guide" in PRESTRESS_SOURCE
    assert "Refined coefficient REVIEW" in PRESTRESS_SOURCE
    assert "Auto-estimated from RH/time/section" in PRESTRESS_SOURCE
    assert "LOSS3B auto-estimates creep/shrinkage/Kid/Kdf" in PRESTRESS_SOURCE
    assert "These are practical starter values for the LOSS3B refined workflow" in PRESTRESS_SOURCE
    assert "Apply calculated losses to force states and strand table" not in PRESTRESS_SOURCE
    assert "girder_prestress_code_loss_settings" in PRESTRESS_SOURCE
    assert "calculate_approximate_prestress_loss" in PRESTRESS_SOURCE
    assert "calculate_refined_aashto_time_dependent_loss" in PRESTRESS_SOURCE
    assert "estimate_refined_aashto_coefficients" in PRESTRESS_SOURCE
    assert "V/S override" in PRESTRESS_SOURCE
    assert "Δfcd source" in PRESTRESS_SOURCE
    assert "Δfcdf source" in PRESTRESS_SOURCE
    assert "Not included / use 0.00 MPa" in PRESTRESS_SOURCE
    assert "Manual input" in PRESTRESS_SOURCE
    assert "Auto from Loads / staged effects (future)" in PRESTRESS_SOURCE
    assert "Δfcd / Δfcdf guidance" in PRESTRESS_SOURCE



def test_refined_coefficient_presets_are_rh_labeled_and_practical(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        DEFAULT_REFINED_COEFFICIENT_PRESET,
        REFINED_COEFFICIENT_PRESETS,
        _apply_refined_coefficient_preset,
        _refined_coefficient_review_messages,
    )

    thailand = REFINED_COEFFICIENT_PRESETS[DEFAULT_REFINED_COEFFICIENT_PRESET]
    assert thailand["humidity_percent"] == 75.0
    assert thailand["Kid"] == 0.85
    assert thailand["eps_bid_microstrain"] == 80.0
    settings = _apply_refined_coefficient_preset({}, DEFAULT_REFINED_COEFFICIENT_PRESET)
    assert settings["humidity_percent"] == 75.0
    assert settings["psi_tf_ti"] == 1.60
    default_messages = _refined_coefficient_review_messages(settings)
    assert any("Δfcd is not included" in message for message in default_messages)
    assert any("Δfcdf is not included" in message for message in default_messages)

    settings_manual_effects = dict(settings)
    settings_manual_effects.update({"delta_fcd_source": "Manual input", "delta_fcdf_source": "Manual input"})
    assert _refined_coefficient_review_messages(settings_manual_effects) == []

    risky = dict(settings_manual_effects)
    risky.update({"eps_bid_microstrain": 180.0, "eps_bdf_microstrain": 110.0, "psi_tf_ti": 2.8})
    messages = _refined_coefficient_review_messages(risky)
    assert any("Shrinkage strain sum" in message for message in messages)
    assert any("Ψb(tf,ti)" in message for message in messages)


def test_refined_deck_sdl_stress_effect_audit_flags_not_included() -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    sys.modules["streamlit"] = st

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        REFINED_STRESS_EFFECT_MANUAL,
        REFINED_STRESS_EFFECT_NOT_INCLUDED,
        _refined_stress_effect_input_dataframe,
    )

    df = _refined_stress_effect_input_dataframe(
        {
            "delta_fcd_source": REFINED_STRESS_EFFECT_NOT_INCLUDED,
            "delta_fcdf_source": REFINED_STRESS_EFFECT_MANUAL,
            "delta_fcd_MPa": 0.0,
            "delta_fcdf_MPa": 0.25,
        }
    )
    assert df.loc[df["Effect"] == "Δfcd", "Status"].iloc[0] == "REVIEW"
    assert df.loc[df["Effect"] == "Δfcdf", "Status"].iloc[0] == "READY"
    assert df.loc[df["Effect"] == "Δfcdf", "Value MPa"].iloc[0] == 0.25


def test_code_based_loss_groups_derive_pjack_from_fpj_ratio(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_approximate_loss_groups_from_tables,
    )

    strand_table = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "Area/Strand_mm2": 98.7,
                "y_mm_from_bottom": 50.0,
            }
        ]
    )
    force_table = pd.DataFrame([{ "Group ID": "Row 1", "Pjack/strand_kN": 999.0 }])
    groups = _girder_approximate_loss_groups_from_tables(strand_table, force_table, fpj_ratio=0.75)
    assert len(groups) == 1
    assert round(groups[0].pjack_per_strand_kN, 3) == round(0.75 * 1860.0 * 98.7 / 1000.0, 3)



def test_project_io_preserves_girder_strand_layout_metadata_source() -> None:
    assert "girder_strand_layout_table" in PROJECT_IO_SOURCE
    assert "girder_prestress_system_settings" in PROJECT_IO_SOURCE
    assert "_girder_strand_layout_metadata_from_session" in PROJECT_IO_SOURCE


def test_strand_layout_normalization_and_station_preview_with_streamlit_stub(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_effective_prestress_preview_dataframe,
        _girder_strand_point_layout_dataframe,
        _normalize_girder_strand_layout_table,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "Strand Size": "15.2 mm low-relaxation strand",
                "No. Strands": 2,
                "Area/Strand_mm2": 140.0,
                "y_mm_from_bottom": 100.0,
                "Pe_transfer/strand_kN": 150.0,
                "Pe_construction/strand_kN": 140.0,
                "Pe_eff_final/strand_kN": 120.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            },
            {
                "Active": True,
                "Group ID": "Row 2",
                "Strand Size": "15.2 mm low-relaxation strand",
                "No. Strands": 2,
                "Area/Strand_mm2": 140.0,
                "y_mm_from_bottom": 200.0,
                "Pe_transfer/strand_kN": 150.0,
                "Pe_construction/strand_kN": 140.0,
                "Pe_eff_final/strand_kN": 120.0,
                "Left debond m": 3.0,
                "Right debond m": 3.0,
            },
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=10.0)
    assert table.loc[0, "Total Aps_mm2"] == 280.0
    assert table.loc[1, "Total Aps_mm2"] == 280.0

    preview = _girder_effective_prestress_preview_dataframe(table, 10.0).set_index("x_m")
    assert preview.loc[0.0, "Effective strands"] == 2
    assert preview.loc[5.0, "Effective strands"] == 4
    assert preview.loc[5.0, "Pe_transfer_eff_kN"] == 600.0
    assert preview.loc[5.0, "yps_eff_mm_from_bottom"] == 150.0

    points = _girder_strand_point_layout_dataframe(table, None)
    assert len(points) == 4
    assert set(points["Group ID"]) == {"Row 1", "Row 2"}


def test_longitudinal_debonding_plot_shows_sleeve_symbols_with_streamlit_stub(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _normalize_girder_strand_layout_table,
        _plot_girder_longitudinal_debonding_layout,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Debonded row",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "Area/Strand_mm2": 98.7,
                "y_mm_from_bottom": 50.0,
                "Left debond m": 1.0,
                "Right debond m": 2.0,
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=10.0)
    fig = _plot_girder_longitudinal_debonding_layout(table, span_length_m=10.0)
    trace_names = [trace.name for trace in fig.data]
    marker_symbols = [getattr(getattr(trace, "marker", None), "symbol", None) for trace in fig.data]

    assert "Debonded" in trace_names
    assert "Bonded" in trace_names
    assert "diamond-open" in marker_symbols
    assert any(annotation.text == "L=1.00 m" for annotation in fig.layout.annotations)
    assert any(annotation.text == "R=2.00 m" for annotation in fig.layout.annotations)
    bonded_traces = [trace for trace in fig.data if trace.name == "Bonded"]
    assert bonded_traces
    assert all(trace.line.color == "#1f77b4" for trace in bonded_traces)


def test_cross_section_plot_and_debond_schedule_show_row_debond_status(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_debonding_schedule_dataframe,
        _normalize_girder_strand_layout_table,
        _plot_girder_strand_cross_section_layout,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "y_mm_from_bottom": 50.0,
                "Left debond m": 1.0,
                "Right debond m": 1.0,
            },
            {
                "Active": True,
                "Group ID": "Row 2",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "y_mm_from_bottom": 100.0,
                "Left debond m": 0.0,
                "Right debond m": 2.0,
            },
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=10.0)
    fig = _plot_girder_strand_cross_section_layout(table, None)
    trace_names = [trace.name for trace in fig.data]
    assert "Bonded" in trace_names or "Debonded" in trace_names
    label_texts = [annotation.text for annotation in fig.layout.annotations]
    assert any(getattr(annotation, "xanchor", None) == "left" for annotation in fig.layout.annotations)
    assert all("<br>" not in label for label in label_texts)
    assert any("Row 1 · total 2 · B=0 · U=2 · Debonded both ends · L=1.00 m · R=1.00 m" == label for label in label_texts)

    schedule = _girder_debonding_schedule_dataframe(table, span_length_m=10.0)
    assert schedule.loc[0, "Debond status"] == "Debonded both ends"
    assert schedule.loc[0, "Left debond m"] == 1.0
    assert schedule.loc[0, "Right debond m"] == 1.0
    assert schedule.loc[1, "Debond status"] == "Right debonded"
    assert schedule.loc[1, "Bonded zone m"] == "0.000 → 8.000"




def test_cross_section_plot_shows_individual_bonded_and_debonded_points(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_debonding_schedule_dataframe,
        _girder_strand_point_layout_dataframe,
        _normalize_girder_strand_layout_table,
        _plot_girder_strand_cross_section_layout,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 6,
                "y_mm_from_bottom": 50.0,
                "Left debond m": 1.0,
                "Right debond m": 1.0,
                "Debonded strand nos": "1,6",
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=10.0)
    points = _girder_strand_point_layout_dataframe(table, None)
    assert points["Debonded selected"].tolist().count(True) == 2
    assert points["Debonded selected"].tolist().count(False) == 4

    fig = _plot_girder_strand_cross_section_layout(table, None)
    trace_names = [trace.name for trace in fig.data]
    assert "Bonded" in trace_names
    assert "Debonded" in trace_names
    assert any("B=4 · U=2" in annotation.text for annotation in fig.layout.annotations)

    schedule = _girder_debonding_schedule_dataframe(table, 10.0)
    assert schedule.loc[0, "Bonded strands"] == 4
    assert schedule.loc[0, "Debonded strands"] == 2
    assert schedule.loc[0, "Debonded strand nos"] == "1, 6"
    assert schedule.loc[0, "Selection mode"] == "Individual"

def test_data_editor_patch_payload_persists_first_edit_without_dataframe_value_error(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    import concrete_pmm_pro.ui.prestress_page as prestress_page  # noqa: PLC0415

    _data_editor_payload_to_dataframe = prestress_page._data_editor_payload_to_dataframe
    _normalize_girder_strand_layout_table = prestress_page._normalize_girder_strand_layout_table
    _sync_girder_strand_layout_editor_to_table = prestress_page._sync_girder_strand_layout_editor_to_table

    base = _normalize_girder_strand_layout_table(
        pd.DataFrame(
            [
                {
                    "Active": True,
                    "Group ID": "Row 1",
                    "Strand Size": "12.7 mm low-relaxation strand",
                    "No. Strands": 19,
                    "y_mm_from_bottom": 50.0,
                    "Left debond m": 0.0,
                    "Right debond m": 0.0,
                }
            ]
        ),
        span_length_m=30.0,
    )
    prestress_page.st.session_state.clear()
    prestress_page.st.session_state["girder_strand_layout_table"] = base
    prestress_page.st.session_state["girder_strand_layout_editor"] = {
        "edited_rows": {0: {"Left debond m": 1.5, "Right debond m": 1.0}},
        "added_rows": [],
        "deleted_rows": [],
    }

    patched = _data_editor_payload_to_dataframe(prestress_page.st.session_state["girder_strand_layout_editor"], base)
    assert patched.loc[0, "Left debond m"] == 1.5
    assert patched.loc[0, "Right debond m"] == 1.0

    _sync_girder_strand_layout_editor_to_table(30.0, "Left/right independent", None)
    saved = prestress_page.st.session_state["girder_strand_layout_table"]
    assert saved.loc[0, "Left debond m"] == 1.5
    assert saved.loc[0, "Right debond m"] == 1.0



def test_data_editor_patch_payload_persists_first_x_coordinate_edit(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    import concrete_pmm_pro.ui.prestress_page as prestress_page  # noqa: PLC0415

    base = prestress_page._normalize_girder_strand_layout_table(
        pd.DataFrame(
            [
                {
                    "Active": True,
                    "Group ID": "Row 1",
                    "Strand Size": "12.7 mm low-relaxation strand",
                    "No. Strands": 4,
                    "Strand x positions mm": "-75,-25,25,75",
                    "y_mm_from_bottom": 50.0,
                }
            ]
        ),
        span_length_m=30.0,
    )
    prestress_page.st.session_state.clear()
    prestress_page.st.session_state["girder_strand_layout_table"] = base
    prestress_page.st.session_state["girder_strand_layout_editor"] = {
        "edited_rows": {0: {"Strand x positions mm": "-90,-30,30,90"}},
        "added_rows": [],
        "deleted_rows": [],
    }

    prestress_page._sync_girder_strand_layout_editor_to_table(30.0, "Left/right independent", None)
    saved = prestress_page.st.session_state["girder_strand_layout_table"]
    assert saved.loc[0, "Strand x positions mm"] == "-90,-30,30,90"
    points = prestress_page._girder_strand_point_layout_dataframe(saved, None)
    assert points["x_mm"].tolist() == [-90.0, -30.0, 30.0, 90.0]



def test_longitudinal_plot_orders_row_1_at_bottom_and_hides_termination_text(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _normalize_girder_strand_layout_table,
        _plot_girder_longitudinal_debonding_layout,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "y_mm_from_bottom": 50.0,
                "Left debond m": 1.0,
                "Right debond m": 1.0,
            },
            {
                "Active": True,
                "Group ID": "Row 2",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "y_mm_from_bottom": 100.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            },
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=10.0)
    fig = _plot_girder_longitudinal_debonding_layout(table, span_length_m=10.0)
    assert list(fig.layout.yaxis.tickvals) == [1, 2]
    assert fig.layout.yaxis.ticktext[0].startswith("Row 1")
    assert all("termination" not in str(getattr(trace, "text", "")).lower() for trace in fig.data)



def test_girder_strand_default_size_is_12_7_mm_with_auto_area(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        DEFAULT_GIRDER_STRAND_SIZE,
        _normalize_girder_strand_layout_table,
    )

    table = _normalize_girder_strand_layout_table(None, span_length_m=30.0)
    assert DEFAULT_GIRDER_STRAND_SIZE == "12.7 mm low-relaxation strand"
    assert set(table["Strand Size"]) == {"12.7 mm low-relaxation strand"}
    assert table.loc[0, "Area/Strand_mm2"] == 98.7
    assert len(table.index) == 2
    assert table["y_mm_from_bottom"].tolist() == [50.0, 100.0]
    assert table["No. Strands"].tolist() == [8, 6]
    assert table.loc[0, "Total Aps_mm2"] == 8 * 98.7
    assert table.loc[0, "Edge CL_mm"] == 45.0
    assert table.loc[0, "Min spacing_mm"] == 50.0



def test_generic_girder_defaults_expose_editable_x_coordinate_list(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        GIRDER_STRAND_LAYOUT_EDITOR_COLUMNS,
        _normalize_girder_strand_layout_table,
        _parse_explicit_x_positions,
    )

    table = _normalize_girder_strand_layout_table(None, span_length_m=30.0)
    assert GIRDER_STRAND_LAYOUT_EDITOR_COLUMNS.index("Strand x positions mm") < GIRDER_STRAND_LAYOUT_EDITOR_COLUMNS.index("y_mm_from_bottom")
    assert "Pe_transfer/strand_kN" not in GIRDER_STRAND_LAYOUT_EDITOR_COLUMNS
    assert "Pe_construction/strand_kN" not in GIRDER_STRAND_LAYOUT_EDITOR_COLUMNS
    assert "Pe_eff_final/strand_kN" not in GIRDER_STRAND_LAYOUT_EDITOR_COLUMNS
    first_count = int(table.loc[0, "No. Strands"])
    coords = _parse_explicit_x_positions(table.loc[0, "Strand x positions mm"], first_count)
    assert len(coords) == first_count
    assert coords == sorted(coords)



def test_strand_x_coordinates_are_shown_as_compact_integer_mm(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _format_explicit_x_positions,
        _normalize_girder_strand_layout_table,
    )

    assert _format_explicit_x_positions([-75.0, -25.0, 25.0, 75.0]) == "-75,-25,25,75"

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 4,
                "Strand x positions mm": "-75.000,-25.000,25.000,75.000",
                "y_mm_from_bottom": 50.0,
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=30.0)
    assert table.loc[0, "Strand x positions mm"] == "-75,-25,25,75"



def test_section_based_default_strand_layout_uses_current_section_width(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.core.models import Point2D, SectionGeometry  # noqa: PLC0415
    from concrete_pmm_pro.ui.prestress_page import _normalize_girder_strand_layout_table  # noqa: PLC0415

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=-300.0, y=-300.0),
            Point2D(x=300.0, y=-300.0),
            Point2D(x=300.0, y=300.0),
            Point2D(x=-300.0, y=300.0),
        ]
    )

    table = _normalize_girder_strand_layout_table(None, span_length_m=30.0, geometry=geometry)

    assert len(table.index) == 2
    assert table["No. Strands"].tolist() == [11, 11]
    assert table["y_mm_from_bottom"].tolist() == [50.0, 100.0]
    assert set(table["Strand Size"]) == {"12.7 mm low-relaxation strand"}

def test_girder_strand_size_controls_spacing_and_edge_clearance(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_strand_point_layout_dataframe,
        _normalize_girder_strand_layout_table,
        _validate_girder_strand_layout,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "15.2 row",
                "Strand Size": "15.2 mm low-relaxation strand",
                "No. Strands": 8,
                "Edge CL_mm": 50.0,
                "Min spacing_mm": 50.0,
                "y_mm_from_bottom": 100.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=20.0)
    assert table.loc[0, "Edge CL_mm"] == 45.0
    assert table.loc[0, "Min spacing_mm"] == 55.0

    errors, warnings = _validate_girder_strand_layout(table, span_length_m=20.0, geometry=None)
    assert errors == []
    assert all("less than minimum" not in warning for warning in warnings)


def test_girder_strand_layout_ui_is_gated_to_beam_girder_preset(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.core.models import PrestressElement  # noqa: PLC0415
    import concrete_pmm_pro.ui.prestress_page as prestress_page  # noqa: PLC0415

    prestress_page.st.session_state = {"analysis_mode_settings": {"member_type": "column_pier_pmm"}, "section_preset_key": "parametric_i_girder"}
    assert not prestress_page._is_girder_prestress_layout_workflow_active()

    prestress_page.st.session_state = {"analysis_mode_settings": {"member_type": "beam_girder"}, "section_preset_key": "rectangle"}
    assert not prestress_page._is_girder_prestress_layout_workflow_active()

    prestress_page.st.session_state = {"analysis_mode_settings": {"member_type": "beam_girder"}, "section_preset_key": "parametric_i_girder"}
    assert prestress_page._is_girder_prestress_layout_workflow_active()

    passive = PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=0, initial_stress_mpa=0, initial_strain=0)
    active = PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=1000, initial_stress_mpa=10, initial_strain=10 / 195000)
    assert not prestress_page._has_active_prestress_force([passive])
    assert prestress_page._has_active_prestress_force([active])


def test_default_prestress_rows_are_inactive_examples() -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    sys.modules.setdefault("streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import _default_prestress_table, load_prestress_steel_database  # noqa: PLC0415

    table = _default_prestress_table(load_prestress_steel_database())
    assert table["Active"].tolist() == [False, False]


def test_girder_strand_points_are_center_out_not_edge_spread(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_strand_point_layout_dataframe,
        _normalize_girder_strand_layout_table,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Two center strands",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "Row center x_mm": 0.0,
                "y_mm_from_bottom": 100.0,
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=20.0)
    points = _girder_strand_point_layout_dataframe(table, geometry=None).sort_values("x_mm")

    assert points["x_mm"].round(6).tolist() == [-25.0, 25.0]
    assert points["Computed spacing_mm"].tolist() == [50.0, 50.0]


def test_prestress_source_contains_compact_strand_editor_and_rerun_guard() -> None:
    assert "GIRDER_STRAND_LAYOUT_EDITOR_COLUMNS" in PRESTRESS_SOURCE
    assert "Left debond m" in PRESTRESS_SOURCE
    assert "Right debond m" in PRESTRESS_SOURCE
    assert "_store_girder_strand_layout_and_rerun_on_change" in PRESTRESS_SOURCE
    assert "centerline outward" in PRESTRESS_SOURCE
    assert "🟨" in PRESTRESS_SOURCE


def test_box_beam_default_strand_layout_passes_void_aware_validation(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.geometry.generators import box_section_fillet, precast_box_beam_exterior  # noqa: PLC0415
    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_strand_point_layout_dataframe,
        _normalize_girder_strand_layout_table,
        _validate_girder_strand_layout,
    )

    geometries = [
        box_section_fillet(
            width_mm=990,
            height_mm=700,
            h1_mm=180,
            h3_mm=160,
            h4_mm=80,
            h5_mm=200,
            h6_mm=300,
            h7_mm=400,
            h8_mm=70,
            b2_mm=100,
            b3_mm=290,
            b4_mm=70,
        ),
        precast_box_beam_exterior(
            width_mm=990,
            height_mm=700,
            h1_mm=180,
            h3_mm=160,
            h4_mm=80,
            h5_mm=200,
            h6_mm=300,
            h7_mm=400,
            h8_mm=70,
            b2_mm=100,
            b3_mm=360,
            b4_mm=70,
        ),
    ]
    for geometry in geometries:
        table = _normalize_girder_strand_layout_table(None, span_length_m=20.0, geometry=geometry)
        errors, warnings = _validate_girder_strand_layout(table, span_length_m=20.0, geometry=geometry)
        assert errors == []
        assert warnings == []
        assert table["y_mm_from_bottom"].tolist() == [50.0, 100.0, 650.0]
        assert table["No. Strands"].tolist() == [18, 6, 2]
        assert table.loc[0, "Debonded strand nos"] == "1,3,16,18"
        assert table.loc[0, "Left debond m"] == 1.0
        assert table.loc[0, "Right debond m"] == 1.0
        assert table.loc[1, "Debonded strand nos"] == ""
        assert table.loc[2, "Debonded strand nos"] == ""
        points = _girder_strand_point_layout_dataframe(table, geometry)
        row2_x = points.loc[points["Group ID"] == "Row 2", "x_mm"].round(6).tolist()
        row3_x = points.loc[points["Group ID"] == "Row 3", "x_mm"].round(6).tolist()
        assert row2_x == [-350.0, -210.0, -70.0, 70.0, 210.0, 350.0]
        assert row3_x == [-350.0, 350.0]



def test_bp1_plank_practical_preset_uses_user_confirmed_layout(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.geometry.generators import parametric_plank_girder_interior  # noqa: PLC0415
    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_strand_point_layout_dataframe,
        _normalize_girder_strand_layout_table,
    )

    geometry = parametric_plank_girder_interior(
        B_mm=990,
        b1_mm=45,
        b2_mm=70,
        b3_mm=850,
        H_mm=450,
        h1_mm=80,
        h2_mm=140,
        Tslab_mm=100,
        Be_mm=1000,
        Ebeam_MPa=35000,
        Edeck_MPa=28560,
        girder_length_mm=12000,
    )
    table = _normalize_girder_strand_layout_table(None, span_length_m=30.0, geometry=geometry)
    assert table["Group ID"].tolist() == ["Row 1", "Row 2"]
    assert table["No. Strands"].tolist() == [16, 2]
    assert table["y_mm_from_bottom"].tolist() == [50.0, 400.0]
    assert table.loc[0, "Debonded strand nos"] == "1,3,14,16"
    assert table.loc[0, "Left debond m"] == 1.0
    assert table.loc[0, "Right debond m"] == 1.0

    points = _girder_strand_point_layout_dataframe(table, geometry)
    row1_x = points.loc[points["Group ID"] == "Row 1", "x_mm"].round(6).tolist()
    row2_x = points.loc[points["Group ID"] == "Row 2", "x_mm"].round(6).tolist()
    assert row1_x == [-425.0, -375.0, -325.0, -275.0, -225.0, -175.0, -125.0, -75.0, 75.0, 125.0, 175.0, 225.0, 275.0, 325.0, 375.0, 425.0]
    assert row2_x == [-375.0, 375.0]
    assert 0.0 not in row1_x



def test_bp1_exterior_plank_top_pair_uses_190_mm_edge_offset(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.geometry.generators import parametric_plank_girder_exterior  # noqa: PLC0415
    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_strand_point_layout_dataframe,
        _normalize_girder_strand_layout_table,
    )

    geometry = parametric_plank_girder_exterior(
        B_mm=990,
        b1_mm=45,
        b2_mm=140,
        b3_mm=850,
        H_mm=450,
        h1_mm=80,
        h2_mm=140,
        Tslab_mm=100,
        Be_mm=1000,
        Ebeam_MPa=35000,
        Edeck_MPa=28560,
        girder_length_mm=12000,
        overhang_mm=500,
    )
    table = _normalize_girder_strand_layout_table(None, span_length_m=30.0, geometry=geometry)
    points = _girder_strand_point_layout_dataframe(table, geometry)
    row2_x = points.loc[points["Group ID"] == "Row 2", "x_mm"].round(6).tolist()
    assert row2_x == [-305.0, 305.0]


def test_cross_section_legend_uses_open_markers_matching_section_symbols(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _normalize_girder_strand_layout_table,
        _plot_girder_strand_cross_section_layout,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 4,
                "y_mm_from_bottom": 50.0,
                "Left debond m": 1.0,
                "Right debond m": 1.0,
                "Debonded strand nos": "1,4",
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=10.0)
    fig = _plot_girder_strand_cross_section_layout(table, None)
    bonded = next(trace for trace in fig.data if trace.name == "Bonded")
    debonded = next(trace for trace in fig.data if trace.name == "Debonded")
    assert bonded.marker.color == "rgba(255,255,255,0.0)"
    assert debonded.marker.color == "rgba(255,255,255,0.0)"
    assert bonded.marker.line.color == "#1f77b4"
    assert debonded.marker.line.color == "#dc2626"
    assert bonded.marker.symbol == "circle"
    assert debonded.marker.symbol == "circle"


def test_cross_section_strand_shapes_are_true_scale_circles(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _normalize_girder_strand_layout_table,
        _plot_girder_strand_cross_section_layout,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "x coordinates (mm)": "-25,25",
                "y_mm_from_bottom": 50.0,
                "Left debond m": 1.0,
                "Right debond m": 1.0,
                "Debonded strand nos": "1",
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=10.0)
    fig = _plot_girder_strand_cross_section_layout(table, None)
    strand_circles = [shape for shape in fig.layout.shapes if getattr(shape, "type", None) == "circle"]
    assert len(strand_circles) == 2
    diameters = sorted(round(float(shape.x1) - float(shape.x0), 3) for shape in strand_circles)
    assert diameters == [12.7, 12.7]
    line_colors = {shape.line.color for shape in strand_circles}
    assert "#1f77b4" in line_colors
    assert "#dc2626" in line_colors


def test_x_coordinate_list_mismatch_warns_without_crashing(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _normalize_girder_strand_layout_table,
        _validate_girder_strand_layout,
    )

    table = _normalize_girder_strand_layout_table(
        pd.DataFrame(
            [
                {
                    "Active": True,
                    "Group ID": "Row 1",
                    "Strand Size": "12.7 mm low-relaxation strand",
                    "No. Strands": 4,
                    "Strand x positions mm": "-100,100",
                    "y_mm_from_bottom": 50.0,
                }
            ]
        ),
        span_length_m=10.0,
    )
    errors, warnings = _validate_girder_strand_layout(table, span_length_m=10.0, geometry=None)
    assert errors == []
    assert any("x coordinates must contain exactly 4 numeric value" in warning for warning in warnings)


def test_box_beam_strand_layout_warns_when_strands_enter_void_or_cover_is_low(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.geometry.generators import box_section_fillet  # noqa: PLC0415
    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _normalize_girder_strand_layout_table,
        _validate_girder_strand_layout,
    )

    geometry = box_section_fillet(
        width_mm=990,
        height_mm=700,
        h1_mm=180,
        h3_mm=160,
        h4_mm=80,
        h5_mm=200,
        h6_mm=300,
        h7_mm=400,
        h8_mm=70,
        b2_mm=100,
        b3_mm=290,
        b4_mm=70,
    )
    void_row = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Void row",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 3,
                "Row center x_mm": 0.0,
                "y_mm_from_bottom": 200.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(void_row, span_length_m=20.0, geometry=geometry)
    errors, warnings = _validate_girder_strand_layout(table, span_length_m=20.0, geometry=geometry)
    assert errors == []
    assert any("inside a void/chamfer" in warning for warning in warnings)

    low_cover_row = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Low cover",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 1,
                "Row center x_mm": 0.0,
                "y_mm_from_bottom": 20.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(low_cover_row, span_length_m=20.0, geometry=geometry)
    errors, warnings = _validate_girder_strand_layout(table, span_length_m=20.0, geometry=geometry)
    assert errors == []
    assert any("minimum strand centerline clearance" in warning or "outside concrete or inside a void/chamfer" in warning for warning in warnings)


def test_girder_strand_editor_first_edit_callback_persists_table(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    import concrete_pmm_pro.ui.prestress_page as page  # noqa: PLC0415

    monkeypatch.setattr(page, "st", st)
    edited = page._normalize_girder_strand_layout_table(None, span_length_m=30.0)
    edited.loc[0, "Left debond m"] = 1.25
    edited.loc[0, "Right debond m"] = 0.75
    st.session_state["girder_strand_layout_editor"] = edited

    page._sync_girder_strand_layout_editor_to_table(30.0, "Left/right independent", None)

    stored = st.session_state["girder_strand_layout_table"]
    assert float(stored.loc[0, "Left debond m"]) == 1.25
    assert float(stored.loc[0, "Right debond m"]) == 0.75



def test_girder_strand_editor_store_does_not_force_rerun_during_numeric_edit(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}

    def _raise_rerun() -> None:
        raise AssertionError("strand editor store must not force rerun while numeric cells are edited")

    st.rerun = _raise_rerun
    st.experimental_rerun = _raise_rerun
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    import concrete_pmm_pro.ui.prestress_page as page  # noqa: PLC0415

    monkeypatch.setattr(page, "st", st)
    previous = page._normalize_girder_strand_layout_table(None, span_length_m=30.0)
    edited = previous.copy()
    edited.loc[0, "Left debond m"] = 1.5
    edited.loc[0, "Right debond m"] = 1.0

    page._store_girder_strand_layout_and_rerun_on_change(previous, edited)

    stored = st.session_state["girder_strand_layout_table"]
    assert float(stored.loc[0, "Left debond m"]) == 1.5
    assert float(stored.loc[0, "Right debond m"]) == 1.0


def test_advisory_recommendation_apply_helper_updates_selected_strands(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    import concrete_pmm_pro.ui.prestress_page as prestress_page  # noqa: PLC0415

    table = prestress_page._normalize_girder_strand_layout_table(
        pd.DataFrame(
            [
                {
                    "Active": True,
                    "Group ID": "Row 1",
                    "Strand Size": "12.7 mm low-relaxation strand",
                    "No. Strands": 19,
                    "y_mm_from_bottom": 50.0,
                    "Left debond m": 0.0,
                    "Right debond m": 0.0,
                    "Debonded strand nos": "",
                }
            ]
        ),
        span_length_m=30.0,
    )
    recommendation = pd.DataFrame(
        [
            {
                "Group ID": "Row 1",
                "Recommended debonded strand nos": "1,19",
                "Recommended count": 2,
                "Left debond m": 1.0,
                "Right debond m": 1.0,
            }
        ]
    )
    applied = prestress_page._apply_girder_advisory_debonding_recommendation(
        table,
        recommendation,
        span_length_m=30.0,
        debond_model="Left/right independent",
        geometry=None,
    )
    assert applied.loc[0, "Debonded strand nos"] == "1,19"
    assert applied.loc[0, "Left debond m"] == 1.0
    assert applied.loc[0, "Right debond m"] == 1.0
    assert "PS6B advisory candidate applied" in applied.loc[0, "Note"]


def test_voided_plank_reuses_practical_plank_prestress_preset(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.geometry.generators import parametric_plank_girder_voided_interior  # noqa: PLC0415
    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_strand_point_layout_dataframe,
        _normalize_girder_strand_layout_table,
    )

    geometry = parametric_plank_girder_voided_interior(
        B_mm=990,
        b1_mm=45,
        b2_mm=70,
        b3_mm=850,
        H_mm=450,
        h1_mm=80,
        h2_mm=140,
        Tslab_mm=100,
        Be_mm=1000,
        Ebeam_MPa=35000,
        Edeck_MPa=28560,
        girder_length_mm=12000,
    )
    table = _normalize_girder_strand_layout_table(None, span_length_m=12.0, geometry=geometry)
    assert table["Group ID"].tolist() == ["Row 1", "Row 2"]
    assert table["No. Strands"].tolist() == [16, 2]
    assert table.loc[0, "Debonded strand nos"] == "1,3,14,16"
    assert table.loc[0, "Left debond m"] == 1.0
    assert table.loc[0, "Right debond m"] == 1.0
    points = _girder_strand_point_layout_dataframe(table, geometry)
    assert points.loc[points["Group ID"] == "Row 2", "x_mm"].round(6).tolist() == [-375.0, 375.0]


def test_voided_exterior_plank_top_pair_uses_exterior_practical_offset(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.geometry.generators import parametric_plank_girder_voided_exterior  # noqa: PLC0415
    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_strand_point_layout_dataframe,
        _normalize_girder_strand_layout_table,
    )

    geometry = parametric_plank_girder_voided_exterior(
        B_mm=990,
        b1_mm=45,
        b2_mm=70,
        b3_mm=920,
        H_mm=450,
        h1_mm=80,
        h2_mm=140,
        Tslab_mm=100,
        Be_mm=1000,
        Ebeam_MPa=35000,
        Edeck_MPa=28560,
        girder_length_mm=12000,
        overhang_mm=500,
    )
    table = _normalize_girder_strand_layout_table(None, span_length_m=12.0, geometry=geometry)
    points = _girder_strand_point_layout_dataframe(table, geometry)
    assert points.loc[points["Group ID"] == "Row 2", "x_mm"].round(6).tolist() == [-305.0, 305.0]


def test_girder_loss1a_manual_force_state_table_and_apply(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _apply_girder_loss_force_states_to_strand_layout,
        _girder_loss_force_state_qa_summary,
        _normalize_girder_loss_force_state_table,
        _normalize_girder_strand_layout_table,
    )

    strand_table = _normalize_girder_strand_layout_table(
        pd.DataFrame(
            [
                {
                    "Active": True,
                    "Group ID": "Row 1",
                    "Strand Size": "12.7 mm low-relaxation strand",
                    "No. Strands": 4,
                    "y_mm_from_bottom": 50.0,
                    "Pe_transfer/strand_kN": 128.0,
                    "Pe_construction/strand_kN": 120.0,
                    "Pe_eff_final/strand_kN": 110.0,
                }
            ]
        ),
        span_length_m=30.0,
    )
    force_table = _normalize_girder_loss_force_state_table(None, strand_table, mode="Manual stage Pe")
    assert force_table.loc[0, "Group ID"] == "Row 1"
    assert force_table.loc[0, "QA status"] == "OK"
    assert force_table.loc[0, "Total loss %"] > 0.0
    status, messages = _girder_loss_force_state_qa_summary(force_table)
    assert status == "OK"
    assert messages == []

    force_table.loc[0, "Pe_eff_final/strand_kN"] = 100.0
    updated = _apply_girder_loss_force_states_to_strand_layout(strand_table, force_table)
    assert float(updated.loc[0, "Pe_eff_final/strand_kN"]) == 100.0


def test_girder_stage_pe_mapping_accepts_force_state_count_alias(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.serviceability.girder_prestress_station import girder_stage_pe_mapping_dataframe  # noqa: PLC0415

    force_state_like_table = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "No. strands": 4,
                "Pe_transfer/strand_kN": 120.0,
                "Pe_construction/strand_kN": 115.0,
                "Pe_eff_final/strand_kN": 105.0,
            }
        ]
    )
    mapping = girder_stage_pe_mapping_dataframe(force_state_like_table).set_index("Stage")
    assert mapping.loc["Transfer", "Status"] == "READY"
    assert mapping.loc["Construction", "Status"] == "READY"
    assert mapping.loc["Final service", "Status"] == "READY"
    assert float(mapping.loc["Transfer", "Pe total kN"]) == 480.0


def test_girder_loss1a_percentage_mode_derives_stage_pe(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _normalize_girder_loss_force_state_table,
        _normalize_girder_strand_layout_table,
    )

    strand_table = _normalize_girder_strand_layout_table(
        pd.DataFrame(
            [
                {
                    "Active": True,
                    "Group ID": "Row 1",
                    "Strand Size": "12.7 mm low-relaxation strand",
                    "No. Strands": 4,
                    "y_mm_from_bottom": 50.0,
                    "Pe_transfer/strand_kN": 120.0,
                    "Pe_construction/strand_kN": 115.0,
                    "Pe_eff_final/strand_kN": 105.0,
                }
            ]
        ),
        span_length_m=30.0,
    )
    loss_input = pd.DataFrame(
        [
            {
                "Group ID": "Row 1",
                "Pjack/strand_kN": 150.0,
                "Transfer loss %": 10.0,
                "Construction loss %": 5.0,
                "Long-term loss %": 10.0,
            }
        ]
    )
    force_table = _normalize_girder_loss_force_state_table(loss_input, strand_table, mode="Percentage loss")
    assert round(float(force_table.loc[0, "Pe_transfer/strand_kN"]), 3) == 135.0
    assert round(float(force_table.loc[0, "Pe_construction/strand_kN"]), 3) == 128.25
    assert round(float(force_table.loc[0, "Pe_eff_final/strand_kN"]), 3) == 115.425
    assert force_table.loc[0, "QA status"] == "OK"


def test_girder_loss1a_data_editor_patch_persists_manual_pe_first_edit(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui import prestress_page  # noqa: PLC0415
    prestress_page.st = st

    strand_table = prestress_page._normalize_girder_strand_layout_table(
        pd.DataFrame(
            [
                {
                    "Active": True,
                    "Group ID": "Row 1",
                    "Strand Size": "12.7 mm low-relaxation strand",
                    "No. Strands": 4,
                    "y_mm_from_bottom": 50.0,
                    "Pe_transfer/strand_kN": 128.0,
                    "Pe_construction/strand_kN": 120.0,
                    "Pe_eff_final/strand_kN": 110.0,
                }
            ]
        ),
        span_length_m=30.0,
    )
    base = prestress_page._normalize_girder_loss_force_state_table(None, strand_table, mode="Manual stage Pe")
    st.session_state["girder_prestress_loss_force_state_table"] = base
    st.session_state["girder_prestress_loss_force_state_editor"] = {
        "edited_rows": {
            0: {
                "Pe_transfer/strand_kN": 124.0,
                "Pe_construction/strand_kN": 118.0,
                "Pe_eff_final/strand_kN": 104.0,
            }
        },
        "added_rows": [],
        "deleted_rows": [],
    }

    prestress_page._sync_girder_loss_force_state_editor_to_table(strand_table, "Manual stage Pe")
    saved = st.session_state["girder_prestress_loss_force_state_table"]
    assert float(saved.loc[0, "Pe_transfer/strand_kN"]) == 124.0
    assert float(saved.loc[0, "Pe_construction/strand_kN"]) == 118.0
    assert float(saved.loc[0, "Pe_eff_final/strand_kN"]) == 104.0
    assert saved.loc[0, "QA status"] == "OK"


def test_girder_loss1a_data_editor_patch_persists_percentage_loss_first_edit(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui import prestress_page  # noqa: PLC0415
    prestress_page.st = st

    strand_table = prestress_page._normalize_girder_strand_layout_table(
        pd.DataFrame(
            [
                {
                    "Active": True,
                    "Group ID": "Row 1",
                    "Strand Size": "12.7 mm low-relaxation strand",
                    "No. Strands": 4,
                    "y_mm_from_bottom": 50.0,
                    "Pe_transfer/strand_kN": 120.0,
                    "Pe_construction/strand_kN": 115.0,
                    "Pe_eff_final/strand_kN": 105.0,
                }
            ]
        ),
        span_length_m=30.0,
    )
    base = prestress_page._normalize_girder_loss_force_state_table(None, strand_table, mode="Percentage loss")
    st.session_state["girder_prestress_loss_force_state_table"] = base
    st.session_state["girder_prestress_loss_force_state_editor"] = {
        "edited_rows": {0: {"Pjack/strand_kN": 150.0, "Transfer loss %": 10.0, "Construction loss %": 5.0, "Long-term loss %": 10.0}},
        "added_rows": [],
        "deleted_rows": [],
    }

    prestress_page._sync_girder_loss_force_state_editor_to_table(strand_table, "Percentage loss")
    saved = st.session_state["girder_prestress_loss_force_state_table"]
    assert round(float(saved.loc[0, "Pe_transfer/strand_kN"]), 3) == 135.0
    assert round(float(saved.loc[0, "Pe_construction/strand_kN"]), 3) == 128.25
    assert round(float(saved.loc[0, "Pe_eff_final/strand_kN"]), 3) == 115.425
    assert saved.loc[0, "QA status"] == "OK"


def test_girder_loss1b_force_state_mapping_and_sls_feed_matching(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui import prestress_page  # noqa: PLC0415
    prestress_page.st = st

    strand_table = prestress_page._normalize_girder_strand_layout_table(
        pd.DataFrame(
            [
                {
                    "Active": True,
                    "Group ID": "Row 1",
                    "Strand Size": "12.7 mm low-relaxation strand",
                    "No. Strands": 4,
                    "y_mm_from_bottom": 50.0,
                    "Pe_transfer/strand_kN": 120.0,
                    "Pe_construction/strand_kN": 115.0,
                    "Pe_eff_final/strand_kN": 105.0,
                }
            ]
        ),
        span_length_m=30.0,
    )
    force_table = prestress_page._normalize_girder_loss_force_state_table(None, strand_table, mode="Manual stage Pe")
    assert prestress_page._girder_force_states_match_strand_layout(strand_table, force_table)
    metrics = prestress_page._stage_pe_mapping_metrics_from_table(force_table, sls_feed_ready=True)
    values_by_title = {metric.title: metric.value for metric in metrics}
    assert values_by_title["Transfer Pe"] == "READY"
    assert values_by_title["Construction Pe"] == "READY"
    assert values_by_title["Service Pe"] == "READY"
    assert [metric.title for metric in metrics][-1] == "SLS feed"
    assert metrics[-1].value == "Ready"

    force_table.loc[0, "Pe_eff_final/strand_kN"] = 100.0
    assert not prestress_page._girder_force_states_match_strand_layout(strand_table, force_table)


def test_loss_display_dataframe_preserves_text_placeholders_without_to_numeric_error(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import _loss_display_dataframe  # noqa: PLC0415

    raw = pd.DataFrame(
        [
            {"Component": "Shrinkage", "Loss MPa": 12.34567, "Formula loss term": "εbdf × Ep × Kdf"},
            {"Component": "Review", "Loss MPa": "—", "Formula loss term": "manual coefficient missing"},
        ]
    )
    display = _loss_display_dataframe(raw)
    assert display.loc[0, "Loss MPa"] == 12.346
    assert display.loc[1, "Loss MPa"] == "—"
    assert display.loc[0, "Formula loss term"] == "εbdf × Ep × Kdf"


def test_refined_auto_coefficients_tolerate_display_rows_without_strand_size(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        DEFAULT_STRAND_EP_MPA,
        _girder_strand_total_aps_yps_ep,
    )

    # LOSS3B auto-coefficient estimation may receive a compact/display table
    # while the editor is rerunning.  Missing Strand Size must fall back to the
    # default product instead of crashing with KeyError.
    compact = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "No. strands": 2,
                "Area/Strand_mm2": 98.7,
                "y from bottom (mm)": 50,
            }
        ]
    )
    total_aps, yps, ep = _girder_strand_total_aps_yps_ep(compact)
    assert round(total_aps, 3) == 197.4
    assert yps == 50.0
    assert ep == DEFAULT_STRAND_EP_MPA
