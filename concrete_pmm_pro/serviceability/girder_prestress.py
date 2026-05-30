"""Beam/Girder effective-prestress stress-effect helpers.

GIRDER.PS1A adds a small, pure-Python kernel for prestress stress components in
future bridge-girder SLS workflows.  It intentionally does **not** change PMM,
prestress input, tendon database, rebar, report, load-case, or UI behavior.

Sign convention for this module matches ``serviceability.girder_stress``:
- compression stress is negative
- tension stress is positive
- ``Pe_eff_kN`` is positive for compressive effective prestress
- ``eccentricity_mm = y_ps - y_centroid`` with y measured upward from the
  selected section-basis bottom fiber
- the equivalent prestress moment is reported in the existing girder convention
  where positive moment is sagging.  A low tendon has negative eccentricity and
  therefore a negative equivalent moment, producing higher bottom compression.

The kernel consumes an already-selected section basis.  The caller must choose
whether that basis is precast gross or composite transformed; this module never
changes section properties and never injects deck/topping into PMM behavior.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from concrete_pmm_pro.core.models import PrestressElement
from concrete_pmm_pro.serviceability.girder_stress import GirderSectionBasis

PrestressStressType = str


@dataclass(frozen=True)
class GirderPrestressFiberStress:
    """Prestress stress contribution at one girder fiber.

    ``axial_stress_MPa`` is always compressive or zero for positive ``Pe_eff``.
    ``eccentric_bending_stress_MPa`` is the stress caused by eccentricity of the
    effective prestress force about the selected section centroid.
    """

    location: str
    y_from_bottom_mm: float
    axial_stress_MPa: float
    eccentric_bending_stress_MPa: float
    total_stress_MPa: float
    stress_type: PrestressStressType


@dataclass(frozen=True)
class GirderPrestressStressResult:
    """Top/bottom prestress stress effect for one selected girder basis."""

    basis_name: str
    Pe_eff_kN: float
    tendon_y_from_bottom_mm: float
    eccentricity_mm: float
    equivalent_moment_kNm: float
    top: GirderPrestressFiberStress
    bottom: GirderPrestressFiberStress
    warnings: tuple[str, ...] = ()

    @property
    def max_compression_MPa(self) -> float:
        """Return the most compressive prestress stress as a negative value."""

        return min(self.top.total_stress_MPa, self.bottom.total_stress_MPa)

    @property
    def max_tension_MPa(self) -> float:
        """Return the maximum tensile prestress stress as a positive value."""

        return max(self.top.total_stress_MPa, self.bottom.total_stress_MPa)


@dataclass(frozen=True)
class GirderPrestressElementSummary:
    """Weighted effective prestress summary from prestress elements.

    This helper uses ``pe_eff_n`` only.  Breaking load and duct diameter are not
    considered effective prestress inputs.  ``tendon_y_from_bottom_mm`` is a
    Pe-weighted centroid in the selected basis coordinates.
    """

    total_pe_eff_kN: float
    tendon_y_from_bottom_mm: float | None
    included_element_count: int
    ignored_element_count: int
    warnings: tuple[str, ...] = ()
    info: tuple[str, ...] = ()


def _require_finite_positive(name: str, value: float) -> None:
    if not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be a positive finite value.")


def _require_finite_nonnegative(name: str, value: float) -> None:
    if not math.isfinite(float(value)) or float(value) < 0.0:
        raise ValueError(f"{name} must be a nonnegative finite value.")


def _stress_type(stress_MPa: float, *, zero_tolerance_MPa: float = 1.0e-9) -> PrestressStressType:
    if abs(float(stress_MPa)) <= zero_tolerance_MPa:
        return "zero"
    return "compression" if stress_MPa < 0.0 else "tension"


def girder_prestress_stress_at_y(
    basis: GirderSectionBasis,
    *,
    Pe_eff_kN: float,
    tendon_y_from_bottom_mm: float,
    y_from_bottom_mm: float,
) -> GirderPrestressFiberStress:
    """Return effective-prestress stress at a y-coordinate on the selected basis.

    ``Pe_eff_kN`` is positive for compressive effective prestress and is assumed
    to already include losses.  The function does not derive ``Pe_eff`` from
    breaking load, strand count, or duct diameter.
    """

    _require_finite_positive("section area", basis.area_mm2)
    _require_finite_positive("section Ix", basis.ix_mm4)
    _require_finite_nonnegative("Pe_eff_kN", Pe_eff_kN)
    if not math.isfinite(float(tendon_y_from_bottom_mm)):
        raise ValueError("tendon_y_from_bottom_mm must be finite.")
    if not math.isfinite(float(y_from_bottom_mm)):
        raise ValueError("y_from_bottom_mm must be finite.")

    Pe_N = float(Pe_eff_kN) * 1000.0
    eccentricity_mm = float(tendon_y_from_bottom_mm) - basis.centroid_y_from_bottom_mm
    equivalent_moment_kNm = float(Pe_eff_kN) * eccentricity_mm / 1000.0
    axial = -Pe_N / basis.area_mm2
    eccentric_bending = equivalent_moment_kNm * 1_000_000.0 * (
        basis.centroid_y_from_bottom_mm - float(y_from_bottom_mm)
    ) / basis.ix_mm4
    total = axial + eccentric_bending
    return GirderPrestressFiberStress(
        location="custom",
        y_from_bottom_mm=float(y_from_bottom_mm),
        axial_stress_MPa=float(axial),
        eccentric_bending_stress_MPa=float(eccentric_bending),
        total_stress_MPa=float(total),
        stress_type=_stress_type(total),
    )


def _with_location(stress: GirderPrestressFiberStress, location: str) -> GirderPrestressFiberStress:
    return GirderPrestressFiberStress(
        location=location,
        y_from_bottom_mm=stress.y_from_bottom_mm,
        axial_stress_MPa=stress.axial_stress_MPa,
        eccentric_bending_stress_MPa=stress.eccentric_bending_stress_MPa,
        total_stress_MPa=stress.total_stress_MPa,
        stress_type=stress.stress_type,
    )


def run_girder_prestress_stress_effect(
    basis: GirderSectionBasis,
    *,
    Pe_eff_kN: float,
    tendon_y_from_bottom_mm: float,
    case_name: str | None = None,
) -> GirderPrestressStressResult:
    """Return top/bottom effective-prestress stress effect for one girder basis."""

    _ = case_name
    warnings: list[str] = list(basis.warnings)
    _require_finite_nonnegative("Pe_eff_kN", Pe_eff_kN)
    if not math.isfinite(float(tendon_y_from_bottom_mm)):
        raise ValueError("tendon_y_from_bottom_mm must be finite.")
    if float(tendon_y_from_bottom_mm) < basis.bottom_fiber_y_from_bottom_mm or float(tendon_y_from_bottom_mm) > basis.top_fiber_y_from_bottom_mm:
        warnings.append(
            "Prestress centroid is outside the selected section basis depth; review tendon coordinates and selected basis."
        )

    top = _with_location(
        girder_prestress_stress_at_y(
            basis,
            Pe_eff_kN=Pe_eff_kN,
            tendon_y_from_bottom_mm=tendon_y_from_bottom_mm,
            y_from_bottom_mm=basis.top_fiber_y_from_bottom_mm,
        ),
        "top",
    )
    bottom = _with_location(
        girder_prestress_stress_at_y(
            basis,
            Pe_eff_kN=Pe_eff_kN,
            tendon_y_from_bottom_mm=tendon_y_from_bottom_mm,
            y_from_bottom_mm=basis.bottom_fiber_y_from_bottom_mm,
        ),
        "bottom",
    )
    eccentricity_mm = float(tendon_y_from_bottom_mm) - basis.centroid_y_from_bottom_mm
    return GirderPrestressStressResult(
        basis_name=basis.basis_name,
        Pe_eff_kN=float(Pe_eff_kN),
        tendon_y_from_bottom_mm=float(tendon_y_from_bottom_mm),
        eccentricity_mm=float(eccentricity_mm),
        equivalent_moment_kNm=float(float(Pe_eff_kN) * eccentricity_mm / 1000.0),
        top=top,
        bottom=bottom,
        warnings=tuple(warnings),
    )


def summarize_girder_prestress_elements(
    prestress_elements: list[PrestressElement],
    *,
    section_bottom_y_mm: float = 0.0,
    include_unbonded: bool = True,
) -> GirderPrestressElementSummary:
    """Return total ``Pe_eff`` and Pe-weighted tendon y-coordinate from elements.

    ``PrestressElement.y_mm`` is assumed to be in the same coordinate system as
    the section geometry.  ``section_bottom_y_mm`` converts it to the selected
    girder-basis coordinate measured upward from the bottom fiber.

    Only ``pe_eff_n`` is used.  This intentionally avoids deriving prestress
    from breaking load, duct diameter, or strand-count metadata.
    """

    if not math.isfinite(float(section_bottom_y_mm)):
        raise ValueError("section_bottom_y_mm must be finite.")

    total_pe_N = 0.0
    weighted_y = 0.0
    included = 0
    ignored = 0
    warnings: list[str] = []
    info: list[str] = []

    for index, element in enumerate(prestress_elements, start=1):
        label = element.label or element.id or f"PS{index}"
        pe_i_N = float(element.pe_eff_n or 0.0) * int(element.count or 1)
        if pe_i_N <= 0.0:
            ignored += 1
            warnings.append(f"Prestress element {label} has no positive Pe_eff and is ignored for girder SLS prestress.")
            continue
        if not element.bonded and not include_unbonded:
            ignored += 1
            warnings.append(f"Unbonded prestress element {label} is ignored by include_unbonded=False.")
            continue
        y_from_bottom = float(element.y_mm) - float(section_bottom_y_mm)
        total_pe_N += pe_i_N
        weighted_y += pe_i_N * y_from_bottom
        included += 1
        info.append(f"Prestress element {label} contributes Pe_eff from pe_eff_n only.")

    if total_pe_N <= 0.0:
        return GirderPrestressElementSummary(
            total_pe_eff_kN=0.0,
            tendon_y_from_bottom_mm=None,
            included_element_count=included,
            ignored_element_count=ignored,
            warnings=tuple(warnings),
            info=tuple(info),
        )

    return GirderPrestressElementSummary(
        total_pe_eff_kN=total_pe_N / 1000.0,
        tendon_y_from_bottom_mm=weighted_y / total_pe_N,
        included_element_count=included,
        ignored_element_count=ignored,
        warnings=tuple(warnings),
        info=tuple(info),
    )


def girder_prestress_stress_result_rows(result: GirderPrestressStressResult) -> list[dict[str, Any]]:
    """Return stable table rows for future UI/report use without importing pandas."""

    return [
        {
            "Fiber": "Top",
            "y from bottom (mm)": result.top.y_from_bottom_mm,
            "Axial prestress (MPa)": result.top.axial_stress_MPa,
            "Eccentric prestress (MPa)": result.top.eccentric_bending_stress_MPa,
            "Total prestress stress (MPa)": result.top.total_stress_MPa,
            "Stress type": result.top.stress_type,
        },
        {
            "Fiber": "Bottom",
            "y from bottom (mm)": result.bottom.y_from_bottom_mm,
            "Axial prestress (MPa)": result.bottom.axial_stress_MPa,
            "Eccentric prestress (MPa)": result.bottom.eccentric_bending_stress_MPa,
            "Total prestress stress (MPa)": result.bottom.total_stress_MPa,
            "Stress type": result.bottom.stress_type,
        },
    ]


def girder_prestress_stress_result_to_dict(result: GirderPrestressStressResult) -> dict[str, Any]:
    """Return a UI/report-friendly dictionary without importing pandas."""

    return {
        "basis_name": result.basis_name,
        "Pe_eff_kN": result.Pe_eff_kN,
        "tendon_y_from_bottom_mm": result.tendon_y_from_bottom_mm,
        "eccentricity_mm": result.eccentricity_mm,
        "equivalent_moment_kNm": result.equivalent_moment_kNm,
        "top_prestress_stress_MPa": result.top.total_stress_MPa,
        "top_stress_type": result.top.stress_type,
        "bottom_prestress_stress_MPa": result.bottom.total_stress_MPa,
        "bottom_stress_type": result.bottom.stress_type,
        "max_compression_MPa": result.max_compression_MPa,
        "max_tension_MPa": result.max_tension_MPa,
        "warnings": list(result.warnings),
    }
