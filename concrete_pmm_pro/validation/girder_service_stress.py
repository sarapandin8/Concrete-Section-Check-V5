"""Validation cases for GIRDER.SLS1A basic girder service-stress helpers."""

from __future__ import annotations

from concrete_pmm_pro.geometry.composite import CompositeDeckInput, calculate_composite_transformed_section
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.serviceability.girder_stress import (
    GirderSectionBasis,
    girder_service_stress_at_y,
    make_girder_basis_from_composite,
    make_girder_basis_from_gross_summary,
    run_basic_girder_service_stress,
)
from concrete_pmm_pro.validation.models import ValidationResult, boolean_validation_result, numeric_validation_result

CATEGORY = "Girder Service Stress"


def validate_rectangular_gross_stress_hand_check() -> list[ValidationResult]:
    """Validate top/bottom fiber stresses against independent closed form."""

    b = 1000.0
    h = 500.0
    area = b * h
    ix = b * h**3 / 12.0
    n_kn = 1000.0
    m_knm = 500.0
    axial = -n_kn * 1000.0 / area
    top_bending = -m_knm * 1_000_000.0 * (h / 2.0) / ix
    bottom_bending = m_knm * 1_000_000.0 * (h / 2.0) / ix

    basis = make_girder_basis_from_gross_summary(summarize_geometry(rectangle(b, h)))
    result = run_basic_girder_service_stress(basis, N_kN=n_kn, M_kNm=m_knm)
    return [
        numeric_validation_result(
            case_id="GIRDER.SLS.RECT.AREA_BASIS",
            category=CATEGORY,
            title="Rectangle gross girder basis area",
            expected=area,
            actual=basis.area_mm2,
            abs_tolerance=1.0e-9,
            units="mm^2",
        ),
        numeric_validation_result(
            case_id="GIRDER.SLS.RECT.TOP",
            category=CATEGORY,
            title="Positive sagging moment gives top compression",
            expected=axial + top_bending,
            actual=result.top.total_stress_MPa,
            abs_tolerance=1.0e-12,
            units="MPa",
            engineering_note="Compression is negative; positive M is sagging.",
        ),
        numeric_validation_result(
            case_id="GIRDER.SLS.RECT.BOTTOM",
            category=CATEGORY,
            title="Positive sagging moment gives bottom tension minus axial compression",
            expected=axial + bottom_bending,
            actual=result.bottom.total_stress_MPa,
            abs_tolerance=1.0e-12,
            units="MPa",
        ),
        boolean_validation_result(
            case_id="GIRDER.SLS.RECT.STRESS_TYPES",
            category=CATEGORY,
            title="Top/bottom stress type classification follows sign convention",
            passed=result.top.stress_type == "compression" and result.bottom.stress_type == "tension",
            expected={"top": "compression", "bottom": "tension"},
            actual={"top": result.top.stress_type, "bottom": result.bottom.stress_type},
        ),
    ]


def validate_hogging_sign_reversal() -> list[ValidationResult]:
    b = 1000.0
    h = 500.0
    m_knm = -500.0
    basis = make_girder_basis_from_gross_summary(summarize_geometry(rectangle(b, h)))
    result = run_basic_girder_service_stress(basis, N_kN=0.0, M_kNm=m_knm)
    return [
        boolean_validation_result(
            case_id="GIRDER.SLS.HOGGING.SIGN",
            category=CATEGORY,
            title="Negative bending reverses top/bottom stress signs",
            passed=result.top.total_stress_MPa > 0.0 and result.bottom.total_stress_MPa < 0.0,
            expected="top tension and bottom compression for negative M",
            actual={"top_MPa": result.top.total_stress_MPa, "bottom_MPa": result.bottom.total_stress_MPa},
        )
    ]


def validate_composite_basis_uses_transformed_properties() -> list[ValidationResult]:
    b = 1000.0
    h = 450.0
    deck = CompositeDeckInput(enabled=True, Tslab_mm=100.0, Be_mm=1000.0, Ebeam_MPa=30000.0, Edeck_MPa=30000.0)
    composite = calculate_composite_transformed_section(summarize_geometry(rectangle(b, h)), deck)
    basis = make_girder_basis_from_composite(composite)
    result = run_basic_girder_service_stress(basis, N_kN=0.0, M_kNm=1000.0)
    return [
        numeric_validation_result(
            case_id="GIRDER.SLS.COMP.AREA",
            category=CATEGORY,
            title="Composite stress basis uses transformed composite area",
            expected=composite.area_mm2,
            actual=basis.area_mm2,
            abs_tolerance=1.0e-9,
            units="mm^2",
        ),
        numeric_validation_result(
            case_id="GIRDER.SLS.COMP.IX",
            category=CATEGORY,
            title="Composite stress basis uses transformed composite Ix",
            expected=composite.ix_mm4,
            actual=basis.ix_mm4,
            abs_tolerance=1.0e-6,
            units="mm^4",
        ),
        boolean_validation_result(
            case_id="GIRDER.SLS.COMP.SAGGING_SIGN",
            category=CATEGORY,
            title="Composite basis preserves sagging sign convention",
            passed=result.top.total_stress_MPa < 0.0 and result.bottom.total_stress_MPa > 0.0,
            expected="top compression and bottom tension",
            actual={"top_MPa": result.top.total_stress_MPa, "bottom_MPa": result.bottom.total_stress_MPa},
        ),
    ]


def validate_point_stress_interpolation() -> list[ValidationResult]:
    basis = GirderSectionBasis(
        basis_name="precast_gross",
        area_mm2=500000.0,
        centroid_y_from_bottom_mm=250.0,
        ix_mm4=10_000_000_000.0,
        top_fiber_y_from_bottom_mm=500.0,
    )
    stress_at_centroid = girder_service_stress_at_y(basis, N_kN=1000.0, M_kNm=500.0, y_from_bottom_mm=250.0)
    return [
        numeric_validation_result(
            case_id="GIRDER.SLS.POINT.CENTROID",
            category=CATEGORY,
            title="Bending stress is zero at centroidal y-coordinate",
            expected=-1000.0 * 1000.0 / basis.area_mm2,
            actual=stress_at_centroid.total_stress_MPa,
            abs_tolerance=1.0e-12,
            units="MPa",
        )
    ]


def validate_girder_service_stress() -> list[ValidationResult]:
    return [
        *validate_rectangular_gross_stress_hand_check(),
        *validate_hogging_sign_reversal(),
        *validate_composite_basis_uses_transformed_properties(),
        *validate_point_stress_interpolation(),
    ]
