from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from concrete_pmm_pro.core.models import PrestressElement
from concrete_pmm_pro.geometry.generators import (
    box_section_fillet,
    box_section_fillet_dimensions,
    circular_hollow,
    psc_i_girder,
    rectangular_hollow,
    single_cell_box_girder,
    u_girder,
)
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.geometry.validation import validate_section_geometry


def test_rectangular_hollow_with_different_wall_thicknesses() -> None:
    geometry = rectangular_hollow(
        width_mm=1000,
        height_mm=800,
        t_top_mm=120,
        t_bottom_mm=160,
        t_left_mm=100,
        t_right_mm=140,
    )
    summary = summarize_geometry(geometry)
    expected_inner_area = (1000 - 100 - 140) * (800 - 120 - 160)

    assert validate_section_geometry(geometry).is_valid
    assert summary.area_mm2 == pytest.approx(1000 * 800 - expected_inner_area)


def test_box_section_fillet_with_inner_fillet() -> None:
    geometry = box_section_fillet(
        width_mm=1200,
        height_mm=900,
        t_top_mm=150,
        t_bottom_mm=170,
        t_left_mm=140,
        t_right_mm=160,
        r_inner_mm=80,
        r_outer_mm=0,
        n_fillet=12,
    )

    result = validate_section_geometry(geometry)
    summary = summarize_geometry(geometry)

    assert result.is_valid, result.errors
    assert summary.area_mm2 > 0
    assert len(geometry.holes[0]) > 4


def test_circular_hollow_rejects_invalid_inner_diameter() -> None:
    with pytest.raises(ValueError, match="D_inner"):
        circular_hollow(outer_diameter_mm=800, inner_diameter_mm=800)


def test_rectangular_hollow_rejects_wall_thickness_too_large() -> None:
    with pytest.raises(ValueError, match="t_left \\+ t_right"):
        rectangular_hollow(width_mm=500, height_mm=500, t_top_mm=50, t_bottom_mm=50, t_left_mm=300, t_right_mm=250)


def test_box_section_fillet_rejects_fillet_radius_too_large() -> None:
    with pytest.raises(ValueError, match="inner void"):
        box_section_fillet(
            width_mm=600,
            height_mm=500,
            t_top_mm=100,
            t_bottom_mm=100,
            t_left_mm=100,
            t_right_mm=100,
            r_inner_mm=180,
        )


def test_single_cell_box_girder_rejects_invalid_web_or_slab_thickness() -> None:
    with pytest.raises(ValueError, match="top slab \\+ bottom slab"):
        single_cell_box_girder(
            width_mm=1000,
            depth_mm=500,
            top_slab_thickness_mm=300,
            bottom_slab_thickness_mm=250,
            web_thickness_mm=100,
        )
    with pytest.raises(ValueError, match="web thickness"):
        single_cell_box_girder(
            width_mm=400,
            depth_mm=600,
            top_slab_thickness_mm=100,
            bottom_slab_thickness_mm=100,
            web_thickness_mm=220,
        )


def test_psc_i_girder_rejects_invalid_dimensions() -> None:
    with pytest.raises(ValueError, match="flange thickness"):
        psc_i_girder(
            depth_mm=500,
            top_flange_width_mm=600,
            top_flange_thickness_mm=300,
            web_width_mm=200,
            bottom_flange_width_mm=500,
            bottom_flange_thickness_mm=250,
        )
    with pytest.raises(ValueError, match="web thickness"):
        psc_i_girder(
            depth_mm=1000,
            top_flange_width_mm=200,
            top_flange_thickness_mm=100,
            web_width_mm=250,
            bottom_flange_width_mm=500,
            bottom_flange_thickness_mm=100,
        )


def test_u_girder_rejects_invalid_dimensions() -> None:
    with pytest.raises(ValueError, match="bottom slab thickness"):
        u_girder(depth_mm=600, top_width_mm=1200, bottom_width_mm=800, wall_thickness_mm=120, bottom_slab_thickness_mm=600)
    with pytest.raises(ValueError, match="top width"):
        u_girder(depth_mm=600, top_width_mm=800, bottom_width_mm=900, wall_thickness_mm=120, bottom_slab_thickness_mm=120)


def test_prestress_database_includes_ps_bar_64_1080_1230() -> None:
    database_path = Path(__file__).resolve().parents[1] / "data" / "prestress_steel_database.csv"
    rows = list(csv.DictReader(database_path.open("r", encoding="utf-8")))
    row = next((item for item in rows if item["name"] == "PS Bar 64 - 1080/1230"), None)

    assert row is not None
    assert {"source", "area_source", "is_catalog_verified"}.issubset(rows[0])
    assert row["type"] == "prestressing_bar"
    assert float(row["diameter_mm"]) == 64.0
    assert float(row["fpy_MPa"]) == 1080.0
    assert float(row["fpu_MPa"]) == 1230.0
    assert row["source"] == "generated"
    assert row["area_source"] == "pi*d^2/4"
    assert row["is_catalog_verified"] == "false"
    assert float(row["area_mm2"]) == pytest.approx(math.pi * 64.0**2 / 4.0, rel=1e-4)


def test_prestress_element_can_represent_bonded_prestressing_bar() -> None:
    element = PrestressElement(
        x_mm=0,
        y_mm=-250,
        area_mm2=3217.0,
        diameter_mm=64.0,
        material_name="PS Bar 64 - 1080/1230",
        steel_type="prestressing_bar",
        fpy_mpa=1080.0,
        fpu_mpa=1230.0,
        ep_mpa=200000.0,
        pe_eff_n=1_500_000.0,
        bonded=True,
    )

    assert element.steel_type == "prestressing_bar"
    assert element.fpy_mpa == 1080.0
    assert element.fpu_mpa == 1230.0
    assert element.ep_mpa == 200000.0
    assert element.pe_eff_n == 1_500_000.0
    assert element.bonded is True


def test_prestress_element_rejects_fpy_not_less_than_fpu() -> None:
    with pytest.raises(ValueError, match="fpy_mpa"):
        PrestressElement(
            x_mm=0,
            y_mm=0,
            area_mm2=100,
            steel_type="prestressing_bar",
            fpy_mpa=1230,
            fpu_mpa=1230,
        )


def test_dimension_labels_include_parameter_symbols() -> None:
    dimensions = box_section_fillet_dimensions(
        width_mm=1200,
        height_mm=900,
        t_top_mm=150,
        t_bottom_mm=200,
        t_left_mm=180,
        t_right_mm=180,
        r_inner_mm=100,
        r_outer_mm=0,
        n_fillet=12,
    )
    labels = [dimension.display_label("symbol_value") for dimension in dimensions]

    assert "B = 1200 mm" in labels
    assert "H = 900 mm" in labels
    assert "t_top = 150 mm" in labels
    assert "t_bottom = 200 mm" in labels
    assert "t_left = 180 mm" in labels
    assert "Ri = 100 mm" in labels
    assert "Ro = 0 mm" in labels


def test_section_builder_source_remains_metadata_driven() -> None:
    source_path = Path(__file__).resolve().parents[1] / "concrete_pmm_pro" / "ui" / "section_builder.py"
    source = source_path.read_text(encoding="utf-8")

    assert "load_section_presets" in source
    assert 'parameter["name"]' in source
    assert "width_mm" not in source
    assert "height_mm" not in source
