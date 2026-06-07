import pandas as pd

from concrete_pmm_pro.ui.analysis_page import (
    _active_beam_uls_demand_dataframe_from_session,
    _beam_uls_check_table,
    _beam_uls_summary_cards,
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
    assert flexure["Status"] == "PLANNED"
    assert flexure["Case"] == "MID"
    assert flexure["Governing x"] == "10.000 m"
    assert flexure["Capacity"] == "-"
    assert flexure["Utilization"] == "-"
    assert shear["Case"] == "END"
    assert torsion["Status"] == "PLANNED"


def test_uls_girder1_empty_state_is_not_ready_without_fake_pass() -> None:
    active = pd.DataFrame(columns=["Active", "Station x (m)", "Case Name", "Mux", "Vuy", "Tu", "Muy", "Vux", "Nu", "Note"])

    cards = _beam_uls_summary_cards(active, workflow_label="Bridge Beam/Girder", code_label="AASHTO LRFD")

    assert cards[0]["value"] == "NOT READY"
    assert "Define or import" in cards[0]["detail"]
    assert all(card["value"] != "PASS" for card in cards)


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
                "Capacity": "φMn preview = 1,800.00 kN-m",
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
    assert flexure["Capacity"] == "φMn preview = 1,800.00 kN-m"
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
                "Capacity": "φMn preview = 1,800.00 kN-m",
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

    assert cards[0]["value"] == "FLEXURE PREVIEW — PASS"
    assert "no overall ULS PASS/FAIL" in cards[0]["detail"]
    assert cards[1]["title"] == "Critical flexure demand / D/C preview"
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
                "Capacity": "φMn preview = 3,580.44 kN-m",
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

    assert cards[0]["value"] == "FLEXURE PREVIEW — FAIL"
    assert cards[0]["status"] == "danger"
    assert "no overall ULS PASS/FAIL" in cards[0]["detail"]


def test_uls_flex1_3_flexure_figure_plots_full_span_section_phi_mn_without_endpoint_review_trace() -> None:
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
            {"Check": "Flexure", "Status": "SECTION PREVIEW", "Governing x": "0.000 m", "Case": "Strength I", "Demand": "0.00 kN-m", "Capacity": "φMn preview = 3,450.00 kN-m", "Utilization": "-", "Demand kN-m": 0.0, "Capacity kN-m": 3450.0, "Utilization value": float("nan"), "Capacity plot sign": 1.0, "Method": "full-span section φMn preview", "Notes": "Zero-Mux endpoint included"},
            {"Check": "Flexure", "Status": "PASS", "Governing x": "5.000 m", "Case": "Strength I", "Demand": "2,500.00 kN-m", "Capacity": "φMn preview = 3,500.00 kN-m", "Utilization": "0.714", "Demand kN-m": 2500.0, "Capacity kN-m": 3500.0, "Utilization value": 0.714, "Capacity plot sign": 1.0, "Method": "slice_envelope", "Notes": "Primary Mux flexure only"},
            {"Check": "Flexure", "Status": "FAIL", "Governing x": "10.000 m", "Case": "Strength I", "Demand": "5,000.00 kN-m", "Capacity": "φMn preview = 3,580.44 kN-m", "Utilization": "1.396", "Demand kN-m": 5000.0, "Capacity kN-m": 3580.44, "Utilization value": 1.396, "Capacity plot sign": 1.0, "Method": "slice_envelope", "Notes": "Primary Mux flexure only"},
            {"Check": "Flexure", "Status": "SECTION PREVIEW", "Governing x": "20.000 m", "Case": "Strength I", "Demand": "0.00 kN-m", "Capacity": "φMn preview = 3,450.00 kN-m", "Utilization": "-", "Demand kN-m": 0.0, "Capacity kN-m": 3450.0, "Utilization value": float("nan"), "Capacity plot sign": 1.0, "Method": "full-span section φMn preview", "Notes": "Zero-Mux endpoint included"},
        ]
    )

    fig = _make_beam_uls_flexure_preview_figure(active, preview, code_label="AASHTO LRFD")
    trace_names = [trace.name for trace in fig.data]
    text_by_trace = {trace.name: list(trace.text) if getattr(trace, "text", None) is not None else [] for trace in fig.data}

    assert "Governing flexure preview" in trace_names
    assert text_by_trace["Governing flexure preview"] == ["FAIL · D/C 1.396"]
    assert all("PASS" not in text for values in text_by_trace.values() for text in values)
    assert not any(str(name).startswith("Endpoint review") for name in trace_names)
    capacity_trace = next(trace for trace in fig.data if trace.name == "φMn preview — Strength I")
    assert list(capacity_trace.x) == [0.0, 5.0, 10.0, 20.0]
    assert list(capacity_trace.y) == [3450.0, 3500.0, 3580.44, 3450.0]


def test_uls_flex1_3_preview_engine_plots_section_phi_mn_at_zero_mux_endpoints() -> None:
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

    assert any("full-span section φMn preview" in message for message in messages)
    endpoints = preview[preview["Governing x"].isin(["0.000 m", "6.000 m"])]
    assert len(endpoints) == 2
    assert set(endpoints["Status"]) == {"SECTION PREVIEW"}
    assert all(endpoints["Capacity kN-m"] > 0.0)
    assert endpoints["Utilization value"].isna().all()
    assert "D/C is not applicable at zero demand" in endpoints.iloc[0]["Notes"]
