import math
import pandas as pd

from concrete_pmm_pro.ui.analysis_page import (
    BEAM_ULS_CHECK_TAB_LABELS,
    _active_beam_uls_demand_dataframe_from_session,
    _beam_uls_calculate_selected_check,
    _beam_uls_check_table,
    _beam_uls_combined_vt_audit_dataframe,
    _beam_uls_combined_vt_check_dataframe,
    _beam_uls_combined_vt_plot_dataframe,
    _beam_uls_combined_vt_source_readiness_dataframe,
    _beam_uls_combined_vt_source_readiness_notes,
    _make_beam_uls_combined_vt_utilization_figure,
    _beam_uls_flexure_audit_dataframe,
    _beam_uls_flexure_analysis_input_for_station,
    _beam_uls_flexure_capacity_state_key,
    _beam_uls_shear_audit_dataframe,
    _beam_uls_shear_check_dataframe,
    _beam_uls_shear_critical_section_dataframe,
    _beam_uls_shear_diagram_boundary_dataframe,
    _beam_uls_shear_detailing_guard,
    _beam_uls_shear_reinforcement_status_dataframe,
    _beam_uls_summary_cards,
    _beam_uls_torsion_audit_dataframe,
    _beam_uls_torsion_check_dataframe,
    _beam_uls_torsion_diagram_boundary_dataframe,
    _beam_uls_torsion_interaction_status,
    _beam_uls_governing_torsion_row,
    _beam_uls_combined_vt_source_strength_gate,
    _make_beam_uls_shear_capacity_figure,
    _make_beam_uls_torsion_capacity_figure,
)


def test_uls_girder1_reads_active_station_rows_from_loads_only() -> None:
    state = {
        "beam_uls_loads_table": [
            {"Active": True, "Station x (m)": "5.0", "Case Name": "ULS-A", "Mux": "1000", "Vuy": "250", "Tu": "0", "Muy": "9", "Vux": "8", "Nu": "7", "Note": "active"},
            {"Active": False, "Station x (m)": "10.0", "Case Name": "ULS-B", "Mux": "9999", "Vuy": "9999", "Tu": "9999", "Muy": "0", "Vux": "0", "Nu": "0", "Note": "inactive"},
        ]
    }

    active = _active_beam_uls_demand_dataframe_from_session(state)

    assert len(active) == 1
    assert active.iloc[0]["Case Name"] == "ULS-A"
    assert active.iloc[0]["Mux"] == 1000.0


def test_uls_girder1_check_table_reports_governing_primary_actions_and_planned_capacity() -> None:
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 0.0, "Case Name": "END", "Mux": 100.0, "Vuy": 500.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 10.0, "Case Name": "MID", "Mux": -900.0, "Vuy": 100.0, "Tu": 25.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )

    table = _beam_uls_check_table(active)

    flexure = table.loc[table["Check"] == "Flexure"].iloc[0]
    shear = table.loc[table["Check"] == "Shear"].iloc[0]
    torsion = table.loc[table["Check"] == "Torsion"].iloc[0]
    combined = table.loc[table["Check"] == "Shear + Torsion"].iloc[0]
    assert flexure["Status"] == "PLANNED"
    assert flexure["Case"] == "MID"
    assert flexure["Governing x"] == "10.000 m"
    assert flexure["Capacity"] == "-"
    assert flexure["Utilization"] == "-"
    assert shear["Case"] == "END"
    assert torsion["Status"] == "LAYOUT REQUIRED"
    assert combined["Status"] == "NOT CALCULATED"
    assert combined["Capacity"] == "Press Calculate Shear + Torsion"


def test_uls_girder1_empty_state_is_not_ready_without_fake_pass() -> None:
    active = pd.DataFrame(columns=["Active", "Station x (m)", "Case Name", "Mux", "Vuy", "Tu", "Muy", "Vux", "Nu", "Note"])

    cards = _beam_uls_summary_cards(active, workflow_label="Bridge Beam/Girder", code_label="AASHTO LRFD")

    assert cards[0]["value"] == "NOT READY"
    assert "Define or import" in cards[0]["detail"]
    assert all(card["value"] != "PASS" for card in cards)




def test_uls_shear_code2_summary_separates_peak_demand_from_governing_check() -> None:
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 0.0, "Case Name": "ULS-G1", "Mux": 100.0, "Vuy": 250.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "support peak"},
            {"Active": True, "Station x (m)": 7.0, "Case Name": "ULS-G1", "Mux": 800.0, "Vuy": 75.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "design check"},
        ]
    )
    shear = pd.DataFrame(
        [
            {
                "Check": "Shear",
                "Status": "PASS",
                "Governing x": "7.000 m",
                "Case": "ULS-G1",
                "Demand": "75.00 kN",
                "Demand kN": 75.0,
                "Capacity": "φVn = 638.79 kN",
                "Utilization": "0.117 / det 0.333",
                "D/C value": 0.117,
                "Governing D/C value": 0.333,
            }
        ]
    )

    cards = _beam_uls_summary_cards(active, workflow_label="Bridge Beam/Girder", code_label="AASHTO LRFD", shear_check_df=shear)
    peak_card = next(card for card in cards if card["title"] == "Peak shear demand")
    check_card = next(card for card in cards if card["title"] == "Governing shear check")

    assert peak_card["value"] == "250.00 kN"
    assert "x=0.000 m" in peak_card["detail"]
    assert "diagram/support demand only" in peak_card["detail"]
    assert check_card["value"] == "75.00 kN · D/C 0.117 / det 0.333"
    assert "x=7.000 m" in check_card["detail"]
    assert "φVn = 638.79 kN" in check_card["detail"]
    assert "250.00" not in check_card["value"]


def test_uls_flex1_check_table_uses_flexure_preview_capacity_and_utilization() -> None:
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 10.0, "Case Name": "Strength I", "Mux": 900.0, "Vuy": 120.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    preview = pd.DataFrame(
        [
            {
                "Check": "Flexure",
                "Status": "PASS",
                "Governing x": "10.000 m",
                "Case": "Strength I",
                "Demand": "900.00 kN-m",
                "Capacity": "φMn = 1,800.00 kN-m",
                "Utilization": "0.500",
                "Demand kN-m": 900.0,
                "Capacity kN-m": 1800.0,
                "Utilization value": 0.5,
                "Method": "slice_envelope",
                "Notes": "Primary Mux flexure only",
            }
        ]
    )

    table = _beam_uls_check_table(active, flexure_preview_df=preview)

    flexure = table.loc[table["Check"] == "Flexure"].iloc[0]
    shear = table.loc[table["Check"] == "Shear"].iloc[0]
    assert flexure["Status"] == "PASS"
    assert flexure["Capacity"] == "φMn = 1,800.00 kN-m"
    assert flexure["Utilization"] == "0.500"
    assert shear["Status"] == "PLANNED"
    assert shear["Capacity"] == "-"


def test_uls_flex1_summary_reports_partial_flexure_preview_not_overall_pass() -> None:
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 10.0, "Case Name": "ACI19-ULS-2", "Mux": 900.0, "Vuy": 120.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    preview = pd.DataFrame(
        [
            {
                "Check": "Flexure",
                "Status": "PASS",
                "Governing x": "10.000 m",
                "Case": "ACI19-ULS-2",
                "Demand": "900.00 kN-m",
                "Capacity": "φMn = 1,800.00 kN-m",
                "Utilization": "0.500",
                "Demand kN-m": 900.0,
                "Capacity kN-m": 1800.0,
                "Utilization value": 0.5,
                "Method": "slice_envelope",
                "Notes": "Primary Mux flexure only",
            }
        ]
    )

    cards = _beam_uls_summary_cards(active, workflow_label="Building Beam/Girder", code_label="ACI 318", flexure_preview_df=preview)

    assert cards[0]["value"] == "FLEXURE CHECK — PASS"
    assert "no overall ULS PASS/FAIL" in cards[0]["detail"]
    assert cards[1]["title"] == "Critical flexure demand / D/C"
    assert "D/C 0.500" in cards[1]["value"]


def test_uls_flex1_preview_engine_returns_phi_mn_for_simple_rc_section() -> None:
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry
    from concrete_pmm_pro.ui.analysis_page import _beam_uls_flexure_preview_dataframe

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 3.0, "Case Name": "ACI19-ULS-2", "Mux": 100.0, "Vuy": 20.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )

    preview, messages = _beam_uls_flexure_preview_dataframe(state, active, code_label="ACI 318", is_building=True)

    assert messages == []
    assert len(preview) == 1
    row = preview.iloc[0]
    assert row["Status"] in {"PASS", "FAIL"}
    assert row["Capacity kN-m"] > 0.0
    assert row["Utilization value"] > 0.0
    assert "Primary Mux flexure only" in row["Notes"]


def test_perf_flex1_capacity_state_key_reuses_same_section_state_for_different_mu_magnitudes() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
    }
    route = beam_girder_uls_strength_route(is_bridge=False, is_building=True, code_edition="ACI 318-19")
    row_a = {"Station x (m)": 3.0, "Case Name": "A", "Mux": 100.0, "Nu": 0.0}
    row_b = {"Station x (m)": 5.0, "Case Name": "B", "Mux": 250.0, "Nu": 0.0}
    row_c = {"Station x (m)": 5.0, "Case Name": "B", "Mux": -250.0, "Nu": 0.0}

    input_a, messages_a = _beam_uls_flexure_analysis_input_for_station(state, row=row_a, strength_route=route)
    input_b, messages_b = _beam_uls_flexure_analysis_input_for_station(state, row=row_b, strength_route=route)
    input_c, messages_c = _beam_uls_flexure_analysis_input_for_station(state, row=row_c, strength_route=route)

    assert input_a is not None and input_b is not None and input_c is not None
    assert messages_a == [] and messages_b == [] and messages_c == []
    key_a = _beam_uls_flexure_capacity_state_key(input_a, strength_route=route, demand_kNm=row_a["Mux"])
    key_b = _beam_uls_flexure_capacity_state_key(input_b, strength_route=route, demand_kNm=row_b["Mux"])
    key_c = _beam_uls_flexure_capacity_state_key(input_c, strength_route=route, demand_kNm=row_c["Mux"])

    assert key_a == key_b
    assert key_a != key_c


def test_perf_flex1_1_capacity_state_key_ignores_heavy_section_metadata() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    base_points = [
        Point2D(x=0.0, y=0.0),
        Point2D(x=300.0, y=0.0),
        Point2D(x=300.0, y=600.0),
        Point2D(x=0.0, y=600.0),
    ]
    route = beam_girder_uls_strength_route(is_bridge=False, is_building=True, code_edition="ACI 318-19")
    common = {
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40")],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
    }
    state_a = {"section_geometry": SectionGeometry(name="A", outer_polygon=base_points, metadata={"ui_blob": [1] * 1000}), **common}
    state_b = {"section_geometry": SectionGeometry(name="A", outer_polygon=base_points, metadata={"ui_blob": [2] * 1000}), **common}
    row = {"Station x (m)": 3.0, "Case Name": "A", "Mux": 100.0, "Nu": 0.0}

    input_a, _ = _beam_uls_flexure_analysis_input_for_station(state_a, row=row, strength_route=route)
    input_b, _ = _beam_uls_flexure_analysis_input_for_station(state_b, row=row, strength_route=route)

    assert input_a is not None and input_b is not None
    assert _beam_uls_flexure_capacity_state_key(input_a, strength_route=route, demand_kNm=100.0) == _beam_uls_flexure_capacity_state_key(input_b, strength_route=route, demand_kNm=100.0)


def test_uls_flex1_1_summary_status_includes_flexure_preview_result() -> None:
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 10.0, "Case Name": "Strength I", "Mux": 5000.0, "Vuy": 120.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    preview = pd.DataFrame(
        [
            {
                "Check": "Flexure",
                "Status": "FAIL",
                "Governing x": "10.000 m",
                "Case": "Strength I",
                "Demand": "5,000.00 kN-m",
                "Capacity": "φMn = 3,580.44 kN-m",
                "Utilization": "1.396",
                "Demand kN-m": 5000.0,
                "Capacity kN-m": 3580.44,
                "Utilization value": 1.396,
                "Method": "slice_envelope",
                "Notes": "Primary Mux flexure only",
            }
        ]
    )

    cards = _beam_uls_summary_cards(active, workflow_label="Bridge Beam/Girder", code_label="AASHTO LRFD", flexure_preview_df=preview)

    assert cards[0]["value"] == "FLEXURE CHECK — FAIL"
    assert cards[0]["status"] == "danger"
    assert "no overall ULS PASS/FAIL" in cards[0]["detail"]


def test_uls_flex1_4_flexure_figure_plots_phi_mn_zero_at_span_boundaries() -> None:
    from concrete_pmm_pro.ui.analysis_page import _make_beam_uls_flexure_preview_figure

    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 0.0, "Case Name": "Strength I", "Mux": 0.0, "Vuy": 0.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 5.0, "Case Name": "Strength I", "Mux": 2500.0, "Vuy": 0.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 10.0, "Case Name": "Strength I", "Mux": 5000.0, "Vuy": 0.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 20.0, "Case Name": "Strength I", "Mux": 0.0, "Vuy": 0.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    preview = pd.DataFrame(
        [
            {"Check": "Flexure", "Status": "SECTION BOUNDARY", "Governing x": "0.000 m", "Case": "Strength I", "Demand": "0.00 kN-m", "Capacity": "φMn = 0.00 kN-m", "Utilization": "-", "Demand kN-m": 0.0, "Capacity kN-m": 0.0, "Utilization value": float("nan"), "Capacity plot sign": 1.0, "Method": "section boundary", "Notes": "Zero-Mux endpoint plotted as boundary"},
            {"Check": "Flexure", "Status": "PASS", "Governing x": "5.000 m", "Case": "Strength I", "Demand": "2,500.00 kN-m", "Capacity": "φMn = 3,500.00 kN-m", "Utilization": "0.714", "Demand kN-m": 2500.0, "Capacity kN-m": 3500.0, "Utilization value": 0.714, "Capacity plot sign": 1.0, "Method": "slice_envelope", "Notes": "Primary Mux flexure only"},
            {"Check": "Flexure", "Status": "FAIL", "Governing x": "10.000 m", "Case": "Strength I", "Demand": "5,000.00 kN-m", "Capacity": "φMn = 3,580.44 kN-m", "Utilization": "1.396", "Demand kN-m": 5000.0, "Capacity kN-m": 3580.44, "Utilization value": 1.396, "Capacity plot sign": 1.0, "Method": "slice_envelope", "Notes": "Primary Mux flexure only"},
            {"Check": "Flexure", "Status": "SECTION BOUNDARY", "Governing x": "20.000 m", "Case": "Strength I", "Demand": "0.00 kN-m", "Capacity": "φMn = 0.00 kN-m", "Utilization": "-", "Demand kN-m": 0.0, "Capacity kN-m": 0.0, "Utilization value": float("nan"), "Capacity plot sign": 1.0, "Method": "section boundary", "Notes": "Zero-Mux endpoint plotted as boundary"},
        ]
    )

    fig = _make_beam_uls_flexure_preview_figure(active, preview, code_label="AASHTO LRFD")
    trace_names = [trace.name for trace in fig.data]
    text_by_trace = {trace.name: list(trace.text) if getattr(trace, "text", None) is not None else [] for trace in fig.data}

    assert "Governing flexure check" in trace_names
    assert text_by_trace["Governing flexure check"] == ["FAIL · D/C 1.396"]
    assert all("PASS" not in text for values in text_by_trace.values() for text in values)
    assert not any(str(name).startswith("Endpoint review") for name in trace_names)
    demand_trace = next(trace for trace in fig.data if trace.name == "Demand Mux — Strength I")
    assert demand_trace.mode == "lines+markers"
    assert demand_trace.line.width >= 3
    assert demand_trace.marker.size >= 7
    capacity_trace = next(trace for trace in fig.data if trace.name == "φMn")
    assert list(capacity_trace.x) == [0.0, 5.0, 10.0, 20.0]
    assert list(capacity_trace.y) == [0.0, 3500.0, 3580.44, 0.0]
    assert capacity_trace.mode == "lines"
    assert capacity_trace.line.color == "red"
    assert capacity_trace.line.dash == "dash"
    assert capacity_trace.line.width == demand_trace.line.width
    assert getattr(capacity_trace, "marker", None) is None or capacity_trace.marker.size is None


def test_uls_flex1_4_engine_plots_zero_phi_mn_at_zero_mux_endpoints() -> None:
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry
    from concrete_pmm_pro.ui.analysis_page import _beam_uls_flexure_preview_dataframe

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 0.0, "Case Name": "ACI19-ULS-2", "Mux": 0.0, "Vuy": 0.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "end"},
            {"Active": True, "Station x (m)": 3.0, "Case Name": "ACI19-ULS-2", "Mux": 100.0, "Vuy": 20.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "mid"},
            {"Active": True, "Station x (m)": 6.0, "Case Name": "ACI19-ULS-2", "Mux": 0.0, "Vuy": 0.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "end"},
        ]
    )

    preview, messages = _beam_uls_flexure_preview_dataframe(state, active, code_label="ACI 318", is_building=True)

    assert any("φMn = 0" in message for message in messages)
    endpoints = preview[preview["Governing x"].isin(["0.000 m", "6.000 m"])]
    assert len(endpoints) == 2
    assert set(endpoints["Status"]) == {"SECTION BOUNDARY"}
    assert all(endpoints["Capacity kN-m"] == 0.0)
    assert endpoints["Utilization value"].isna().all()
    assert "D/C is not applicable at zero demand" in endpoints.iloc[0]["Notes"]


def test_uls_code_route1_bridge_and_building_routes_are_code_specific() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route

    bridge = beam_girder_uls_strength_route(
        is_bridge=True,
        is_building=False,
        project_design_code="ACI 318",  # stale input should not override workflow
        code_edition="AASHTO LRFD 9th Edition",
    )
    building = beam_girder_uls_strength_route(
        is_bridge=False,
        is_building=True,
        project_design_code="AASHTO LRFD",  # stale input should not override workflow
        code_edition="ACI 318-19",
    )

    assert bridge.workflow_label == "Bridge Beam/Girder"
    assert bridge.project_design_code == "AASHTO LRFD"
    assert bridge.display_code_label == "AASHTO LRFD 9th Edition"
    assert "AASHTO LRFD" in bridge.flexure_engine_label
    assert "AASHTO LRFD" in bridge.shear_engine_label
    assert bridge.is_code_specific_shear_ready

    assert building.workflow_label == "Building Beam/Girder"
    assert building.project_design_code == "ACI 318"
    assert building.display_code_label == "ACI 318-19"
    assert building.default_combo_label == "ACI19-ULS-2"
    assert "ACI 318" in building.flexure_engine_label
    assert "ACI 318" in building.shear_engine_label
    assert building.is_code_specific_shear_ready


def test_uls_code_route1_analysis_uses_route_basis_notes_in_flexure_rows() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry
    from concrete_pmm_pro.ui.analysis_page import _beam_uls_flexure_preview_dataframe

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 3.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 20.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD 9th Edition")

    preview, messages = _beam_uls_flexure_preview_dataframe(state, active, strength_route=route)

    assert messages == []
    assert len(preview) == 1
    notes = str(preview.iloc[0]["Notes"])
    assert "AASHTO LRFD flexure route" in notes
    assert "AASHTO LRFD-compatible strain compatibility" in preview.iloc[0]["Strain compatibility basis"]
    assert "AASHTO LRFD" in preview.iloc[0]["φ policy"]


def test_uls_flex_code1_basis_separates_bridge_prestressed_and_building_aci() -> None:
    from concrete_pmm_pro.analysis.uls_flexure_code_basis import beam_girder_flexure_code_basis
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route

    bridge = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD 9th Edition")
    building = beam_girder_uls_strength_route(is_bridge=False, is_building=True, code_edition="ACI 318-19")

    bridge_basis = beam_girder_flexure_code_basis(bridge, has_bonded_prestress=True)
    building_basis = beam_girder_flexure_code_basis(building, has_bonded_prestress=True)

    assert bridge_basis.requires_nominal_capacity
    assert bridge_basis.resistance_factor == 1.0
    assert "AASHTO LRFD" in bridge_basis.capacity_label
    assert "nominal strain-compatibility" in bridge_basis.method_label
    assert bridge_basis.strain_compatibility_basis == "AASHTO LRFD-compatible strain compatibility"
    assert "φ = 1.00" in bridge_basis.resistance_factor_policy

    assert not building_basis.requires_nominal_capacity
    assert building_basis.resistance_factor is None
    assert "ACI 318" in building_basis.capacity_label
    assert "strain-based φ" in building_basis.method_label
    assert building_basis.strain_compatibility_basis == "ACI 318-compatible strain compatibility"
    assert "strain-based φ" in building_basis.resistance_factor_policy


def test_uls_flex_code1_apply_bridge_phi_layer_to_nominal_capacity() -> None:
    from concrete_pmm_pro.analysis.uls_flexure_code_basis import apply_flexure_code_basis, beam_girder_flexure_code_basis
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route

    bridge = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD 9th Edition")
    bridge_basis = beam_girder_flexure_code_basis(bridge, has_bonded_prestress=True)

    routed, note = apply_flexure_code_basis(phi_capacity_nmm=900.0, nominal_capacity_nmm=1000.0, basis=bridge_basis)

    assert routed == 1000.0
    assert "φ = 1.00" in note


def test_uls_flex_code1_apply_building_aci_keeps_strain_phi_capacity() -> None:
    from concrete_pmm_pro.analysis.uls_flexure_code_basis import apply_flexure_code_basis, beam_girder_flexure_code_basis
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route

    building = beam_girder_uls_strength_route(is_bridge=False, is_building=True, code_edition="ACI 318-19")
    building_basis = beam_girder_flexure_code_basis(building, has_bonded_prestress=True)

    routed, note = apply_flexure_code_basis(phi_capacity_nmm=900.0, nominal_capacity_nmm=1000.0, basis=building_basis)

    assert routed == 900.0
    assert "ACI 318" in note



def test_uls_flex_verify1_audit_dataframe_exposes_benchmark_values() -> None:
    preview = pd.DataFrame(
        [
            {
                "Check": "Flexure",
                "Status": "FAIL",
                "Governing x": "10.000 m",
                "Case": "Strength I",
                "Demand": "5,000.00 kN-m",
                "Capacity": "φMn = 4,000.00 kN-m",
                "Utilization": "1.250",
                "Demand kN-m": 5000.0,
                "Capacity kN-m": 4000.0,
                "Utilization value": 1.25,
                "Mn nominal kN-m": 4000.0,
                "φ value": 1.0,
                "φMn kN-m": 4000.0,
                "D/C value": 1.25,
                "Bending direction": "Sagging (+Mux)",
                "Tension face": "Bottom face",
                "Code basis": "φMn — AASHTO LRFD",
                "Strain compatibility basis": "AASHTO LRFD-compatible strain compatibility",
                "φ policy": "AASHTO LRFD prestressed flexure: φ = 1.00 applied to nominal Mn",
                "Solver basis": "Nominal Mn from section equilibrium / strain compatibility",
                "Method": "AASHTO LRFD φ × nominal strain-compatibility Mn",
                "Benchmark readiness": "Benchmark against AASHTO/PCI or commercial girder software using Mn, φ, φMn, and D/C",
                "Notes": "Primary Mux flexure only",
            }
        ]
    )

    audit = _beam_uls_flexure_audit_dataframe(preview)

    assert list(audit.columns)[:11] == [
        "Governing",
        "Station x",
        "Case",
        "Status",
        "Direction",
        "Tension face",
        "Mu demand",
        "Mn nominal",
        "φ",
        "φMn",
        "D/C",
    ]
    row = audit.iloc[0]
    assert row["Governing"] == "Yes"
    assert row["Mn nominal"] == "4,000.00 kN-m"
    assert row["φ"] == "1.000"
    assert row["φMn"] == "4,000.00 kN-m"
    assert row["D/C"] == "1.250"
    assert row["Code basis"] == "φMn — AASHTO LRFD"
    assert row["SC basis"] == "AASHTO LRFD-compatible strain compatibility"
    assert "φ = 1.00" in row["φ policy"]
    assert row["Solver basis"] == "Nominal Mn from section equilibrium / strain compatibility"
    assert row["Tension face"] == "Bottom face"


def test_uls_flex_verify1_engine_populates_nominal_mn_and_effective_phi() -> None:
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry
    from concrete_pmm_pro.ui.analysis_page import _beam_uls_flexure_preview_dataframe

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 3.0, "Case Name": "ACI19-ULS-2", "Mux": 100.0, "Vuy": 20.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )

    preview, _ = _beam_uls_flexure_preview_dataframe(state, active, code_label="ACI 318", is_building=True)

    row = preview.iloc[0]
    assert row["Mn nominal kN-m"] > 0.0
    assert row["φMn kN-m"] == row["Capacity kN-m"]
    assert 0.0 < row["φ value"] <= 1.0
    assert row["Bending direction"] == "Sagging (+Mux)"
    assert row["Tension face"] == "Bottom face"
    assert "ACI 318" in row["Code basis"]
    assert "Benchmark" in row["Benchmark readiness"]
    assert row["Strain compatibility basis"] == "ACI 318-compatible strain compatibility"
    assert "strain-based φ" in row["φ policy"]



def test_uls_shear1_provided_stirrup_layout_calculates_phi_vn_for_building() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_shear_reinforcement_table": [
            {
                "Active": True,
                "Zone": "Support",
                "x_start_m": 0.0,
                "x_end_m": 6.0,
                "Bar Size": "DB12",
                "Diameter_mm": 12.0,
                "Legs": 2,
                "Spacing_mm": 150.0,
                "fy_MPa": 400.0,
                "Note": "provided",
            }
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 3.0, "Case Name": "ACI19-ULS-2", "Mux": 100.0, "Vuy": 120.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=False, is_building=True, code_edition="ACI 318-19")

    shear = _beam_uls_shear_check_dataframe(state, active, strength_route=route)

    assert len(shear) == 1
    row = shear.iloc[0]
    assert row["Status"] in {"PASS", "FAIL"}
    assert row["φVn kN"] > 0.0
    assert row["φVc kN"] > 0.0
    assert row["φVs kN"] > 0.0
    assert row["D/C value"] > 0.0
    assert "ACI 318" in row["Code basis"]
    assert "DB12" in row["Stirrup"]


def test_uls_shear1_check_table_uses_governing_shear_capacity() -> None:
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 3.0, "Case Name": "ACI19-ULS-2", "Mux": 100.0, "Vuy": 120.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    shear = pd.DataFrame(
        [
            {
                "Check": "Shear",
                "Status": "PASS",
                "Governing x": "3.000 m",
                "Case": "ACI19-ULS-2",
                "Demand": "120.00 kN",
                "Capacity": "φVn = 450.00 kN",
                "Utilization": "0.267",
                "Demand kN": 120.0,
                "φVn kN": 450.0,
                "D/C value": 0.267,
            }
        ]
    )

    table = _beam_uls_check_table(active, shear_check_df=shear)

    shear_row = table.loc[table["Check"] == "Shear"].iloc[0]
    assert shear_row["Status"] == "PASS"
    assert shear_row["Capacity"] == "φVn = 450.00 kN"
    assert shear_row["Utilization"] == "0.267"


def test_uls_shear1_audit_dataframe_exposes_capacity_components() -> None:
    shear = pd.DataFrame(
        [
            {
                "Check": "Shear",
                "Status": "FAIL",
                "Governing x": "1.000 m",
                "Case": "Strength I",
                "Demand kN": 900.0,
                "φVn kN": 800.0,
                "φVc kN": 200.0,
                "φVs kN": 600.0,
                "D/C value": 1.125,
                "Zone": "Support",
                "Stirrup": "DB12 × 2 legs @ 100 mm",
                "Av/s mm2/m": 2262.0,
                "bw mm": 300.0,
                "d mm": 550.0,
                "dv mm": 500.0,
                "φ": 0.9,
                "Code basis": "φVn — AASHTO LRFD-compatible",
                "Method": "AASHTO LRFD-compatible simplified sectional shear (θ=45° first-pass)",
                "Notes": "benchmark pending",
            }
        ]
    )

    audit = _beam_uls_shear_audit_dataframe(shear)

    row = audit.iloc[0]
    assert row["Governing"] == "Yes"
    assert row["φVn"] == "800.00 kN"
    assert row["φVc"] == "200.00 kN"
    assert row["φVs"] == "600.00 kN"
    assert row["D/C"] == "1.125"
    assert "AASHTO" in row["Code basis"]



def test_uls_shear2_detailing_guard_passes_reasonable_aci_stirrups() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route

    route = beam_girder_uls_strength_route(is_bridge=False, is_building=True, code_edition="ACI 318-19")

    guard = _beam_uls_shear_detailing_guard(
        strength_route=route,
        fc_MPa=30.0,
        bw_mm=300.0,
        d_eff_mm=550.0,
        dv_mm=float("nan"),
        spacing_mm=150.0,
        avs_mm2_per_mm=2.0 * 3.141592653589793 * 12.0 * 12.0 / 4.0 / 150.0,
        fy_MPa=400.0,
    )

    assert guard["Detailing status"] == "PASS"
    assert guard["Av/s required mm2/m"] > 0.0
    assert guard["s max mm"] == 275.0
    assert guard["Detailing D/C value"] <= 1.0


def test_uls_shear2_spacing_or_avs_failure_downgrades_shear_status() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_shear_reinforcement_table": [
            {
                "Active": True,
                "Zone": "Sparse",
                "x_start_m": 0.0,
                "x_end_m": 6.0,
                "Bar Size": "DB10",
                "Diameter_mm": 10.0,
                "Legs": 2,
                "Spacing_mm": 600.0,
                "fy_MPa": 400.0,
                "Note": "intentionally too sparse",
            }
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 3.0, "Case Name": "ACI19-ULS-2", "Mux": 100.0, "Vuy": 20.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=False, is_building=True, code_edition="ACI 318-19")

    shear = _beam_uls_shear_check_dataframe(state, active, strength_route=route)

    row = shear.iloc[0]
    assert row["Status"] == "FAIL"
    assert row["Strength status"] == "PASS"
    assert row["Detailing status"] == "FAIL"
    assert row["Detailing D/C value"] > 1.0
    assert "spacing" in row["Notes"].lower() or "av/s" in row["Notes"].lower()


def test_uls_shear2_audit_dataframe_exposes_detailing_guard_columns() -> None:
    shear = pd.DataFrame(
        [
            {
                "Check": "Shear",
                "Status": "FAIL",
                "Strength status": "PASS",
                "Detailing status": "FAIL",
                "Governing x": "1.000 m",
                "Case": "Strength I",
                "Demand kN": 100.0,
                "φVn kN": 800.0,
                "φVc kN": 200.0,
                "φVs kN": 600.0,
                "D/C value": 0.125,
                "Strength D/C value": 0.125,
                "Detailing D/C value": 1.50,
                "Av/s required mm2/m": 300.0,
                "s max mm": 250.0,
                "Spacing D/C": 1.50,
                "Zone": "Support",
                "Stirrup": "DB10 × 2 legs @ 375 mm",
                "Av/s mm2/m": 200.0,
                "bw mm": 300.0,
                "d mm": 550.0,
                "dv mm": 500.0,
                "φ": 0.75,
                "Code basis": "φVn — ACI 318",
                "Method": "ACI 318 simplified one-way shear with provided stirrups",
                "Notes": "Provided stirrup spacing exceeds guard",
            }
        ]
    )

    audit = _beam_uls_shear_audit_dataframe(shear)

    row = audit.iloc[0]
    assert row["Strength"] == "PASS"
    assert row["Detailing"] == "FAIL"
    assert row["Strength D/C"] == "0.125"
    assert row["Detailing D/C"] == "1.500"
    assert row["Av/s min"] == "300.00 mm²/m"
    assert row["s max"] == "250.00 mm"
    assert row["Spacing D/C"] == "1.500"



def test_uls_shear2_1_status_dataframe_explains_inactive_stirrup_zones() -> None:
    state = {
        "beam_girder_shear_reinforcement_table": [
            {
                "Active": False,
                "Zone": "Support",
                "x_start_m": 0.0,
                "x_end_m": 4.0,
                "Bar Size": "DB12",
                "Diameter_mm": 12.0,
                "Legs": 2,
                "Spacing_mm": 150.0,
                "fy_MPa": 400.0,
                "Note": "template",
            }
        ]
    }

    status = _beam_uls_shear_reinforcement_status_dataframe(state)

    assert len(status) == 1
    row = status.iloc[0]
    assert row["Active"] == "No"
    assert row["Readiness"] == "INACTIVE — not used for φVn"
    assert row["Av/s provided"].endswith("mm²/m")



def test_uls_shear2_2_capacity_diagram_adds_end_boundary_values_without_governing() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_system_settings": {"span_length_m": 20.0},
        "beam_girder_shear_reinforcement_table": [
            {
                "Active": True,
                "Zone": "Full span",
                "x_start_m": 0.0,
                "x_end_m": 20.0,
                "Bar Size": "DB12",
                "Diameter_mm": 12.0,
                "Legs": 2,
                "Spacing_mm": 150.0,
                "fy_MPa": 400.0,
                "Note": "provided",
            }
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 2.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 250.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 18.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": -250.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    shear = _beam_uls_shear_check_dataframe(state, active, strength_route=route)
    boundary = _beam_uls_shear_diagram_boundary_dataframe(state, active, strength_route=route)
    fig = _make_beam_uls_shear_capacity_figure(active, shear, code_label="AASHTO LRFD", boundary_capacity_df=boundary)

    assert len(boundary) == 2
    assert set(boundary["Governing x"]) == {"0.000 m", "20.000 m"}
    assert set(boundary["Status"]) == {"DIAGRAM BOUNDARY"}
    assert boundary["φVn kN"].min() > 0.0
    assert boundary["D/C value"].isna().all()
    demand_trace = next(trace for trace in fig.data if trace.name == "Demand Vuy — Strength I")
    assert demand_trace.mode == "lines+markers"
    assert demand_trace.line.width >= 3
    assert demand_trace.marker.size >= 7
    vn_trace = next(trace for trace in fig.data if trace.name == "φVn")
    neg_vn_trace = next(trace for trace in fig.data if trace.name == "-φVn")
    vc_trace = next(trace for trace in fig.data if trace.name == "φVc")
    assert min(vn_trace.x) == 0.0
    assert max(vn_trace.x) == 20.0
    assert vn_trace.mode == "lines"
    assert vn_trace.line.color == "red"
    assert vn_trace.line.dash == "dash"
    assert vn_trace.line.width == demand_trace.line.width
    assert getattr(vn_trace, "marker", None) is None or vn_trace.marker.size is None
    assert neg_vn_trace.mode == "lines"
    assert neg_vn_trace.line.color == "red"
    assert neg_vn_trace.line.dash == "dash"
    assert neg_vn_trace.line.width == demand_trace.line.width
    assert getattr(neg_vn_trace, "marker", None) is None or neg_vn_trace.marker.size is None
    assert vc_trace.mode == "lines"
    assert vc_trace.line.color == "orange"
    assert vc_trace.line.dash == "dash"
    assert getattr(vc_trace, "marker", None) is None or vc_trace.marker.size is None



def test_uls_shear3_critical_sections_are_inserted_and_considered_governing() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_system_settings": {"span_length_m": 20.0},
        "beam_girder_shear_reinforcement_table": [
            {
                "Active": True,
                "Zone": "Support",
                "x_start_m": 0.0,
                "x_end_m": 20.0,
                "Bar Size": "DB12",
                "Diameter_mm": 12.0,
                "Legs": 2,
                "Spacing_mm": 150.0,
                "fy_MPa": 400.0,
                "Note": "provided",
            }
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 0.0, "Case Name": "Strength I", "Mux": 10.0, "Vuy": 300.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 10.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 0.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 20.0, "Case Name": "Strength I", "Mux": 10.0, "Vuy": -300.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    critical = _beam_uls_shear_critical_section_dataframe(state, active, strength_route=route)
    combined = pd.concat([_beam_uls_shear_check_dataframe(state, active, strength_route=route), critical], ignore_index=True)
    fig = _make_beam_uls_shear_capacity_figure(active, combined, code_label="AASHTO LRFD", critical_section_df=critical)

    assert len(critical) == 2
    assert set(critical["Station type"]) == {"CRITICAL SHEAR SECTION"}
    assert set(critical["Support side"]) == {"Left", "Right"}
    assert critical["Critical offset m"].min() > 0.0
    assert critical["D/C value"].notna().all()
    assert any(trace.name == "Critical section for shear loading" for trace in fig.data)


def test_uls_ui2_check_tabs_are_main_workspace_labels() -> None:
    assert BEAM_ULS_CHECK_TAB_LABELS == ["Flexure", "Shear", "Torsion", "Shear + Torsion"]


def test_uls_ui2_shear_torsion_interaction_status_does_not_fake_pass() -> None:
    no_torsion = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 5.0, "Case Name": "Strength I", "Mux": 1000.0, "Vuy": 300.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    with_torsion = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 5.0, "Case Name": "Strength I", "Mux": 1000.0, "Vuy": 300.0, "Tu": 45.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )

    no_torsion_status = _beam_uls_torsion_interaction_status(no_torsion)
    with_torsion_status = _beam_uls_torsion_interaction_status(with_torsion)

    assert no_torsion_status["value"] == "Not applicable — Tu not active"
    assert no_torsion_status["status"] == "neutral"
    assert with_torsion_status["value"] == "CHECK REQUIRED — shear + torsion interaction not implemented"
    assert with_torsion_status["status"] == "warning"
    assert "45.00 kN-m" in with_torsion_status["detail"]
    assert "Do not certify" in with_torsion_status["detail"]


def test_perf_uls2_requires_manual_calculate_before_selected_check_runs() -> None:
    from pathlib import Path

    source = Path("concrete_pmm_pro/ui/analysis_page.py").read_text()

    assert 'calc_label = f"Calculate {selected_check}"' in source
    assert 'st.button(calc_label' in source
    assert 'type="primary"' in source
    assert 'has not been calculated for the current inputs' in source
    assert '_beam_uls_calculate_selected_check(' in source
    assert 'Capacity diagrams, utilization, and audit output are intentionally withheld' in source


def test_uls_ui2_source_places_check_tabs_under_compact_table_without_general_diagram_expander() -> None:
    from pathlib import Path

    source = Path("concrete_pmm_pro/ui/analysis_page.py").read_text()
    compact_idx = source.index('st.markdown("#### Compact ULS check table")')
    selector_idx = source.index('"ULS check to calculate"')
    audit_idx = source.index('with st.expander("ULS demand table — audit / source data"')

    assert selector_idx < compact_idx < audit_idx
    assert "st.tabs(BEAM_ULS_CHECK_TAB_LABELS)" not in source
    assert 'with st.expander("ULS demand/capacity diagrams"' not in source
    assert 'with st.expander("Flexure strength audit / benchmark output"' in source
    assert 'with st.expander("Shear strength audit / provided stirrup output"' in source



def test_uls_shear3_1_critical_marker_is_visible_even_when_phi_vn_not_ready() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_system_settings": {"span_length_m": 20.0},
        "beam_girder_shear_reinforcement_table": [],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 2.0, "Case Name": "Strength I", "Mux": 10.0, "Vuy": 250.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 10.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 0.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 20.0, "Case Name": "Strength I", "Mux": 10.0, "Vuy": -250.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    station = _beam_uls_shear_check_dataframe(state, active, strength_route=route)
    critical = _beam_uls_shear_critical_section_dataframe(state, active, strength_route=route)
    fig = _make_beam_uls_shear_capacity_figure(active, pd.concat([station, critical], ignore_index=True), code_label="AASHTO LRFD", critical_section_df=critical)

    assert len(critical) == 2
    assert set(critical["Station type"]) == {"CRITICAL SHEAR SECTION"}
    assert set(critical["Status"]) == {"LAYOUT REQUIRED"}
    assert any(str(note).find("active stirrup zone covers the critical section") >= 0 for note in critical["Notes"])
    assert any(trace.name == "Critical section for shear loading" for trace in fig.data)


def test_uls_shear4_manual_effective_d_dv_drives_shear_capacity_and_critical_offset() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_system_settings": {"span_length_m": 20.0},
        "beam_girder_shear_depth_settings": {
            "mode": "Manual effective d / dv",
            "d_mm": 520.0,
            "dv_mm": 480.0,
            "note": "test design depth",
        },
        "beam_girder_shear_reinforcement_table": [
            {
                "Active": True,
                "Zone": "Full span",
                "x_start_m": 0.0,
                "x_end_m": 20.0,
                "Bar Size": "DB12",
                "Diameter_mm": 12.0,
                "Legs": 2,
                "Spacing_mm": 150.0,
                "fy_MPa": 400.0,
                "Note": "provided",
            }
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 0.0, "Case Name": "Strength I", "Mux": 10.0, "Vuy": 300.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 10.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 0.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 20.0, "Case Name": "Strength I", "Mux": 10.0, "Vuy": -300.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    shear = _beam_uls_shear_check_dataframe(state, active, strength_route=route)
    critical = _beam_uls_shear_critical_section_dataframe(state, active, strength_route=route)

    assert set(round(float(value), 1) for value in shear["d mm"].dropna()) == {520.0}
    assert set(round(float(value), 1) for value in shear["dv mm"].dropna()) == {480.0}
    assert set(round(float(value), 3) for value in critical["Critical offset m"].dropna()) == {0.48}
    assert "Manual" in str(shear.iloc[0]["Notes"])


def test_uls_shear4_1_critical_markers_use_station_depth_when_support_input_path_is_not_available() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=1500.0),
            Point2D(x=0.0, y=1500.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C40", fc_MPa=40.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=75.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=75.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_system_settings": {"span_length_m": 20.0},
        "beam_girder_shear_reinforcement_table": [
            {
                "Active": True,
                "Zone": "Support L",
                "x_start_m": 0.0,
                "x_end_m": 3.0,
                "Bar Size": "DB12",
                "Diameter_mm": 12.0,
                "Legs": 2,
                "Spacing_mm": 250.0,
                "fy_MPa": 400.0,
                "Note": "provided",
            },
            {
                "Active": True,
                "Zone": "Midspan",
                "x_start_m": 3.0,
                "x_end_m": 17.0,
                "Bar Size": "DB12",
                "Diameter_mm": 12.0,
                "Legs": 2,
                "Spacing_mm": 250.0,
                "fy_MPa": 400.0,
                "Note": "provided",
            },
            {
                "Active": True,
                "Zone": "Support R",
                "x_start_m": 17.0,
                "x_end_m": 20.0,
                "Bar Size": "DB12",
                "Diameter_mm": 12.0,
                "Legs": 2,
                "Spacing_mm": 250.0,
                "fy_MPa": 400.0,
                "Note": "provided",
            },
        ],
    }
    # Screenshot-like station set: no explicit x=0 support row, but capacity rows
    # and d/dv are already available in the Shear card. Critical-section marker
    # generation must reuse those station d/dv values instead of disappearing.
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 1.7, "Case Name": "ULS-G1", "Mux": 100.0, "Vuy": 250.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 7.0, "Case Name": "ULS-G1", "Mux": 800.0, "Vuy": 75.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 19.7, "Case Name": "ULS-G1", "Mux": 100.0, "Vuy": -250.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    shear = _beam_uls_shear_check_dataframe(state, active, strength_route=route)
    critical = _beam_uls_shear_critical_section_dataframe(state, active, strength_route=route)
    fig = _make_beam_uls_shear_capacity_figure(active, pd.concat([shear, critical], ignore_index=True), code_label="AASHTO LRFD", critical_section_df=critical)

    assert not shear.empty
    assert shear["dv mm"].notna().any()
    assert len(critical) == 2
    assert set(critical["Station type"]) == {"CRITICAL SHEAR SECTION"}
    assert any(trace.name == "Critical section for shear loading" for trace in fig.data)


def test_uls_torsion_code2_aci_route_reports_phi_tn_without_fake_unsafe_pass() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_shear_reinforcement_table": [
            {
                "Active": True,
                "Zone": "Closed hoop zone",
                "x_start_m": 0.0,
                "x_end_m": 6.0,
                "Bar Size": "DB12",
                "Diameter_mm": 12.0,
                "Legs": 2,
                "Spacing_mm": 150.0,
                "fy_MPa": 400.0,
                "Note": "provided closed stirrup for first-pass torsion",
            }
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 3.0, "Case Name": "ACI19-ULS-2", "Mux": 100.0, "Vuy": 20.0, "Tu": 10.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=False, is_building=True, code_edition="ACI 318-19")

    torsion = _beam_uls_torsion_check_dataframe(state, active, strength_route=route)

    row = torsion.iloc[0]
    assert row["Status"] in {"REVIEW", "BELOW THRESHOLD", "FAIL"}
    assert row["Transverse status"] in {"PASS", "THRESHOLD OK"}
    assert row["Longitudinal status"] in {"PASS", "FAIL", "NOT CHECKED", "LAYOUT REQUIRED"}
    assert row["φTn kN-m"] > 0.0
    assert row["D/C value"] > 0.0
    assert row["φ"] == 0.75
    assert "ACI 318" in row["Code basis"]
    assert "Longitudinal torsion" in row["Notes"]


def test_uls_torsion2_uses_existing_rebar_table_as_longitudinal_al_source() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=400.0, y=0.0),
            Point2D(x=400.0, y=900.0),
            Point2D(x=0.0, y=900.0),
        ]
    )
    base_state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C40", fc_MPa=40.0),
        "rebars": [],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "section_has_ordinary_rebar": True,
        "beam_girder_shear_reinforcement_table": [
            {"Active": True, "Zone": "Support", "x_start_m": 0.0, "x_end_m": 10.0, "Bar Size": "DB12", "Diameter_mm": 12.0, "Legs": 2, "Spacing_mm": 200.0, "fy_MPa": 400.0, "Note": "provided"}
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 2.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 20.0, "Tu": 20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    without_rebar = _beam_uls_torsion_check_dataframe(base_state, active, strength_route=route).iloc[0]
    assert without_rebar["Longitudinal status"] in {"LAYOUT REQUIRED", "NOT CHECKED"}

    state = dict(base_state)
    state["rebars"] = [Rebar(x_mm=60.0 + i * 20.0, y_mm=80.0, diameter_mm=25.0, material_name="SD40") for i in range(12)]
    with_rebar = _beam_uls_torsion_check_dataframe(state, active, strength_route=route).iloc[0]
    assert with_rebar["Longitudinal status"] == "PASS"
    assert with_rebar["Al provided mm2"] > with_rebar["Al req mm2"]
    assert with_rebar["Al utilization"] <= 1.0
    assert "existing Rebar table" in with_rebar["Notes"]
    assert with_rebar["Status"] in {"PASS", "REVIEW", "BELOW THRESHOLD"}

    disabled_state = dict(state)
    disabled_state["section_has_ordinary_rebar"] = False
    disabled = _beam_uls_torsion_check_dataframe(disabled_state, active, strength_route=route).iloc[0]
    assert disabled["Longitudinal status"] in {"LAYOUT REQUIRED", "NOT CHECKED"}


def test_uls_torsion1_bridge_and_building_routes_use_different_phi() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=400.0, y=0.0),
            Point2D(x=400.0, y=900.0),
            Point2D(x=0.0, y=900.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C40", fc_MPa=40.0),
        "rebars": [Rebar(x_mm=200.0, y_mm=80.0, diameter_mm=25.0, material_name="SD40")],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_shear_reinforcement_table": [
            {"Active": True, "Zone": "Support", "x_start_m": 0.0, "x_end_m": 10.0, "Bar Size": "DB12", "Diameter_mm": 12.0, "Legs": 2, "Spacing_mm": 200.0, "fy_MPa": 400.0, "Note": "provided"}
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 2.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 20.0, "Tu": 20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    bridge = _beam_uls_torsion_check_dataframe(state, active, strength_route=beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD"))
    building = _beam_uls_torsion_check_dataframe(state, active, strength_route=beam_girder_uls_strength_route(is_bridge=False, is_building=True, code_edition="ACI 318-19"))

    assert bridge.iloc[0]["φ"] == 0.90
    assert building.iloc[0]["φ"] == 0.75
    assert bridge.iloc[0]["φTn kN-m"] > building.iloc[0]["φTn kN-m"]
    assert "AASHTO" in bridge.iloc[0]["Code basis"]
    assert "ACI" in building.iloc[0]["Code basis"]


def test_uls_torsion1_figure_uses_unmarked_red_check_lines_and_marked_demand() -> None:
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 0.0, "Case Name": "Strength I", "Mux": 0.0, "Vuy": 0.0, "Tu": 5.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 5.0, "Case Name": "Strength I", "Mux": 0.0, "Vuy": 0.0, "Tu": -10.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    torsion = pd.DataFrame(
        [
            {"Status": "REVIEW", "Governing x": "0.000 m", "Case": "Strength I", "Demand kN-m": 5.0, "Abs demand kN-m": 5.0, "φTn kN-m": 40.0, "φTcr kN-m": 8.0, "D/C value": 0.125},
            {"Status": "REVIEW", "Governing x": "5.000 m", "Case": "Strength I", "Demand kN-m": -10.0, "Abs demand kN-m": 10.0, "φTn kN-m": 40.0, "φTcr kN-m": 8.0, "D/C value": 0.25},
        ]
    )

    fig = _make_beam_uls_torsion_capacity_figure(active, torsion, code_label="AASHTO LRFD")

    demand = next(trace for trace in fig.data if str(trace.name).startswith("Demand Tu"))
    phi_tn = next(trace for trace in fig.data if trace.name == "φTn")
    assert demand.mode == "lines+markers"
    assert phi_tn.mode == "lines"
    assert phi_tn.line.color == "red"
    assert phi_tn.line.dash == "dash"


def test_uls_torsion1_figure_uses_boundary_rows_to_extend_phi_tn_to_member_ends() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=400.0, y=0.0),
            Point2D(x=400.0, y=900.0),
            Point2D(x=0.0, y=900.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C40", fc_MPa=40.0),
        "rebars": [Rebar(x_mm=200.0, y_mm=80.0, diameter_mm=25.0, material_name="SD40")],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_shear_reinforcement_table": [
            {"Active": True, "Zone": "Support", "x_start_m": 0.0, "x_end_m": 20.0, "Bar Size": "DB12", "Diameter_mm": 12.0, "Legs": 2, "Spacing_mm": 200.0, "fy_MPa": 400.0, "Note": "provided"}
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 2.0, "Case Name": "Strength I", "Mux": 0.0, "Vuy": 0.0, "Tu": 20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 18.0, "Case Name": "Strength I", "Mux": 0.0, "Vuy": 0.0, "Tu": -20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    torsion = _beam_uls_torsion_check_dataframe(state, active, strength_route=route)
    boundary = _beam_uls_torsion_diagram_boundary_dataframe(state, active, strength_route=route)
    fig = _make_beam_uls_torsion_capacity_figure(active, torsion, code_label="AASHTO LRFD", boundary_capacity_df=boundary)

    assert not boundary.empty
    assert set(boundary["Governing x"]) == {"0.000 m", "20.000 m"}
    phi_tn = next(trace for trace in fig.data if trace.name == "φTn")
    assert min(float(x) for x in phi_tn.x) == 0.0
    assert max(float(x) for x in phi_tn.x) == 20.0


def test_uls_codeverify1_aci_318_19_uses_chapter_22_basis_not_legacy_chapter_11() -> None:
    from concrete_pmm_pro.analysis.uls_shear_torsion_code_basis import ACI_318_19_CHAPTER_BASIS

    assert ACI_318_19_CHAPTER_BASIS["strength_reduction_factors"] == "ACI 318-19 Chapter 21"
    assert ACI_318_19_CHAPTER_BASIS["sectional_strength"] == "ACI 318-19 Chapter 22"
    assert "22.5" in ACI_318_19_CHAPTER_BASIS["one_way_shear"]
    assert "22.7" in ACI_318_19_CHAPTER_BASIS["torsional_strength"]
    assert all("Chapter 11" not in value for value in ACI_318_19_CHAPTER_BASIS.values())


def test_uls_codeverify1_blocks_us_aci_vc_coefficient_in_metric_calculations() -> None:
    from concrete_pmm_pro.analysis.uls_shear_torsion_code_basis import (
        ACI_METRIC_SIMPLIFIED_ONE_WAY_VC_FACTOR,
        ACI_US_SIMPLIFIED_ONE_WAY_VC_FACTOR,
        aci_metric_vc_is_unit_safe,
    )

    assert ACI_METRIC_SIMPLIFIED_ONE_WAY_VC_FACTOR == 0.17
    assert ACI_US_SIMPLIFIED_ONE_WAY_VC_FACTOR == 2.0
    assert aci_metric_vc_is_unit_safe(0.17)
    assert not aci_metric_vc_is_unit_safe(2.0)


def test_uls_codeverify1_audit_keeps_first_pass_bridge_and_psc_items_out_of_final_pass() -> None:
    from concrete_pmm_pro.analysis.uls_shear_torsion_code_basis import audit_items_for_route

    bridge_psc_items = audit_items_for_route("AASHTO_PSC")
    assert bridge_psc_items
    assert any(item.risk_level == "CRITICAL" for item in bridge_psc_items)
    assert all(item.implementation_status in {"PARTIAL", "MISSING"} for item in bridge_psc_items)
    assert any("Combined V+T" in item.check_item for item in bridge_psc_items)


def test_uls_vt1_combined_shear_torsion_review_check_produces_stress_and_transverse_dc() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=400.0, y=0.0),
            Point2D(x=400.0, y=900.0),
            Point2D(x=0.0, y=900.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C40", fc_MPa=40.0),
        "rebars": [
            Rebar(x_mm=80.0, y_mm=80.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=320.0, y_mm=80.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=80.0, y_mm=820.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=320.0, y_mm=820.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_shear_reinforcement_table": [
            {"Active": True, "Zone": "Full", "x_start_m": 0.0, "x_end_m": 20.0, "Bar Size": "DB12", "Diameter_mm": 12.0, "Legs": 2, "Spacing_mm": 150.0, "fy_MPa": 400.0, "Note": "provided"}
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 2.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 150.0, "Tu": 20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 18.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": -150.0, "Tu": -20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    vt = _beam_uls_combined_vt_check_dataframe(state, active, strength_route=route)
    audit = _beam_uls_combined_vt_audit_dataframe(vt)

    assert not vt.empty
    assert {"LOAD STATION", "CRITICAL SHEAR SECTION"}.issubset(set(vt["Station type"]))
    design_rows = vt[vt["Status"] != "NOT APPLICABLE"]
    assert not design_rows.empty
    assert design_rows["Stress D/C value"].notna().any()
    assert design_rows["Transverse D/C value"].notna().any()
    assert design_rows["Longitudinal D/C value"].notna().any()
    assert "Longitudinal status" in design_rows.columns
    assert "PASS" in set(design_rows["Status"]) or "PASS — REVIEW" in set(design_rows["Status"]) or "FAIL" in set(design_rows["Status"])
    assert not audit.empty
    assert "(Av+2At)/s req" in audit.columns
    assert "Al req" in audit.columns
    assert "Al provided" in audit.columns


def test_uls_vt2_1_calculate_shear_torsion_builds_internal_source_rows() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=400.0, y=0.0),
            Point2D(x=400.0, y=900.0),
            Point2D(x=0.0, y=900.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C40", fc_MPa=40.0),
        "rebars": [
            Rebar(x_mm=80.0, y_mm=80.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=320.0, y_mm=80.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=80.0, y_mm=820.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=320.0, y_mm=820.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_shear_reinforcement_table": [
            {"Active": True, "Zone": "Full", "x_start_m": 0.0, "x_end_m": 20.0, "Bar Size": "DB12", "Diameter_mm": 12.0, "Legs": 2, "Spacing_mm": 150.0, "fy_MPa": 400.0, "Note": "provided"}
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 2.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 150.0, "Tu": 20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
            {"Active": True, "Station x (m)": 18.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": -150.0, "Tu": -20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    result = _beam_uls_calculate_selected_check(state, active, selected_check="Shear + Torsion", strength_route=route)

    assert not result["combined_vt_df"].empty
    assert not result["shear_check_df"].empty
    assert not result["torsion_check_df"].empty
    assert "shear_boundary_capacity_df" in result
    assert "torsion_boundary_capacity_df" in result
    assert _beam_uls_combined_vt_source_readiness_notes(result["combined_vt_df"]) == []


def test_uls_vt2_5_combined_vt_treats_zero_shear_as_valid_and_plots_member_end_boundaries() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=400.0, y=0.0),
            Point2D(x=400.0, y=900.0),
            Point2D(x=0.0, y=900.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C40", fc_MPa=40.0),
        "rebars": [
            Rebar(x_mm=80.0, y_mm=80.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=320.0, y_mm=80.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=80.0, y_mm=820.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=320.0, y_mm=820.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_shear_reinforcement_table": [
            {"Active": True, "Zone": "Full", "x_start_m": 0.0, "x_end_m": 20.0, "Bar Size": "DB12", "Diameter_mm": 12.0, "Legs": 2, "Spacing_mm": 150.0, "fy_MPa": 400.0, "Note": "provided"}
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 0.0, "Case Name": "Strength I", "Mux": 1.0, "Vuy": 250.0, "Tu": 20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "member end"},
            {"Active": True, "Station x (m)": 10.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 0.0, "Tu": 20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "zero shear"},
            {"Active": True, "Station x (m)": 20.0, "Case Name": "Strength I", "Mux": 1.0, "Vuy": -250.0, "Tu": -20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "member end"},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    vt = _beam_uls_combined_vt_check_dataframe(state, active, strength_route=route)
    mid = vt[vt["Governing x"] == "10.000 m"].iloc[0]
    ends = vt[vt["Governing x"].isin(["0.000 m", "20.000 m"])]
    readiness = _beam_uls_combined_vt_source_readiness_dataframe(vt)

    assert set(ends["Status"]) == {"DIAGRAM BOUNDARY"}
    assert set(ends["Station type"]) == {"DIAGRAM BOUNDARY"}
    assert ends["Overall D/C value"].notna().any()
    assert mid["Status"] in {"PASS", "PASS — REVIEW", "FAIL"}
    assert mid["Shear stress MPa"] == 0.0
    assert mid["Av shear req mm2/mm"] == 0.0
    assert "10.000 m" not in set(readiness["Station x"])
    assert "0.000 m" not in set(readiness["Station x"])
    assert "20.000 m" not in set(readiness["Station x"])
    fig = _make_beam_uls_combined_vt_utilization_figure(vt, code_label="AASHTO LRFD")
    stress_trace = next(trace for trace in fig.data if str(trace.name).startswith("Stress interaction D/C"))
    assert min(float(x) for x in stress_trace.x) == 0.0
    assert max(float(x) for x in stress_trace.x) == 20.0
    governing_trace = next(trace for trace in fig.data if trace.name == "Governing V+T check")
    assert all(float(x) not in {0.0, 20.0} for x in governing_trace.x)


def test_uls_vt2_6_combined_vt_adds_endpoint_boundaries_when_load_rows_start_inside_span() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=400.0, y=0.0),
            Point2D(x=400.0, y=900.0),
            Point2D(x=0.0, y=900.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C40", fc_MPa=40.0),
        "rebars": [
            Rebar(x_mm=80.0, y_mm=80.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=320.0, y_mm=80.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=80.0, y_mm=820.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=320.0, y_mm=820.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_shear_reinforcement_table": [
            {"Active": True, "Zone": "Full", "x_start_m": 0.0, "x_end_m": 20.0, "Bar Size": "DB12", "Diameter_mm": 12.0, "Legs": 2, "Spacing_mm": 150.0, "fy_MPa": 400.0, "Note": "provided"}
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 2.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 250.0, "Tu": 20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "inside left"},
            {"Active": True, "Station x (m)": 10.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 0.0, "Tu": 20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "zero shear"},
            {"Active": True, "Station x (m)": 18.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": -250.0, "Tu": 20.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "inside right"},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    vt = _beam_uls_combined_vt_check_dataframe(state, active, strength_route=route)
    ends = vt[vt["Governing x"].isin(["0.000 m", "20.000 m"])]
    assert len(ends) == 2
    assert set(ends["Station type"]) == {"DIAGRAM BOUNDARY"}
    fig = _make_beam_uls_combined_vt_utilization_figure(vt, code_label="AASHTO LRFD")
    for trace_name in ["Stress interaction D/C", "Transverse reinforcement D/C", "Longitudinal Al D/C"]:
        trace = next(trace for trace in fig.data if str(trace.name).startswith(trace_name))
        pairs = {round(float(x), 6): y for x, y in zip(trace.x, trace.y)}
        assert min(float(x) for x in trace.x) == 0.0
        assert max(float(x) for x in trace.x) == 20.0
        assert math.isfinite(float(pairs[0.0]))
        assert math.isfinite(float(pairs[20.0]))

    table = _beam_uls_check_table(active, combined_vt_df=vt)
    combined = table.loc[table["Check"] == "Shear + Torsion"].iloc[0]
    assert combined["Status"] in {"PASS — REVIEW", "FAIL", "DATA REQUIRED", "REVIEW — SOURCE"}
    assert "Vu" in combined["Demand"] and "Tu" in combined["Demand"]


def test_uls_vt2_7_combined_vt_plot_fills_endpoint_boundary_values_for_all_traces() -> None:
    vt = pd.DataFrame(
        [
            {"Status": "DIAGRAM BOUNDARY", "Station type": "DIAGRAM BOUNDARY", "Governing x": "0.000 m", "Case": "Strength I", "Stress D/C value": float("nan"), "Transverse D/C value": float("nan"), "Longitudinal D/C value": float("nan"), "Overall D/C value": float("nan")},
            {"Status": "PASS — REVIEW", "Station type": "LOAD STATION", "Governing x": "2.000 m", "Case": "Strength I", "Stress D/C value": 0.25, "Transverse D/C value": 0.55, "Longitudinal D/C value": 0.20, "Overall D/C value": 0.55},
            {"Status": "PASS — REVIEW", "Station type": "LOAD STATION", "Governing x": "18.000 m", "Case": "Strength I", "Stress D/C value": 0.26, "Transverse D/C value": 0.56, "Longitudinal D/C value": 0.21, "Overall D/C value": 0.56},
            {"Status": "DIAGRAM BOUNDARY", "Station type": "DIAGRAM BOUNDARY", "Governing x": "20.000 m", "Case": "Strength I", "Stress D/C value": float("nan"), "Transverse D/C value": float("nan"), "Longitudinal D/C value": float("nan"), "Overall D/C value": float("nan")},
        ]
    )

    plot_df = _beam_uls_combined_vt_plot_dataframe(vt)
    ends = plot_df[plot_df["__x_m"].isin([0.0, 20.0])]

    assert len(ends) == 2
    for column in ["Stress D/C value", "Transverse D/C value", "Longitudinal D/C value"]:
        assert ends[column].notna().all()

    fig = _make_beam_uls_combined_vt_utilization_figure(vt, code_label="AASHTO LRFD")
    for trace_name in ["Stress interaction D/C", "Transverse reinforcement D/C", "Longitudinal Al D/C"]:
        trace = next(trace for trace in fig.data if str(trace.name).startswith(trace_name))
        assert min(float(x) for x in trace.x) == 0.0
        assert max(float(x) for x in trace.x) == 20.0


def test_uls_vt2_7_compact_table_blocks_combined_row_when_source_strength_fails() -> None:
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 7.0, "Case Name": "ULS-G1", "Mux": 100.0, "Vuy": 75.0, "Tu": 100.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    vt = pd.DataFrame(
        [
            {"Check": "Shear + Torsion", "Status": "PASS — REVIEW", "Governing x": "7.000 m", "Case": "ULS-G1", "Vu kN": 75.0, "Tu kN-m": 100.0, "Overall D/C value": 0.567},
        ]
    )
    torsion = pd.DataFrame(
        [
            {"Check": "Torsion", "Status": "FAIL", "Governing x": "7.000 m", "Case": "ULS-G1", "Demand": "100.00 kN-m", "Capacity": "φTn = 88.20 kN-m", "Utilization": "1.134", "D/C value": 1.134},
        ]
    )
    shear = pd.DataFrame(
        [
            {"Check": "Shear", "Status": "PASS", "Governing x": "7.000 m", "Case": "ULS-G1", "Demand": "75.00 kN", "Capacity": "φVn = 558.26 kN", "Utilization": "0.134", "Governing D/C value": 0.134},
        ]
    )

    table = _beam_uls_check_table(active, shear_check_df=shear, torsion_check_df=torsion, combined_vt_df=vt)
    combined = table.loc[table["Check"] == "Shear + Torsion"].iloc[0]

    assert combined["Status"] == "BLOCKED — SOURCE FAIL"
    assert "source gate BLOCKED" in combined["Capacity"]
    assert "interaction 0.567" in combined["Utilization"]
    assert "Torsion FAIL" in combined["Utilization"]


def test_uls_vt2_2_combined_vt_utilization_figure_plots_dc_and_limit() -> None:
    vt = pd.DataFrame(
        [
            {"Status": "PASS — REVIEW", "Governing x": "2.000 m", "Case": "Strength I", "Stress D/C value": 0.25, "Transverse D/C value": 0.55, "Longitudinal D/C value": 0.65, "Overall D/C value": 0.65},
            {"Status": "FAIL", "Governing x": "5.000 m", "Case": "Strength I", "Stress D/C value": 1.15, "Transverse D/C value": 0.60, "Longitudinal D/C value": 0.70, "Overall D/C value": 1.15},
        ]
    )

    fig = _make_beam_uls_combined_vt_utilization_figure(vt, code_label="AASHTO LRFD")

    names = {str(trace.name) for trace in fig.data}
    assert "Stress interaction D/C — Strength I" in names
    assert "Transverse reinforcement D/C — Strength I" in names
    assert "Longitudinal Al D/C — Strength I" in names
    assert "Limit D/C = 1.0" in names
    limit = next(trace for trace in fig.data if trace.name == "Limit D/C = 1.0")
    assert limit.mode == "lines"
    assert limit.line.dash == "dash"
    assert any(trace.name == "Governing V+T check" for trace in fig.data)


def test_uls_vt2_1_source_readiness_notes_explain_data_required_rows() -> None:
    vt = pd.DataFrame(
        [
            {
                "Status": "DATA REQUIRED",
                "Governing x": "7.000 m",
                "Case": "ULS-G1",
                "Stress status": "DATA REQUIRED",
                "Transverse status": "DATA REQUIRED",
                "Longitudinal status": "LAYOUT REQUIRED",
                "Notes": "Combined V+T needs finite shear capacity terms, torsion hoop geometry, active transverse zone, and section/material input.",
            }
        ]
    )

    notes = _beam_uls_combined_vt_source_readiness_notes(vt)
    readiness = _beam_uls_combined_vt_source_readiness_dataframe(vt)

    assert any("Stress interaction source data" in note for note in notes)
    assert any("Transverse source data" in note for note in notes)
    assert any("Longitudinal Al source" in note for note in notes)
    assert not readiness.empty
    assert readiness.iloc[0]["Station x"] == "7.000 m"
    assert "Missing section/material" in readiness.iloc[0]["Stress source"]
    assert "Missing active stirrup" in readiness.iloc[0]["Transverse source"]
    assert "Missing/insufficient" in readiness.iloc[0]["Longitudinal source"]


def test_uls_torsion_code2_promotes_complete_strength_and_detailing_to_pass() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=500.0, y=0.0),
            Point2D(x=500.0, y=1000.0),
            Point2D(x=0.0, y=1000.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C45", fc_MPa=45.0),
        "rebars": [Rebar(x_mm=60.0 + i * 35.0, y_mm=80.0, diameter_mm=25.0, material_name="SD40") for i in range(12)],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "section_has_ordinary_rebar": True,
        "beam_girder_shear_reinforcement_table": [
            {"Active": True, "Zone": "Closed Hoop", "x_start_m": 0.0, "x_end_m": 20.0, "Bar Size": "DB16", "Diameter_mm": 16.0, "Legs": 2, "Spacing_mm": 100.0, "fy_MPa": 400.0, "Note": "complete torsion zone"}
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 7.0, "Case Name": "ULS-G1", "Mux": 500.0, "Vuy": 75.0, "Tu": 50.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    torsion = _beam_uls_torsion_check_dataframe(state, active, strength_route=route)
    row = torsion.iloc[0]

    assert row["Status"] == "PASS"
    assert row["Transverse status"] == "PASS"
    assert row["Longitudinal status"] == "PASS"
    assert row["Detailing status"] == "PASS"
    assert row["Spacing D/C"] <= 1.0
    assert "TORSION.CODE2" in row["Notes"]


def test_uls_vt_code1_compact_table_can_report_pass_when_sources_are_clear() -> None:
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 7.0, "Case Name": "ULS-G1", "Mux": 100.0, "Vuy": 75.0, "Tu": 50.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    vt = pd.DataFrame(
        [
            {"Check": "Shear + Torsion", "Status": "PASS", "Governing x": "7.000 m", "Case": "ULS-G1", "Vu kN": 75.0, "Tu kN-m": 50.0, "Overall D/C value": 0.454},
        ]
    )
    torsion = pd.DataFrame(
        [
            {"Check": "Torsion", "Status": "PASS", "Governing x": "7.000 m", "Case": "ULS-G1", "Demand": "50.00 kN-m", "Capacity": "φTn = 110.24 kN-m", "Utilization": "0.454", "D/C value": 0.454},
        ]
    )
    shear = pd.DataFrame(
        [
            {"Check": "Shear", "Status": "PASS", "Governing x": "7.000 m", "Case": "ULS-G1", "Demand": "75.00 kN", "Capacity": "φVn = 558.26 kN", "Utilization": "0.134", "Governing D/C value": 0.134},
        ]
    )

    table = _beam_uls_check_table(active, shear_check_df=shear, torsion_check_df=torsion, combined_vt_df=vt)
    combined = table.loc[table["Check"] == "Shear + Torsion"].iloc[0]

    assert combined["Status"] == "PASS"
    assert combined["Capacity"] == "Interaction / (Av+2At)/s / Al"
    assert combined["Utilization"] == "0.454"


def test_uls_torsion_code2_excludes_member_end_boundaries_from_governing_and_source_gate() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=500.0, y=0.0),
            Point2D(x=500.0, y=1000.0),
            Point2D(x=0.0, y=1000.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C45", fc_MPa=45.0),
        "rebars": [Rebar(x_mm=60.0 + i * 35.0, y_mm=80.0, diameter_mm=25.0, material_name="SD40") for i in range(12)],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "section_has_ordinary_rebar": True,
        "beam_girder_system_settings": {"span_length_m": 20.0},
        "beam_girder_shear_reinforcement_table": [
            {"Active": True, "Zone": "Interior closed hoop", "x_start_m": 2.0, "x_end_m": 18.0, "Bar Size": "DB16", "Diameter_mm": 16.0, "Legs": 2, "Spacing_mm": 100.0, "fy_MPa": 400.0, "Note": "complete interior torsion zone"}
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 0.0, "Case Name": "ULS-G1", "Mux": 500.0, "Vuy": 75.0, "Tu": 100.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "member end"},
            {"Active": True, "Station x (m)": 7.0, "Case Name": "ULS-G1", "Mux": 500.0, "Vuy": 75.0, "Tu": 100.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "design station"},
            {"Active": True, "Station x (m)": 20.0, "Case Name": "ULS-G1", "Mux": 500.0, "Vuy": 75.0, "Tu": 100.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "member end"},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    torsion = _beam_uls_torsion_check_dataframe(state, active, strength_route=route)
    assert set(torsion.loc[torsion["Governing x"].isin(["0.000 m", "20.000 m"]), "Station type"]) == {"DIAGRAM BOUNDARY"}

    governing = _beam_uls_governing_torsion_row(torsion)
    assert governing is not None
    assert governing["Governing x"] == "7.000 m"
    assert governing["Status"] == "PASS"

    shear = pd.DataFrame(
        [
            {"Check": "Shear", "Status": "PASS", "Governing x": "7.000 m", "Case": "ULS-G1", "Demand": "75.00 kN", "Capacity": "φVn = 643.87 kN", "Utilization": "0.116", "Governing D/C value": 0.116},
        ]
    )
    source_gate = _beam_uls_combined_vt_source_strength_gate(shear, torsion)
    assert source_gate["value"] == "CLEAR"

    vt = pd.DataFrame(
        [
            {"Check": "Shear + Torsion", "Status": "PASS", "Station type": "LOAD STATION", "Governing x": "7.000 m", "Case": "ULS-G1", "Vu kN": 75.0, "Tu kN-m": 100.0, "Overall D/C value": 0.454},
        ]
    )
    compact = _beam_uls_check_table(active, shear_check_df=shear, torsion_check_df=torsion, combined_vt_df=vt)
    torsion_row = compact.loc[compact["Check"] == "Torsion"].iloc[0]
    combined_row = compact.loc[compact["Check"] == "Shear + Torsion"].iloc[0]
    assert torsion_row["Status"] == "PASS"
    assert torsion_row["Governing x"] == "7.000 m"
    assert combined_row["Status"] == "PASS"


def test_uls_shear_code2_requires_active_zone_coverage_for_design_station() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_shear_reinforcement_table": [
            {
                "Active": True,
                "Zone": "Left support only",
                "x_start_m": 0.0,
                "x_end_m": 2.0,
                "Bar Size": "DB12",
                "Diameter_mm": 12.0,
                "Legs": 2,
                "Spacing_mm": 150.0,
                "fy_MPa": 400.0,
                "Note": "does not cover station 5 m",
            }
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 5.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 100.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    shear = _beam_uls_shear_check_dataframe(state, active, strength_route=route)

    row = shear.iloc[0]
    assert row["Status"] == "LAYOUT REQUIRED"
    assert "covers this design/check station" in row["Notes"]
    assert not math.isfinite(float(row["φVn kN"]))


def test_uls_shear_code2_caps_nominal_vn_without_failing_when_demand_is_below_capped_capacity() -> None:
    from concrete_pmm_pro.analysis.uls_strength_routing import beam_girder_uls_strength_route
    from concrete_pmm_pro.core.models import ConcreteMaterial, Point2D, Rebar, RebarMaterial, SectionGeometry

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=0.0, y=0.0),
            Point2D(x=300.0, y=0.0),
            Point2D(x=300.0, y=600.0),
            Point2D(x=0.0, y=600.0),
        ]
    )
    state = {
        "section_geometry": geometry,
        "concrete_material": ConcreteMaterial(name="C30", fc_MPa=30.0),
        "rebars": [
            Rebar(x_mm=75.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
            Rebar(x_mm=225.0, y_mm=50.0, diameter_mm=25.0, material_name="SD40"),
        ],
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0)],
        "prestress_elements": [],
        "beam_girder_shear_depth_settings": {"mode": "Manual effective d / dv", "d_mm": 550.0, "dv_mm": 500.0},
        "beam_girder_shear_reinforcement_table": [
            {
                "Active": True,
                "Zone": "Dense",
                "x_start_m": 0.0,
                "x_end_m": 20.0,
                "Bar Size": "DB32",
                "Diameter_mm": 32.0,
                "Legs": 8,
                "Spacing_mm": 40.0,
                "fy_MPa": 500.0,
                "Note": "dense enough to trigger Vn cap",
            }
        ],
    }
    active = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": 5.0, "Case Name": "Strength I", "Mux": 100.0, "Vuy": 200.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": ""},
        ]
    )
    route = beam_girder_uls_strength_route(is_bridge=True, is_building=False, code_edition="AASHTO LRFD")

    shear = _beam_uls_shear_check_dataframe(state, active, strength_route=route)

    row = shear.iloc[0]
    assert row["Status"] == "PASS"
    assert row["Vn limit status"] == "CAPPED"
    assert row["φVn kN"] == row["φVn limit kN"]
    assert row["Vn uncapped kN"] > row["Vn limit kN"]
    assert "capped" in row["Notes"].lower()
