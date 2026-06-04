from __future__ import annotations

import pandas as pd

from concrete_pmm_pro.serviceability.girder_prestress_station import (
    active_strand_groups_at_station,
    debonded_strand_numbers_for_row,
    effective_strand_count_in_row_at_station,
    evaluate_girder_prestress_station,
    girder_advisory_debonding_recommendation_dataframe,
    girder_advisory_debonding_recommendations,
    girder_critical_transfer_station_dataframe,
    girder_debonding_layout_zones,
    girder_debonding_preview_status,
    girder_debonding_rule_audit_dataframe,
    girder_debonding_rule_checks,
    girder_debonding_zones_for_row,
    girder_prestress_station_dataframe,
    girder_stage_pe_mapping_dataframe,
    girder_stage_pe_mapping_status,
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




def test_individual_debonded_strand_selection_partially_reduces_support_effective_count() -> None:
    layout = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "No. Strands": 10,
                "Area/Strand_mm2": 100.0,
                "Total Aps_mm2": 1000.0,
                "y_mm_from_bottom": 50.0,
                "Pe_transfer/strand_kN": 150.0,
                "Pe_construction/strand_kN": 140.0,
                "Pe_eff_final/strand_kN": 120.0,
                "Left debond m": 1.0,
                "Right debond m": 1.0,
                "Debonded strand nos": "1,2,9,10",
            }
        ]
    )
    row = layout.iloc[0]
    assert debonded_strand_numbers_for_row(row) == (1, 2, 9, 10)
    assert effective_strand_count_in_row_at_station(row, x_m=0.0, span_length_m=10.0) == 6
    assert effective_strand_count_in_row_at_station(row, x_m=5.0, span_length_m=10.0) == 10

    support = evaluate_girder_prestress_station(layout, x_m=0.0, span_length_m=10.0)
    assert support.effective_strands == 6
    assert support.aps_eff_mm2 == 600.0
    assert support.pe_transfer_eff_kN == 900.0


def test_debonding_rule_audit_reports_row_based_preview_and_review_items() -> None:
    audit = girder_debonding_rule_audit_dataframe(_layout(), span_length_m=20.0)
    assert "PS6A scope" in set(audit["Rule"])
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


def test_advisory_debonding_recommendation_selects_symmetric_outer_pairs_with_code_guardrails() -> None:
    layout = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "No. Strands": 19,
                "Area/Strand_mm2": 98.7,
                "y_mm_from_bottom": 50.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            },
            {
                "Active": True,
                "Group ID": "Row 2",
                "No. Strands": 17,
                "Area/Strand_mm2": 98.7,
                "y_mm_from_bottom": 100.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            },
        ]
    )
    recommendations = girder_advisory_debonding_recommendations(layout, span_length_m=30.0)
    assert recommendations[0].group_id == "Row 1"
    assert recommendations[0].recommended_numbers == (1, 19)
    assert recommendations[0].left_debond_m == 1.0
    assert recommendations[0].right_debond_m == 1.0
    assert recommendations[0].guardrail_status == "ADVISORY OK"
    assert recommendations[1].recommended_numbers == (1, 17)
    assert recommendations[1].left_debond_m == 1.5
    proposed = sum(len(item.recommended_numbers) for item in recommendations)
    assert proposed <= int((19 + 17) * 0.25)



def test_advisory_debonding_recommendation_uses_spaced_pairs_when_more_than_one_pair_is_requested() -> None:
    layout = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "No. Strands": 18,
                "Area/Strand_mm2": 98.7,
                "y_mm_from_bottom": 50.0,
            },
        ]
    )
    recommendations = girder_advisory_debonding_recommendations(layout, span_length_m=30.0, max_pairs_per_row=2)
    assert recommendations[0].recommended_numbers == (1, 3, 16, 18)


def test_advisory_debonding_recommendation_dataframe_reports_no_action_when_limits_are_exhausted() -> None:
    layout = pd.DataFrame(
        [
            {"Active": True, "Group ID": "Small row", "No. Strands": 3, "y_mm_from_bottom": 50.0},
        ]
    )
    df = girder_advisory_debonding_recommendation_dataframe(layout, span_length_m=10.0)
    assert df.loc[0, "Guardrail status"] == "NO ACTION"
    assert df.loc[0, "Recommended debonded strand nos"] == "—"
    assert "25%" in df.loc[0, "Engineering reason"] or "40%" in df.loc[0, "Engineering reason"]


def test_stage_pe_mapping_reports_ready_sources_for_all_sls_stages() -> None:
    mapping = girder_stage_pe_mapping_dataframe(_layout())
    assert mapping["Stage"].tolist() == ["Transfer", "Construction", "Final service"]
    assert mapping["Status"].tolist() == ["READY", "READY", "READY"]
    assert mapping.loc[mapping["Stage"] == "Transfer", "Pe total kN"].iloc[0] == 1100.0
    status, messages = girder_stage_pe_mapping_status(_layout())
    assert status == "READY"
    assert messages == []


def test_stage_pe_mapping_flags_missing_service_pe_before_sls_use() -> None:
    layout = _layout().copy()
    layout.loc[layout["Group ID"] == "Independent debond", "Pe_eff_final/strand_kN"] = 0.0
    mapping = girder_stage_pe_mapping_dataframe(layout).set_index("Stage")
    assert mapping.loc["Final service", "Status"] == "REVIEW"
    assert "Independent debond" in mapping.loc["Final service", "Engineering note"]
    status, messages = girder_stage_pe_mapping_status(layout)
    assert status == "REVIEW"
    assert any("Final service" in message for message in messages)
