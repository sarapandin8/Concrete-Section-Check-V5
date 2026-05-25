from __future__ import annotations

from pathlib import Path

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
from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, PrestressElement, Rebar, RebarMaterial
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.serviceability import ServiceabilitySettings
import concrete_pmm_pro.ui.analysis_page as analysis_page_module
from concrete_pmm_pro.ui.analysis_page import (
    PMM_3D_LAYER_DEFAULTS,
    PMM_3D_MASTER_TOGGLE_KEY,
    _pmm_3d_display_enabled_from_state,
    _should_generate_pmm_3d_figure_from_state,
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
