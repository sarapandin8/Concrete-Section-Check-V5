"""Approximate prestress-loss helpers for precast pretensioned girders.

GIRDER.LOSS2A intentionally implements only an approximate code-based loss
estimate for pretensioned girder workflows.  It does not perform refined
AASHTO time-dependent analysis, transfer-length ramping, development-length,
shear, or end-zone reinforcement design.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd

MPA_PER_KSI = 6.894757293168361

LOSS_RESULT_COLUMNS = [
    "Group ID",
    "No. strands",
    "Pjack/strand_kN",
    "fpj_MPa",
    "fcgp_MPa",
    "ES loss MPa",
    "LT loss MPa",
    "Total loss MPa",
    "Pe_transfer/strand_kN",
    "Pe_construction/strand_kN",
    "Pe_eff_final/strand_kN",
    "Total loss %",
    "Status",
    "Engineering note",
]

LOSS_INPUT_AUDIT_COLUMNS = [
    "Item",
    "Value",
    "Source",
    "Status",
    "Engineering note",
]


@dataclass(frozen=True)
class GirderLossStrandGroupInput:
    """One strand group participating in the approximate loss estimate."""

    group_id: str
    no_strands: int
    area_per_strand_mm2: float
    y_mm_from_bottom: float
    pjack_per_strand_kN: float
    Ep_MPa: float = 195000.0
    fpu_MPa: float = 1860.0

    @property
    def total_aps_mm2(self) -> float:
        return max(0, int(self.no_strands)) * max(float(self.area_per_strand_mm2), 0.0)

    @property
    def fpj_MPa(self) -> float:
        area = max(float(self.area_per_strand_mm2), 0.0)
        if area <= 1.0e-12:
            return 0.0
        return max(float(self.pjack_per_strand_kN), 0.0) * 1000.0 / area


@dataclass(frozen=True)
class GirderApproximateLossInput:
    """Input bundle for the LOSS2A approximate code-based estimate."""

    groups: tuple[GirderLossStrandGroupInput, ...]
    section_area_mm2: float
    section_Ix_mm4: float
    centroid_y_from_bottom_mm: float
    fci_MPa: float
    fc_MPa: float
    Eci_MPa: float
    humidity_percent: float
    relaxation_class: str = "Low relaxation"
    es_tolerance_MPa: float = 0.05
    max_iterations: int = 25

    @property
    def total_aps_mm2(self) -> float:
        return sum(group.total_aps_mm2 for group in self.groups)


@dataclass(frozen=True)
class GirderApproximateLossGroupResult:
    group_id: str
    no_strands: int
    pjack_per_strand_kN: float
    fpj_MPa: float
    fcgp_MPa: float
    es_loss_MPa: float
    lt_loss_MPa: float
    total_loss_MPa: float
    pe_transfer_per_strand_kN: float
    pe_construction_per_strand_kN: float
    pe_final_per_strand_kN: float
    total_loss_percent: float
    status: str
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "Group ID": self.group_id,
            "No. strands": self.no_strands,
            "Pjack/strand_kN": self.pjack_per_strand_kN,
            "fpj_MPa": self.fpj_MPa,
            "fcgp_MPa": self.fcgp_MPa,
            "ES loss MPa": self.es_loss_MPa,
            "LT loss MPa": self.lt_loss_MPa,
            "Total loss MPa": self.total_loss_MPa,
            "Pe_transfer/strand_kN": self.pe_transfer_per_strand_kN,
            "Pe_construction/strand_kN": self.pe_construction_per_strand_kN,
            "Pe_eff_final/strand_kN": self.pe_final_per_strand_kN,
            "Total loss %": self.total_loss_percent,
            "Status": self.status,
            "Engineering note": self.note,
        }


@dataclass(frozen=True)
class GirderApproximateLossResult:
    group_results: tuple[GirderApproximateLossGroupResult, ...]
    es_iterations: int
    gamma_h: float
    gamma_st: float
    relaxation_loss_MPa: float
    status: str
    messages: tuple[str, ...]

    def result_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([row.as_dict() for row in self.group_results], columns=LOSS_RESULT_COLUMNS)

    def summary_dataframe(self) -> pd.DataFrame:
        if not self.group_results:
            return pd.DataFrame(columns=["Metric", "Value", "Status"])
        total_pjack = sum(row.pjack_per_strand_kN * row.no_strands for row in self.group_results)
        total_transfer = sum(row.pe_transfer_per_strand_kN * row.no_strands for row in self.group_results)
        total_final = sum(row.pe_final_per_strand_kN * row.no_strands for row in self.group_results)
        loss_percent = 0.0 if total_pjack <= 1e-9 else (1.0 - total_final / total_pjack) * 100.0
        return pd.DataFrame(
            [
                {"Metric": "Total Pjack", "Value": f"{total_pjack:,.1f} kN", "Status": "INFO"},
                {"Metric": "Total Pe_transfer", "Value": f"{total_transfer:,.1f} kN", "Status": "INFO"},
                {"Metric": "Total Pe_final", "Value": f"{total_final:,.1f} kN", "Status": "INFO"},
                {"Metric": "Total loss", "Value": f"{loss_percent:.1f}%", "Status": self.status},
                {"Metric": "ES iterations", "Value": str(self.es_iterations), "Status": "INFO"},
            ]
        )


def ksi_to_mpa(value_ksi: float) -> float:
    return float(value_ksi) * MPA_PER_KSI


def mpa_to_ksi(value_mpa: float) -> float:
    return float(value_mpa) / MPA_PER_KSI


def aashto_humidity_factor(humidity_percent: float) -> float:
    """Return γh = 1.7 - 0.01H for approximate AASHTO-style LT loss."""

    return 1.7 - 0.01 * float(humidity_percent)


def aashto_strength_factor(fci_MPa: float) -> float:
    """Return γst = 5 / (1 + f'ci) with f'ci in ksi."""

    fci_ksi = max(mpa_to_ksi(float(fci_MPa)), 1.0e-9)
    return 5.0 / (1.0 + fci_ksi)


def relaxation_loss_MPa(relaxation_class: str) -> float:
    label = str(relaxation_class or "").strip().lower()
    if "stress" in label and "relieved" in label:
        return ksi_to_mpa(10.0)
    return ksi_to_mpa(2.4)


def calculate_elastic_shortening_iterative(input_data: GirderApproximateLossInput) -> tuple[dict[str, float], dict[str, float], int]:
    """Return ES loss and fcgp by group using an iterative pretensioned model.

    Compression is treated as positive for the loss calculation.  The total
    prestress force and eccentricity are recomputed each iteration, so fcgp is
    based on the post-ES stress state rather than the raw jacking stress.
    """

    if input_data.section_area_mm2 <= 0.0:
        raise ValueError("Section area must be positive for elastic shortening loss.")
    if input_data.section_Ix_mm4 <= 0.0:
        raise ValueError("Section Ix must be positive for elastic shortening loss.")
    if input_data.Eci_MPa <= 0.0:
        raise ValueError("Eci must be positive for elastic shortening loss.")

    groups = tuple(group for group in input_data.groups if group.no_strands > 0 and group.area_per_strand_mm2 > 0.0)
    if not groups:
        return {}, {}, 0

    fp_current = {group.group_id: group.fpj_MPa for group in groups}
    es_loss = {group.group_id: 0.0 for group in groups}
    fcgp_by_group = {group.group_id: 0.0 for group in groups}
    iterations = 0
    for iteration in range(1, max(int(input_data.max_iterations), 1) + 1):
        iterations = iteration
        total_force_N = sum(group.total_aps_mm2 * fp_current[group.group_id] for group in groups)
        total_moment_Nmm = sum(
            group.total_aps_mm2
            * fp_current[group.group_id]
            * (group.y_mm_from_bottom - input_data.centroid_y_from_bottom_mm)
            for group in groups
        )
        max_delta = 0.0
        next_fp: dict[str, float] = {}
        for group in groups:
            dy = group.y_mm_from_bottom - input_data.centroid_y_from_bottom_mm
            fcgp = total_force_N / input_data.section_area_mm2 + total_moment_Nmm * dy / input_data.section_Ix_mm4
            fcgp = max(float(fcgp), 0.0)
            es = max(float(group.Ep_MPa), 0.0) / input_data.Eci_MPa * fcgp
            fp_new = max(group.fpj_MPa - es, 0.0)
            max_delta = max(max_delta, abs(fp_new - fp_current[group.group_id]))
            next_fp[group.group_id] = fp_new
            es_loss[group.group_id] = es
            fcgp_by_group[group.group_id] = fcgp
        fp_current = next_fp
        if max_delta <= max(float(input_data.es_tolerance_MPa), 1.0e-9):
            break
    return es_loss, fcgp_by_group, iterations


def calculate_aashto_approximate_long_term_loss_MPa(
    *,
    fpi_MPa: float,
    total_aps_mm2: float,
    section_area_mm2: float,
    humidity_percent: float,
    fci_MPa: float,
    relaxation_class: str = "Low relaxation",
) -> tuple[float, float, float, float]:
    """Return approximate long-term loss and factors in MPa.

    Internal expression is evaluated in ksi using the AASHTO-style approximate
    terms documented for this milestone, then converted back to MPa.
    """

    if section_area_mm2 <= 0.0:
        raise ValueError("Section area must be positive for long-term loss.")
    fpi_ksi = max(mpa_to_ksi(float(fpi_MPa)), 0.0)
    ratio = max(float(total_aps_mm2), 0.0) / float(section_area_mm2)
    gamma_h = aashto_humidity_factor(float(humidity_percent))
    gamma_st = aashto_strength_factor(float(fci_MPa))
    fpR_MPa = relaxation_loss_MPa(relaxation_class)
    fpR_ksi = mpa_to_ksi(fpR_MPa)
    loss_ksi = 10.0 * fpi_ksi * ratio * gamma_h * gamma_st + 12.0 * gamma_h * gamma_st + fpR_ksi
    return ksi_to_mpa(max(loss_ksi, 0.0)), gamma_h, gamma_st, fpR_MPa


def calculate_approximate_prestress_loss(input_data: GirderApproximateLossInput) -> GirderApproximateLossResult:
    """Calculate LOSS2A approximate prestress losses for active strand groups."""

    messages: list[str] = []
    if not input_data.groups:
        return GirderApproximateLossResult((), 0, 0.0, 0.0, 0.0, "MISSING", ("No active strand groups are available.",))
    if not (40.0 <= float(input_data.humidity_percent) <= 100.0):
        messages.append("Relative humidity is outside the 40%–100% advisory range.")
    if input_data.fci_MPa <= 0.0:
        messages.append("f'ci is missing or non-positive.")
    if input_data.fc_MPa <= 0.0:
        messages.append("f'c is missing or non-positive.")

    es_losses, fcgp_by_group, iterations = calculate_elastic_shortening_iterative(input_data)
    group_results: list[GirderApproximateLossGroupResult] = []
    gamma_h = aashto_humidity_factor(input_data.humidity_percent)
    gamma_st = aashto_strength_factor(input_data.fci_MPa)
    fpR = relaxation_loss_MPa(input_data.relaxation_class)
    for group in input_data.groups:
        fpj = group.fpj_MPa
        es = es_losses.get(group.group_id, 0.0)
        fpi = max(fpj - es, 0.0)
        lt, gamma_h, gamma_st, fpR = calculate_aashto_approximate_long_term_loss_MPa(
            fpi_MPa=fpi,
            total_aps_mm2=input_data.total_aps_mm2,
            section_area_mm2=input_data.section_area_mm2,
            humidity_percent=input_data.humidity_percent,
            fci_MPa=input_data.fci_MPa,
            relaxation_class=input_data.relaxation_class,
        )
        final_stress = max(fpi - lt, 0.0)
        pe_transfer = group.area_per_strand_mm2 * fpi / 1000.0
        pe_final = group.area_per_strand_mm2 * final_stress / 1000.0
        total_loss = fpj - final_stress
        loss_percent = 0.0 if fpj <= 1.0e-9 else total_loss / fpj * 100.0
        row_messages: list[str] = []
        if loss_percent < 5.0:
            row_messages.append("total loss below 5%")
        if loss_percent > 35.0:
            row_messages.append("total loss above 35%")
        if final_stress > fpj:
            row_messages.append("final stress exceeds jacking stress")
        status = "OK" if not row_messages else "REVIEW"
        group_results.append(
            GirderApproximateLossGroupResult(
                group_id=group.group_id,
                no_strands=group.no_strands,
                pjack_per_strand_kN=group.pjack_per_strand_kN,
                fpj_MPa=fpj,
                fcgp_MPa=fcgp_by_group.get(group.group_id, 0.0),
                es_loss_MPa=es,
                lt_loss_MPa=lt,
                total_loss_MPa=total_loss,
                pe_transfer_per_strand_kN=pe_transfer,
                pe_construction_per_strand_kN=pe_transfer,
                pe_final_per_strand_kN=pe_final,
                total_loss_percent=loss_percent,
                status=status,
                note="Approximate code-based estimate; engineering review required." if not row_messages else "; ".join(row_messages),
            )
        )
    statuses = {row.status for row in group_results}
    overall = "OK" if statuses == {"OK"} and not messages else "REVIEW"
    return GirderApproximateLossResult(tuple(group_results), iterations, gamma_h, gamma_st, fpR, overall, tuple(messages))


def loss_result_dataframe_to_force_state_table(result_table: pd.DataFrame, current_force_table: pd.DataFrame | None = None) -> pd.DataFrame:
    """Map a LOSS2A result table to the existing force-state table schema."""

    current_by_group: dict[str, dict[str, Any]] = {}
    if current_force_table is not None:
        current = pd.DataFrame(current_force_table)
        if not current.empty and "Group ID" in current.columns:
            current_by_group = {str(row.get("Group ID")): row.to_dict() for _, row in current.iterrows() if str(row.get("Group ID") or "").strip()}
    rows: list[dict[str, Any]] = []
    for _, row in pd.DataFrame(result_table).iterrows():
        group = str(row.get("Group ID") or "strand group")
        existing = current_by_group.get(group, {})
        pjack = float(row.get("Pjack/strand_kN") or 0.0)
        pe_transfer = float(row.get("Pe_transfer/strand_kN") or 0.0)
        pe_construction = float(row.get("Pe_construction/strand_kN") or pe_transfer)
        pe_final = float(row.get("Pe_eff_final/strand_kN") or 0.0)
        transfer_loss = 0.0 if pjack <= 1.0e-9 else (1.0 - pe_transfer / pjack) * 100.0
        construction_loss = 0.0 if pe_transfer <= 1.0e-9 else (1.0 - pe_construction / pe_transfer) * 100.0
        long_term_loss = 0.0 if pe_construction <= 1.0e-9 else (1.0 - pe_final / pe_construction) * 100.0
        total_loss = 0.0 if pjack <= 1.0e-9 else (1.0 - pe_final / pjack) * 100.0
        rows.append(
            {
                "Active": bool(existing.get("Active", True)),
                "Group ID": group,
                "No. strands": int(row.get("No. strands") or existing.get("No. strands") or 0),
                "Pjack/strand_kN": pjack,
                "Transfer loss %": transfer_loss,
                "Pe_transfer/strand_kN": pe_transfer,
                "Construction loss %": construction_loss,
                "Pe_construction/strand_kN": pe_construction,
                "Long-term loss %": long_term_loss,
                "Pe_eff_final/strand_kN": pe_final,
                "Total loss %": total_loss,
                "QA status": "OK" if str(row.get("Status")) == "OK" else "REVIEW",
                "Note": row.get("Engineering note") or "LOSS2A approximate code-based estimate applied.",
            }
        )
    return pd.DataFrame(rows)
