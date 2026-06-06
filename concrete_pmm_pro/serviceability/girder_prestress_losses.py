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
PSI_PER_MPA = 1000.0 / MPA_PER_KSI
MM_PER_INCH = 25.4

LOSS_BASIS_AASHTO_APPROXIMATE = "AASHTO LRFD approximate"
LOSS_BASIS_ACI_PCI_APPROXIMATE = "ACI 318 / PCI-style approximate"

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

ACI_PCI_VS_TYPICAL_RANGES_IN: dict[str, tuple[float, float]] = {
    "i_girder": (3.0, 4.5),
    "box_beam": (3.5, 5.0),
    "plank_girder": (2.5, 4.0),
    "u_girder": (3.0, 5.0),
    "generic_girder": (2.0, 6.0),
}

ACI_PCI_VS_FALLBACK_IN: dict[str, float] = {
    "i_girder": 3.5,
    "box_beam": 4.0,
    "plank_girder": 3.0,
    "u_girder": 4.0,
    "generic_girder": 3.5,
}


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
    # Optional ACI/PCI-style approximate parameters. Defaults keep existing AASHTO behavior unchanged.
    volume_surface_ratio_mm: float = 88.9  # 3.5 in typical PCI starting value for I-girders
    kcir: float = 0.90
    kcr: float = 2.0
    ksh: float = 1.0
    fcds_MPa: float = 0.0
    self_weight_moment_kNm: float = 0.0

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


@dataclass(frozen=True)
class AciPciGuidedLossInputSelection:
    """Auditable assistant-selected inputs for ACI/PCI-style approximate loss.

    Values are intentionally advisory defaults. They reduce manual data entry but
    remain visible so the engineer can review or override project-specific
    assumptions. V/S is stored in mm internally and shown in inches because the
    PCI-style shrinkage expression in this app expects inches.
    """

    section_family: str
    volume_surface_ratio_mm: float
    volume_surface_source: str
    volume_surface_status: str
    volume_surface_note: str
    kcir: float = 0.90
    kcr: float = 2.00
    ksh: float = 1.00
    kcir_source: str = "PCI shortcut"
    kcr_source: str = "Assumed normal-weight concrete"
    ksh_source: str = "Typical pretensioned final estimate"
    kcr_status: str = "OK"
    ksh_status: str = "OK"
    messages: tuple[str, ...] = ()

    @property
    def volume_surface_ratio_in(self) -> float:
        return max(float(self.volume_surface_ratio_mm), 0.0) / MM_PER_INCH

    def audit_dataframe(self) -> pd.DataFrame:
        rows = [
            {
                "Item": "V/S",
                "Value": f"{self.volume_surface_ratio_in:.2f} in. ({self.volume_surface_ratio_mm:.1f} mm)",
                "Source": self.volume_surface_source,
                "Status": self.volume_surface_status,
                "Engineering note": self.volume_surface_note,
            },
            {
                "Item": "Kcir",
                "Value": f"{self.kcir:.2f}",
                "Source": self.kcir_source,
                "Status": "OK",
                "Engineering note": "Elastic-shortening shortcut coefficient for the PCI-style approximate method.",
            },
            {
                "Item": "Kcr",
                "Value": f"{self.kcr:.2f}",
                "Source": self.kcr_source,
                "Status": self.kcr_status,
                "Engineering note": "Creep coefficient selection based on concrete density/type assumption; override if project criteria differ.",
            },
            {
                "Item": "Ksh",
                "Value": f"{self.ksh:.2f}",
                "Source": self.ksh_source,
                "Status": self.ksh_status,
                "Engineering note": "Shrinkage time-basis coefficient for a typical pretensioned final estimate.",
            },
        ]
        return pd.DataFrame(rows, columns=LOSS_INPUT_AUDIT_COLUMNS)


def normalize_aci_pci_section_family(section_preset_key: str | None = None, section_category: str | None = None) -> str:
    """Map app section preset metadata to a broad ACI/PCI V/S advisory family."""

    key = str(section_preset_key or "").strip().casefold()
    category = str(section_category or "").strip().casefold()
    if "i_girder" in key or "i-girder" in key or "i girder" in key:
        return "i_girder"
    if "box" in key or "box" in category:
        return "box_beam"
    if "plank" in key or "plank" in category:
        return "plank_girder"
    if "u_girder" in key or "u-girder" in key or "u girder" in key:
        return "u_girder"
    return "generic_girder"


def aci_pci_vs_typical_range_in(section_family: str) -> tuple[float, float]:
    return ACI_PCI_VS_TYPICAL_RANGES_IN.get(str(section_family), ACI_PCI_VS_TYPICAL_RANGES_IN["generic_girder"])


def aci_pci_vs_fallback_mm(section_family: str) -> float:
    return ACI_PCI_VS_FALLBACK_IN.get(str(section_family), ACI_PCI_VS_FALLBACK_IN["generic_girder"]) * MM_PER_INCH


def aci_pci_kcr_from_density(density_kg_m3: float | None) -> tuple[float, str, str]:
    """Return a practical Kcr default from concrete density/type assumption."""

    density = 2400.0 if density_kg_m3 is None else float(density_kg_m3)
    if density >= 2200.0:
        return 2.0, "Auto from concrete density ≥ 2200 kg/m³", "OK"
    if density >= 1850.0:
        return 1.6, "Auto assumed sand-lightweight from concrete density", "REVIEW"
    return 1.6, "Auto assumed lightweight from low concrete density", "REVIEW"


def estimate_aci_pci_guided_loss_inputs(
    *,
    section_area_mm2: float | None,
    exposed_perimeter_mm: float | None,
    section_preset_key: str | None = None,
    section_category: str | None = None,
    concrete_density_kg_m3: float | None = None,
) -> AciPciGuidedLossInputSelection:
    """Select auditable ACI/PCI approximate-loss inputs from current project data."""

    family = normalize_aci_pci_section_family(section_preset_key, section_category)
    messages: list[str] = []
    source = "Auto from current section geometry"
    status = "OK"
    note = "Computed as A/Pexposed from gross section area and outer exposed perimeter, then converted from mm to inch for PCI-style shrinkage."
    area = 0.0 if section_area_mm2 is None else float(section_area_mm2)
    perimeter = 0.0 if exposed_perimeter_mm is None else float(exposed_perimeter_mm)
    if area > 0.0 and perimeter > 0.0:
        vs_mm = estimate_volume_surface_ratio_mm(area, perimeter)
    else:
        vs_mm = aci_pci_vs_fallback_mm(family)
        source = "Preset by section family"
        status = "REVIEW"
        note = "Section geometry/perimeter is incomplete; using a family starter V/S. Verify before final design."
        messages.append("V/S was not calculated from geometry because section area or exposed perimeter is missing.")
    low, high = aci_pci_vs_typical_range_in(family)
    vs_in = vs_mm / MM_PER_INCH if vs_mm > 0.0 else 0.0
    if vs_in <= 0.0:
        status = "REVIEW"
        note = "V/S is non-positive; review section geometry and exposed perimeter."
        messages.append("V/S is non-positive.")
    elif not (low <= vs_in <= high):
        status = "REVIEW"
        note += f" Typical advisory range for {family.replace('_', ' ')} is about {low:.1f}–{high:.1f} in.; review exposed-surface assumptions."
        messages.append(f"Auto V/S {vs_in:.2f} in. is outside the advisory {family} range {low:.1f}–{high:.1f} in.")
    else:
        note += f" Within advisory {family.replace('_', ' ')} range {low:.1f}–{high:.1f} in."
    kcr, kcr_source, kcr_status = aci_pci_kcr_from_density(concrete_density_kg_m3)
    if kcr_status == "REVIEW":
        messages.append("Kcr was selected from a lightweight-concrete density assumption; verify concrete type/project criteria.")
    return AciPciGuidedLossInputSelection(
        section_family=family,
        volume_surface_ratio_mm=vs_mm,
        volume_surface_source=source,
        volume_surface_status=status,
        volume_surface_note=note,
        kcir=0.90,
        kcr=kcr,
        ksh=1.00,
        kcr_source=kcr_source,
        kcr_status=kcr_status,
        messages=tuple(messages),
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

def _mpa_to_psi(value_mpa: float) -> float:
    return float(value_mpa) * PSI_PER_MPA


def _psi_to_mpa(value_psi: float) -> float:
    return float(value_psi) / PSI_PER_MPA


def pci_relaxation_constants(relaxation_class: str) -> tuple[float, float, str]:
    """Return PCI-style relaxation constants (Kre psi, J, note)."""

    label = str(relaxation_class or "").strip().lower()
    if "stress" in label and "relieved" in label:
        return 20_000.0, 0.15, "270-ksi stress-relieved strand PCI table constants"
    return 5_000.0, 0.04, "270-ksi low-relaxation strand PCI table constants"


def pci_relaxation_c_factor(fsi_over_fpu: float) -> float:
    """Interpolate the PCI C factor for 270-ksi low-relaxation strand.

    The documented table covers fsi/fpu from 0.68 to 0.80.  Values outside
    the table are clamped because this is an approximate engineering preview,
    not a final loss-design certificate.
    """

    table = (
        (0.68, 0.90),
        (0.70, 0.98),
        (0.72, 1.05),
        (0.74, 1.11),
        (0.76, 1.16),
        (0.78, 1.22),
        (0.80, 1.28),
    )
    x = float(fsi_over_fpu)
    if x <= table[0][0]:
        return table[0][1]
    if x >= table[-1][0]:
        return table[-1][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return table[-1][1]


def _pci_shrinkage_loss_MPa(*, Ep_MPa: float, ksh: float, volume_surface_ratio_mm: float, humidity_percent: float) -> float:
    vs_in = max(float(volume_surface_ratio_mm), 0.0) / MM_PER_INCH
    rh = min(max(float(humidity_percent), 0.0), 100.0)
    vs_factor = max(1.0 - 0.06 * vs_in, 0.0)
    return max(8.2e-6 * max(float(ksh), 0.0) * max(float(Ep_MPa), 0.0) * vs_factor * (100.0 - rh), 0.0)


def _pci_relaxation_loss_MPa(
    *,
    relaxation_class: str,
    fpj_MPa: float,
    fpu_MPa: float,
    es_loss_MPa: float,
    creep_loss_MPa: float,
    shrinkage_loss_MPa: float,
) -> tuple[float, float, float, str]:
    fsi_over_fpu = 0.0 if float(fpu_MPa) <= 1.0e-9 else max(float(fpj_MPa), 0.0) / float(fpu_MPa)
    c_factor = pci_relaxation_c_factor(fsi_over_fpu)
    kre_psi, j_factor, note = pci_relaxation_constants(relaxation_class)
    prior_losses_psi = _mpa_to_psi(max(float(es_loss_MPa), 0.0) + max(float(creep_loss_MPa), 0.0) + max(float(shrinkage_loss_MPa), 0.0))
    relaxation_psi = max((kre_psi - j_factor * prior_losses_psi) * c_factor, 0.0)
    return _psi_to_mpa(relaxation_psi), c_factor, j_factor, note


def calculate_aci_pci_approximate_prestress_loss(input_data: GirderApproximateLossInput) -> GirderApproximateLossResult:
    """Calculate an ACI 318 project / PCI-style approximate pretensioned loss estimate.

    This is intentionally separate from the existing AASHTO approximate helper.
    It implements the PCI-style component workflow documented for ACI-governed
    precast pretensioned members: ES + CR + SH + RE.  Compression is positive
    internally for loss calculations; returned Pe values keep the existing app
    convention of positive prestress force magnitude per strand.
    """

    messages: list[str] = [
        "ACI/PCI-style approximate loss preview: ACI 318 requires losses to be considered but does not prescribe these equations directly; review against project PCI/ACI criteria.",
    ]
    if not input_data.groups:
        return GirderApproximateLossResult((), 0, 0.0, 0.0, 0.0, "MISSING", ("No active strand groups are available.",))
    if input_data.section_area_mm2 <= 0.0:
        raise ValueError("Section area must be positive for ACI/PCI approximate loss.")
    if input_data.section_Ix_mm4 <= 0.0:
        raise ValueError("Section Ix must be positive for ACI/PCI approximate loss.")
    if input_data.Eci_MPa <= 0.0:
        raise ValueError("Eci must be positive for ACI/PCI approximate loss.")
    Ec_MPa = 4700.0 * max(float(input_data.fc_MPa), 1.0) ** 0.5
    if not (40.0 <= float(input_data.humidity_percent) <= 100.0):
        messages.append("Relative humidity is outside the 40%–100% advisory range.")
    if input_data.volume_surface_ratio_mm <= 0.0:
        messages.append("V/S is non-positive; PCI shrinkage loss uses zero V/S correction.")
    if input_data.self_weight_moment_kNm <= 0.0:
        messages.append("Self-weight moment Mg is zero/not available; PCI fcir does not include self-weight relief.")

    groups = tuple(group for group in input_data.groups if group.no_strands > 0 and group.area_per_strand_mm2 > 0.0)
    total_force_N = sum(group.total_aps_mm2 * group.fpj_MPa for group in groups)
    total_prestress_moment_Nmm = sum(
        group.total_aps_mm2 * group.fpj_MPa * (group.y_mm_from_bottom - input_data.centroid_y_from_bottom_mm)
        for group in groups
    )
    Mg_Nmm = max(float(input_data.self_weight_moment_kNm), 0.0) * 1_000_000.0

    group_results: list[GirderApproximateLossGroupResult] = []
    max_re = 0.0
    for group in groups:
        fpj = group.fpj_MPa
        dy = float(group.y_mm_from_bottom - input_data.centroid_y_from_bottom_mm)
        prestress_compression = total_force_N / input_data.section_area_mm2 + total_prestress_moment_Nmm * dy / input_data.section_Ix_mm4
        prestress_compression = max(float(prestress_compression), 0.0)
        self_weight_relief = Mg_Nmm * abs(dy) / input_data.section_Ix_mm4
        fcir = max(max(float(input_data.kcir), 0.0) * prestress_compression - self_weight_relief, 0.0)
        es = max(group.Ep_MPa, 0.0) / input_data.Eci_MPa * fcir
        creep = max(float(input_data.kcr), 0.0) * max(group.Ep_MPa, 0.0) / Ec_MPa * max(fcir - max(float(input_data.fcds_MPa), 0.0), 0.0)
        shrinkage = _pci_shrinkage_loss_MPa(
            Ep_MPa=group.Ep_MPa,
            ksh=float(input_data.ksh),
            volume_surface_ratio_mm=float(input_data.volume_surface_ratio_mm),
            humidity_percent=float(input_data.humidity_percent),
        )
        relaxation, c_factor, j_factor, relaxation_note = _pci_relaxation_loss_MPa(
            relaxation_class=input_data.relaxation_class,
            fpj_MPa=fpj,
            fpu_MPa=group.fpu_MPa,
            es_loss_MPa=es,
            creep_loss_MPa=creep,
            shrinkage_loss_MPa=shrinkage,
        )
        max_re = max(max_re, relaxation)
        transfer_stress = max(fpj - es, 0.0)
        final_stress = max(fpj - es - creep - shrinkage - relaxation, 0.0)
        pe_transfer = group.area_per_strand_mm2 * transfer_stress / 1000.0
        pe_final = group.area_per_strand_mm2 * final_stress / 1000.0
        total_loss = fpj - final_stress
        loss_percent = 0.0 if fpj <= 1.0e-9 else total_loss / fpj * 100.0
        row_messages: list[str] = []
        if loss_percent < 5.0:
            row_messages.append("total loss below 5%")
        if loss_percent > 35.0:
            row_messages.append("total loss above 35%")
        fsi_over_fpu = 0.0 if group.fpu_MPa <= 1.0e-9 else fpj / group.fpu_MPa
        if not (0.68 <= fsi_over_fpu <= 0.80):
            row_messages.append("fpj/fpu outside PCI C-factor table range; C factor was clamped")
        status = "OK" if not row_messages else "REVIEW"
        note = (
            f"ACI/PCI-style approximate: ES={es:.1f} MPa, CR={creep:.1f} MPa, SH={shrinkage:.1f} MPa, RE={relaxation:.1f} MPa; "
            f"Kcir={float(input_data.kcir):.2f}, Kcr={float(input_data.kcr):.2f}, Ksh={float(input_data.ksh):.2f}, "
            f"C={c_factor:.2f}, J={j_factor:.2f}; {relaxation_note}."
        )
        if row_messages:
            note += " REVIEW: " + "; ".join(row_messages)
        group_results.append(
            GirderApproximateLossGroupResult(
                group_id=group.group_id,
                no_strands=group.no_strands,
                pjack_per_strand_kN=group.pjack_per_strand_kN,
                fpj_MPa=fpj,
                fcgp_MPa=fcir,
                es_loss_MPa=es,
                lt_loss_MPa=creep + shrinkage + relaxation,
                total_loss_MPa=total_loss,
                pe_transfer_per_strand_kN=pe_transfer,
                pe_construction_per_strand_kN=pe_transfer,
                pe_final_per_strand_kN=pe_final,
                total_loss_percent=loss_percent,
                status=status,
                note=note,
            )
        )
    statuses = {row.status for row in group_results}
    overall = "OK" if statuses == {"OK"} and len(messages) == 1 else "REVIEW"
    return GirderApproximateLossResult(tuple(group_results), 1, 0.0, 0.0, max_re, overall, tuple(messages))



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

REFINED_INTERVAL_RESULT_COLUMNS = [
    "Group ID",
    "Interval",
    "Shrinkage loss MPa",
    "Creep loss MPa",
    "Relaxation loss MPa",
    "Deck shrinkage loss MPa",
    "Subtotal loss MPa",
    "Pe at end/strand_kN",
    "Status",
    "Engineering note",
]




REFINED_COEFFICIENT_AUDIT_COLUMNS = [
    "Coefficient",
    "Value",
    "Source",
    "Status",
    "Engineering note",
]


@dataclass(frozen=True)
class RefinedAashtoCoefficientInput:
    """Input for auto-estimating refined AASHTO time-dependent coefficients.

    LOSS3B estimates the refined coefficients used by the LOSS3A manual
    coefficient engine from basic humidity/time/section data.  The estimate is
    intentionally auditable and still allows project-specific overrides.
    """

    section_area_mm2: float
    exposed_perimeter_mm: float
    section_Ix_mm4: float
    centroid_y_from_bottom_mm: float
    total_aps_mm2: float
    yps_mm_from_bottom: float
    Ep_MPa: float
    Eci_MPa: float
    Ec_MPa: float
    fci_MPa: float
    fc_MPa: float
    humidity_percent: float
    age_transfer_days: float
    age_deck_days: float
    final_age_days: float
    composite_area_mm2: float | None = None
    composite_Ix_mm4: float | None = None
    composite_centroid_y_from_bottom_mm: float | None = None


@dataclass(frozen=True)
class RefinedAashtoCoefficientResult:
    """Auto-estimated refined AASHTO coefficients and audit metadata."""

    Kid: float
    Kdf: float
    eps_bid: float
    eps_bdf: float
    psi_td_ti: float
    psi_tf_ti: float
    psi_tf_td: float
    volume_surface_mm: float
    volume_surface_in: float
    ks: float
    khc: float
    khs: float
    kf: float
    ktd_td_ti: float
    ktd_tf_ti: float
    ktd_tf_td: float
    status: str
    messages: tuple[str, ...]
    kdf_basis: str = "precast gross fallback"

    @property
    def eps_bid_microstrain(self) -> float:
        return self.eps_bid * 1.0e6

    @property
    def eps_bdf_microstrain(self) -> float:
        return self.eps_bdf * 1.0e6

    def as_settings_update(self) -> dict[str, float]:
        return {
            "Kid": self.Kid,
            "Kdf": self.Kdf,
            "eps_bid_microstrain": self.eps_bid_microstrain,
            "eps_bdf_microstrain": self.eps_bdf_microstrain,
            "psi_td_ti": self.psi_td_ti,
            "psi_tf_ti": self.psi_tf_ti,
            "psi_tf_td": self.psi_tf_td,
        }

    def audit_dataframe(self) -> pd.DataFrame:
        rows = [
            {
                "Coefficient": "V/S",
                "Value": f"{self.volume_surface_mm:.1f} mm ({self.volume_surface_in:.2f} in)",
                "Source": "Section geometry",
                "Status": "READY" if self.volume_surface_mm > 0.0 else "MISSING",
                "Engineering note": "Outer exposed perimeter estimate; void perimeter is not included in LOSS3B.",
            },
            {"Coefficient": "ks", "Value": self.ks, "Source": "Auto", "Status": "READY", "Engineering note": "V/S size factor."},
            {"Coefficient": "khc", "Value": self.khc, "Source": "Auto", "Status": "READY", "Engineering note": "Humidity factor for creep."},
            {"Coefficient": "khs", "Value": self.khs, "Source": "Auto", "Status": "READY", "Engineering note": "Humidity factor for shrinkage."},
            {"Coefficient": "kf", "Value": self.kf, "Source": "Auto", "Status": "READY", "Engineering note": "Concrete strength factor using f'ci."},
            {"Coefficient": "ktd(td,ti)", "Value": self.ktd_td_ti, "Source": "Auto", "Status": "READY", "Engineering note": "Time development factor for transfer-to-deck interval."},
            {"Coefficient": "ktd(tf,ti)", "Value": self.ktd_tf_ti, "Source": "Auto", "Status": "READY", "Engineering note": "Time development factor from transfer to final."},
            {"Coefficient": "ktd(tf,td)", "Value": self.ktd_tf_td, "Source": "Auto", "Status": "READY", "Engineering note": "Time development factor for deck-to-final interval."},
            {"Coefficient": "Ψb(td,ti)", "Value": self.psi_td_ti, "Source": "Auto", "Status": "READY", "Engineering note": "Estimated creep coefficient."},
            {"Coefficient": "Ψb(tf,ti)", "Value": self.psi_tf_ti, "Source": "Auto", "Status": "READY", "Engineering note": "Estimated total creep coefficient."},
            {"Coefficient": "Ψb(tf,td)", "Value": self.psi_tf_td, "Source": "Auto", "Status": "READY", "Engineering note": "Estimated creep coefficient after deck placement."},
            {"Coefficient": "εbid", "Value": f"{self.eps_bid_microstrain:.1f} microstrain", "Source": "Auto", "Status": "READY", "Engineering note": "Estimated shrinkage strain before deck placement."},
            {"Coefficient": "εbdf", "Value": f"{self.eps_bdf_microstrain:.1f} microstrain", "Source": "Auto", "Status": "READY", "Engineering note": "Estimated shrinkage strain after deck placement."},
            {"Coefficient": "Kid", "Value": self.Kid, "Source": "Auto", "Status": "READY" if 0.0 < self.Kid <= 1.0 else "REVIEW", "Engineering note": "Transfer-to-deck interaction coefficient."},
            {"Coefficient": "Kdf", "Value": self.Kdf, "Source": "Auto", "Status": "READY" if 0.0 < self.Kdf <= 1.0 else "REVIEW", "Engineering note": f"Deck-to-final interaction coefficient basis: {self.kdf_basis}."},
        ]
        return pd.DataFrame(rows, columns=REFINED_COEFFICIENT_AUDIT_COLUMNS)


def estimate_volume_surface_ratio_mm(section_area_mm2: float, exposed_perimeter_mm: float) -> float:
    """Return V/S in mm using gross area and exposed perimeter."""

    if exposed_perimeter_mm <= 0.0:
        return 0.0
    return max(float(section_area_mm2), 0.0) / float(exposed_perimeter_mm)


def _aashto_time_development_factor(duration_days: float, fci_ksi: float) -> float:
    duration = max(float(duration_days), 0.0)
    fci = max(float(fci_ksi), 0.1)
    denominator = 12.0 * (100.0 - 4.0 * fci) / (fci + 20.0) + duration
    if denominator <= 0.0:
        return 0.0
    return duration / denominator


def _aashto_creep_coefficient(
    *,
    volume_surface_in: float,
    humidity_percent: float,
    fci_ksi: float,
    duration_days: float,
    loading_age_days: float,
) -> tuple[float, dict[str, float]]:
    vs = max(float(volume_surface_in), 0.0)
    H = float(humidity_percent)
    fci = max(float(fci_ksi), 0.1)
    ti = max(float(loading_age_days), 0.1)
    ks = max(1.45 - 0.13 * vs, 1.0)
    khc = 1.56 - 0.008 * H
    kf = 5.0 / (1.0 + fci)
    ktd = _aashto_time_development_factor(duration_days, fci)
    psi = 1.9 * ks * khc * kf * ktd * ti ** (-0.118)
    return max(psi, 0.0), {"ks": ks, "khc": khc, "kf": kf, "ktd": ktd}


def _aashto_shrinkage_strain(
    *,
    volume_surface_in: float,
    humidity_percent: float,
    fci_ksi: float,
    duration_days: float,
) -> tuple[float, dict[str, float]]:
    vs = max(float(volume_surface_in), 0.0)
    H = float(humidity_percent)
    fci = max(float(fci_ksi), 0.1)
    ks = max(1.45 - 0.13 * vs, 1.0)
    khs = 2.00 - 0.014 * H
    kf = 5.0 / (1.0 + fci)
    ktd = _aashto_time_development_factor(duration_days, fci)
    strain = ks * khs * kf * ktd * 0.48e-3
    return max(strain, 0.0), {"ks": ks, "khs": khs, "kf": kf, "ktd": ktd}


def estimate_kid(
    *,
    Ep_MPa: float,
    Eci_MPa: float,
    Aps_mm2: float,
    Ag_mm2: float,
    epg_mm: float,
    Ig_mm4: float,
    psi_td_ti: float,
) -> float:
    if min(Eci_MPa, Ag_mm2, Ig_mm4) <= 0.0:
        return 0.0
    term = (Ep_MPa / Eci_MPa) * (Aps_mm2 / Ag_mm2) * (1.0 + Ag_mm2 * epg_mm**2 / Ig_mm4) * (1.0 + 0.7 * psi_td_ti)
    return 1.0 / (1.0 + max(term, 0.0))


def estimate_kdf(
    *,
    Ep_MPa: float,
    Ec_MPa: float,
    Aps_mm2: float,
    Ac_mm2: float,
    epc_mm: float,
    Ic_mm4: float,
    psi_tf_td: float,
) -> float:
    if min(Ec_MPa, Ac_mm2, Ic_mm4) <= 0.0:
        return 0.0
    term = (Ep_MPa / Ec_MPa) * (Aps_mm2 / Ac_mm2) * (1.0 + Ac_mm2 * epc_mm**2 / Ic_mm4) * (1.0 + 0.7 * psi_tf_td)
    return 1.0 / (1.0 + max(term, 0.0))


def estimate_refined_aashto_coefficients(input_data: RefinedAashtoCoefficientInput) -> RefinedAashtoCoefficientResult:
    """Estimate refined AASHTO coefficients from RH/time/section data.

    This is an auditable coefficient estimate, not a final project-specific
    clause-certified creep/shrinkage model.  Load-derived Δfcd/Δfcdf remain
    manual inputs in LOSS3B.
    """

    messages: list[str] = []
    if input_data.exposed_perimeter_mm <= 0.0:
        messages.append("Exposed perimeter is missing; V/S cannot be auto-estimated.")
    if not (40.0 <= input_data.humidity_percent <= 100.0):
        messages.append("Relative humidity is outside the advisory 40%–100% range.")
    if input_data.age_transfer_days <= 0.0:
        messages.append("Transfer age ti must be positive.")
    if input_data.age_deck_days <= input_data.age_transfer_days:
        messages.append("Deck-placement age td must be greater than transfer age ti.")
    if input_data.final_age_days <= input_data.age_deck_days:
        messages.append("Final age tf must be greater than deck-placement age td.")
    vs_mm = estimate_volume_surface_ratio_mm(input_data.section_area_mm2, input_data.exposed_perimeter_mm)
    vs_in = vs_mm / 25.4 if vs_mm > 0.0 else 0.0
    fci_ksi = max(mpa_to_ksi(input_data.fci_MPa), 0.1)
    td_ti = max(input_data.age_deck_days - input_data.age_transfer_days, 0.0)
    tf_ti = max(input_data.final_age_days - input_data.age_transfer_days, 0.0)
    tf_td = max(input_data.final_age_days - input_data.age_deck_days, 0.0)
    psi_td_ti, creep_1 = _aashto_creep_coefficient(
        volume_surface_in=vs_in,
        humidity_percent=input_data.humidity_percent,
        fci_ksi=fci_ksi,
        duration_days=td_ti,
        loading_age_days=input_data.age_transfer_days,
    )
    psi_tf_ti, creep_total = _aashto_creep_coefficient(
        volume_surface_in=vs_in,
        humidity_percent=input_data.humidity_percent,
        fci_ksi=fci_ksi,
        duration_days=tf_ti,
        loading_age_days=input_data.age_transfer_days,
    )
    psi_tf_td, creep_2 = _aashto_creep_coefficient(
        volume_surface_in=vs_in,
        humidity_percent=input_data.humidity_percent,
        fci_ksi=fci_ksi,
        duration_days=tf_td,
        loading_age_days=input_data.age_deck_days,
    )
    eps_total_deck, shrink_1 = _aashto_shrinkage_strain(
        volume_surface_in=vs_in,
        humidity_percent=input_data.humidity_percent,
        fci_ksi=fci_ksi,
        duration_days=td_ti,
    )
    eps_total_final, shrink_final = _aashto_shrinkage_strain(
        volume_surface_in=vs_in,
        humidity_percent=input_data.humidity_percent,
        fci_ksi=fci_ksi,
        duration_days=tf_ti,
    )
    eps_bid = eps_total_deck
    eps_bdf = max(eps_total_final - eps_total_deck, 0.0)
    epg = input_data.yps_mm_from_bottom - input_data.centroid_y_from_bottom_mm
    Kid = estimate_kid(
        Ep_MPa=input_data.Ep_MPa,
        Eci_MPa=input_data.Eci_MPa,
        Aps_mm2=input_data.total_aps_mm2,
        Ag_mm2=input_data.section_area_mm2,
        epg_mm=epg,
        Ig_mm4=input_data.section_Ix_mm4,
        psi_td_ti=psi_td_ti,
    )
    composite_area = input_data.composite_area_mm2 if input_data.composite_area_mm2 and input_data.composite_area_mm2 > 0.0 else input_data.section_area_mm2
    composite_Ix = input_data.composite_Ix_mm4 if input_data.composite_Ix_mm4 and input_data.composite_Ix_mm4 > 0.0 else input_data.section_Ix_mm4
    composite_cy = (
        input_data.composite_centroid_y_from_bottom_mm
        if input_data.composite_centroid_y_from_bottom_mm is not None
        else input_data.centroid_y_from_bottom_mm
    )
    kdf_basis = "composite transformed section" if input_data.composite_area_mm2 and input_data.composite_Ix_mm4 else "precast gross fallback"
    if kdf_basis == "precast gross fallback":
        messages.append("Kdf uses precast gross fallback; composite transformed properties are not auto-derived in LOSS3B.")
    epc = input_data.yps_mm_from_bottom - composite_cy
    Kdf = estimate_kdf(
        Ep_MPa=input_data.Ep_MPa,
        Ec_MPa=input_data.Ec_MPa,
        Aps_mm2=input_data.total_aps_mm2,
        Ac_mm2=float(composite_area),
        epc_mm=epc,
        Ic_mm4=float(composite_Ix),
        psi_tf_td=psi_tf_td,
    )
    # Use representative factors from total creep/final shrinkage for display.
    ks = creep_total.get("ks", shrink_final.get("ks", 0.0))
    khc = creep_total.get("khc", 0.0)
    khs = shrink_final.get("khs", 0.0)
    kf = creep_total.get("kf", shrink_final.get("kf", 0.0))
    if eps_bid + eps_bdf > 300.0e-6:
        messages.append("Auto-estimated shrinkage strain exceeds 300 microstrain; review RH/V/S/time assumptions.")
    if psi_tf_ti > 4.0:
        messages.append("Auto-estimated Ψb(tf,ti) exceeds 4.0; review creep assumptions.")
    if Kid <= 0.0 or Kid > 1.0 or Kdf <= 0.0 or Kdf > 1.0:
        messages.append("Auto-estimated Kid/Kdf outside 0–1; review section and prestress data.")
    status = "OK" if not messages else "REVIEW"
    return RefinedAashtoCoefficientResult(
        Kid=Kid,
        Kdf=Kdf,
        eps_bid=eps_bid,
        eps_bdf=eps_bdf,
        psi_td_ti=psi_td_ti,
        psi_tf_ti=psi_tf_ti,
        psi_tf_td=psi_tf_td,
        volume_surface_mm=vs_mm,
        volume_surface_in=vs_in,
        ks=ks,
        khc=khc,
        khs=khs,
        kf=kf,
        ktd_td_ti=creep_1.get("ktd", 0.0),
        ktd_tf_ti=creep_total.get("ktd", 0.0),
        ktd_tf_td=creep_2.get("ktd", 0.0),
        status=status,
        messages=tuple(messages),
        kdf_basis=kdf_basis,
    )


@dataclass(frozen=True)
class RefinedAashtoManualCoefficientInput:
    """Manual-coefficient refined AASHTO time-dependent loss input.

    LOSS3A intentionally uses user-supplied refined coefficients/stresses
    instead of predicting AASHTO creep/shrinkage coefficients internally.  This
    keeps the first refined workflow auditable and avoids silently embedding
    project-specific assumptions in the app.
    """

    groups: tuple[GirderLossStrandGroupInput, ...]
    section_area_mm2: float
    section_Ix_mm4: float
    centroid_y_from_bottom_mm: float
    fci_MPa: float
    fc_MPa: float
    Eci_MPa: float
    Ec_MPa: float
    fpy_MPa: float = 1670.0
    relaxation_class: str = "Low relaxation"
    age_transfer_days: float = 1.0
    age_deck_days: float = 30.0
    final_age_days: float = 10000.0
    Kid: float = 1.0
    Kdf: float = 1.0
    eps_bid: float = 150.0e-6
    eps_bdf: float = 100.0e-6
    psi_td_ti: float = 1.0
    psi_tf_ti: float = 2.0
    psi_tf_td: float = 1.0
    delta_fcd_MPa: float = 0.0
    delta_fcdf_MPa: float = 0.0
    es_tolerance_MPa: float = 0.05
    max_iterations: int = 25
    # Optional ACI/PCI-style approximate parameters. Defaults keep existing AASHTO behavior unchanged.
    volume_surface_ratio_mm: float = 88.9  # 3.5 in typical PCI starting value for I-girders
    kcir: float = 0.90
    kcr: float = 2.0
    ksh: float = 1.0
    fcds_MPa: float = 0.0
    self_weight_moment_kNm: float = 0.0


@dataclass(frozen=True)
class RefinedAashtoGroupResult:
    group_id: str
    no_strands: int
    pjack_per_strand_kN: float
    fpj_MPa: float
    fcgp_MPa: float
    es_loss_MPa: float
    sr_loss_MPa: float
    cr_loss_MPa: float
    r1_loss_MPa: float
    sd_loss_MPa: float
    cd_loss_MPa: float
    r2_loss_MPa: float
    ss_loss_MPa: float
    total_loss_MPa: float
    pe_transfer_per_strand_kN: float
    pe_construction_per_strand_kN: float
    pe_final_per_strand_kN: float
    total_loss_percent: float
    status: str
    note: str

    def as_loss_dict(self) -> dict[str, Any]:
        lt_loss = self.sr_loss_MPa + self.cr_loss_MPa + self.r1_loss_MPa + self.sd_loss_MPa + self.cd_loss_MPa + self.r2_loss_MPa + self.ss_loss_MPa
        return {
            "Group ID": self.group_id,
            "No. strands": self.no_strands,
            "Pjack/strand_kN": self.pjack_per_strand_kN,
            "fpj_MPa": self.fpj_MPa,
            "fcgp_MPa": self.fcgp_MPa,
            "ES loss MPa": self.es_loss_MPa,
            "LT loss MPa": lt_loss,
            "Total loss MPa": self.total_loss_MPa,
            "Pe_transfer/strand_kN": self.pe_transfer_per_strand_kN,
            "Pe_construction/strand_kN": self.pe_construction_per_strand_kN,
            "Pe_eff_final/strand_kN": self.pe_final_per_strand_kN,
            "Total loss %": self.total_loss_percent,
            "Status": self.status,
            "Engineering note": self.note,
        }

    def interval_dicts(self) -> list[dict[str, Any]]:
        interval_1 = self.sr_loss_MPa + self.cr_loss_MPa + self.r1_loss_MPa
        interval_2 = self.sd_loss_MPa + self.cd_loss_MPa + self.r2_loss_MPa + self.ss_loss_MPa
        return [
            {
                "Group ID": self.group_id,
                "Interval": "Transfer → deck placement",
                "Shrinkage loss MPa": self.sr_loss_MPa,
                "Creep loss MPa": self.cr_loss_MPa,
                "Relaxation loss MPa": self.r1_loss_MPa,
                "Deck shrinkage loss MPa": 0.0,
                "Subtotal loss MPa": interval_1,
                "Pe at end/strand_kN": self.pe_construction_per_strand_kN,
                "Status": self.status,
                "Engineering note": "Pe_construction at deck placement / construction stage.",
            },
            {
                "Group ID": self.group_id,
                "Interval": "Deck placement → final",
                "Shrinkage loss MPa": self.sd_loss_MPa,
                "Creep loss MPa": self.cd_loss_MPa,
                "Relaxation loss MPa": self.r2_loss_MPa,
                "Deck shrinkage loss MPa": self.ss_loss_MPa,
                "Subtotal loss MPa": interval_2,
                "Pe at end/strand_kN": self.pe_final_per_strand_kN,
                "Status": self.status,
                "Engineering note": "Pe_final at final service stage.",
            },
        ]


@dataclass(frozen=True)
class RefinedAashtoLossResult:
    group_results: tuple[RefinedAashtoGroupResult, ...]
    es_iterations: int
    status: str
    messages: tuple[str, ...]

    def result_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([row.as_loss_dict() for row in self.group_results], columns=LOSS_RESULT_COLUMNS)

    def interval_dataframe(self) -> pd.DataFrame:
        records: list[dict[str, Any]] = []
        for row in self.group_results:
            records.extend(row.interval_dicts())
        return pd.DataFrame(records, columns=REFINED_INTERVAL_RESULT_COLUMNS)

    def summary_dataframe(self) -> pd.DataFrame:
        if not self.group_results:
            return pd.DataFrame(columns=["Metric", "Value", "Status"])
        total_pjack = sum(row.pjack_per_strand_kN * row.no_strands for row in self.group_results)
        total_transfer = sum(row.pe_transfer_per_strand_kN * row.no_strands for row in self.group_results)
        total_construction = sum(row.pe_construction_per_strand_kN * row.no_strands for row in self.group_results)
        total_final = sum(row.pe_final_per_strand_kN * row.no_strands for row in self.group_results)
        total_loss_percent = 0.0 if total_pjack <= 1e-9 else (1.0 - total_final / total_pjack) * 100.0
        return pd.DataFrame(
            [
                {"Metric": "Total Pjack", "Value": f"{total_pjack:,.1f} kN", "Status": "INFO"},
                {"Metric": "Total Pe_transfer", "Value": f"{total_transfer:,.1f} kN", "Status": "INFO"},
                {"Metric": "Total Pe_construction", "Value": f"{total_construction:,.1f} kN", "Status": "INFO"},
                {"Metric": "Total Pe_final", "Value": f"{total_final:,.1f} kN", "Status": "INFO"},
                {"Metric": "Total loss", "Value": f"{total_loss_percent:.1f}%", "Status": self.status},
                {"Metric": "ES iterations", "Value": str(self.es_iterations), "Status": "INFO"},
            ]
        )


def _relaxation_kl(relaxation_class: str) -> float:
    label = str(relaxation_class or "").strip().lower()
    return 7.0 if "stress" in label and "relieved" in label else 30.0


def _refined_relaxation_loss_MPa(fpt_MPa: float, fpy_MPa: float, relaxation_class: str) -> tuple[float, str | None]:
    if fpy_MPa <= 0.0:
        return 0.0, "fpy is non-positive; relaxation term set to zero."
    kl = _relaxation_kl(relaxation_class)
    ratio_term = fpt_MPa / fpy_MPa - 0.55
    if ratio_term <= 0.0:
        return 0.0, "Relaxation term fpt/fpy - 0.55 is non-positive; review fpt/fpy input."
    return max(fpt_MPa / kl * ratio_term, 0.0), None


def calculate_refined_aashto_time_dependent_loss(input_data: RefinedAashtoManualCoefficientInput) -> RefinedAashtoLossResult:
    """Calculate LOSS3A refined AASHTO-style losses using manual coefficients.

    This function intentionally requires Kid/Kdf, creep coefficients, shrinkage
    strain, and deck stress-effect inputs from the caller.  It does not predict
    AASHTO creep/shrinkage coefficients or load-derived deck stress effects.
    """

    messages: list[str] = []
    if not input_data.groups:
        return RefinedAashtoLossResult((), 0, "MISSING", ("No active strand groups are available.",))
    if input_data.age_deck_days <= input_data.age_transfer_days:
        messages.append("Deck-placement age td must be greater than transfer age ti.")
    if input_data.final_age_days <= input_data.age_deck_days:
        messages.append("Final age tf must be greater than deck-placement age td.")
    if input_data.Kid <= 0.0:
        messages.append("Kid must be positive.")
    if input_data.Kdf <= 0.0:
        messages.append("Kdf must be positive.")
    if min(input_data.eps_bid, input_data.eps_bdf, input_data.psi_td_ti, input_data.psi_tf_ti, input_data.psi_tf_td) < 0.0:
        messages.append("Shrinkage strain and creep coefficients must be non-negative.")
    if input_data.psi_tf_ti < input_data.psi_td_ti:
        messages.append("Ψb(tf,ti) is smaller than Ψb(td,ti); interval-2 creep may be inconsistent.")
    if input_data.Eci_MPa <= 0.0 or input_data.Ec_MPa <= 0.0:
        messages.append("Concrete modulus values must be positive.")

    approx_input = GirderApproximateLossInput(
        groups=input_data.groups,
        section_area_mm2=input_data.section_area_mm2,
        section_Ix_mm4=input_data.section_Ix_mm4,
        centroid_y_from_bottom_mm=input_data.centroid_y_from_bottom_mm,
        fci_MPa=input_data.fci_MPa,
        fc_MPa=input_data.fc_MPa,
        Eci_MPa=input_data.Eci_MPa,
        humidity_percent=70.0,
        relaxation_class=input_data.relaxation_class,
        es_tolerance_MPa=input_data.es_tolerance_MPa,
        max_iterations=input_data.max_iterations,
    )
    es_losses, fcgp_by_group, iterations = calculate_elastic_shortening_iterative(approx_input)
    group_results: list[RefinedAashtoGroupResult] = []
    for group in input_data.groups:
        fpj = group.fpj_MPa
        es = es_losses.get(group.group_id, 0.0)
        fpt = max(fpj - es, 0.0)
        fcgp = fcgp_by_group.get(group.group_id, 0.0)
        r1, relax_note = _refined_relaxation_loss_MPa(fpt, input_data.fpy_MPa, input_data.relaxation_class)
        r2 = r1
        sr = max(input_data.eps_bid * group.Ep_MPa * input_data.Kid, 0.0)
        cr = max(group.Ep_MPa / input_data.Eci_MPa * input_data.psi_td_ti * input_data.Kid * fcgp, 0.0)
        sd = max(input_data.eps_bdf * group.Ep_MPa * input_data.Kdf, 0.0)
        interval2_creep_coeff = max(input_data.psi_tf_ti - input_data.psi_td_ti, 0.0)
        cd = max(
            group.Ep_MPa / input_data.Eci_MPa * interval2_creep_coeff * input_data.Kdf * fcgp
            + group.Ep_MPa / input_data.Ec_MPa * input_data.psi_tf_td * input_data.Kdf * input_data.delta_fcd_MPa,
            0.0,
        )
        ss = max(group.Ep_MPa / input_data.Ec_MPa * input_data.delta_fcdf_MPa * input_data.Kdf * (1.0 + 0.7 * input_data.psi_tf_td), 0.0)
        interval1 = sr + cr + r1
        interval2 = sd + cd + r2 + ss
        final_stress = max(fpt - interval1 - interval2, 0.0)
        construction_stress = max(fpt - interval1, 0.0)
        pe_transfer = group.area_per_strand_mm2 * fpt / 1000.0
        pe_construction = group.area_per_strand_mm2 * construction_stress / 1000.0
        pe_final = group.area_per_strand_mm2 * final_stress / 1000.0
        total_loss = fpj - final_stress
        total_loss_percent = 0.0 if fpj <= 1.0e-9 else total_loss / fpj * 100.0
        row_messages: list[str] = []
        if relax_note:
            row_messages.append(relax_note)
        if pe_construction > pe_transfer + 1e-9:
            row_messages.append("Pe_construction exceeds Pe_transfer.")
        if pe_final > pe_construction + 1e-9:
            row_messages.append("Pe_final exceeds Pe_construction.")
        if total_loss_percent < 5.0:
            row_messages.append("total loss below 5%")
        if total_loss_percent > 40.0:
            row_messages.append("total loss above 40%")
        status = "OK" if not row_messages and not messages else "REVIEW"
        group_results.append(
            RefinedAashtoGroupResult(
                group_id=group.group_id,
                no_strands=group.no_strands,
                pjack_per_strand_kN=group.pjack_per_strand_kN,
                fpj_MPa=fpj,
                fcgp_MPa=fcgp,
                es_loss_MPa=es,
                sr_loss_MPa=sr,
                cr_loss_MPa=cr,
                r1_loss_MPa=r1,
                sd_loss_MPa=sd,
                cd_loss_MPa=cd,
                r2_loss_MPa=r2,
                ss_loss_MPa=ss,
                total_loss_MPa=total_loss,
                pe_transfer_per_strand_kN=pe_transfer,
                pe_construction_per_strand_kN=pe_construction,
                pe_final_per_strand_kN=pe_final,
                total_loss_percent=total_loss_percent,
                status=status,
                note="Refined AASHTO manual-coefficient preview; engineering review required." if not row_messages else "; ".join(row_messages),
            )
        )
    statuses = {row.status for row in group_results}
    overall = "OK" if statuses == {"OK"} and not messages else "REVIEW"
    return RefinedAashtoLossResult(tuple(group_results), iterations, overall, tuple(messages))
