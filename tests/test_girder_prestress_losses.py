from __future__ import annotations

import math

import pandas as pd

from concrete_pmm_pro.serviceability.girder_prestress_losses import (
    GirderApproximateLossInput,
    GirderLossStrandGroupInput,
    calculate_aashto_approximate_long_term_loss_MPa,
    calculate_approximate_prestress_loss,
    calculate_elastic_shortening_iterative,
    loss_result_dataframe_to_force_state_table,
    relaxation_loss_MPa,
)


def _loss_input() -> GirderApproximateLossInput:
    groups = (
        GirderLossStrandGroupInput(
            group_id="Row 1",
            no_strands=16,
            area_per_strand_mm2=98.7,
            y_mm_from_bottom=50.0,
            pjack_per_strand_kN=137.7,
            Ep_MPa=195000.0,
            fpu_MPa=1860.0,
        ),
        GirderLossStrandGroupInput(
            group_id="Row 2",
            no_strands=2,
            area_per_strand_mm2=98.7,
            y_mm_from_bottom=350.0,
            pjack_per_strand_kN=137.7,
            Ep_MPa=195000.0,
            fpu_MPa=1860.0,
        ),
    )
    return GirderApproximateLossInput(
        groups=groups,
        section_area_mm2=350000.0,
        section_Ix_mm4=7.0e9,
        centroid_y_from_bottom_mm=220.0,
        fci_MPa=36.0,
        fc_MPa=45.0,
        Eci_MPa=4700.0 * math.sqrt(36.0),
        humidity_percent=70.0,
        relaxation_class="Low relaxation",
    )


def test_elastic_shortening_iteration_returns_post_es_loss_and_fcgp() -> None:
    es, fcgp, iterations = calculate_elastic_shortening_iterative(_loss_input())
    assert iterations >= 1
    assert es["Row 1"] > 0.0
    assert fcgp["Row 1"] > 0.0
    assert es["Row 1"] != es["Row 2"]


def test_aashto_approximate_long_term_loss_uses_humidity_strength_and_relaxation() -> None:
    loss_low, gamma_h, gamma_st, fpR = calculate_aashto_approximate_long_term_loss_MPa(
        fpi_MPa=1200.0,
        total_aps_mm2=1800.0,
        section_area_mm2=350000.0,
        humidity_percent=70.0,
        fci_MPa=36.0,
        relaxation_class="Low relaxation",
    )
    loss_stress_relieved, *_ = calculate_aashto_approximate_long_term_loss_MPa(
        fpi_MPa=1200.0,
        total_aps_mm2=1800.0,
        section_area_mm2=350000.0,
        humidity_percent=70.0,
        fci_MPa=36.0,
        relaxation_class="Stress-relieved",
    )
    assert abs(gamma_h - 1.0) < 1.0e-12
    assert gamma_st > 0.0
    assert round(fpR, 3) == round(relaxation_loss_MPa("Low relaxation"), 3)
    assert loss_stress_relieved > loss_low


def test_approximate_loss_maps_to_stage_pe_and_preserves_order() -> None:
    result = calculate_approximate_prestress_loss(_loss_input())
    df = result.result_dataframe().set_index("Group ID")
    assert result.status in {"OK", "REVIEW"}
    assert df.loc["Row 1", "Pe_transfer/strand_kN"] < df.loc["Row 1", "Pjack/strand_kN"]
    assert df.loc["Row 1", "Pe_construction/strand_kN"] == df.loc["Row 1", "Pe_transfer/strand_kN"]
    assert df.loc["Row 1", "Pe_eff_final/strand_kN"] < df.loc["Row 1", "Pe_transfer/strand_kN"]
    assert df.loc["Row 1", "Total loss %"] > 5.0


def test_loss_result_dataframe_maps_to_existing_force_state_schema() -> None:
    result = calculate_approximate_prestress_loss(_loss_input()).result_dataframe()
    force = loss_result_dataframe_to_force_state_table(result, pd.DataFrame())
    assert {
        "Pjack/strand_kN",
        "Pe_transfer/strand_kN",
        "Pe_construction/strand_kN",
        "Pe_eff_final/strand_kN",
        "Transfer loss %",
        "Long-term loss %",
    }.issubset(force.columns)
    assert force.loc[0, "Pe_construction/strand_kN"] == force.loc[0, "Pe_transfer/strand_kN"]
    assert force.loc[0, "Pe_eff_final/strand_kN"] < force.loc[0, "Pe_transfer/strand_kN"]

from concrete_pmm_pro.serviceability.girder_prestress_losses import (
    RefinedAashtoManualCoefficientInput,
    calculate_refined_aashto_time_dependent_loss,
)


def _refined_input() -> RefinedAashtoManualCoefficientInput:
    base = _loss_input()
    return RefinedAashtoManualCoefficientInput(
        groups=base.groups,
        section_area_mm2=base.section_area_mm2,
        section_Ix_mm4=base.section_Ix_mm4,
        centroid_y_from_bottom_mm=base.centroid_y_from_bottom_mm,
        fci_MPa=base.fci_MPa,
        fc_MPa=base.fc_MPa,
        Eci_MPa=base.Eci_MPa,
        Ec_MPa=4700.0 * math.sqrt(base.fc_MPa),
        fpy_MPa=1670.0,
        relaxation_class="Low relaxation",
        age_transfer_days=1.0,
        age_deck_days=30.0,
        final_age_days=10000.0,
        Kid=0.95,
        Kdf=0.85,
        eps_bid=120.0e-6,
        eps_bdf=90.0e-6,
        psi_td_ti=0.60,
        psi_tf_ti=1.60,
        psi_tf_td=0.80,
        delta_fcd_MPa=0.20,
        delta_fcdf_MPa=0.10,
    )


def test_refined_aashto_manual_coefficients_produce_ordered_stage_pe() -> None:
    result = calculate_refined_aashto_time_dependent_loss(_refined_input())
    df = result.result_dataframe().set_index("Group ID")
    assert result.status in {"OK", "REVIEW"}
    assert df.loc["Row 1", "Pe_transfer/strand_kN"] < df.loc["Row 1", "Pjack/strand_kN"]
    assert df.loc["Row 1", "Pe_construction/strand_kN"] < df.loc["Row 1", "Pe_transfer/strand_kN"]
    assert df.loc["Row 1", "Pe_eff_final/strand_kN"] < df.loc["Row 1", "Pe_construction/strand_kN"]
    assert df.loc["Row 1", "Total loss %"] > 5.0


def test_refined_aashto_interval_dataframe_separates_two_time_intervals() -> None:
    result = calculate_refined_aashto_time_dependent_loss(_refined_input())
    intervals = result.interval_dataframe()
    assert set(intervals["Interval"]) == {"Transfer → deck placement", "Deck placement → final"}
    assert {"Shrinkage loss MPa", "Creep loss MPa", "Relaxation loss MPa", "Deck shrinkage loss MPa"}.issubset(intervals.columns)
    assert (intervals["Subtotal loss MPa"] >= 0.0).all()
