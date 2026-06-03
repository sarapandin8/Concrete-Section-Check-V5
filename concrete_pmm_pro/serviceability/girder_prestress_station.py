"""Station-based active prestress helpers for simple-supported precast girders.

GIRDER.PS5A intentionally evaluates only the *active strand-group metadata*
from the girder strand layout/debonding table.  It does not calculate
prestress losses, transfer-length force build-up, SLS stress, PMM capacity, or
code-certified debonding design recommendations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import pandas as pd

_ACTIVE_COLUMN = "Active"
_GROUP_ID_COLUMN = "Group ID"
_COUNT_COLUMN = "No. Strands"
_AREA_PER_STRAND_COLUMN = "Area/Strand_mm2"
_TOTAL_APS_COLUMN = "Total Aps_mm2"
_Y_FROM_BOTTOM_COLUMN = "y_mm_from_bottom"
_LEFT_DEBOND_COLUMN = "Left debond m"
_RIGHT_DEBOND_COLUMN = "Right debond m"
_PE_TRANSFER_PER_STRAND_COLUMN = "Pe_transfer/strand_kN"
_PE_CONSTRUCTION_PER_STRAND_COLUMN = "Pe_construction/strand_kN"
_PE_FINAL_PER_STRAND_COLUMN = "Pe_eff_final/strand_kN"

STATION_PREVIEW_COLUMNS = [
    "x_m",
    "Effective strand groups",
    "Effective strands",
    "Aps_eff_mm2",
    "Pe_transfer_eff_kN",
    "Pe_construction_eff_kN",
    "Pe_eff_final_eff_kN",
    "yps_eff_mm_from_bottom",
    "Active group IDs",
]


@dataclass(frozen=True)
class ActiveStrandGroup:
    """One strand group that is effective at a station in the PS5A model."""

    group_id: str
    no_strands: int
    area_per_strand_mm2: float
    total_aps_mm2: float
    y_mm_from_bottom: float
    pe_transfer_per_strand_kN: float
    pe_construction_per_strand_kN: float
    pe_eff_final_per_strand_kN: float
    left_debond_m: float
    right_debond_m: float

    @property
    def pe_transfer_total_kN(self) -> float:
        return self.no_strands * self.pe_transfer_per_strand_kN

    @property
    def pe_construction_total_kN(self) -> float:
        return self.no_strands * self.pe_construction_per_strand_kN

    @property
    def pe_eff_final_total_kN(self) -> float:
        return self.no_strands * self.pe_eff_final_per_strand_kN


@dataclass(frozen=True)
class GirderPrestressStationResult:
    """Effective prestress metadata at one girder station."""

    x_m: float
    active_groups: tuple[ActiveStrandGroup, ...]

    @property
    def effective_group_count(self) -> int:
        return len(self.active_groups)

    @property
    def effective_strands(self) -> int:
        return sum(group.no_strands for group in self.active_groups)

    @property
    def aps_eff_mm2(self) -> float:
        return sum(group.total_aps_mm2 for group in self.active_groups)

    @property
    def pe_transfer_eff_kN(self) -> float:
        return sum(group.pe_transfer_total_kN for group in self.active_groups)

    @property
    def pe_construction_eff_kN(self) -> float:
        return sum(group.pe_construction_total_kN for group in self.active_groups)

    @property
    def pe_eff_final_eff_kN(self) -> float:
        return sum(group.pe_eff_final_total_kN for group in self.active_groups)

    @property
    def yps_eff_mm_from_bottom(self) -> float | None:
        aps = self.aps_eff_mm2
        if aps <= 0.0:
            return None
        return sum(group.total_aps_mm2 * group.y_mm_from_bottom for group in self.active_groups) / aps

    @property
    def active_group_ids(self) -> str:
        return ", ".join(group.group_id for group in self.active_groups)

    def as_dict(self) -> dict[str, Any]:
        return {
            "x_m": self.x_m,
            "Effective strand groups": self.effective_group_count,
            "Effective strands": self.effective_strands,
            "Aps_eff_mm2": self.aps_eff_mm2,
            "Pe_transfer_eff_kN": self.pe_transfer_eff_kN,
            "Pe_construction_eff_kN": self.pe_construction_eff_kN,
            "Pe_eff_final_eff_kN": self.pe_eff_final_eff_kN,
            "yps_eff_mm_from_bottom": self.yps_eff_mm_from_bottom,
            "Active group IDs": self.active_group_ids,
        }


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(numeric):
        return None
    return numeric


def _to_bool_default_true(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"false", "0", "no", "n", "inactive", "off"}:
        return False
    if text in {"true", "1", "yes", "y", "active", "on"}:
        return True
    return True


def _clamp_span_length(span_length_m: float) -> float:
    span = _to_float(span_length_m)
    if span is None or span <= 0.0:
        raise ValueError("span_length_m must be a positive number.")
    return float(span)


def _row_mappings(table: pd.DataFrame | Iterable[Mapping[str, Any]] | None) -> list[Mapping[str, Any]]:
    if table is None:
        return []
    df = pd.DataFrame(table)
    if df.empty:
        return []
    return [row.to_dict() for _, row in df.iterrows()]


def active_girder_strand_rows(table: pd.DataFrame | Iterable[Mapping[str, Any]] | None) -> list[Mapping[str, Any]]:
    """Return active layout rows, preserving the original row dictionaries."""

    active: list[Mapping[str, Any]] = []
    for row in _row_mappings(table):
        if _to_bool_default_true(row.get(_ACTIVE_COLUMN)):
            active.append(row)
    return active


def strand_group_effective_at_station(row: Mapping[str, Any], x_m: float, span_length_m: float) -> bool:
    """Return whether a group contributes at station x in the PS5A model.

    A group is treated as effective from the left sleeve termination to the
    right sleeve termination.  Force build-up over transfer length is
    deliberately not modeled in GIRDER.PS5A.
    """

    span = _clamp_span_length(span_length_m)
    x = _to_float(x_m)
    if x is None:
        return False
    left = _to_float(row.get(_LEFT_DEBOND_COLUMN)) or 0.0
    right = _to_float(row.get(_RIGHT_DEBOND_COLUMN)) or 0.0
    left = min(max(float(left), 0.0), span)
    right = min(max(float(right), 0.0), span)
    bonded_start = left
    bonded_end = span - right
    return bonded_start - 1e-9 <= float(x) <= bonded_end + 1e-9


def station_candidates_from_debonding(table: pd.DataFrame | Iterable[Mapping[str, Any]] | None, span_length_m: float) -> list[float]:
    """Return compact station candidates for preview and QA tables."""

    span = _clamp_span_length(span_length_m)
    stations = {0.0, span, span / 2.0}
    for row in active_girder_strand_rows(table):
        left = _to_float(row.get(_LEFT_DEBOND_COLUMN)) or 0.0
        right = _to_float(row.get(_RIGHT_DEBOND_COLUMN)) or 0.0
        for station in (left, span - right):
            if 0.0 <= station <= span:
                stations.add(round(float(station), 6))
    return sorted(stations)


def _active_group_from_row(row: Mapping[str, Any]) -> ActiveStrandGroup:
    count = _to_float(row.get(_COUNT_COLUMN)) or 0.0
    no_strands = max(0, int(round(count)))
    area_per = _to_float(row.get(_AREA_PER_STRAND_COLUMN)) or 0.0
    total_aps = _to_float(row.get(_TOTAL_APS_COLUMN))
    if total_aps is None:
        total_aps = no_strands * area_per
    return ActiveStrandGroup(
        group_id=str(row.get(_GROUP_ID_COLUMN) or "strand group"),
        no_strands=no_strands,
        area_per_strand_mm2=float(area_per),
        total_aps_mm2=max(0.0, float(total_aps)),
        y_mm_from_bottom=float(_to_float(row.get(_Y_FROM_BOTTOM_COLUMN)) or 0.0),
        pe_transfer_per_strand_kN=max(0.0, float(_to_float(row.get(_PE_TRANSFER_PER_STRAND_COLUMN)) or 0.0)),
        pe_construction_per_strand_kN=max(0.0, float(_to_float(row.get(_PE_CONSTRUCTION_PER_STRAND_COLUMN)) or 0.0)),
        pe_eff_final_per_strand_kN=max(0.0, float(_to_float(row.get(_PE_FINAL_PER_STRAND_COLUMN)) or 0.0)),
        left_debond_m=max(0.0, float(_to_float(row.get(_LEFT_DEBOND_COLUMN)) or 0.0)),
        right_debond_m=max(0.0, float(_to_float(row.get(_RIGHT_DEBOND_COLUMN)) or 0.0)),
    )


def active_strand_groups_at_station(
    table: pd.DataFrame | Iterable[Mapping[str, Any]] | None,
    *,
    x_m: float,
    span_length_m: float,
) -> tuple[ActiveStrandGroup, ...]:
    """Return active strand groups at station x."""

    span = _clamp_span_length(span_length_m)
    groups: list[ActiveStrandGroup] = []
    for row in active_girder_strand_rows(table):
        if strand_group_effective_at_station(row, x_m, span):
            group = _active_group_from_row(row)
            if group.no_strands > 0 and group.total_aps_mm2 > 0.0:
                groups.append(group)
    return tuple(groups)


def evaluate_girder_prestress_station(
    table: pd.DataFrame | Iterable[Mapping[str, Any]] | None,
    *,
    x_m: float,
    span_length_m: float,
) -> GirderPrestressStationResult:
    """Evaluate effective strand count, Aps, yps, and Pe states at station x."""

    span = _clamp_span_length(span_length_m)
    x_value = _to_float(x_m)
    if x_value is None:
        raise ValueError("x_m must be a number.")
    x_clamped = min(max(float(x_value), 0.0), span)
    return GirderPrestressStationResult(
        x_m=round(x_clamped, 6),
        active_groups=active_strand_groups_at_station(table, x_m=x_clamped, span_length_m=span),
    )


def girder_prestress_station_results(
    table: pd.DataFrame | Iterable[Mapping[str, Any]] | None,
    *,
    span_length_m: float,
    stations_m: Iterable[float] | None = None,
) -> list[GirderPrestressStationResult]:
    """Evaluate station-based active prestress metadata along the girder."""

    span = _clamp_span_length(span_length_m)
    stations = list(stations_m) if stations_m is not None else station_candidates_from_debonding(table, span)
    unique_stations = sorted({round(min(max(float(x), 0.0), span), 6) for x in stations})
    return [evaluate_girder_prestress_station(table, x_m=x, span_length_m=span) for x in unique_stations]


def girder_prestress_station_dataframe(
    table: pd.DataFrame | Iterable[Mapping[str, Any]] | None,
    *,
    span_length_m: float,
    stations_m: Iterable[float] | None = None,
) -> pd.DataFrame:
    """Return a UI/report-friendly station preview dataframe.

    The values are metadata for staged prestress preview and future SLS graphs;
    they are not a prestress-loss calculation and do not update analysis
    stresses by themselves.
    """

    results = girder_prestress_station_results(table, span_length_m=span_length_m, stations_m=stations_m)
    return pd.DataFrame([result.as_dict() for result in results], columns=STATION_PREVIEW_COLUMNS)
