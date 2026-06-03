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
_DEBONDED_STRAND_NOS_COLUMN = "Debonded strand nos"
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


DEBONDING_RULE_AUDIT_COLUMNS = [
    "Rule",
    "Status",
    "Demand / value",
    "Limit / expectation",
    "Engineering note",
]

CRITICAL_TRANSFER_STATION_COLUMNS = [
    "x_m",
    "Station type",
    "Source",
    "Review note",
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
class GirderDebondingZone:
    """Longitudinal bonded/debonded zone for one strand group.

    The zone is visualization/metadata only.  A debonded sleeve zone means the
    group is intentionally treated as not effective in the PS5 active-prestress
    station preview.  Transfer-length force build-up after the sleeve
    termination is a later milestone and is not represented here.
    """

    group_id: str
    zone_type: str
    x_start_m: float
    x_end_m: float
    is_effective: bool

    @property
    def length_m(self) -> float:
        return max(0.0, self.x_end_m - self.x_start_m)

    def as_dict(self) -> dict[str, Any]:
        return {
            "Group ID": self.group_id,
            "Zone": self.zone_type,
            "x_start_m": self.x_start_m,
            "x_end_m": self.x_end_m,
            "Length_m": self.length_m,
            "Effective in PS5 preview": self.is_effective,
        }


@dataclass(frozen=True)
class GirderDebondingRuleCheck:
    """One row-based debonding rule check for PS5C preview QA.

    This is not an individual-strand code certification check.  It intentionally
    audits only information currently available in the row-based strand layout:
    debond lengths, left/right symmetry, sleeve termination stations, and
    critical station candidates.
    """

    rule: str
    status: str
    demand: str
    limit: str
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "Rule": self.rule,
            "Status": self.status,
            "Demand / value": self.demand,
            "Limit / expectation": self.limit,
            "Engineering note": self.note,
        }


@dataclass(frozen=True)
class GirderCriticalTransferStation:
    """Critical station candidate for future transfer stress review."""

    x_m: float
    station_type: str
    source: str
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "x_m": round(self.x_m, 6),
            "Station type": self.station_type,
            "Source": self.source,
            "Review note": self.note,
        }


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



def explicit_debonded_strand_numbers(row: Mapping[str, Any]) -> tuple[int, ...]:
    """Parse explicitly selected debonded strand numbers within one row.

    The supported PS6A syntax is a comma/space separated list such as
    ``1, 2, 18, 19``.  Ranges such as ``1-4`` are also accepted as a UI
    convenience.  Numbers are 1-based within the row, matching the plotted
    strand labels.  Invalid/out-of-range tokens are ignored here and surfaced
    by the UI/QA layer; this helper is intentionally safe for solver-adjacent
    station calculations.
    """

    count = int(max(0, round(_to_float(row.get(_COUNT_COLUMN)) or 0.0)))
    raw = row.get(_DEBONDED_STRAND_NOS_COLUMN)
    if raw is None or str(raw).strip() == "":
        return ()
    text = str(raw).strip().replace(";", ",").replace(" ", ",")
    selected: set[int] = set()
    for token in [part.strip() for part in text.split(",") if part.strip()]:
        if "-" in token:
            parts = [part.strip() for part in token.split("-", 1)]
            try:
                start, end = int(parts[0]), int(parts[1])
            except (TypeError, ValueError):
                continue
            lo, hi = sorted((start, end))
            for value in range(lo, hi + 1):
                if 1 <= value <= count:
                    selected.add(value)
            continue
        try:
            value = int(token)
        except (TypeError, ValueError):
            continue
        if 1 <= value <= count:
            selected.add(value)
    return tuple(sorted(selected))


def debonded_strand_numbers_for_row(row: Mapping[str, Any]) -> tuple[int, ...]:
    """Return strand numbers treated as debonded in the PS6A preview.

    Backward compatibility is deliberate: existing PS5 row-based projects with
    left/right debond lengths but no explicit strand numbers still mean the
    full row is debonded over the sleeved zone.  Once the user enters explicit
    strand numbers, only those strands are ignored inside the sleeve.
    """

    count = int(max(0, round(_to_float(row.get(_COUNT_COLUMN)) or 0.0)))
    explicit = explicit_debonded_strand_numbers(row)
    if explicit:
        return explicit
    left = _to_float(row.get(_LEFT_DEBOND_COLUMN)) or 0.0
    right = _to_float(row.get(_RIGHT_DEBOND_COLUMN)) or 0.0
    if (left > 1e-9 or right > 1e-9) and count > 0:
        return tuple(range(1, count + 1))
    return ()


def effective_strand_count_in_row_at_station(row: Mapping[str, Any], x_m: float, span_length_m: float) -> int:
    """Return the effective strand count for one row at station x.

    Outside sleeve zones all strands in the row are effective.  Inside a
    sleeved zone, explicitly selected debonded strand numbers are ignored.  If
    no explicit strand numbers are provided, PS5 row-based semantics are
    preserved and the full row is ignored inside the sleeve.
    """

    span = _clamp_span_length(span_length_m)
    x = _to_float(x_m)
    if x is None:
        return 0
    count = int(max(0, round(_to_float(row.get(_COUNT_COLUMN)) or 0.0)))
    if count <= 0:
        return 0
    left = min(max(float(_to_float(row.get(_LEFT_DEBOND_COLUMN)) or 0.0), 0.0), span)
    right = min(max(float(_to_float(row.get(_RIGHT_DEBOND_COLUMN)) or 0.0), 0.0), span)
    x_value = float(x)
    inside_left_sleeve = left > 1e-9 and x_value < left - 1e-9
    inside_right_sleeve = right > 1e-9 and x_value > span - right + 1e-9
    if not inside_left_sleeve and not inside_right_sleeve:
        return count
    debonded_count = len(debonded_strand_numbers_for_row(row))
    return max(0, count - debonded_count)


def debonded_strand_count_for_row(row: Mapping[str, Any]) -> int:
    """Return number of row strands selected/treated as debonded."""

    return len(debonded_strand_numbers_for_row(row))

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
    return effective_strand_count_in_row_at_station(row, float(x), span) > 0


def girder_debonding_zones_for_row(row: Mapping[str, Any], span_length_m: float) -> tuple[GirderDebondingZone, ...]:
    """Return debonded sleeve and bonded/effective zones for one row.

    GIRDER.PS5B uses these zones for commercial-style longitudinal graphics.
    This helper deliberately mirrors the PS5A step-function active strand model:
    no prestress force is counted within a debonded sleeve zone, and full row
    force is counted in the bonded/effective zone.  Transfer-length ramping and
    development checks remain outside this milestone.
    """

    span = _clamp_span_length(span_length_m)
    group_id = str(row.get(_GROUP_ID_COLUMN) or "strand group")
    left = min(max(float(_to_float(row.get(_LEFT_DEBOND_COLUMN)) or 0.0), 0.0), span)
    right = min(max(float(_to_float(row.get(_RIGHT_DEBOND_COLUMN)) or 0.0), 0.0), span)
    bonded_start = left
    bonded_end = span - right

    zones: list[GirderDebondingZone] = []
    if left > 1e-9:
        zones.append(
            GirderDebondingZone(
                group_id=group_id,
                zone_type="Left debonded sleeve",
                x_start_m=0.0,
                x_end_m=round(left, 6),
                is_effective=False,
            )
        )
    if bonded_end >= bonded_start and bonded_end - bonded_start > 1e-9:
        zones.append(
            GirderDebondingZone(
                group_id=group_id,
                zone_type="Bonded / effective",
                x_start_m=round(bonded_start, 6),
                x_end_m=round(bonded_end, 6),
                is_effective=True,
            )
        )
    if right > 1e-9:
        zones.append(
            GirderDebondingZone(
                group_id=group_id,
                zone_type="Right debonded sleeve",
                x_start_m=round(span - right, 6),
                x_end_m=round(span, 6),
                is_effective=False,
            )
        )
    return tuple(zones)


def girder_debonding_layout_zones(
    table: pd.DataFrame | Iterable[Mapping[str, Any]] | None,
    *,
    span_length_m: float,
) -> tuple[GirderDebondingZone, ...]:
    """Return longitudinal bonded/debonded zones for all active strand rows."""

    zones: list[GirderDebondingZone] = []
    for row in active_girder_strand_rows(table):
        zones.extend(girder_debonding_zones_for_row(row, span_length_m))
    return tuple(zones)


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



def _active_row_count_and_debonded_count(table: pd.DataFrame | Iterable[Mapping[str, Any]] | None) -> tuple[int, int]:
    active_rows = active_girder_strand_rows(table)
    debonded_rows = 0
    for row in active_rows:
        left = _to_float(row.get(_LEFT_DEBOND_COLUMN)) or 0.0
        right = _to_float(row.get(_RIGHT_DEBOND_COLUMN)) or 0.0
        if left > 1e-9 or right > 1e-9:
            debonded_rows += 1
    return len(active_rows), debonded_rows


def girder_critical_transfer_stations(
    table: pd.DataFrame | Iterable[Mapping[str, Any]] | None,
    *,
    span_length_m: float,
) -> tuple[GirderCriticalTransferStation, ...]:
    """Return row-based critical station candidates for transfer-stage review.

    The list includes end faces and every sleeve termination location.  It is
    intended for PS5C QA/navigation only; transfer length ramping and actual
    stress checks remain future milestones.
    """

    span = _clamp_span_length(span_length_m)
    stations: dict[float, GirderCriticalTransferStation] = {
        0.0: GirderCriticalTransferStation(
            x_m=0.0,
            station_type="End face",
            source="Left support",
            note="Transfer stress review station; debonded rows are not effective in the PS5 preview.",
        ),
        span: GirderCriticalTransferStation(
            x_m=span,
            station_type="End face",
            source="Right support",
            note="Transfer stress review station; debonded rows are not effective in the PS5 preview.",
        ),
    }
    for row in active_girder_strand_rows(table):
        group_id = str(row.get(_GROUP_ID_COLUMN) or "strand group")
        left = min(max(float(_to_float(row.get(_LEFT_DEBOND_COLUMN)) or 0.0), 0.0), span)
        right = min(max(float(_to_float(row.get(_RIGHT_DEBOND_COLUMN)) or 0.0), 0.0), span)
        if left > 1e-9:
            x = round(left, 6)
            source = f"{group_id} left sleeve"
            if x in stations:
                source = f"{stations[x].source}; {source}"
            stations[x] = GirderCriticalTransferStation(
                x_m=x,
                station_type="Sleeve transition",
                source=source,
                note="Beginning of bonded zone in the PS5 step-function model; transfer-length force build-up is not modeled.",
            )
        if right > 1e-9:
            x = round(span - right, 6)
            source = f"{group_id} right sleeve"
            if x in stations:
                source = f"{stations[x].source}; {source}"
            stations[x] = GirderCriticalTransferStation(
                x_m=x,
                station_type="Sleeve transition",
                source=source,
                note="End of bonded zone in the PS5 step-function model; transfer-length force reduction/ramp is not modeled.",
            )
    return tuple(stations[x] for x in sorted(stations))


def girder_debonding_rule_checks(
    table: pd.DataFrame | Iterable[Mapping[str, Any]] | None,
    *,
    span_length_m: float,
) -> tuple[GirderDebondingRuleCheck, ...]:
    """Return row-based debonding QA checks for the PS5C dashboard.

    These checks intentionally avoid claiming final AASHTO/ACI compliance
    because the current layout does not yet identify individual strand IDs
    within a row.  Percent debonded strand limits become a future milestone
    once individual strand selection is available.
    """

    span = _clamp_span_length(span_length_m)
    checks: list[GirderDebondingRuleCheck] = []
    active_rows = active_girder_strand_rows(table)
    active_count, debonded_count = _active_row_count_and_debonded_count(table)
    explicit_rows = sum(1 for row in active_rows if explicit_debonded_strand_numbers(row))
    checks.append(
        GirderDebondingRuleCheck(
            rule="PS6A scope",
            status="PREVIEW",
            demand=f"{explicit_rows} explicit row(s); {debonded_count} debonded row(s) / {active_count} active row(s)",
            limit="Individual strand selection preview",
            note="PS6A can track selected strand numbers within a row, but this is still not a final AASHTO/ACI code-certified debonding design.",
        )
    )
    if not active_rows:
        checks.append(
            GirderDebondingRuleCheck(
                rule="Active rows",
                status="REVIEW",
                demand="0 active rows",
                limit="At least one active strand row",
                note="No active strand layout is available for debonding QA.",
            )
        )
        return tuple(checks)

    limit_l5 = span / 5.0
    max_left = 0.0
    max_right = 0.0
    max_sum = 0.0
    asymmetric_groups: list[str] = []
    no_bonded_zone_groups: list[str] = []
    terminations: dict[float, list[str]] = {}
    for row in active_rows:
        group_id = str(row.get(_GROUP_ID_COLUMN) or "strand group")
        left = min(max(float(_to_float(row.get(_LEFT_DEBOND_COLUMN)) or 0.0), 0.0), span)
        right = min(max(float(_to_float(row.get(_RIGHT_DEBOND_COLUMN)) or 0.0), 0.0), span)
        max_left = max(max_left, left)
        max_right = max(max_right, right)
        max_sum = max(max_sum, left + right)
        if left > 1e-9 or right > 1e-9:
            if abs(left - right) > 1e-6:
                asymmetric_groups.append(group_id)
            if left > 1e-9:
                terminations.setdefault(round(left, 6), []).append(f"{group_id} left")
            if right > 1e-9:
                terminations.setdefault(round(span - right, 6), []).append(f"{group_id} right")
        if left + right >= span - 1e-9:
            no_bonded_zone_groups.append(group_id)

    max_debond = max(max_left, max_right)
    checks.append(
        GirderDebondingRuleCheck(
            rule="Debond length",
            status="OK" if max_debond <= limit_l5 + 1e-9 else "ERROR",
            demand=f"max L/R = {max_debond:.3f} m",
            limit=f"L/5 = {limit_l5:.3f} m",
            note="Preview check against a common maximum debonded length rule; verify against the governing project code edition.",
        )
    )
    checks.append(
        GirderDebondingRuleCheck(
            rule="Bonded zone remains",
            status="OK" if not no_bonded_zone_groups else "ERROR",
            demand=f"max left+right = {max_sum:.3f} m",
            limit=f"< span = {span:.3f} m",
            note="Rows must retain a bonded/effective zone in the PS5 step-function preview. Review: "
            + (", ".join(no_bonded_zone_groups) if no_bonded_zone_groups else "all active rows retain bonded zone."),
        )
    )
    checks.append(
        GirderDebondingRuleCheck(
            rule="Left/right symmetry",
            status="OK" if not asymmetric_groups else "REVIEW",
            demand="symmetric" if not asymmetric_groups else ", ".join(asymmetric_groups),
            limit="left length = right length per row for symmetric simple-span defaults",
            note="Independent left/right debonding is allowed in the UI, but asymmetric layouts require engineering justification.",
        )
    )
    repeated = {station: labels for station, labels in terminations.items() if len(labels) > 1}
    checks.append(
        GirderDebondingRuleCheck(
            rule="Sleeve termination staggering",
            status="OK" if not repeated else "REVIEW",
            demand="unique termination stations" if not repeated else "; ".join(f"x={x:.3f} m: {len(labels)} row-end(s)" for x, labels in sorted(repeated.items())),
            limit="avoid terminating many sleeves at the same station",
            note="This is a row-based warning only; future individual-strand modeling is required for code-style per-section termination limits.",
        )
    )
    total_strands = sum(int(max(0, round(_to_float(row.get(_COUNT_COLUMN)) or 0.0))) for row in active_rows)
    debonded_strands = sum(debonded_strand_count_for_row(row) for row in active_rows)
    total_ratio = debonded_strands / total_strands if total_strands > 0 else 0.0
    checks.append(
        GirderDebondingRuleCheck(
            rule="Total debonded strand ratio",
            status="OK" if total_ratio <= 0.25 + 1e-9 else "REVIEW",
            demand=f"{debonded_strands} / {total_strands} = {total_ratio:.1%}",
            limit="≤ 25% preview limit",
            note="Computed from explicit selected strand numbers; blank selection with debond length preserves row-based all-strands behavior.",
        )
    )
    over_row_limits: list[str] = []
    row_ratio_demands: list[str] = []
    for row in active_rows:
        group_id = str(row.get(_GROUP_ID_COLUMN) or "strand group")
        row_total = int(max(0, round(_to_float(row.get(_COUNT_COLUMN)) or 0.0)))
        row_debonded = debonded_strand_count_for_row(row)
        ratio = row_debonded / row_total if row_total > 0 else 0.0
        if row_debonded > 0:
            row_ratio_demands.append(f"{group_id}: {row_debonded}/{row_total}={ratio:.1%}")
        if ratio > 0.40 + 1e-9:
            over_row_limits.append(group_id)
    checks.append(
        GirderDebondingRuleCheck(
            rule="Per-row debonded strand ratio",
            status="OK" if not over_row_limits else "REVIEW",
            demand="; ".join(row_ratio_demands) if row_ratio_demands else "0 selected debonded strands",
            limit="≤ 40% per row preview limit",
            note="Review rows over the preview limit: " + (", ".join(over_row_limits) if over_row_limits else "none."),
        )
    )
    critical = girder_critical_transfer_stations(table, span_length_m=span)
    checks.append(
        GirderDebondingRuleCheck(
            rule="Critical transfer stations",
            status="OK",
            demand=", ".join(f"{station.x_m:.3f}" for station in critical),
            limit="end faces + sleeve transitions",
            note="These stations should be carried forward to transfer stress review; transfer-length ramp is not modeled in PS5C.",
        )
    )
    return tuple(checks)


def girder_debonding_rule_audit_dataframe(
    table: pd.DataFrame | Iterable[Mapping[str, Any]] | None,
    *,
    span_length_m: float,
) -> pd.DataFrame:
    checks = girder_debonding_rule_checks(table, span_length_m=span_length_m)
    return pd.DataFrame([check.as_dict() for check in checks], columns=DEBONDING_RULE_AUDIT_COLUMNS)


def girder_critical_transfer_station_dataframe(
    table: pd.DataFrame | Iterable[Mapping[str, Any]] | None,
    *,
    span_length_m: float,
) -> pd.DataFrame:
    stations = girder_critical_transfer_stations(table, span_length_m=span_length_m)
    return pd.DataFrame([station.as_dict() for station in stations], columns=CRITICAL_TRANSFER_STATION_COLUMNS)


def girder_debonding_preview_status(
    table: pd.DataFrame | Iterable[Mapping[str, Any]] | None,
    *,
    span_length_m: float,
) -> str:
    statuses = {check.status for check in girder_debonding_rule_checks(table, span_length_m=span_length_m)}
    if "ERROR" in statuses:
        return "ERROR"
    if "REVIEW" in statuses:
        return "REVIEW"
    return "OK"


def _active_group_from_row(row: Mapping[str, Any], *, effective_no_strands: int | None = None) -> ActiveStrandGroup:
    count = _to_float(row.get(_COUNT_COLUMN)) or 0.0
    row_no_strands = max(0, int(round(count)))
    no_strands = row_no_strands if effective_no_strands is None else max(0, int(effective_no_strands))
    area_per = _to_float(row.get(_AREA_PER_STRAND_COLUMN)) or 0.0
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
        effective_count = effective_strand_count_in_row_at_station(row, x_m, span)
        if effective_count > 0:
            group = _active_group_from_row(row, effective_no_strands=effective_count)
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
