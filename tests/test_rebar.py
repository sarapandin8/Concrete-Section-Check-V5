from __future__ import annotations

import pandas as pd
import pytest

from concrete_pmm_pro.core.models import Rebar
from concrete_pmm_pro.geometry.generators import rectangle, rectangular_hollow
from concrete_pmm_pro.ui.rebar_page import (
    load_rebar_database,
    rebars_from_dataframe,
    rebars_valid_for_analysis,
    validate_rebars_against_geometry,
)


def test_rebar_database_loads() -> None:
    rebar_db = load_rebar_database()

    assert {"name", "type", "diameter_mm", "area_mm2", "fy_MPa", "Es_MPa"}.issubset(rebar_db.columns)
    assert "DB25" in set(rebar_db["name"])


def test_rebar_area_property_for_db25() -> None:
    rebar = Rebar(x_mm=0, y_mm=0, diameter_mm=25)

    assert rebar.area_mm2 == pytest.approx(490.9, rel=1e-3)


def test_rebars_from_dataframe_creates_rebar_objects() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 10, "y_mm": 20, "Bar Size": "DB25", "Diameter_mm": None, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert not result.errors
    assert len(result.rebars) == 1
    assert result.rebars[0].label == "B1"
    assert result.rebars[0].diameter_mm == 25


def test_selected_database_bar_size_overrides_manual_diameter() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 0, "y_mm": 0, "Bar Size": "DB25", "Diameter_mm": 99, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert not result.errors
    assert result.rebars[0].diameter_mm == 25


def test_custom_bar_size_with_diameter_creates_rebar() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "C1", "x_mm": 0, "y_mm": 0, "Bar Size": "Custom", "Diameter_mm": 23, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert not result.errors
    assert result.rebars[0].diameter_mm == 23
    assert any("Custom" in warning for warning in result.warnings)


def test_custom_bar_size_without_diameter_gives_error() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "C1", "x_mm": 0, "y_mm": 0, "Bar Size": "Custom", "Diameter_mm": None, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert any("Custom" in error and "Diameter_mm" in error for error in result.errors)


def test_unknown_bar_size_with_diameter_creates_custom_rebar_with_warning() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "U1", "x_mm": 0, "y_mm": 0, "Bar Size": "UNKNOWN", "Diameter_mm": 21, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert not result.errors
    assert result.rebars[0].diameter_mm == 21
    assert any("not in the database" in warning for warning in result.warnings)


def test_unknown_bar_size_without_diameter_gives_error() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "U1", "x_mm": 0, "y_mm": 0, "Bar Size": "UNKNOWN", "Diameter_mm": None, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert any("not in the database" in error for error in result.errors)


def test_inactive_rows_are_ignored() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": False, "Label": "B1", "x_mm": "bad", "y_mm": "bad", "Bar Size": "DB25", "Diameter_mm": -1, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert not result.errors
    assert result.rebars == []


def test_invalid_diameter_is_rejected() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 0, "y_mm": 0, "Bar Size": "", "Diameter_mm": -20, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert any("Diameter_mm" in error for error in result.errors)
    assert result.rebars == []


def test_nonnumeric_coordinates_give_errors() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": "x", "y_mm": "y", "Bar Size": "DB20", "Diameter_mm": None, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert any("x_mm" in error for error in result.errors)
    assert any("y_mm" in error for error in result.errors)


def test_total_as_calculation_with_count() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "B", "x_mm": 0, "y_mm": 0, "Bar Size": "DB25", "Diameter_mm": None, "Material": "SD40", "Count": 3, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)
    total_as = sum(rebar.area_mm2 for rebar in result.rebars)

    assert len(result.rebars) == 3
    assert total_as == pytest.approx(3 * 490.9, rel=1e-3)
    assert [rebar.label for rebar in result.rebars] == ["B-1", "B-2", "B-3"]


def test_rebar_outside_section_is_detected() -> None:
    geometry = rectangle(width_mm=400, height_mm=400)
    rebars = [Rebar(x_mm=300, y_mm=0, diameter_mm=20, label="OUT")]

    errors = validate_rebars_against_geometry(rebars, geometry)

    assert any("outside concrete" in error for error in errors)
    assert rebars_valid_for_analysis(RebarParseResultForTest(rebars), errors) is False


def test_rebar_inside_hole_is_detected() -> None:
    geometry = rectangular_hollow(width_mm=1000, height_mm=800, t_top_mm=100, t_bottom_mm=100, t_left_mm=100, t_right_mm=100)
    rebars = [Rebar(x_mm=0, y_mm=0, diameter_mm=20, label="VOID")]

    errors = validate_rebars_against_geometry(rebars, geometry)

    assert any("inside a void" in error for error in errors)
    assert rebars_valid_for_analysis(RebarParseResultForTest(rebars), errors) is False


def RebarParseResultForTest(rebars: list[Rebar]):
    from concrete_pmm_pro.ui.rebar_page import RebarParseResult

    return RebarParseResult(rebars=rebars, errors=[], warnings=[], info=[])
