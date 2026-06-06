"""Beam/Girder SLS auto-load component helpers.

GIRDER.SLS5A keeps load-component calculation separate from the SLS stress
solver.  The helpers here convert simple-span girder/system metadata into
preview line loads and station moments only; they do not change PMM, code-limit,
prestress-loss, or stress-formula logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


DEFAULT_SPAN_LENGTH_M = 20.0
DEFAULT_GIRDER_SPACING_M = 1.0
DEFAULT_NUMBER_OF_GIRDERS = 6
DEFAULT_CONCRETE_UNIT_WEIGHT_KN_M3 = 24.0
DEFAULT_BARRIER_SIDEWALK_TOTAL_AREA_BOTH_SIDES_M2 = 1.50
DEFAULT_WEARING_THICKNESS_MM = 80.0
DEFAULT_OTHER_SDL_AREA_LOAD_KPA = 0.0
DEFAULT_BUILDING_SERVICE_SDL_KN_M2 = 0.0
DEFAULT_BUILDING_SERVICE_LL_KN_M2 = 0.0
DEFAULT_BUILDING_ADDITIONAL_SDL_KN_M2 = 0.0

BEAM_GIRDER_SYSTEM_SETTINGS_KEY = "beam_girder_system_settings"
BEAM_GIRDER_SLS_AUTO_LOAD_SETTINGS_KEY = "beam_girder_sls_auto_load_settings"
BUILDING_BEAM_GIRDER_SERVICE_LOAD_SETTINGS_KEY = "building_beam_girder_service_load_settings"


@dataclass(frozen=True)
class BeamGirderSystemSettings:
    """Single-source Beam/Girder system settings used by load previews."""

    span_length_m: float = DEFAULT_SPAN_LENGTH_M
    girder_spacing_m: float = DEFAULT_GIRDER_SPACING_M
    number_of_girders: int = DEFAULT_NUMBER_OF_GIRDERS
    concrete_unit_weight_kN_m3: float = DEFAULT_CONCRETE_UNIT_WEIGHT_KN_M3
    tributary_width_m: float | None = None
    use_girder_spacing_as_tributary_width: bool = False

    @property
    def effective_tributary_width_m(self) -> float:
        if self.use_girder_spacing_as_tributary_width:
            return self.girder_spacing_m
        if _positive_float(self.tributary_width_m) is not None:
            return float(self.tributary_width_m)
        return self.girder_spacing_m

    def as_metadata(self) -> dict[str, Any]:
        return {
            "span_length_m": self.span_length_m,
            "girder_spacing_m": self.girder_spacing_m,
            "number_of_girders": self.number_of_girders,
            "concrete_unit_weight_kN_m3": self.concrete_unit_weight_kN_m3,
            "tributary_width_m": self.tributary_width_m,
            "use_girder_spacing_as_tributary_width": self.use_girder_spacing_as_tributary_width,
        }


@dataclass(frozen=True)
class BeamGirderSLSAutoLoadSettings:
    """Engineer-editable SLS load-component settings for precast girders."""

    include_transfer_girder_self_weight: bool = True
    include_construction_girder_self_weight: bool = True
    include_construction_wet_topping: bool = True
    include_service_barrier_sidewalk: bool = True
    barrier_sidewalk_total_area_both_sides_m2: float = DEFAULT_BARRIER_SIDEWALK_TOTAL_AREA_BOTH_SIDES_M2
    barrier_sidewalk_unit_weight_kN_m3: float = DEFAULT_CONCRETE_UNIT_WEIGHT_KN_M3
    include_service_wearing_surface: bool = True
    wearing_thickness_mm: float = DEFAULT_WEARING_THICKNESS_MM
    wearing_unit_weight_kN_m3: float = DEFAULT_CONCRETE_UNIT_WEIGHT_KN_M3
    include_service_other_sdl: bool = False
    other_sdl_mode: str = "Area load kN/m²"
    other_sdl_area_load_kN_m2: float = DEFAULT_OTHER_SDL_AREA_LOAD_KPA
    other_sdl_line_load_kN_m_per_girder: float = 0.0

    @property
    def barrier_sidewalk_area_per_side_m2(self) -> float:
        return max(float(self.barrier_sidewalk_total_area_both_sides_m2), 0.0) / 2.0

    def as_metadata(self) -> dict[str, Any]:
        return {
            "include_transfer_girder_self_weight": self.include_transfer_girder_self_weight,
            "include_construction_girder_self_weight": self.include_construction_girder_self_weight,
            "include_construction_wet_topping": self.include_construction_wet_topping,
            "include_service_barrier_sidewalk": self.include_service_barrier_sidewalk,
            "barrier_sidewalk_total_area_both_sides_m2": self.barrier_sidewalk_total_area_both_sides_m2,
            "barrier_sidewalk_unit_weight_kN_m3": self.barrier_sidewalk_unit_weight_kN_m3,
            "include_service_wearing_surface": self.include_service_wearing_surface,
            "wearing_thickness_mm": self.wearing_thickness_mm,
            "wearing_unit_weight_kN_m3": self.wearing_unit_weight_kN_m3,
            "include_service_other_sdl": self.include_service_other_sdl,
            "other_sdl_mode": self.other_sdl_mode,
            "other_sdl_area_load_kN_m2": self.other_sdl_area_load_kN_m2,
            "other_sdl_line_load_kN_m_per_girder": self.other_sdl_line_load_kN_m_per_girder,
        }


@dataclass(frozen=True)
class BuildingBeamGirderServiceLoadSettings:
    """Building Beam/Girder ACI service load inputs.

    These are building-style area/line loads used to generate simple-span
    service bending actions. Bridge-only components such as barrier, sidewalk,
    wearing surface, and CSiBridge LL+IM are intentionally excluded.
    """

    include_service_sdl: bool = True
    service_sdl_kN_m2: float = DEFAULT_BUILDING_SERVICE_SDL_KN_M2
    include_service_ll: bool = True
    service_ll_kN_m2: float = DEFAULT_BUILDING_SERVICE_LL_KN_M2
    include_additional_sdl: bool = False
    additional_sdl_mode: str = "Area load kN/m²"
    additional_sdl_kN_m2: float = DEFAULT_BUILDING_ADDITIONAL_SDL_KN_M2
    additional_sdl_line_load_kN_m: float = 0.0

    def as_metadata(self) -> dict[str, Any]:
        return {
            "include_service_sdl": self.include_service_sdl,
            "service_sdl_kN_m2": self.service_sdl_kN_m2,
            "include_service_ll": self.include_service_ll,
            "service_ll_kN_m2": self.service_ll_kN_m2,
            "include_additional_sdl": self.include_additional_sdl,
            "additional_sdl_mode": self.additional_sdl_mode,
            "additional_sdl_kN_m2": self.additional_sdl_kN_m2,
            "additional_sdl_line_load_kN_m": self.additional_sdl_line_load_kN_m,
        }


@dataclass(frozen=True)
class SLSAutoLoadBreakdown:
    """Line-load summary for one SLS stage."""

    stage_label: str
    component_loads_kN_m: tuple[tuple[str, float], ...]

    @property
    def total_kN_m(self) -> float:
        return sum(value for _label, value in self.component_loads_kN_m)

    @property
    def component_label(self) -> str:
        if not self.component_loads_kN_m:
            return "No auto load components"
        return " + ".join(f"{label} {value:.3f} kN/m" for label, value in self.component_loads_kN_m)

    def as_rows(self) -> list[dict[str, Any]]:
        rows = [
            {"Stage": self.stage_label, "Component": label, "w_kN/m per girder": value}
            for label, value in self.component_loads_kN_m
        ]
        rows.append({"Stage": self.stage_label, "Component": "Total auto load", "w_kN/m per girder": self.total_kN_m})
        return rows


def _positive_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric > 0.0:
        return numeric
    return None


def _nonnegative_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(numeric, 0.0)


def _positive_int(value: Any, default: int) -> int:
    try:
        numeric = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return numeric if numeric > 0 else default


def system_settings_from_mapping(mapping: Mapping[str, Any] | None) -> BeamGirderSystemSettings:
    data = dict(mapping or {})
    return BeamGirderSystemSettings(
        span_length_m=_positive_float(data.get("span_length_m")) or DEFAULT_SPAN_LENGTH_M,
        girder_spacing_m=_positive_float(data.get("girder_spacing_m")) or DEFAULT_GIRDER_SPACING_M,
        number_of_girders=_positive_int(data.get("number_of_girders"), DEFAULT_NUMBER_OF_GIRDERS),
        concrete_unit_weight_kN_m3=_positive_float(data.get("concrete_unit_weight_kN_m3")) or DEFAULT_CONCRETE_UNIT_WEIGHT_KN_M3,
        tributary_width_m=_positive_float(data.get("tributary_width_m")),
        use_girder_spacing_as_tributary_width=bool(data.get("use_girder_spacing_as_tributary_width", False)),
    )


def auto_load_settings_from_mapping(mapping: Mapping[str, Any] | None) -> BeamGirderSLSAutoLoadSettings:
    data = dict(mapping or {})
    default = BeamGirderSLSAutoLoadSettings()
    return BeamGirderSLSAutoLoadSettings(
        include_transfer_girder_self_weight=bool(data.get("include_transfer_girder_self_weight", default.include_transfer_girder_self_weight)),
        include_construction_girder_self_weight=bool(data.get("include_construction_girder_self_weight", default.include_construction_girder_self_weight)),
        include_construction_wet_topping=bool(data.get("include_construction_wet_topping", default.include_construction_wet_topping)),
        include_service_barrier_sidewalk=bool(data.get("include_service_barrier_sidewalk", default.include_service_barrier_sidewalk)),
        barrier_sidewalk_total_area_both_sides_m2=_positive_float(data.get("barrier_sidewalk_total_area_both_sides_m2")) or DEFAULT_BARRIER_SIDEWALK_TOTAL_AREA_BOTH_SIDES_M2,
        barrier_sidewalk_unit_weight_kN_m3=_positive_float(data.get("barrier_sidewalk_unit_weight_kN_m3")) or DEFAULT_CONCRETE_UNIT_WEIGHT_KN_M3,
        include_service_wearing_surface=bool(data.get("include_service_wearing_surface", default.include_service_wearing_surface)),
        wearing_thickness_mm=_positive_float(data.get("wearing_thickness_mm")) or DEFAULT_WEARING_THICKNESS_MM,
        wearing_unit_weight_kN_m3=_positive_float(data.get("wearing_unit_weight_kN_m3")) or DEFAULT_CONCRETE_UNIT_WEIGHT_KN_M3,
        include_service_other_sdl=bool(data.get("include_service_other_sdl", default.include_service_other_sdl)),
        other_sdl_mode=str(data.get("other_sdl_mode") or default.other_sdl_mode),
        other_sdl_area_load_kN_m2=_nonnegative_float(data.get("other_sdl_area_load_kN_m2"), default.other_sdl_area_load_kN_m2),
        other_sdl_line_load_kN_m_per_girder=_nonnegative_float(
            data.get("other_sdl_line_load_kN_m_per_girder"),
            default.other_sdl_line_load_kN_m_per_girder,
        ),
    )


def building_service_load_settings_from_mapping(mapping: Mapping[str, Any] | None) -> BuildingBeamGirderServiceLoadSettings:
    data = dict(mapping or {})
    default = BuildingBeamGirderServiceLoadSettings()
    return BuildingBeamGirderServiceLoadSettings(
        include_service_sdl=bool(data.get("include_service_sdl", default.include_service_sdl)),
        service_sdl_kN_m2=_nonnegative_float(data.get("service_sdl_kN_m2"), default.service_sdl_kN_m2),
        include_service_ll=bool(data.get("include_service_ll", default.include_service_ll)),
        service_ll_kN_m2=_nonnegative_float(data.get("service_ll_kN_m2"), default.service_ll_kN_m2),
        include_additional_sdl=bool(data.get("include_additional_sdl", default.include_additional_sdl)),
        additional_sdl_mode=str(data.get("additional_sdl_mode") or default.additional_sdl_mode),
        additional_sdl_kN_m2=_nonnegative_float(data.get("additional_sdl_kN_m2"), default.additional_sdl_kN_m2),
        additional_sdl_line_load_kN_m=_nonnegative_float(
            data.get("additional_sdl_line_load_kN_m"),
            default.additional_sdl_line_load_kN_m,
        ),
    )


def girder_self_weight_kN_m(precast_area_mm2: float, concrete_unit_weight_kN_m3: float) -> float:
    """Return precast girder self-weight as kN/m from gross area in mm²."""

    return max(float(precast_area_mm2), 0.0) / 1_000_000.0 * max(float(concrete_unit_weight_kN_m3), 0.0)


def wet_topping_load_kN_m(t_slab_mm: float, tributary_width_m: float, unit_weight_kN_m3: float) -> float:
    return max(float(t_slab_mm), 0.0) / 1000.0 * max(float(tributary_width_m), 0.0) * max(float(unit_weight_kN_m3), 0.0)


def barrier_sidewalk_load_per_girder_kN_m(
    system: BeamGirderSystemSettings,
    settings: BeamGirderSLSAutoLoadSettings,
) -> float:
    total = max(settings.barrier_sidewalk_total_area_both_sides_m2, 0.0) * max(settings.barrier_sidewalk_unit_weight_kN_m3, 0.0)
    return total / max(int(system.number_of_girders), 1)


def wearing_surface_load_per_girder_kN_m(
    system: BeamGirderSystemSettings,
    settings: BeamGirderSLSAutoLoadSettings,
) -> float:
    return wet_topping_load_kN_m(
        settings.wearing_thickness_mm,
        system.effective_tributary_width_m,
        settings.wearing_unit_weight_kN_m3,
    )


def other_sdl_load_per_girder_kN_m(
    system: BeamGirderSystemSettings,
    settings: BeamGirderSLSAutoLoadSettings,
) -> float:
    mode = str(settings.other_sdl_mode or "").casefold()
    if "direct" in mode or "kN/m".casefold() in mode and "m²" not in mode:
        return max(settings.other_sdl_line_load_kN_m_per_girder, 0.0)
    return max(settings.other_sdl_area_load_kN_m2, 0.0) * system.effective_tributary_width_m


def building_service_load_components_kN_m(
    system: BeamGirderSystemSettings,
    settings: BuildingBeamGirderServiceLoadSettings,
) -> tuple[tuple[str, float], ...]:
    """Return Building service UDL components as kN/m along the member."""

    components: list[tuple[str, float]] = []
    tributary = system.effective_tributary_width_m
    if settings.include_service_sdl:
        value = max(settings.service_sdl_kN_m2, 0.0) * tributary
        if value > 0.0:
            components.append(("Building SDL", value))
    if settings.include_additional_sdl:
        mode = str(settings.additional_sdl_mode or "").casefold()
        if "direct" in mode or ("kn/m" in mode and "m²" not in mode):
            value = max(settings.additional_sdl_line_load_kN_m, 0.0)
        else:
            value = max(settings.additional_sdl_kN_m2, 0.0) * tributary
        if value > 0.0:
            components.append(("Additional SDL", value))
    if settings.include_service_ll:
        value = max(settings.service_ll_kN_m2, 0.0) * tributary
        if value > 0.0:
            components.append(("Building LL", value))
    return tuple(components)


def building_service_total_load_kN_m(
    system: BeamGirderSystemSettings,
    settings: BuildingBeamGirderServiceLoadSettings,
) -> float:
    return sum(value for _label, value in building_service_load_components_kN_m(system, settings))


def building_service_moment_rows(
    system: BeamGirderSystemSettings,
    settings: BuildingBeamGirderServiceLoadSettings,
    stations_m: Iterable[float] | None = None,
) -> list[dict[str, Any]]:
    """Return preview station rows for Building service UDL moments."""

    stations = list(stations_m or default_sls_station_grid(system.span_length_m, divisions=20))
    total_w = building_service_total_load_kN_m(system, settings)
    return [
        {
            "Station x (m)": x,
            "w service (kN/m)": total_w,
            "Mx service (kN-m)": simple_span_udl_moment_kNm(total_w, x, system.span_length_m),
            "Vy service (kN)": simple_span_udl_shear_kN(total_w, x, system.span_length_m),
        }
        for x in stations
    ]


def simple_span_udl_moment_kNm(w_kN_m: float, x_m: float, span_length_m: float) -> float:
    """Return simple-span UDL moment at station x in kN-m."""

    span = _positive_float(span_length_m) or DEFAULT_SPAN_LENGTH_M
    x = min(max(float(x_m), 0.0), span)
    return max(float(w_kN_m), 0.0) * x * (span - x) / 2.0


def simple_span_udl_shear_kN(w_kN_m: float, x_m: float, span_length_m: float) -> float:
    """Return simple-span UDL shear at station x in kN."""

    span = _positive_float(span_length_m) or DEFAULT_SPAN_LENGTH_M
    x = min(max(float(x_m), 0.0), span)
    return max(float(w_kN_m), 0.0) * (span / 2.0 - x)


def default_sls_station_grid(span_length_m: float, extra_stations_m: Iterable[float] | None = None, divisions: int = 20) -> list[float]:
    """Return a compact station grid for auto-generated stress diagrams."""

    span = _positive_float(span_length_m) or DEFAULT_SPAN_LENGTH_M
    n = max(2, int(divisions))
    stations = {round(span * i / n, 6) for i in range(n + 1)}
    for value in extra_stations_m or []:
        try:
            x = float(value)
        except (TypeError, ValueError):
            continue
        if 0.0 <= x <= span:
            stations.add(round(x, 6))
    return sorted(stations)



def building_auto_load_breakdown_for_stage(
    *,
    stage_label: str,
    system: BeamGirderSystemSettings,
    service_settings: BuildingBeamGirderServiceLoadSettings,
    precast_area_mm2: float,
    topping_thickness_mm: float,
) -> SLSAutoLoadBreakdown:
    """Return Building Beam/Girder ACI stage auto-load components.

    BUILDING.SLS1B intentionally keeps Building SLS load generation separate
    from Bridge-only SDL components. Transfer and Construction use auto
    precast/topping self-weight where possible; Service uses building SDL/LL
    inputs from the Building Loads workflow. This helper only returns simple
    line-load components for preview moment generation; it does not change any
    stress formula, prestress force state, PMM, or code-limit logic.
    """

    stage = str(stage_label or "").casefold()
    components: list[tuple[str, float]] = []
    self_weight = girder_self_weight_kN_m(precast_area_mm2, system.concrete_unit_weight_kN_m3)
    if "transfer" in stage:
        if self_weight > 0.0:
            components.append(("Precast girder self-weight", self_weight))
    elif "construction" in stage:
        if self_weight > 0.0:
            components.append(("Precast girder self-weight", self_weight))
        wet = wet_topping_load_kN_m(topping_thickness_mm, system.effective_tributary_width_m, system.concrete_unit_weight_kN_m3)
        if wet > 0.0:
            components.append(("Wet topping/slab", wet))
    elif "service" in stage:
        components.extend(building_service_load_components_kN_m(system, service_settings))
    return SLSAutoLoadBreakdown(stage_label=stage_label, component_loads_kN_m=tuple(components))

def auto_load_breakdown_for_stage(
    *,
    stage_label: str,
    system: BeamGirderSystemSettings,
    settings: BeamGirderSLSAutoLoadSettings,
    precast_area_mm2: float,
    topping_thickness_mm: float,
) -> SLSAutoLoadBreakdown:
    """Return auto line-load components for one SLS stage."""

    stage = str(stage_label or "").casefold()
    components: list[tuple[str, float]] = []
    self_weight = girder_self_weight_kN_m(precast_area_mm2, system.concrete_unit_weight_kN_m3)
    if "transfer" in stage:
        if settings.include_transfer_girder_self_weight and self_weight > 0.0:
            components.append(("Girder self-weight", self_weight))
    elif "construction" in stage:
        if settings.include_construction_girder_self_weight and self_weight > 0.0:
            components.append(("Girder self-weight", self_weight))
        if settings.include_construction_wet_topping:
            wet = wet_topping_load_kN_m(topping_thickness_mm, system.effective_tributary_width_m, system.concrete_unit_weight_kN_m3)
            if wet > 0.0:
                components.append(("Wet deck/topping", wet))
    elif "service" in stage:
        if settings.include_service_barrier_sidewalk:
            barrier = barrier_sidewalk_load_per_girder_kN_m(system, settings)
            if barrier > 0.0:
                components.append(("Barrier/Parapet/Sidewalk", barrier))
        if settings.include_service_wearing_surface:
            wearing = wearing_surface_load_per_girder_kN_m(system, settings)
            if wearing > 0.0:
                components.append(("Wearing surface", wearing))
        if settings.include_service_other_sdl:
            other = other_sdl_load_per_girder_kN_m(system, settings)
            if other > 0.0:
                components.append(("Other SDL", other))
    return SLSAutoLoadBreakdown(stage_label=stage_label, component_loads_kN_m=tuple(components))
