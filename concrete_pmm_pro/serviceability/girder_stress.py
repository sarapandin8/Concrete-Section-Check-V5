"""Beam/Girder elastic service-stress helpers.

GIRDER.SLS1A intentionally adds a small, pure-Python stress kernel for future
precast/composite girder workflows.  It does **not** modify PMM, prestress,
rebar, report, load-case, or UI behavior.

Sign convention for this module:
- compression stress is negative
- tension stress is positive
- axial compression ``N_kN`` is positive
- major bending ``M_kNm`` is positive for sagging action
  (top fiber compression, bottom fiber tension)

For a selected section basis:

    sigma(y) = -N/A + M*(yb - y_centroid)/Ix

where ``yb`` is the point coordinate measured from the bottom fiber.  With this
convention a positive sagging moment gives negative stress at the top fiber and
positive stress at the bottom fiber.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from concrete_pmm_pro.geometry.composite import CompositeTransformedSection
from concrete_pmm_pro.geometry.summary import GeometrySummary

SectionBasisName = Literal["precast_gross", "composite_transformed"]
FiberName = Literal["top", "bottom"]
StressType = Literal["compression", "tension", "zero"]


@dataclass(frozen=True)
class GirderSectionBasis:
    """Section basis for one-dimensional girder service stress checks.

    Coordinates are measured upward from the bottom fiber, which is a clearer
    convention for bridge-girder stress reporting than a centroid-centered plot
    coordinate.  The basis can represent either the precast gross section or a
    transformed composite section, but the caller must choose explicitly.
    """

    basis_name: SectionBasisName
    area_mm2: float
    centroid_y_from_bottom_mm: float
    ix_mm4: float
    top_fiber_y_from_bottom_mm: float
    bottom_fiber_y_from_bottom_mm: float = 0.0
    warnings: tuple[str, ...] = ()

    @property
    def total_depth_mm(self) -> float:
        return self.top_fiber_y_from_bottom_mm - self.bottom_fiber_y_from_bottom_mm

    @property
    def c_top_mm(self) -> float:
        return self.top_fiber_y_from_bottom_mm - self.centroid_y_from_bottom_mm

    @property
    def c_bottom_mm(self) -> float:
        return self.centroid_y_from_bottom_mm - self.bottom_fiber_y_from_bottom_mm

    @property
    def z_top_mm3(self) -> float:
        return self.ix_mm4 / self.c_top_mm

    @property
    def z_bottom_mm3(self) -> float:
        return self.ix_mm4 / self.c_bottom_mm


@dataclass(frozen=True)
class GirderFiberStress:
    """Stress result for one named fiber or user-specified y-coordinate."""

    location: str
    y_from_bottom_mm: float
    axial_stress_MPa: float
    bending_stress_MPa: float
    total_stress_MPa: float
    stress_type: StressType


@dataclass(frozen=True)
class GirderServiceStressResult:
    """Top/bottom fiber stress result for one service action case."""

    basis_name: SectionBasisName
    N_kN: float
    M_kNm: float
    top: GirderFiberStress
    bottom: GirderFiberStress
    warnings: tuple[str, ...] = ()

    @property
    def max_compression_MPa(self) -> float:
        """Return the most compressive stress magnitude as a negative value."""

        return min(self.top.total_stress_MPa, self.bottom.total_stress_MPa)

    @property
    def max_tension_MPa(self) -> float:
        """Return the maximum tensile stress as a positive value."""

        return max(self.top.total_stress_MPa, self.bottom.total_stress_MPa)


def _require_finite_positive(name: str, value: float) -> None:
    if not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be a positive finite value.")


def _stress_type(stress_MPa: float, *, zero_tolerance_MPa: float = 1.0e-9) -> StressType:
    if abs(stress_MPa) <= zero_tolerance_MPa:
        return "zero"
    return "compression" if stress_MPa < 0.0 else "tension"


def make_girder_basis_from_gross_summary(summary: GeometrySummary) -> GirderSectionBasis:
    """Build a girder SLS basis from existing precast gross section properties."""

    _require_finite_positive("gross area", float(summary.area_mm2))
    if summary.ix_nmm4 is None:
        raise ValueError("Gross Ix must be available for girder service stress.")
    if summary.y_min_mm is None or summary.y_max_mm is None:
        raise ValueError("Gross top/bottom fiber coordinates are required for girder service stress.")
    _require_finite_positive("gross Ix", float(summary.ix_nmm4))
    bottom = float(summary.y_min_mm)
    top = float(summary.y_max_mm)
    depth = top - bottom
    _require_finite_positive("gross section depth", depth)
    centroid_y_from_bottom = float(summary.centroid_y_mm) - bottom
    return GirderSectionBasis(
        basis_name="precast_gross",
        area_mm2=float(summary.area_mm2),
        centroid_y_from_bottom_mm=centroid_y_from_bottom,
        ix_mm4=float(summary.ix_nmm4),
        top_fiber_y_from_bottom_mm=depth,
        bottom_fiber_y_from_bottom_mm=0.0,
        warnings=(),
    )


def make_girder_basis_from_composite(composite: CompositeTransformedSection) -> GirderSectionBasis:
    """Build a girder SLS basis from transformed composite section properties."""

    if not composite.active:
        raise ValueError("Composite transformed section is not active.")
    _require_finite_positive("composite transformed area", composite.area_mm2)
    _require_finite_positive("composite transformed Ix", composite.ix_mm4)
    _require_finite_positive("composite transformed depth", composite.total_depth_mm)
    return GirderSectionBasis(
        basis_name="composite_transformed",
        area_mm2=float(composite.area_mm2),
        centroid_y_from_bottom_mm=float(composite.centroid_y_from_bottom_mm),
        ix_mm4=float(composite.ix_mm4),
        top_fiber_y_from_bottom_mm=float(composite.total_depth_mm),
        bottom_fiber_y_from_bottom_mm=0.0,
        warnings=tuple(composite.warnings),
    )


def girder_service_stress_at_y(
    basis: GirderSectionBasis,
    *,
    N_kN: float = 0.0,
    M_kNm: float = 0.0,
    y_from_bottom_mm: float,
) -> GirderFiberStress:
    """Return elastic service stress at a y-coordinate on the selected basis.

    ``N_kN`` is positive in compression.  ``M_kNm`` is positive sagging.
    Stresses are reported in MPa with compression negative.
    """

    _require_finite_positive("section area", basis.area_mm2)
    _require_finite_positive("section Ix", basis.ix_mm4)
    if not math.isfinite(float(N_kN)) or not math.isfinite(float(M_kNm)):
        raise ValueError("N_kN and M_kNm must be finite values.")
    if not math.isfinite(float(y_from_bottom_mm)):
        raise ValueError("y_from_bottom_mm must be finite.")

    axial = -float(N_kN) * 1000.0 / basis.area_mm2
    bending = float(M_kNm) * 1_000_000.0 * (basis.centroid_y_from_bottom_mm - float(y_from_bottom_mm)) / basis.ix_mm4
    total = axial + bending
    return GirderFiberStress(
        location="custom",
        y_from_bottom_mm=float(y_from_bottom_mm),
        axial_stress_MPa=float(axial),
        bending_stress_MPa=float(bending),
        total_stress_MPa=float(total),
        stress_type=_stress_type(total),
    )


def _with_location(stress: GirderFiberStress, location: str) -> GirderFiberStress:
    return GirderFiberStress(
        location=location,
        y_from_bottom_mm=stress.y_from_bottom_mm,
        axial_stress_MPa=stress.axial_stress_MPa,
        bending_stress_MPa=stress.bending_stress_MPa,
        total_stress_MPa=stress.total_stress_MPa,
        stress_type=stress.stress_type,
    )


def run_basic_girder_service_stress(
    basis: GirderSectionBasis,
    *,
    N_kN: float = 0.0,
    M_kNm: float = 0.0,
    case_name: str | None = None,
) -> GirderServiceStressResult:
    """Return top and bottom elastic stresses for one girder service action.

    ``case_name`` is accepted for future reporting and intentionally unused in
    the result model in this first milestone to keep the data model minimal.
    """

    _ = case_name
    top = _with_location(
        girder_service_stress_at_y(
            basis,
            N_kN=N_kN,
            M_kNm=M_kNm,
            y_from_bottom_mm=basis.top_fiber_y_from_bottom_mm,
        ),
        "top",
    )
    bottom = _with_location(
        girder_service_stress_at_y(
            basis,
            N_kN=N_kN,
            M_kNm=M_kNm,
            y_from_bottom_mm=basis.bottom_fiber_y_from_bottom_mm,
        ),
        "bottom",
    )
    return GirderServiceStressResult(
        basis_name=basis.basis_name,
        N_kN=float(N_kN),
        M_kNm=float(M_kNm),
        top=top,
        bottom=bottom,
        warnings=basis.warnings,
    )


def girder_service_stress_result_to_dict(result: GirderServiceStressResult) -> dict[str, Any]:
    """Return a UI/report-friendly dictionary without importing pandas."""

    return {
        "basis_name": result.basis_name,
        "N_kN": result.N_kN,
        "M_kNm": result.M_kNm,
        "top_stress_MPa": result.top.total_stress_MPa,
        "top_stress_type": result.top.stress_type,
        "bottom_stress_MPa": result.bottom.total_stress_MPa,
        "bottom_stress_type": result.bottom.stress_type,
        "max_compression_MPa": result.max_compression_MPa,
        "max_tension_MPa": result.max_tension_MPa,
        "warnings": list(result.warnings),
    }
