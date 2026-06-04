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


GIRDER_STAGE_PE_MAPPING_COLUMNS = [
    "Stage",
    "Pe source",
    "Source column",
    "Active groups",
    "Ready groups",
    "Pe total kN",
    "Status",
    "Engineering note",
]

GIRDER_STAGE_PE_SPECS = [
    (
        "Transfer",
        "Pe_transfer / strand",
        _PE_TRANSFER_PER_STRAND_COLUMN,
        "Use for transfer/release SLS checks with the precast section basis.",
    ),
    (
        "Construction",
        "Pe_construction / strand",
        _PE_CONSTRUCTION_PER_STRAND_COLUMN,
        "Use for construction-stage SLS checks before final service losses.",
    ),
    (
        "Final service",
        "Pe_final / strand",
        _PE_FINAL_PER_STRAND_COLUMN,
        "Use for final service SLS checks after long-term losses.",
    ),
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

ADVISORY_DEBONDING_RECOMMENDATION_COLUMNS = [
    "Group ID",
    "Row order",
    "No. strands",
    "Recommended debonded strand nos",
    "Recommended count",
    "Left debond m",
    "Right debond m",
    "Guardrail status",
    "Engineering reason",
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
class GirderDebondingAdvisoryRecommendation:
    """One code-aware advisory debonding recommendation row.

    PS6B is intentionally advisory.  It uses common debonding guardrails
    (total 25%, per-row 40%, symmetric strand-pair selection, and L/5 length
    cap) to propose candidate debonded strand numbers.  It does not perform
    final transfer stress, development, shear, end-zone, or loss checks.
    """

    group_id: str
    row_order: int
    no_strands: int
    recommended_numbers: tuple[int, ...]
    left_debond_m: float
    right_debond_m: float
    guardrail_status: str
    engineering_reason: str

    @property
    def recommended_numbers_label(self) -> str:
        return ",".join(str(value) for value in self.recommended_numbers) if self.recommended_numbers else "—"

    def as_dict(self) -> dict[str, Any]:
        return {
            "Group ID": self.group_id,
            "Row order": self.row_order,
            "No. strands": self.no_strands,
            "Recommended debonded strand nos": self.recommended_numbers_label,
            "Recommended count": len(self.recommended_numbers),
            "Left debond m": self.left_debond_m,
            "Right debond m": self.right_debond_m,
            "Guardrail status": self.guardrail_status,
            "Engineering reason": self.engineering_reason,
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



def _active_layout_rows(table: pd.DataFrame | None) -> pd.DataFrame:
    if table is None:
        return pd.DataFrame()
    df = pd.DataFrame(table).copy()
    if df.empty:
        return df
    # Strand layout tables use ``No. Strands`` while the LOSS1A force-state
    # editor intentionally displays the compact label ``No. strands``.  Stage
    # Pe mapping is a data-flow audit and must accept both shapes; otherwise
    # valid force-state rows are incorrectly reported as MISSING.
    if _COUNT_COLUMN not in df.columns and "No. strands" in df.columns:
        df[_COUNT_COLUMN] = df["No. strands"]
    if _ACTIVE_COLUMN in df.columns:
        active = df[_ACTIVE_COLUMN].fillna(True).astype(bool)
        df = df.loc[active].copy()
    return df.reset_index(drop=True)


def girder_stage_pe_mapping_dataframe(table: pd.DataFrame | None) -> pd.DataFrame:
    """Return stage-to-Pe source readiness for girder SLS data flow.

    LOSS1B audits only whether the active strand layout has positive Pe values
    available for each SLS stage. It does not perform stress analysis or
    code-certified prestress-loss calculations.
    """

    active = _active_layout_rows(table)
    active_count = len(active.index)
    rows: list[dict[str, Any]] = []
    for stage, source_label, column, base_note in GIRDER_STAGE_PE_SPECS:
        if active.empty:
            rows.append(
                {
                    "Stage": stage,
                    "Pe source": source_label,
                    "Source column": column,
                    "Active groups": 0,
                    "Ready groups": 0,
                    "Pe total kN": 0.0,
                    "Status": "MISSING",
                    "Engineering note": "No active girder strand groups are available for SLS stage Pe mapping.",
                }
            )
            continue
        counts = pd.to_numeric(active.get(_COUNT_COLUMN, pd.Series([0] * active_count)), errors="coerce").fillna(0.0)
        pe_values = pd.to_numeric(active.get(column, pd.Series([0.0] * active_count)), errors="coerce").fillna(0.0)
        ready_mask = pe_values.gt(0.0) & counts.gt(0.0)
        ready_count = int(ready_mask.sum())
        pe_total = float((counts * pe_values).sum())
        if ready_count == active_count and active_count > 0:
            status = "READY"
            note = base_note
        elif ready_count > 0:
            status = "REVIEW"
            missing_groups = active.loc[~ready_mask, _GROUP_ID_COLUMN].astype(str).tolist() if _GROUP_ID_COLUMN in active.columns else []
            suffix = f" Missing/zero Pe for: {', '.join(missing_groups)}." if missing_groups else " Some groups have missing/zero Pe."
            note = base_note + suffix
        else:
            status = "MISSING"
            note = base_note + " No positive Pe is defined for this stage."
        rows.append(
            {
                "Stage": stage,
                "Pe source": source_label,
                "Source column": column,
                "Active groups": active_count,
                "Ready groups": ready_count,
                "Pe total kN": pe_total,
                "Status": status,
                "Engineering note": note,
            }
        )
    return pd.DataFrame(rows, columns=GIRDER_STAGE_PE_MAPPING_COLUMNS)


def girder_stage_pe_mapping_status(table: pd.DataFrame | None) -> tuple[str, list[str]]:
    """Return overall stage Pe mapping readiness and review messages."""

    mapping = girder_stage_pe_mapping_dataframe(table)
    if mapping.empty:
        return "MISSING", ["No stage Pe mapping rows are available."]
    statuses = [str(value) for value in mapping.get("Status", pd.Series(dtype=str)).tolist()]
    messages = [
        f"{row['Stage']}: {row['Engineering note']}"
        for _, row in mapping.iterrows()
        if str(row.get("Status")) != "READY"
    ]
    if all(status == "READY" for status in statuses):
        return "READY", []
    if any(status == "REVIEW" for status in statuses):
        return "REVIEW", messages
    return "MISSING", messages

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


def _symmetric_outer_pair_numbers(no_strands: int, requested_count: int) -> tuple[int, ...]:
    """Return practical symmetric spaced-pair strand numbers.

    BP1/PS6B uses the user's preferred practical pattern: symmetric pairs are
    selected from the outside while skipping one strand between selected pairs
    where possible.  For example, 18 strands and four requested debonded
    strands returns 1, 3, 16, 18 rather than adjacent 1, 2, 17, 18.
    """

    count = max(0, int(no_strands))
    requested = max(0, int(requested_count))
    if count < 2 or requested < 2:
        return ()
    even_requested = requested if requested % 2 == 0 else requested - 1
    max_even = (count // 2) * 2
    selected_count = min(even_requested, max_even)
    pair_count = selected_count // 2
    selected: list[int] = []
    for pair_index in range(pair_count):
        offset = pair_index * 2
        left = 1 + offset
        right = count - offset
        if left >= right:
            break
        selected.extend([left, right])
    if len(selected) < selected_count:
        # Fallback for small rows where spaced pairs run out of room.
        for offset in range(count // 2):
            candidate = [1 + offset, count - offset]
            for value in candidate:
                if value not in selected:
                    selected.append(value)
                if len(selected) >= selected_count:
                    break
            if len(selected) >= selected_count:
                break
    return tuple(sorted(set(selected)))


def girder_advisory_debonding_recommendations(
    table: pd.DataFrame | Iterable[Mapping[str, Any]] | None,
    *,
    span_length_m: float,
    max_pairs_per_row: int = 1,
    base_debond_length_m: float = 1.0,
    length_step_m: float = 0.5,
) -> tuple[GirderDebondingAdvisoryRecommendation, ...]:
    """Return a conservative code-aware advisory debonding layout.

    The recommendation is intentionally a starter layout, not final design. It
    selects symmetric spaced strand pairs from lower rows first because those
    strands usually have the largest eccentricity in straight pretensioned
    girders.  Selection is limited by common code guardrails: total debonded
    strands <= 25%, per-row debonded strands <= 40%, symmetric pair selection,
    and debond length <= L/5.
    """

    span = _clamp_span_length(span_length_m)
    active_rows = list(active_girder_strand_rows(table))
    total_strands = sum(max(0, int(round(_to_float(row.get(_COUNT_COLUMN)) or 0.0))) for row in active_rows)
    total_limit = int(total_strands * 0.25)
    total_limit -= total_limit % 2  # preserve symmetric pair selection globally
    remaining = max(0, total_limit)
    length_limit = span / 5.0
    sorted_rows = sorted(
        enumerate(active_rows, start=1),
        key=lambda item: (float(_to_float(item[1].get(_Y_FROM_BOTTOM_COLUMN)) or 0.0), item[0]),
    )
    recommendations: list[GirderDebondingAdvisoryRecommendation] = []
    proposed_row_index = 0
    for row_order, row in sorted_rows:
        group_id = str(row.get(_GROUP_ID_COLUMN) or f"Row {row_order}")
        row_total = max(0, int(round(_to_float(row.get(_COUNT_COLUMN)) or 0.0)))
        per_row_limit = int(row_total * 0.40)
        per_row_limit -= per_row_limit % 2
        requested = max(0, int(max_pairs_per_row)) * 2
        select_count = min(requested, per_row_limit, remaining)
        numbers = _symmetric_outer_pair_numbers(row_total, select_count)
        if numbers:
            length = min(length_limit, base_debond_length_m + proposed_row_index * length_step_m)
            length = max(0.0, round(length, 3))
            remaining -= len(numbers)
            proposed_row_index += 1
            recommendations.append(
                GirderDebondingAdvisoryRecommendation(
                    group_id=group_id,
                    row_order=row_order,
                    no_strands=row_total,
                    recommended_numbers=numbers,
                    left_debond_m=length,
                    right_debond_m=length,
                    guardrail_status="ADVISORY OK",
                    engineering_reason=(
                        "Symmetric spaced pair selected from lower rows first. Guardrails applied: "
                        "total <=25%, row <=40%, symmetric pair, debond length <=L/5. "
                        "Final transfer stress, development, shear, and end-zone checks are still required."
                    ),
                )
            )
        else:
            if row_total < 2:
                reason = "Skipped: fewer than two strands; symmetric pair selection is not possible."
            elif per_row_limit < 2:
                reason = "Skipped: 40% per-row preview limit permits no symmetric pair in this row."
            elif remaining < 2:
                reason = "Skipped: 25% total preview limit is already used by lower candidate rows."
            else:
                reason = "Skipped: no code-aware symmetric pair selected by the conservative starter rule."
            recommendations.append(
                GirderDebondingAdvisoryRecommendation(
                    group_id=group_id,
                    row_order=row_order,
                    no_strands=row_total,
                    recommended_numbers=(),
                    left_debond_m=0.0,
                    right_debond_m=0.0,
                    guardrail_status="NO ACTION",
                    engineering_reason=reason,
                )
            )
    return tuple(recommendations)


def girder_advisory_debonding_recommendation_dataframe(
    table: pd.DataFrame | Iterable[Mapping[str, Any]] | None,
    *,
    span_length_m: float,
    max_pairs_per_row: int = 1,
) -> pd.DataFrame:
    recommendations = girder_advisory_debonding_recommendations(
        table,
        span_length_m=span_length_m,
        max_pairs_per_row=max_pairs_per_row,
    )
    return pd.DataFrame([item.as_dict() for item in recommendations], columns=ADVISORY_DEBONDING_RECOMMENDATION_COLUMNS)


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
