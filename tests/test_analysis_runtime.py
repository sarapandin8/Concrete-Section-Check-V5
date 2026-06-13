from __future__ import annotations

from pathlib import Path

import pandas as pd

from concrete_pmm_pro.analysis.runtime import (
    ACCURACY_PRESET_RESOLUTIONS,
    AnalysisRuntimeMetadata,
    accuracy_preset_resolution,
    analysis_input_hash,
    apply_accuracy_preset_to_settings,
    cache_status_for_hash,
    demand_capacity_input_hash,
    recalculation_required,
    serviceability_input_hash,
    timed_call,
)
from concrete_pmm_pro.analysis.capacity_check import DemandCapacityResult, DemandCapacitySummary
from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, PrestressElement, Rebar, RebarMaterial
from concrete_pmm_pro.geometry.generators import rectangle, rectangular_hollow
from concrete_pmm_pro.serviceability import ServiceabilitySettings
import concrete_pmm_pro.ui.analysis_page as analysis_page_module
from concrete_pmm_pro.ui.analysis_page import (
    PMM_3D_LAYER_DEFAULTS,
    PMM_3D_MASTER_TOGGLE_KEY,
    _diagnostic_summary_message,
    _diagnostics_to_dataframe,
    _aci_rc_pmm_ui_status,
    _filter_pmm_closeout_warnings,
    _method_validation_status_cards,
    _method_validation_status_rows,
    _pmm_closeout_solver_mode_label,
    _readiness_actions_to_dataframe,
    _readiness_blocking_action,
    _validation_status_compact_dataframe,
    _validation_status_detail_dataframe,
    _pmm_3d_display_enabled_from_state,
    _should_generate_pmm_3d_figure_from_state,
    _column_pier_shear_check_dataframe,
    _column_pier_aci_seismic_spacing_summary_dataframe,
    _column_pier_torsion_check_dataframe,
    _column_pier_combined_vt_check_dataframe,
    _column_pier_governing_combined_vt_row,
    _column_pier_check_decision_rows,
    _column_pier_uls_decision_summary_cards,
)


def _analysis_input(**kwargs) -> AnalysisInput:
    data = {
        "section_geometry": rectangle(width_mm=400, height_mm=600),
        "concrete_material": ConcreteMaterial(name="C35", fc_MPa=35, ecu=0.003, beta1=0.80),
        "rebar_materials": [RebarMaterial(name="SD40", fy_MPa=400, Es_MPa=200000)],
        "rebars": [
            Rebar(x_mm=-150, y_mm=-250, diameter_mm=25, material_name="SD40", label="B1"),
            Rebar(x_mm=150, y_mm=250, diameter_mm=25, material_name="SD40", label="B2"),
        ],
        "prestress_elements": [
            PrestressElement(x_mm=0, y_mm=-150, area_mm2=140, steel_type="strand", pe_eff_n=100_000, bonded=True)
        ],
        "load_cases": [LoadCase(name="ULS-01", Pu_N=1_000_000, Mux_Nmm=100_000_000, Muy_Nmm=50_000_000, load_type="ULS")],
        "settings": AnalysisSettings(neutral_axis_angle_steps=12, neutral_axis_depth_steps=10),
    }
    data.update(kwargs)
    return AnalysisInput(**data)


def _column_pier_shear_state(
    *,
    code: str = "ACI 318",
    vux: float = 80.0,
    vuy: float = 120.0,
    tu: float = 0.0,
    closed_layout: str = "Closed ties / hoops",
) -> dict[str, object]:
    return {
        "design_code": code,
        "code_edition": "ACI 318-19" if code == "ACI 318" else "AASHTO LRFD 9th Edition",
        "column_uls_loads_table": pd.DataFrame(
            [
                {
                    "Active": True,
                    "Case Name": "ULS-COL",
                    "Pu": 1000.0,
                    "Mux": 100.0,
                    "Muy": 50.0,
                    "Vux": vux,
                    "Vuy": vuy,
                    "Tu": tu,
                    "Note": "test",
                }
            ]
        ),
        "column_pier_transverse_reinforcement_table": pd.DataFrame(
            [
                {
                    "Active": True,
                    "Zone": "Typical shaft",
                    "x_start_m": 0.0,
                    "x_end_m": 6.0,
                    "Bar Size": "DB12",
                    "Diameter_mm": 12.0,
                    "Legs": 2,
                    "Spacing_mm": 150.0,
                    "fy_MPa": 390.0,
                    "Note": "closed hoops",
                }
            ]
        ),
        "column_pier_transverse_reinforcement_settings": {
            "closed_tie_layout": closed_layout,
            "torsion_core_basis": "Auto from section and tie offset",
            "tie_center_offset_mm": 50.0,
        },
    }


def test_column_pier_aci_shear_preview_reads_vux_vuy_and_transverse_region() -> None:
    analysis_input = _analysis_input(prestress_elements=[])
    df = _column_pier_shear_check_dataframe(_column_pier_shear_state(), analysis_input)

    assert set(df["Direction"]) == {"Vux", "Vuy"}
    assert set(df["Status"]) == {"Preview PASS"}
    assert (pd.to_numeric(df["phiVn kN"], errors="coerce") > pd.to_numeric(df["Abs demand kN"], errors="coerce")).all()
    assert (pd.to_numeric(df["Av/s mm2/mm"], errors="coerce") > 0.0).all()


def test_column_pier_aci_shear_hollow_section_breadth_subtracts_void() -> None:
    section = rectangular_hollow(
        width_mm=1000.0,
        height_mm=800.0,
        t_left_mm=130.0,
        t_right_mm=130.0,
        t_top_mm=110.0,
        t_bottom_mm=110.0,
    )
    analysis_input = _analysis_input(section_geometry=section, prestress_elements=[])
    df = _column_pier_shear_check_dataframe(_column_pier_shear_state(vux=0.0, vuy=50.0), analysis_input)

    assert list(df["Direction"]) == ["Vuy"]
    bw_mm = float(df.iloc[0]["bw mm"])
    assert abs(bw_mm - 260.0) <= 1.0e-6
    assert bw_mm < 1000.0
    assert "holes/voids" in str(df.iloc[0]["Notes"])


def test_column_pier_aashto_shear_remains_review_without_capacity_claim() -> None:
    analysis_input = _analysis_input(prestress_elements=[])
    df = _column_pier_shear_check_dataframe(_column_pier_shear_state(code="AASHTO LRFD"), analysis_input)

    assert set(df["Status"]) == {"REVIEW"}
    assert df["Capacity"].eq("-").all()
    assert df["Notes"].str.contains("AASHTO LRFD Column/Pier shear is not implemented").all()


def test_column_pier_shear_view_reads_aci_seismic_spacing_advisor_summary() -> None:
    analysis_input = _analysis_input(prestress_elements=[])
    state = _column_pier_shear_state()
    state["rebars"] = analysis_input.rebars
    state["column_pier_transverse_reinforcement_settings"]["seismic_detailing"] = "ACI 318 special seismic confinement advisor"
    state["column_pier_transverse_reinforcement_settings"]["seismic_hx_mm"] = 300.0

    df = _column_pier_aci_seismic_spacing_summary_dataframe(state, analysis_input)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["Recommendation"] == "Recommended seismic spacing (ACI advisor)"
    assert row["Tie / hoop"] == "DB12 x 2 legs @ 100 mm"
    assert row["Suggested spacing"] == "100 mm"
    assert row["Governing criterion"] == "0.25 x minimum outside section dimension"
    assert "Control section row only" in row["Analysis use"]


def test_column_pier_aci_torsion_preview_reads_tu_closed_ties_and_ordinary_al() -> None:
    analysis_input = _analysis_input(prestress_elements=[])
    state = _column_pier_shear_state(vux=0.0, vuy=0.0, tu=20.0)
    state["rebars"] = analysis_input.rebars

    df = _column_pier_torsion_check_dataframe(state, analysis_input)

    assert list(df["Status"]) == ["Preview PASS"]
    assert list(df["Transverse status"]) == ["PASS"]
    assert list(df["Longitudinal status"]) == ["PASS"]
    assert float(df.iloc[0]["phiTn kN-m"]) > float(df.iloc[0]["Demand kN-m"])
    assert float(df.iloc[0]["Al provided mm2"]) > float(df.iloc[0]["Al req mm2"])


def test_column_pier_aci_torsion_open_ties_remain_review_without_capacity_claim() -> None:
    analysis_input = _analysis_input(prestress_elements=[])
    state = _column_pier_shear_state(vux=0.0, vuy=0.0, tu=20.0, closed_layout="Open ties - shear only review")
    state["rebars"] = analysis_input.rebars

    df = _column_pier_torsion_check_dataframe(state, analysis_input)

    assert list(df["Status"]) == ["REVIEW"]
    assert df["Capacity"].eq("-").all()
    assert "requires closed ties/hoops or spiral" in str(df.iloc[0]["Notes"])


def test_column_pier_aashto_torsion_remains_review_without_capacity_claim() -> None:
    analysis_input = _analysis_input(prestress_elements=[])
    state = _column_pier_shear_state(code="AASHTO LRFD", vux=0.0, vuy=0.0, tu=20.0)
    state["rebars"] = analysis_input.rebars

    df = _column_pier_torsion_check_dataframe(state, analysis_input)

    assert set(df["Status"]) == {"REVIEW"}
    assert df["Capacity"].eq("-").all()
    assert df["Notes"].str.contains("AASHTO LRFD Column/Pier torsion is not implemented").all()


def test_column_pier_aci_combined_vt_gate_reads_shear_torsion_and_ordinary_al() -> None:
    analysis_input = _analysis_input(prestress_elements=[])
    state = _column_pier_shear_state(vux=80.0, vuy=120.0, tu=20.0)
    state["rebars"] = analysis_input.rebars

    df = _column_pier_combined_vt_check_dataframe(state, analysis_input)
    governing = _column_pier_governing_combined_vt_row(df)

    assert set(df["Direction"]) == {"Vux", "Vuy"}
    assert set(df["Status"]) == {"PASS"}
    assert (pd.to_numeric(df["Overall D/C value"], errors="coerce") < 1.0).all()
    assert (pd.to_numeric(df["Provided Av+2At per s mm2/mm"], errors="coerce") > 0.0).all()
    assert governing is not None
    assert governing["Check"] == "Shear + Torsion"
    assert "ordinary longitudinal Al" in str(governing["Notes"])


def test_column_pier_uls_closeout_decision_summary_combines_pmm_shear_torsion_and_vt() -> None:
    analysis_input = _analysis_input(prestress_elements=[])
    state = _column_pier_shear_state(vux=80.0, vuy=120.0, tu=20.0)
    state["rebars"] = analysis_input.rebars
    state["rc_demand_capacity_result"] = DemandCapacitySummary(
        results=[
            DemandCapacityResult(
                combo_name="ULS-COL",
                Pu_N=1_000_000.0,
                Mux_Nmm=100_000_000.0,
                Muy_Nmm=50_000_000.0,
                Mu_Nmm=111_803_398.9,
                moment_angle_rad=0.0,
                capacity_Mn_Nmm=400_000_000.0,
                capacity_phiMn_Nmm=360_000_000.0,
                capacity_phiPn_N=2_000_000.0,
                dcr=0.32,
                status="PASS",
                message="benchmark PMM row",
            )
        ],
        governing_combo="ULS-COL",
        max_dcr=0.32,
        overall_status="PASS",
    )

    rows = _column_pier_check_decision_rows(state, analysis_input)
    by_check = {row["Check"]: row for row in rows}

    assert list(by_check) == ["Flexural (PMM)", "Shear", "Torsion", "Shear + Torsion"]
    assert by_check["Flexural (PMM)"]["Status"] == "PASS"
    assert by_check["Flexural (PMM)"]["D/C"] == "0.320"
    assert by_check["Shear"]["Status"] == "PASS"
    assert by_check["Torsion"]["Status"] == "PASS"
    assert by_check["Shear + Torsion"]["Status"] == "PASS"
    assert "QA1" in by_check["Shear + Torsion"]["Route / Scope"]

    cards = _column_pier_uls_decision_summary_cards(rows, analysis_input, state)
    assert cards[0]["value"] == "Available for final review"
    assert cards[2]["value"] == "PASS"


def test_column_pier_uls_closeout_decision_summary_flags_aashto_and_active_prestress_review() -> None:
    analysis_input = _analysis_input()
    state = _column_pier_shear_state(code="AASHTO LRFD", vux=80.0, vuy=120.0, tu=20.0)
    state["rebars"] = analysis_input.rebars

    rows = _column_pier_check_decision_rows(state, analysis_input)
    by_check = {row["Check"]: row for row in rows}
    cards = _column_pier_uls_decision_summary_cards(rows, analysis_input, state)

    assert by_check["Flexural (PMM)"]["Status"] == "NOT READY"
    assert by_check["Shear"]["Status"] == "REVIEW"
    assert by_check["Torsion"]["Status"] == "REVIEW"
    assert by_check["Shear + Torsion"]["Status"] == "REVIEW"
    assert cards[0]["value"] == "REVIEW / incomplete"
    assert cards[1]["status"] == "warning"
    assert cards[3]["value"] == "Present"
    assert cards[3]["status"] == "warning"


def test_column_pier_aci_combined_vt_gate_fails_high_torsion_demand() -> None:
    analysis_input = _analysis_input(prestress_elements=[])
    state = _column_pier_shear_state(vux=80.0, vuy=120.0, tu=800.0)
    state["rebars"] = analysis_input.rebars

    df = _column_pier_combined_vt_check_dataframe(state, analysis_input)

    assert "FAIL" in set(df["Status"])
    assert (pd.to_numeric(df["Overall D/C value"], errors="coerce") > 1.0).any()


def test_column_pier_aashto_combined_vt_remains_review_without_final_claim() -> None:
    analysis_input = _analysis_input(prestress_elements=[])
    state = _column_pier_shear_state(code="AASHTO LRFD", vux=80.0, vuy=120.0, tu=20.0)
    state["rebars"] = analysis_input.rebars

    df = _column_pier_combined_vt_check_dataframe(state, analysis_input)

    assert set(df["Status"]) == {"REVIEW"}
    assert df["Notes"].str.contains("AASHTO LRFD Column/Pier combined shear-torsion interaction is not implemented").all()


def test_column_pier_combined_vt_with_active_prestress_stays_review() -> None:
    analysis_input = _analysis_input()
    state = _column_pier_shear_state(vux=80.0, vuy=120.0, tu=20.0)
    state["rebars"] = analysis_input.rebars

    df = _column_pier_combined_vt_check_dataframe(state, analysis_input)

    assert set(df["Status"]) == {"REVIEW"}
    assert df["Notes"].str.contains("Active prestress is present").all()


def test_analysis_input_hash_is_stable_for_identical_engineering_inputs() -> None:
    assert analysis_input_hash(_analysis_input(), "Standard") == analysis_input_hash(_analysis_input(), "Standard")


def test_analysis_input_hash_changes_when_geometry_changes() -> None:
    base = analysis_input_hash(_analysis_input(), "Standard")
    changed = analysis_input_hash(_analysis_input(section_geometry=rectangle(width_mm=450, height_mm=600)), "Standard")

    assert changed != base


def test_analysis_input_hash_changes_when_material_rebar_prestress_load_or_preset_changes() -> None:
    base_input = _analysis_input()
    base = analysis_input_hash(base_input, "Standard")

    assert analysis_input_hash(_analysis_input(concrete_material=ConcreteMaterial(name="C40", fc_MPa=40)), "Standard") != base
    assert analysis_input_hash(_analysis_input(rebars=[Rebar(x_mm=0, y_mm=0, diameter_mm=32)]), "Standard") != base
    assert (
        analysis_input_hash(
            _analysis_input(prestress_elements=[PrestressElement(x_mm=0, y_mm=-100, area_mm2=200, pe_eff_n=150_000)]),
            "Standard",
        )
        != base
    )
    assert (
        analysis_input_hash(
            _analysis_input(load_cases=[LoadCase(name="ULS-02", Pu_N=2_000_000, Mux_Nmm=100_000_000, load_type="ULS")]),
            "Standard",
        )
        != base
    )
    assert analysis_input_hash(base_input, "Fast") != base


def test_analysis_input_hash_ignores_ui_only_notes_labels_and_ids() -> None:
    base = _analysis_input()
    changed = _analysis_input(
        concrete_material=ConcreteMaterial(name="C35", fc_MPa=35, ecu=0.003, beta1=0.80, note="ui note"),
        rebars=[
            Rebar(x_mm=-150, y_mm=-250, diameter_mm=25, material_name="SD40", label="renamed"),
            Rebar(x_mm=150, y_mm=250, diameter_mm=25, material_name="SD40", label="other"),
        ],
        prestress_elements=[
            PrestressElement(
                id="different-id",
                x_mm=0,
                y_mm=-150,
                area_mm2=140,
                steel_type="strand",
                pe_eff_n=100_000,
                bonded=True,
                label="renamed tendon",
            )
        ],
        load_cases=[
            LoadCase(
                name="ULS-01",
                Pu_N=1_000_000,
                Mux_Nmm=100_000_000,
                Muy_Nmm=50_000_000,
                load_type="ULS",
                note="ui note",
            )
        ],
        settings=AnalysisSettings(neutral_axis_angle_steps=12, neutral_axis_depth_steps=10, note="ui note"),
    )

    assert analysis_input_hash(base, "Standard") == analysis_input_hash(changed, "Standard")


def test_cache_status_reports_reuse_and_changed_input() -> None:
    current = "abc"

    assert cache_status_for_hash(current, current, True) == "Cached result used"
    assert recalculation_required(current, current, True) is False
    assert cache_status_for_hash(current, "def", True) == "Input changed, recalculation required"
    assert recalculation_required(current, "def", True) is True


def test_cache_status_reports_no_cached_result() -> None:
    assert cache_status_for_hash("abc", None, False) == "No cached result"
    assert recalculation_required("abc", None, False) is True


def test_fast_accuracy_preset_uses_practical_resolution() -> None:
    fast = accuracy_preset_resolution("Fast")

    assert fast["neutral_axis_angle_steps"] == 18
    assert fast["neutral_axis_depth_steps"] == 30


def test_standard_accuracy_preset_uses_practical_default_resolution() -> None:
    standard = accuracy_preset_resolution("Standard")

    assert standard["neutral_axis_angle_steps"] == 24
    assert standard["neutral_axis_depth_steps"] == 40


def test_high_accuracy_preset_uses_practical_review_resolution() -> None:
    high_accuracy = accuracy_preset_resolution("High Accuracy")

    assert high_accuracy["neutral_axis_angle_steps"] == 36
    assert high_accuracy["neutral_axis_depth_steps"] == 60


def test_default_accuracy_preset_is_standard() -> None:
    assert AnalysisRuntimeMetadata().accuracy_preset == "Standard"
    assert accuracy_preset_resolution(None) == accuracy_preset_resolution("Standard")


def test_visible_accuracy_presets_do_not_expose_heavy_resolutions() -> None:
    visible_resolutions = {
        (resolution["neutral_axis_angle_steps"], resolution["neutral_axis_depth_steps"])
        for resolution in ACCURACY_PRESET_RESOLUTIONS.values()
    }

    assert (72, 120) not in visible_resolutions
    assert (144, 180) not in visible_resolutions


def test_standard_accuracy_preset_applies_practical_resolution() -> None:
    settings = AnalysisSettings()
    standard = apply_accuracy_preset_to_settings(settings, "Standard")

    assert standard.neutral_axis_angle_steps == 24
    assert standard.neutral_axis_depth_steps == 40


def test_fast_and_high_accuracy_presets_adjust_existing_resolution_parameters() -> None:
    assert accuracy_preset_resolution("Fast")["neutral_axis_angle_steps"] < accuracy_preset_resolution("Standard")["neutral_axis_angle_steps"]
    assert (
        accuracy_preset_resolution("High Accuracy")["neutral_axis_depth_steps"]
        > accuracy_preset_resolution("Standard")["neutral_axis_depth_steps"]
    )


def test_3d_pmm_display_toggle_defaults_off() -> None:
    assert _pmm_3d_display_enabled_from_state({}) is False
    assert _should_generate_pmm_3d_figure_from_state({}) is False
    assert PMM_3D_LAYER_DEFAULTS["show_pmm_3d_surface"] is True
    assert PMM_3D_LAYER_DEFAULTS["show_pmm_3d_current_pu_slice"] is True
    assert PMM_3D_LAYER_DEFAULTS["show_pmm_3d_selected_point"] is True
    assert PMM_3D_LAYER_DEFAULTS["show_pmm_3d_all_load_points"] is False


def test_normal_3d_pmm_ui_does_not_expose_raw_points_toggle() -> None:
    source = Path(analysis_page_module.__file__).read_text(encoding="utf-8")

    assert "Show PMM raw points" not in source
    assert "show_pmm_3d_raw_points" not in source


def test_3d_pmm_display_toggle_does_not_change_solver_input_hash() -> None:
    analysis_input = _analysis_input()
    state_off = {PMM_3D_MASTER_TOGGLE_KEY: False}
    state_on = {PMM_3D_MASTER_TOGGLE_KEY: True}
    base_hash = analysis_input_hash(analysis_input, "Standard")

    assert _pmm_3d_display_enabled_from_state(state_off) is False
    assert _pmm_3d_display_enabled_from_state(state_on) is True
    assert analysis_input_hash(analysis_input, "Standard") == base_hash
    assert analysis_input_hash(analysis_input, "Standard") == base_hash


def test_3d_pmm_generation_is_skipped_when_master_toggle_is_false() -> None:
    state = {
        PMM_3D_MASTER_TOGGLE_KEY: False,
        "show_pmm_3d_surface": True,
        "show_pmm_3d_current_pu_slice": True,
        "show_pmm_3d_selected_point": True,
        "show_pmm_3d_all_load_points": True,
    }

    assert _should_generate_pmm_3d_figure_from_state(state) is False


def test_3d_pmm_generation_requires_at_least_one_enabled_layer() -> None:
    state = {
        PMM_3D_MASTER_TOGGLE_KEY: True,
        "show_pmm_3d_surface": False,
        "show_pmm_3d_current_pu_slice": False,
        "show_pmm_3d_selected_point": False,
        "show_pmm_3d_all_load_points": False,
    }

    assert _should_generate_pmm_3d_figure_from_state({PMM_3D_MASTER_TOGGLE_KEY: True}) is True
    assert _should_generate_pmm_3d_figure_from_state(state) is False


def test_serviceability_input_hash_changes_with_serviceability_settings() -> None:
    analysis_input = _analysis_input()
    base = serviceability_input_hash(analysis_input, ServiceabilitySettings(enabled=True))
    changed = serviceability_input_hash(analysis_input, ServiceabilitySettings(enabled=True, use_transformed_section=True))

    assert changed != base


def test_demand_capacity_input_hash_is_stable_for_identical_pmm_hash_and_load_cases() -> None:
    load_cases = [LoadCase(name="ULS-01", Pu_N=1_000_000, Mux_Nmm=100_000_000, Muy_Nmm=50_000_000, load_type="ULS")]

    assert demand_capacity_input_hash("pmm-hash", load_cases) == demand_capacity_input_hash("pmm-hash", load_cases)


def test_demand_capacity_input_hash_changes_when_pmm_hash_changes() -> None:
    load_cases = [LoadCase(name="ULS-01", Pu_N=1_000_000, Mux_Nmm=100_000_000, Muy_Nmm=50_000_000, load_type="ULS")]

    assert demand_capacity_input_hash("pmm-hash-a", load_cases) != demand_capacity_input_hash("pmm-hash-b", load_cases)


def test_demand_capacity_input_hash_changes_when_pu_changes() -> None:
    base = [LoadCase(name="ULS-01", Pu_N=1_000_000, Mux_Nmm=100_000_000, Muy_Nmm=50_000_000, load_type="ULS")]
    changed = [LoadCase(name="ULS-01", Pu_N=1_100_000, Mux_Nmm=100_000_000, Muy_Nmm=50_000_000, load_type="ULS")]

    assert demand_capacity_input_hash("pmm-hash", changed) != demand_capacity_input_hash("pmm-hash", base)


def test_demand_capacity_input_hash_changes_when_mux_or_muy_changes() -> None:
    base = [LoadCase(name="ULS-01", Pu_N=1_000_000, Mux_Nmm=100_000_000, Muy_Nmm=50_000_000, load_type="ULS")]
    changed_mux = [LoadCase(name="ULS-01", Pu_N=1_000_000, Mux_Nmm=120_000_000, Muy_Nmm=50_000_000, load_type="ULS")]
    changed_muy = [LoadCase(name="ULS-01", Pu_N=1_000_000, Mux_Nmm=100_000_000, Muy_Nmm=60_000_000, load_type="ULS")]
    base_hash = demand_capacity_input_hash("pmm-hash", base)

    assert demand_capacity_input_hash("pmm-hash", changed_mux) != base_hash
    assert demand_capacity_input_hash("pmm-hash", changed_muy) != base_hash


def test_demand_capacity_input_hash_changes_when_active_status_changes() -> None:
    base = [
        LoadCase(name="ULS-01", Pu_N=1_000_000, Mux_Nmm=100_000_000, Muy_Nmm=50_000_000, load_type="ULS"),
        LoadCase(name="ULS-02", Pu_N=1_200_000, Mux_Nmm=90_000_000, Muy_Nmm=40_000_000, load_type="ULS", active=False),
    ]
    changed = [
        LoadCase(name="ULS-01", Pu_N=1_000_000, Mux_Nmm=100_000_000, Muy_Nmm=50_000_000, load_type="ULS"),
        LoadCase(name="ULS-02", Pu_N=1_200_000, Mux_Nmm=90_000_000, Muy_Nmm=40_000_000, load_type="ULS", active=True),
    ]

    assert demand_capacity_input_hash("pmm-hash", changed) != demand_capacity_input_hash("pmm-hash", base)


def test_demand_capacity_input_hash_ignores_ui_only_notes() -> None:
    base = [LoadCase(name="ULS-01", Pu_N=1_000_000, Mux_Nmm=100_000_000, Muy_Nmm=50_000_000, load_type="ULS")]
    changed = [
        LoadCase(
            name="ULS-01",
            Pu_N=1_000_000,
            Mux_Nmm=100_000_000,
            Muy_Nmm=50_000_000,
            load_type="ULS",
            note="UI-only review note",
        )
    ]

    assert demand_capacity_input_hash("pmm-hash", changed) == demand_capacity_input_hash("pmm-hash", base)


def test_timed_call_returns_result_and_timing() -> None:
    result, timing = timed_call("quick operation", lambda value: value + 1, 1)

    assert result == 2
    assert timing.label == "quick operation"
    assert timing.elapsed_seconds >= 0

from concrete_pmm_pro.analysis.capacity_check import DemandCapacityResult, DemandCapacitySummary
from concrete_pmm_pro.ui.analysis_page import (
    _active_load_case_usage_summary,
    _analysis_result_overview_cards,
    _demand_capacity_transparency_dataframe,
)


def _synthetic_dc_summary_for_transparency() -> DemandCapacitySummary:
    return DemandCapacitySummary(
        results=[
            DemandCapacityResult(
                combo_name="ULS-GOV",
                Pu_N=1_500_000.0,
                Mux_Nmm=120_000_000.0,
                Muy_Nmm=90_000_000.0,
                Mu_Nmm=150_000_000.0,
                moment_angle_rad=0.64,
                capacity_Mn_Nmm=None,
                capacity_phiMn_Nmm=100_000_000.0,
                capacity_phiPn_N=1_500_000.0,
                dcr=1.5,
                status="FAIL",
                message="Synthetic governing case.",
                capacity_method="slice_envelope",
                slice_method="interpolated",
                envelope_method="convex_hull",
                used_fallback=False,
                warning_count=2,
            ),
            DemandCapacityResult(
                combo_name="ULS-OK",
                Pu_N=900_000.0,
                Mux_Nmm=50_000_000.0,
                Muy_Nmm=0.0,
                Mu_Nmm=50_000_000.0,
                moment_angle_rad=0.0,
                capacity_Mn_Nmm=None,
                capacity_phiMn_Nmm=100_000_000.0,
                capacity_phiPn_N=900_000.0,
                dcr=0.5,
                status="PASS",
                message="Synthetic pass.",
                capacity_method="point_cloud_fallback",
                slice_method="tolerance_fallback",
                envelope_method="N/A",
                used_fallback=True,
                warning_count=1,
            ),
        ],
        governing_combo="ULS-GOV",
        max_dcr=1.5,
        overall_status="FAIL",
    )


def test_analysis_transparency_dataframe_marks_governing_and_methods() -> None:
    df = _demand_capacity_transparency_dataframe(_synthetic_dc_summary_for_transparency())

    assert list(df["Case Name"]) == ["ULS-GOV", "ULS-OK"]
    assert df.loc[0, "Governing"] == "Yes"
    assert df.loc[0, "D/C"] == 1.5
    assert df.loc[0, "Available_phiMn_kNm"] == 100.0
    assert df.loc[1, "Fallback"] == "Yes"
    assert df.loc[1, "Capacity Method"] == "point_cloud_fallback"


def test_active_load_case_usage_summary_separates_uls_sls_and_inactive() -> None:
    cases = [
        LoadCase(name="ULS-1", load_type="ULS", active=True),
        LoadCase(name="SLS-1", load_type="SLS", active=True),
        LoadCase(name="ULS-OFF", load_type="ULS", active=False),
    ]

    summary = _active_load_case_usage_summary(cases)

    assert summary["total"] == 3
    assert summary["active_uls"] == 1
    assert summary["active_sls"] == 1
    assert summary["inactive"] == 1


def test_analysis_overview_cards_expose_governing_case_and_fallback_counts() -> None:
    cards = _analysis_result_overview_cards(
        _synthetic_dc_summary_for_transparency(),
        [LoadCase(name="ULS-GOV", load_type="ULS"), LoadCase(name="SLS-1", load_type="SLS")],
    )
    card_map = {card["title"]: card for card in cards}

    assert card_map["Overall ULS Status"]["value"] == "FAIL"
    assert card_map["Governing Case"]["value"] == "ULS-GOV"
    assert card_map["Max D/C"]["value"] == "1.500"
    assert card_map["Active ULS Used"]["value"] == "1"
    assert card_map["Fallback Cases"]["value"] == "1"


def test_readiness_blocking_action_explains_no_active_uls_fix() -> None:
    action = _readiness_blocking_action("No active ULS load cases are available.")

    assert action["Where to Fix"] == "Loads"
    assert "Add or activate" in action["Recommended Action"]
    assert "strength load case" in action["Recommended Action"]


def test_readiness_actions_dataframe_is_actionable_for_multiple_errors() -> None:
    df = _readiness_actions_to_dataframe(
        [
            "Section geometry is missing.",
            "No active longitudinal reinforcement or bonded prestress elements are available for PMM analysis.",
        ]
    )

    assert list(df.columns) == ["Blocking Item", "Where to Fix", "Recommended Action"]
    assert list(df["Where to Fix"]) == ["Sections", "Sections / Prestress"]
    assert all(df["Recommended Action"].str.len() > 20)


def test_diagnostic_messages_are_cleaned_and_deduplicated() -> None:
    messages = [
        "WARNING: Bonded prestress is included using the current prototype strain compatibility model.",
        "Bonded prestress is included using the current prototype strain compatibility model.",
        "INFO: Generated 960 PMM point(s).",
        "Generated 960 PMM point(s).",
        "",
    ]

    cleaned = analysis_page_module._deduplicate_diagnostic_messages(messages)

    assert cleaned == [
        "Bonded prestress is included using the current prototype strain compatibility model.",
        "Generated 960 PMM point(s).",
    ]


def test_diagnostic_messages_are_classified_for_commercial_display() -> None:
    assert analysis_page_module._classify_diagnostic_message(
        "PMM results are prototype results for engineering review."
    ) == "Solver limitation note"
    assert analysis_page_module._classify_diagnostic_message(
        "PMM numeric warning: NaN values detected in PMM dataframe columns: eps_t."
    ) == "Numerical note"
    assert analysis_page_module._classify_diagnostic_message(
        "PS1: Prestress stress reached fpu cap."
    ) == "Numerical note"
    assert analysis_page_module._classify_diagnostic_message(
        "Directional moment D/C prefers a cleaned PMM slice envelope at Pu, then falls back to interpolated-slice or point-cloud methods when needed."
    ) == "Engineering review warning"


def test_pmm_closeout_solver_mode_label_separates_rc_only_from_prestress() -> None:
    settings = AnalysisSettings(include_prestress=True)

    rc_only_label = _pmm_closeout_solver_mode_label(
        settings,
        prestress_system_enabled=True,
        bonded_prestress_elements=[],
    )
    prestress_label = _pmm_closeout_solver_mode_label(
        settings,
        prestress_system_enabled=True,
        bonded_prestress_elements=[object()],
    )

    assert rc_only_label == "ACI RC Flexural PMM: Finalized Production Preview"
    assert "Prototype" not in rc_only_label
    assert "AASHTO" not in rc_only_label
    assert "code-certified" not in rc_only_label.lower()
    assert prestress_label == "RC + Bonded Prestress PMM - Engineering Review"


def test_pmm_closeout_warning_filter_removes_rc_only_blanket_prototype_warning() -> None:
    warnings = [
        "PMM results are prototype results for engineering review. Final production-grade validation is future work.",
        "Demand/capacity check uses cleaned Pu-slice PMM capacity extraction with ray-intersection; benchmark validation remains in progress.",
    ]

    rc_only = _filter_pmm_closeout_warnings(warnings, result_has_bonded_prestress=False)
    prestressed = _filter_pmm_closeout_warnings(warnings, result_has_bonded_prestress=True)

    assert all("prototype results" not in warning for warning in rc_only)
    assert any("Demand/capacity check uses cleaned Pu-slice" in warning for warning in rc_only)
    assert any("prototype results" in warning for warning in prestressed)


def test_diagnostic_guidance_explains_prestress_fpu_cap_action() -> None:
    guidance = analysis_page_module._diagnostic_guidance("PS1: Prestress stress reached fpu cap.")

    assert guidance["Severity"] == "Numerical note"
    assert guidance["Source"] == "Prestress model"
    assert "Pe_eff/fpe" in guidance["Recommended Action"]
    assert "Prestress tab" in guidance["Where to Check"]
    assert "Potential" in guidance["Governing Impact"] or "Unknown" in guidance["Governing Impact"]


def test_diagnostic_guidance_explains_eps_t_nan_as_numerical_note() -> None:
    guidance = analysis_page_module._diagnostic_guidance(
        "PMM numeric warning: NaN values detected in PMM dataframe columns: eps_t."
    )

    assert guidance["Severity"] == "Numerical note"
    assert "compression-controlled" in guidance["Meaning"]
    assert "No input change" in guidance["Recommended Action"]


def test_diagnostics_dataframe_contains_actionable_columns() -> None:
    df = analysis_page_module._diagnostics_to_dataframe(
        [
            "PS2: Prestress compression reversal is not modeled; tensile strain was clamped to zero.",
            "PMM results are prototype results for engineering review.",
        ]
    )

    expected_columns = {
        "Source",
        "Severity",
        "Message",
        "Meaning",
        "Possible Cause",
        "Recommended Action",
        "Governing Impact",
        "Where to Check",
    }
    assert expected_columns.issubset(set(df.columns))


def test_diagnostic_guidance_reports_no_direct_eps_t_governing_impact() -> None:
    from concrete_pmm_pro.analysis.capacity_check import DemandCapacityResult, DemandCapacitySummary, PASS
    from concrete_pmm_pro.ui.analysis_page import _diagnostics_to_dataframe

    dc_summary = DemandCapacitySummary(
        results=[
            DemandCapacityResult(
                combo_name="ULS-01",
                Pu_N=1_000_000,
                Mux_Nmm=100_000_000,
                Muy_Nmm=0.0,
                Mu_Nmm=100_000_000,
                moment_angle_rad=0.0,
                capacity_Mn_Nmm=None,
                capacity_phiMn_Nmm=250_000_000,
                capacity_phiPn_N=1_000_000,
                dcr=0.4,
                status=PASS,
                message="Checked using PMM slice envelope at Pu.",
                capacity_method="slice_envelope",
            )
        ],
        governing_combo="ULS-01",
        max_dcr=0.4,
        overall_status=PASS,
    )

    guidance = _diagnostics_to_dataframe(
        ["NaN values detected in PMM dataframe columns: eps_t."],
        dc_summary=dc_summary,
    )

    assert guidance.loc[0, "Severity"] == "Numerical note"
    assert "No direct governing impact" in guidance.loc[0, "Governing Impact"]
    assert guidance.loc[0, "Action Priority"] == "Usually no action"


def test_diagnostic_guidance_flags_governing_fallback_as_directly_relevant() -> None:
    from concrete_pmm_pro.analysis.capacity_check import DemandCapacityResult, DemandCapacitySummary, PASS
    from concrete_pmm_pro.ui.analysis_page import _diagnostics_to_dataframe

    dc_summary = DemandCapacitySummary(
        results=[
            DemandCapacityResult(
                combo_name="ULS-02",
                Pu_N=1_500_000,
                Mux_Nmm=120_000_000,
                Muy_Nmm=50_000_000,
                Mu_Nmm=130_000_000,
                moment_angle_rad=0.1,
                capacity_Mn_Nmm=None,
                capacity_phiMn_Nmm=300_000_000,
                capacity_phiPn_N=1_500_000,
                dcr=0.43,
                status=PASS,
                message="Checked using interpolated slice fallback at Pu.",
                capacity_method="interpolated_slice",
                used_fallback=True,
                warning_count=2,
            )
        ],
        governing_combo="ULS-02",
        max_dcr=0.43,
        overall_status=PASS,
    )

    guidance = _diagnostics_to_dataframe(
        ["Directional moment D/C prefers a cleaned PMM slice envelope at Pu, then falls back to interpolated-slice or point-cloud methods when needed."],
        dc_summary=dc_summary,
    )

    assert guidance.loc[0, "Severity"] == "Engineering review warning"
    assert "Directly relevant" in guidance.loc[0, "Governing Impact"]
    assert guidance.loc[0, "Action Priority"] == "Check before relying on governing result"


def test_diagnostic_guidance_distinguishes_background_prestress_surface_warning() -> None:
    from concrete_pmm_pro.analysis.capacity_check import DemandCapacityResult, DemandCapacitySummary, PASS
    from concrete_pmm_pro.ui.analysis_page import _diagnostics_to_dataframe
    import pandas as pd

    df = pd.DataFrame(
        {
            "phiPn_capped_N": [900_000.0, 1_000_000.0, 1_100_000.0],
            "prestress_reached_fpu_cap_count": [0, 0, 0],
            "prestress_stress_warning_count": [0, 0, 0],
        }
    )
    dc_summary = DemandCapacitySummary(
        results=[
            DemandCapacityResult(
                combo_name="ULS-03",
                Pu_N=1_000_000,
                Mux_Nmm=120_000_000,
                Muy_Nmm=0.0,
                Mu_Nmm=120_000_000,
                moment_angle_rad=0.0,
                capacity_Mn_Nmm=None,
                capacity_phiMn_Nmm=300_000_000,
                capacity_phiPn_N=1_000_000,
                dcr=0.4,
                status=PASS,
                message="Checked using PMM slice envelope at Pu.",
                capacity_method="slice_envelope",
            )
        ],
        governing_combo="ULS-03",
        max_dcr=0.4,
        overall_status=PASS,
    )

    guidance = _diagnostics_to_dataframe(["PS1: Prestress stress reached fpu cap."], df=df, dc_summary=dc_summary)

    assert "Background PMM-surface warning" in guidance.loc[0, "Governing Impact"]
    assert guidance.loc[0, "Severity"] == "Numerical note"
    assert guidance.loc[0, "Action Priority"] == "Usually no action"


def test_compression_reversal_is_escalated_only_when_near_governing_region() -> None:
    import pandas as pd
    from concrete_pmm_pro.analysis.capacity_check import DemandCapacityResult, DemandCapacitySummary

    df = pd.DataFrame(
        {
            "phiPn_capped_N": [100_000.0, 1_000_000.0],
            "prestress_compression_reversal_count": [0, 2],
        }
    )
    dc_summary = DemandCapacitySummary(
        results=[
            DemandCapacityResult(
                combo_name="ULS-01",
                Pu_N=100_000.0,
                Mux_Nmm=1.0,
                Muy_Nmm=0.0,
                Mu_Nmm=1.0,
                moment_angle_rad=0.0,
                capacity_Mn_Nmm=12.0,
                capacity_phiMn_Nmm=10.0,
                capacity_phiPn_N=100_000.0,
                dcr=0.1,
                status="PASS",
                message="OK",
                capacity_method="slice_envelope",
            )
        ],
        governing_combo="ULS-01",
        max_dcr=0.1,
        warnings=[],
    )

    assert not analysis_page_module._compression_reversal_near_governing(df, dc_summary)

    near_summary = DemandCapacitySummary(
        results=[
            DemandCapacityResult(
                combo_name="ULS-01",
                Pu_N=1_000_000.0,
                Mux_Nmm=1.0,
                Muy_Nmm=0.0,
                Mu_Nmm=1.0,
                moment_angle_rad=0.0,
                capacity_Mn_Nmm=12.0,
                capacity_phiMn_Nmm=10.0,
                capacity_phiPn_N=1_000_000.0,
                dcr=0.1,
                status="PASS",
                message="OK",
                capacity_method="slice_envelope",
            )
        ],
        governing_combo="ULS-01",
        max_dcr=0.1,
        warnings=[],
    )
    assert analysis_page_module._compression_reversal_near_governing(df, near_summary)


def test_method_validation_status_rows_include_core_commercial_status_items() -> None:
    rows = analysis_page_module._method_validation_status_rows(
        result_has_active_prestress=True,
        result_has_passive_prestress=False,
    )
    areas = {row["Area"] for row in rows}
    case_ids = {row["Case ID"] for row in rows}

    assert "ACI RC Flexural PMM status" in areas
    assert "RC PMM strain compatibility" in areas
    assert "Directional PMM D/C extraction" in areas
    assert "Prestress-aware axial cap" in areas
    assert "Active bonded prestress model" in areas
    assert "SLS / Stress & Cracking" in areas
    assert "PMM.FINAL.RC1.STATUS.READINESS1" in case_ids
    assert "VALID.PMM.DC1" in case_ids
    assert "QA.PO1" in case_ids
    assert "VALID.PS1" in case_ids


def test_aci_rc_pmm_ui_status_uses_guarded_production_preview_wording() -> None:
    status = _aci_rc_pmm_ui_status()

    assert status["label"] == "ACI RC Flexural PMM: Finalized Production Preview"
    assert "ACI 318 RC Column/Pier/Wall/Pylon PMM only" in status["detail"]
    assert "not AASHTO LRFD" in status["detail"]
    assert "not final code-certified" in status["detail"]
    assert "Final code-certified ACI/AASHTO PMM design" not in status["label"]


def test_method_validation_status_rows_surface_pmm_ui_status_scope_guard() -> None:
    rows = _method_validation_status_rows(result_has_active_prestress=False, result_has_passive_prestress=False)
    status_row = next(row for row in rows if row["Case ID"] == "PMM.FINAL.RC1.STATUS.READINESS1")

    assert "Finalized Production Preview" in status_row["Design Use Guidance"]
    assert "AASHTO LRFD PMM" in status_row["Remaining Engineering Limitation"]
    assert "shear" in status_row["Remaining Engineering Limitation"]
    assert "torsion" in status_row["Remaining Engineering Limitation"]
    assert "final code-certified" not in status_row["Design Use Guidance"].lower()


def test_method_validation_status_rows_add_passive_ps_when_present() -> None:
    rows = analysis_page_module._method_validation_status_rows(
        result_has_active_prestress=False,
        result_has_passive_prestress=True,
    )

    assert any(row["Case ID"] == "SOLVER.PS.PASSIVE1" for row in rows)
    assert not any(row["Case ID"] == "VALID.PS1" for row in rows)


def test_method_validation_status_cards_count_status_groups() -> None:
    rows = analysis_page_module._method_validation_status_rows(
        result_has_active_prestress=True,
        result_has_passive_prestress=True,
    )
    cards = analysis_page_module._method_validation_status_cards(rows)
    card_map = {card["title"]: card for card in cards}

    assert int(card_map["Validated / Implemented"]["value"]) >= 4
    assert int(card_map["Planned Checks"]["value"]) >= 1
    assert card_map["Method Basis"]["value"] == "ACI RC PMM"
    assert card_map["Method Basis"]["detail"] == "ACI RC Flexural PMM: Finalized Production Preview"



def test_validation_status_rows_include_design_use_guidance() -> None:
    rows = _method_validation_status_rows(result_has_active_prestress=True, result_has_passive_prestress=False)

    assert rows
    assert all(row.get("Design Use Guidance") for row in rows)
    active_row = next(row for row in rows if row["Area"] == "Active bonded prestress model")
    assert "engineering review" in active_row["Design Use Guidance"]


def test_validation_status_compact_and_detail_tables_use_different_depths() -> None:
    rows = _method_validation_status_rows(result_has_active_prestress=True, result_has_passive_prestress=True)
    compact_df = _validation_status_compact_dataframe(rows)
    detail_df = _validation_status_detail_dataframe(rows)

    assert list(compact_df.columns) == [
        "Area",
        "Validation Status",
        "Design Use Guidance",
        "Case ID",
    ]
    assert "Evidence / Benchmark" not in compact_df.columns
    assert "Evidence / Benchmark" in detail_df.columns
    assert "Remaining Engineering Limitation" in detail_df.columns

def test_diagnostic_summary_distinguishes_background_review_from_governing_warning() -> None:
    message, level = _diagnostic_summary_message(["PMM numeric warning: NaN values detected in PMM dataframe columns: eps_t."])

    assert level == "info"
    assert "No direct governing-result warning detected" in message


def test_diagnostics_compact_table_keeps_core_columns_available() -> None:
    df = _diagnostics_to_dataframe(["Demand/capacity check uses prototype PMM interpolation. Independent engineering verification is required."])

    for column in ["Source", "Severity", "Message", "Governing Impact", "Action Priority", "Where to Check"]:
        assert column in df.columns
    for detail_column in ["Meaning", "Possible Cause", "Recommended Action"]:
        assert detail_column in df.columns


def test_validation_status_planned_card_names_sls_check() -> None:
    rows = _method_validation_status_rows(result_has_active_prestress=True, result_has_passive_prestress=False, include_sls=True)
    cards = _method_validation_status_cards(rows)
    planned_card = next(card for card in cards if card["title"] == "Planned Checks")

    assert planned_card["value"] == "1"
    assert "SLS" in str(planned_card["detail"])
