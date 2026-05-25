from __future__ import annotations

from concrete_pmm_pro.geometry import default_registry
from concrete_pmm_pro.geometry.presets import load_section_presets
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.geometry.validation import validate_section_geometry


def test_all_presets_generate_valid_geometry_and_dimensions() -> None:
    for preset in load_section_presets():
        params = {parameter["name"]: parameter["default"] for parameter in preset["parameters"]}
        geometry = default_registry.geometry(preset["generator"])(**params, name=preset["display_name"])
        dimensions = default_registry.dimensions(preset["dimensions_generator"])(**params)
        validation = validate_section_geometry(geometry)
        summary = summarize_geometry(geometry)

        assert validation.is_valid, f"{preset['key']}: {validation.errors}"
        assert summary.area_mm2 > 0
        assert dimensions, f"{preset['key']} should provide at least one DimensionItem"
