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

    assert cards[0]["value"] == "FLEXURE PREVIEW"
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
