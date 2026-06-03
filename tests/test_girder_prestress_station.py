from __future__ import annotations

import pandas as pd

from concrete_pmm_pro.serviceability.girder_prestress_station import (
    active_strand_groups_at_station,
    evaluate_girder_prestress_station,
    girder_critical_transfer_station_dataframe,
    girder_debonding_layout_zones,
    girder_debonding_preview_status,
    girder_debonding_rule_audit_dataframe,
    girder_debonding_rule_checks,
    girder_debonding_zones_for_row,
    girder_prestress_station_dataframe,
    station_candidates_from_debonding,
    strand_group_effective_at_station,
)


def _layout() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Bottom fully bonded",
                "No. Strands": 4,
                "Area/Strand_mm2": 100.0,
                "Total Aps_mm2": 400.0,
                "y_mm_from_bottom": 50.0,
                "Pe_transfer/strand_kN": 150.0,
                "Pe_construction/strand_kN": 140.0,
                "Pe_eff_final/strand_kN": 120.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            },
            {
                "Active": True,
                "Group ID": "Upper symmetric debond",
                "No. Strands": 2,
                "Area/Strand_mm2": 100.0,
                "Total Aps_mm2": 200.0,
                "y_mm_from_bottom": 150.0,
                "Pe_transfer/strand_kN": 150.0,
                "Pe_construction/strand_kN": 140.0,
                "Pe_eff_final/strand_kN": 120.0,
                "Left debond m": 2.0,
                "Right debond m": 2.0,
            },
            {
                "Active": True,
                "Group ID": "Independent debond",
                "No. Strands": 2,
                "Area/Strand_mm2": 100.0,
                "Total Aps_mm2": 200.0,
                "y_mm_from_bottom": 250.0,
                "Pe_transfer/strand_kN": 100.0,
                "Pe_construction/strand_kN": 90.0,
                "Pe_eff_final/strand_kN": 80.0,
                "Left debond m": 1.0,
                "Right debond m": 3.0,
            },
            {
                "Active": False,
                "Group ID": "Inactive row",
                "No. Strands": 10,
                "Area/Strand_mm2": 100.0,
                "Total Aps_mm2": 1000.0,
                "y_mm_from_bottom": 500.0,
                "Pe_transfer/strand_kN": 999.0,
                "Pe_construction/strand_kN": 999.0,
                "Pe_eff_final/strand_kN": 999.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            },
        ]
    )


def test_station_candidates_include_debond_terminations_and_midspan() -> None:
    stations = station_candidates_from_debonding(_layout(), span_length_m=10.0)
    assert stations == [0.0, 1.0, 2.0, 5.0, 7.0, 8.0, 10.0]


def test_active_group_detection_uses_left_and_right_debond_lengths() -> None:
    layout = _layout()
    row = layout.loc[2]
    assert not strand_group_effective_at_station(row, x_m=0.5, span_length_m=10.0)
    assert strand_group_effective_at_station(row, x_m=1.0, span_length_m=10.0)
    assert strand_group_effective_at_station(row, x_m=7.0, span_length_m=10.0)
    assert not strand_group_effective_at_station(row, x_m=7.5, span_length_m=10.0)


def test_station_result_at_support_ignores_debonded_and_inactive_groups() -> None:
    result = evaluate_girder_prestress_station(_layout(), x_m=0.0, span_length_m=10.0)
    assert result.effective_strands == 4
    assert result.aps_eff_mm2 == 400.0
    assert result.pe_transfer_eff_kN == 600.0
    assert result.pe_construction_eff_kN == 560.0
    assert result.pe_eff_final_eff_kN == 480.0
    assert result.yps_eff_mm_from_bottom == 50.0
    assert result.active_group_ids == "Bottom fully bonded"


def test_station_result_at_midspan_has_all_active_groups_and_area_weighted_yps() -> None:
    result = evaluate_girder_prestress_station(_layout(), x_m=5.0, span_length_m=10.0)
    assert result.effective_group_count == 3
    assert result.effective_strands == 8
    assert result.aps_eff_mm2 == 800.0
    assert result.pe_transfer_eff_kN == 1100.0
    assert result.pe_construction_eff_kN == 1020.0
    assert result.pe_eff_final_eff_kN == 880.0
    assert result.yps_eff_mm_from_bottom == 125.0
    assert result.active_group_ids == "Bottom fully bonded, Upper symmetric debond, Independent debond"


def test_all_debonded_support_zone_has_zero_effective_prestress() -> None:
    layout = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Debonded row A",
                "No. Strands": 2,
                "Area/Strand_mm2": 100.0,
                "Total Aps_mm2": 200.0,
                "y_mm_from_bottom": 50.0,
                "Pe_transfer/strand_kN": 150.0,
                "Pe_construction/strand_kN": 140.0,
                "Pe_eff_final/strand_kN": 120.0,
                "Left debond m": 1.0,
                "Right debond m": 1.0,
            },
            {
                "Active": True,
                "Group ID": "Debonded row B",
                "No. Strands": 2,
                "Area/Strand_mm2": 100.0,
                "Total Aps_mm2": 200.0,
                "y_mm_from_bottom": 100.0,
                "Pe_transfer/strand_kN": 150.0,
                "Pe_construction/strand_kN": 140.0,
                "Pe_eff_final/strand_kN": 120.0,
                "Left debond m": 1.5,
                "Right debond m": 1.5,
            },
        ]
    )
    result = evaluate_girder_prestress_station(layout, x_m=0.0, span_length_m=10.0)
    assert result.effective_group_count == 0
    assert result.effective_strands == 0
    assert result.aps_eff_mm2 == 0.0
    assert result.pe_transfer_eff_kN == 0.0
    assert result.yps_eff_mm_from_bottom is None


def test_dataframe_preview_keeps_legacy_columns_and_adds_active_group_ids() -> None:
    preview = girder_prestress_station_dataframe(_layout(), span_length_m=10.0).set_index("x_m")
    assert preview.loc[0.0, "Effective strands"] == 4
    assert preview.loc[5.0, "Effective strands"] == 8
    assert preview.loc[5.0, "Aps_eff_mm2"] == 800.0
    assert preview.loc[5.0, "yps_eff_mm_from_bottom"] == 125.0
    assert "Active group IDs" in preview.columns


def test_active_strand_groups_at_station_returns_group_level_breakdown() -> None:
    groups = active_strand_groups_at_station(_layout(), x_m=5.0, span_length_m=10.0)
    assert [group.group_id for group in groups] == ["Bottom fully bonded", "Upper symmetric debond", "Independent debond"]
    assert [group.no_strands for group in groups] == [4, 2, 2]


def test_debonding_zones_for_row_expose_debonded_sleeves_and_effective_zone() -> None:
    row = _layout().loc[2]
    zones = girder_debonding_zones_for_row(row, span_length_m=10.0)

    assert [zone.zone_type for zone in zones] == [
        "Left debonded sleeve",
        "Bonded / effective",
        "Right debonded sleeve",
    ]
    assert [(zone.x_start_m, zone.x_end_m) for zone in zones] == [(0.0, 1.0), (1.0, 7.0), (7.0, 10.0)]
    assert [zone.is_effective for zone in zones] == [False, True, False]


def test_debonding_layout_zones_ignore_inactive_rows() -> None:
    zones = girder_debonding_layout_zones(_layout(), span_length_m=10.0)
    group_ids = [zone.group_id for zone in zones]

    assert "Inactive row" not in group_ids
    assert group_ids.count("Bottom fully bonded") == 1
    assert group_ids.count("Upper symmetric debond") == 3
    assert group_ids.count("Independent debond") == 3


def test_debonding_rule_audit_reports_row_based_preview_and_review_items() -> None:
    audit = girder_debonding_rule_audit_dataframe(_layout(), span_length_m=20.0)
    assert "PS5C scope" in set(audit["Rule"])
    assert "Left/right symmetry" in set(audit["Rule"])
    symmetry = audit[audit["Rule"] == "Left/right symmetry"].iloc[0]
    assert symmetry["Status"] == "REVIEW"
    assert "Independent debond" in symmetry["Demand / value"]
    assert girder_debonding_preview_status(_layout(), span_length_m=20.0) == "REVIEW"


def test_debonding_rule_audit_flags_debond_length_over_l_over_5() -> None:
    layout = _layout().copy()
    layout.loc[1, "Left debond m"] = 3.0
    checks = {check.rule: check for check in girder_debonding_rule_checks(layout, span_length_m=10.0)}
    assert checks["Debond length"].status == "ERROR"
    assert "L/5 = 2.000 m" in checks["Debond length"].limit
    assert girder_debonding_preview_status(layout, span_length_m=10.0) == "ERROR"


def test_critical_transfer_station_dataframe_includes_end_faces_and_sleeve_transitions() -> None:
    critical = girder_critical_transfer_station_dataframe(_layout(), span_length_m=10.0)
    assert critical["x_m"].tolist() == [0.0, 1.0, 2.0, 7.0, 8.0, 10.0]
    assert critical.loc[0, "Station type"] == "End face"
    assert "Sleeve transition" in set(critical["Station type"])
    assert any("transfer-length" in note for note in critical["Review note"])
