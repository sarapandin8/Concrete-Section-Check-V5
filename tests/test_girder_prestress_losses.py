from __future__ import annotations

import math

import pandas as pd

from concrete_pmm_pro.serviceability.girder_prestress_losses import (
    GirderApproximateLossInput,
    GirderLossStrandGroupInput,
    RefinedAashtoCoefficientInput,
    calculate_aashto_approximate_long_term_loss_MPa,
    calculate_aci_pci_approximate_prestress_loss,
    calculate_approximate_prestress_loss,
    calculate_elastic_shortening_iterative,
    aci_pci_kcr_from_density,
    estimate_aci_pci_guided_loss_inputs,
    estimate_kdf,
    estimate_kid,
    estimate_refined_aashto_coefficients,
    estimate_volume_surface_ratio_mm,
    loss_result_dataframe_to_force_state_table,
    pci_relaxation_c_factor,
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



def test_pci_relaxation_c_factor_interpolates_and_clamps() -> None:
    assert pci_relaxation_c_factor(0.67) == pci_relaxation_c_factor(0.68)
    assert pci_relaxation_c_factor(0.81) == pci_relaxation_c_factor(0.80)
    mid = pci_relaxation_c_factor(0.75)
    assert 1.11 < mid < 1.16


def test_aci_pci_approximate_loss_separates_es_cr_sh_re_from_aashto() -> None:
    base = _loss_input()
    aci_input = GirderApproximateLossInput(
        groups=base.groups,
        section_area_mm2=base.section_area_mm2,
        section_Ix_mm4=base.section_Ix_mm4,
        centroid_y_from_bottom_mm=base.centroid_y_from_bottom_mm,
        fci_MPa=base.fci_MPa,
        fc_MPa=base.fc_MPa,
        Eci_MPa=base.Eci_MPa,
        humidity_percent=75.0,
        relaxation_class="Low relaxation",
        volume_surface_ratio_mm=3.5 * 25.4,
        kcir=0.90,
        kcr=2.0,
        ksh=1.0,
        self_weight_moment_kNm=250.0,
    )
    result = calculate_aci_pci_approximate_prestress_loss(aci_input)
    df = result.result_dataframe().set_index("Group ID")
    assert result.status in {"OK", "REVIEW"}
    assert any("ACI/PCI-style approximate" in message for message in result.messages)
    assert df.loc["Row 1", "ES loss MPa"] > 0.0
    assert df.loc["Row 1", "LT loss MPa"] > 0.0
    assert df.loc["Row 1", "Pe_transfer/strand_kN"] < df.loc["Row 1", "Pjack/strand_kN"]
    assert df.loc["Row 1", "Pe_eff_final/strand_kN"] < df.loc["Row 1", "Pe_transfer/strand_kN"]
    assert "CR=" in str(df.loc["Row 1", "Engineering note"])
    assert "SH=" in str(df.loc["Row 1", "Engineering note"])
    assert "RE=" in str(df.loc["Row 1", "Engineering note"])


def test_aci_pci_shrinkage_loss_reduces_at_higher_relative_humidity() -> None:
    low_rh = calculate_aci_pci_approximate_prestress_loss(
        GirderApproximateLossInput(
            groups=_loss_input().groups,
            section_area_mm2=_loss_input().section_area_mm2,
            section_Ix_mm4=_loss_input().section_Ix_mm4,
            centroid_y_from_bottom_mm=_loss_input().centroid_y_from_bottom_mm,
            fci_MPa=_loss_input().fci_MPa,
            fc_MPa=_loss_input().fc_MPa,
            Eci_MPa=_loss_input().Eci_MPa,
            humidity_percent=50.0,
            volume_surface_ratio_mm=3.5 * 25.4,
        )
    ).result_dataframe()
    high_rh = calculate_aci_pci_approximate_prestress_loss(
        GirderApproximateLossInput(
            groups=_loss_input().groups,
            section_area_mm2=_loss_input().section_area_mm2,
            section_Ix_mm4=_loss_input().section_Ix_mm4,
            centroid_y_from_bottom_mm=_loss_input().centroid_y_from_bottom_mm,
            fci_MPa=_loss_input().fci_MPa,
            fc_MPa=_loss_input().fc_MPa,
            Eci_MPa=_loss_input().Eci_MPa,
            humidity_percent=85.0,
            volume_surface_ratio_mm=3.5 * 25.4,
        )
    ).result_dataframe()
    assert high_rh.loc[0, "Total loss MPa"] < low_rh.loc[0, "Total loss MPa"]

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



def test_refined_auto_coefficient_estimate_returns_auditable_values() -> None:
    result = estimate_refined_aashto_coefficients(
        RefinedAashtoCoefficientInput(
            section_area_mm2=350000.0,
            exposed_perimeter_mm=2600.0,
            section_Ix_mm4=7.0e9,
            centroid_y_from_bottom_mm=220.0,
            total_aps_mm2=1776.6,
            yps_mm_from_bottom=85.0,
            Ep_MPa=195000.0,
            Eci_MPa=4700.0 * math.sqrt(36.0),
            Ec_MPa=4700.0 * math.sqrt(45.0),
            fci_MPa=36.0,
            fc_MPa=45.0,
            humidity_percent=75.0,
            age_transfer_days=1.0,
            age_deck_days=30.0,
            final_age_days=10000.0,
        )
    )
    assert result.volume_surface_mm > 0.0
    assert 0.0 < result.Kid <= 1.0
    assert 0.0 < result.Kdf <= 1.0
    assert result.psi_td_ti > 0.0
    assert result.psi_tf_ti >= result.psi_td_ti
    assert result.eps_bid_microstrain > 0.0
    assert result.eps_bdf_microstrain >= 0.0
    audit = result.audit_dataframe()
    assert {"Ψb(td,ti)", "εbid", "Kid", "Kdf"}.issubset(set(audit["Coefficient"]))


def test_refined_kid_kdf_reduce_with_prestress_interaction() -> None:
    kid = estimate_kid(
        Ep_MPa=195000.0,
        Eci_MPa=28000.0,
        Aps_mm2=1800.0,
        Ag_mm2=350000.0,
        epg_mm=-140.0,
        Ig_mm4=7.0e9,
        psi_td_ti=0.6,
    )
    kdf = estimate_kdf(
        Ep_MPa=195000.0,
        Ec_MPa=31500.0,
        Aps_mm2=1800.0,
        Ac_mm2=350000.0,
        epc_mm=-140.0,
        Ic_mm4=7.0e9,
        psi_tf_td=1.0,
    )
    assert 0.0 < kid < 1.0
    assert 0.0 < kdf < 1.0
    assert estimate_volume_surface_ratio_mm(350000.0, 2600.0) > 0.0


def test_aci_pci_guided_inputs_compute_vs_in_from_mm_geometry_and_select_normal_weight_kcr() -> None:
    guided = estimate_aci_pci_guided_loss_inputs(
        section_area_mm2=450000.0,
        exposed_perimeter_mm=4000.0,
        section_preset_key="parametric_i_girder",
        section_category="Precast Composite Girder",
        concrete_density_kg_m3=2400.0,
    )
    assert round(guided.volume_surface_ratio_mm, 3) == 112.5
    assert round(guided.volume_surface_ratio_in, 3) == round(112.5 / 25.4, 3)
    assert guided.kcir == 0.90
    assert guided.kcr == 2.0
    assert guided.ksh == 1.0
    assert guided.volume_surface_status in {"OK", "REVIEW"}
    audit = guided.audit_dataframe()
    assert set(["V/S", "Kcir", "Kcr", "Ksh"]).issubset(set(audit["Item"]))
    assert "in." in str(audit.loc[audit["Item"] == "V/S", "Value"].iloc[0])
    assert "mm" in str(audit.loc[audit["Item"] == "V/S", "Value"].iloc[0])


def test_aci_pci_guided_inputs_use_family_fallback_when_geometry_missing() -> None:
    guided = estimate_aci_pci_guided_loss_inputs(
        section_area_mm2=None,
        exposed_perimeter_mm=None,
        section_preset_key="precast_box_beam_exterior",
        concrete_density_kg_m3=2400.0,
    )
    assert guided.volume_surface_ratio_in > 0.0
    assert guided.volume_surface_source == "Preset by section family"
    assert guided.volume_surface_status == "REVIEW"
    assert guided.messages


def test_aci_pci_kcr_from_density_flags_lightweight_review() -> None:
    kcr_normal, source_normal, status_normal = aci_pci_kcr_from_density(2400.0)
    assert kcr_normal == 2.0
    assert status_normal == "OK"
    assert "density" in source_normal
    kcr_light, _source_light, status_light = aci_pci_kcr_from_density(2000.0)
    assert kcr_light == 1.6
    assert status_light == "REVIEW"
