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
