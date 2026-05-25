"""Elastic SLS concrete stress checks for gross or transformed sections.

Serviceability display convention:
- compression stress is negative
- tension stress is positive

This convention is intentionally separate from the ULS PMM internal force
convention, where compression force is positive.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.serviceability.limits import (
    ServiceabilityLimitSet,
    build_serviceability_limit_set,
    check_service_stress_point,
    summarize_serviceability_results,
)
from concrete_pmm_pro.serviceability.loads import get_active_sls_load_cases
from concrete_pmm_pro.serviceability.models import (
    GrossSectionProperties,
    PrestressServiceContribution,
    ServiceStressPointResult,
    ServiceabilitySettings,
    ServiceabilitySummary,
)
from concrete_pmm_pro.serviceability.prestress import (
    elastic_prestress_stress_gross,
    elastic_prestress_stress_section_basis,
    summarize_effective_prestress_for_sls,
)
from concrete_pmm_pro.serviceability.points import merge_default_and_custom_stress_check_points
from concrete_pmm_pro.serviceability.section_basis import get_serviceability_section_basis
from concrete_pmm_pro.serviceability.section_properties import compute_gross_section_properties, default_stress_check_points
from concrete_pmm_pro.serviceability.transformed import compute_uncracked_transformed_section_properties

NEAR_ZERO_STRESS_MPA = 1.0e-9


def elastic_concrete_stress_gross(
    Pu_N: float,
    Mux_Nmm: float,
    Muy_Nmm: float,
    x_mm: float,
    y_mm: float,
    props: GrossSectionProperties,
) -> float:
    """Return gross-section elastic concrete stress in MPa.

    Coordinates are measured from the section model origin, then shifted to
    centroidal coordinates. Compression is displayed as negative and tension
    as positive:

    sigma = -Pu/A + Mux*dy/Ix + Muy*dx/Iy

    The current gross SLS check intentionally ignores Ixy coupling;
    unsymmetric bending is a future refinement.
    """

    return elastic_concrete_stress_section_basis(
        Pu_N=Pu_N,
        Mux_Nmm=Mux_Nmm,
        Muy_Nmm=Muy_Nmm,
        x_mm=x_mm,
        y_mm=y_mm,
        area_mm2=props.area_mm2,
        centroid_x_mm=props.centroid_x_mm,
        centroid_y_mm=props.centroid_y_mm,
        Ix_mm4=props.Ix_mm4,
        Iy_mm4=props.Iy_mm4,
        Ixy_mm4=props.Ixy_mm4,
    )


def elastic_concrete_stress_section_basis(
    Pu_N: float,
    Mux_Nmm: float,
    Muy_Nmm: float,
    x_mm: float,
    y_mm: float,
    area_mm2: float,
    centroid_x_mm: float,
    centroid_y_mm: float,
    Ix_mm4: float,
    Iy_mm4: float,
    Ixy_mm4: float = 0.0,
) -> float:
    """Return elastic concrete stress for the selected section basis.

    The current SLS convention displays compression as negative and tension as
    positive. Ixy is accepted for metadata/warnings, but the current
    formula intentionally uses the simplified uncoupled Ix/Iy expression.
    """

    _ = Ixy_mm4
    dx = x_mm - centroid_x_mm
    dy = y_mm - centroid_y_mm
    return -Pu_N / area_mm2 + Mux_Nmm * dy / Ix_mm4 + Muy_Nmm * dx / Iy_mm4


def elastic_concrete_stress_gross_with_prestress(
    Pu_N: float,
    Mux_Nmm: float,
    Muy_Nmm: float,
    x_mm: float,
    y_mm: float,
    props: GrossSectionProperties,
    prestress_contribution: PrestressServiceContribution | None = None,
) -> dict[str, float]:
    """Return external, effective prestress, and total gross concrete stress.

    Compression stress is negative and tension stress is positive.
    """

    external_stress = elastic_concrete_stress_gross(Pu_N, Mux_Nmm, Muy_Nmm, x_mm, y_mm, props)
    prestress_stress = (
        elastic_prestress_stress_gross(x_mm, y_mm, props, prestress_contribution)
        if prestress_contribution is not None
        else 0.0
    )
    return {
        "external_stress_MPa": external_stress,
        "prestress_stress_MPa": prestress_stress,
        "total_stress_MPa": external_stress + prestress_stress,
    }


def elastic_concrete_stress_section_basis_with_prestress(
    Pu_N: float,
    Mux_Nmm: float,
    Muy_Nmm: float,
    x_mm: float,
    y_mm: float,
    area_mm2: float,
    centroid_x_mm: float,
    centroid_y_mm: float,
    Ix_mm4: float,
    Iy_mm4: float,
    Ixy_mm4: float = 0.0,
    prestress_contribution: PrestressServiceContribution | None = None,
) -> dict[str, float]:
    """Return external, effective prestress, and total stress for a basis."""

    external_stress = elastic_concrete_stress_section_basis(
        Pu_N=Pu_N,
        Mux_Nmm=Mux_Nmm,
        Muy_Nmm=Muy_Nmm,
        x_mm=x_mm,
        y_mm=y_mm,
        area_mm2=area_mm2,
        centroid_x_mm=centroid_x_mm,
        centroid_y_mm=centroid_y_mm,
        Ix_mm4=Ix_mm4,
        Iy_mm4=Iy_mm4,
        Ixy_mm4=Ixy_mm4,
    )
    prestress_stress = (
        elastic_prestress_stress_section_basis(
            x_mm=x_mm,
            y_mm=y_mm,
            area_mm2=area_mm2,
            centroid_x_mm=centroid_x_mm,
            centroid_y_mm=centroid_y_mm,
            Ix_mm4=Ix_mm4,
            Iy_mm4=Iy_mm4,
            contribution=prestress_contribution,
        )
        if prestress_contribution is not None
        else 0.0
    )
    return {
        "external_stress_MPa": external_stress,
        "prestress_stress_MPa": prestress_stress,
        "total_stress_MPa": external_stress + prestress_stress,
    }


def service_stress_limits(fc_MPa: float, settings: ServiceabilitySettings) -> dict[str, float | bool]:
    """Return concrete service stress limits in MPa."""

    limits = build_serviceability_limit_set(fc_MPa, settings)
    return {
        "compression_limit_MPa": limits.compression_limit_MPa,
        "tension_limit_MPa": limits.tension_limit_MPa,
        "allow_tension": limits.allow_tension,
        "no_tension_check": limits.no_tension_required,
        "decompression_check": limits.decompression_required,
    }


def check_concrete_stress_status(
    stress_MPa: float,
    compression_limit_MPa: float,
    tension_limit_MPa: float,
    allow_tension: bool = True,
) -> tuple[str, str]:
    """Classify a concrete service stress result."""

    limits = ServiceabilityLimitSet(
        compression_limit_MPa=compression_limit_MPa,
        tension_limit_MPa=max(tension_limit_MPa, 0.0),
        allow_tension=allow_tension,
        no_tension_required=not allow_tension or tension_limit_MPa <= 0,
        decompression_required=False,
        stress_zero_tolerance_MPa=NEAR_ZERO_STRESS_MPA,
    )
    status, message, _utilization, _stress_type = check_service_stress_point(stress_MPa, limits)
    return status, message


def _stress_type(stress_MPa: float) -> str:
    if abs(stress_MPa) <= NEAR_ZERO_STRESS_MPA:
        return "Zero"
    return "Compression" if stress_MPa < 0 else "Tension"


def _stress_limit_and_utilization(
    stress_MPa: float,
    compression_limit_MPa: float,
    tension_limit_MPa: float,
    allow_tension: bool,
) -> tuple[float | None, float | None]:
    if abs(stress_MPa) <= NEAR_ZERO_STRESS_MPA:
        return None, 0.0
    if stress_MPa < 0:
        return compression_limit_MPa, abs(stress_MPa) / compression_limit_MPa if compression_limit_MPa > 0 else None
    if not allow_tension or tension_limit_MPa <= 0:
        return tension_limit_MPa, None
    return tension_limit_MPa, stress_MPa / tension_limit_MPa


def _limit_for_stress_type(stress_type: str, limits: ServiceabilityLimitSet) -> float | None:
    if stress_type == "Compression":
        return limits.compression_limit_MPa
    if stress_type == "Tension":
        return limits.tension_limit_MPa
    return None


def _filtered_stress_check_points(
    check_points: list,
    settings: ServiceabilitySettings,
) -> list:
    if settings.critical_point_filter == "extreme_fibers_only":
        return [point for point in check_points if point.point_type == "extreme_fiber"]
    return check_points


def _i_xy_warning_needed(props: GrossSectionProperties) -> bool:
    reference = math.sqrt(props.Ix_mm4 * props.Iy_mm4)
    if reference <= 0:
        return False
    return abs(props.Ixy_mm4) > 1.0e-6 * reference


def _summary_status(results: list[ServiceStressPointResult]) -> str:
    if not results:
        return "NOT_CHECKED"
    if any(result.status == "FAIL" for result in results):
        return "FAIL"
    return "PASS"


def _summary_metrics(results: list[ServiceStressPointResult]) -> dict[str, Any]:
    max_compression = None
    max_tension = None
    max_utilization = None
    governing_combo = None
    governing_point = None
    for result in results:
        if result.stress_MPa is None:
            continue
        if result.stress_MPa < 0:
            compression = abs(result.stress_MPa)
            max_compression = compression if max_compression is None else max(max_compression, compression)
        elif result.stress_MPa > 0:
            max_tension = result.stress_MPa if max_tension is None else max(max_tension, result.stress_MPa)

        governs = False
        if result.utilization is not None:
            if max_utilization is None or result.utilization > max_utilization:
                governs = True
        elif result.status == "FAIL" and max_utilization is None:
            governs = True
        if governs:
            max_utilization = result.utilization
            governing_combo = result.combo_name
            governing_point = result.point_name
    return {
        "max_compression_MPa": max_compression,
        "max_tension_MPa": max_tension,
        "max_utilization": max_utilization,
        "governing_combo": governing_combo,
        "governing_point": governing_point,
    }


def run_elastic_sls_stress_check(
    analysis_input: AnalysisInput,
    serviceability_settings: ServiceabilitySettings,
    custom_stress_check_points: list | None = None,
    include_default_stress_check_points: bool = True,
) -> ServiceabilitySummary:
    """Run elastic SLS stress checks using gross or uncracked transformed basis."""

    warnings: list[str] = ["Compression is negative and tension is positive in SLS stress results."]
    info: list[str] = []
    gross_section_properties = compute_gross_section_properties(analysis_input.section_geometry)
    warnings.extend(gross_section_properties.warnings)

    transformed_section_properties = None
    if serviceability_settings.use_transformed_section:
        transformed_section_properties = compute_uncracked_transformed_section_properties(
            gross_section_properties,
            analysis_input.concrete_material,
            analysis_input.rebars,
            analysis_input.rebar_materials,
            analysis_input.prestress_elements,
            analysis_input.prestress_materials,
            serviceability_settings,
        )
        warnings.extend(transformed_section_properties.warnings)
        info.extend(transformed_section_properties.info)

    basis = get_serviceability_section_basis(gross_section_properties, transformed_section_properties, serviceability_settings)
    basis_name = str(basis["basis_name"])
    area_mm2 = float(basis["area_mm2"])
    centroid_x_mm = float(basis["centroid_x_mm"])
    centroid_y_mm = float(basis["centroid_y_mm"])
    ix_mm4 = float(basis["Ix_mm4"])
    iy_mm4 = float(basis["Iy_mm4"])
    ixy_mm4 = float(basis["Ixy_mm4"])
    warnings.extend(list(basis["warnings"]))
    info.extend(list(basis["info"]))
    if basis_name == "gross":
        warnings.append("Gross section stress check.")
    else:
        warnings.append("Transformed section stress check is uncracked only. Cracked section analysis is future work.")

    prestress_contribution = None
    if serviceability_settings.include_prestress_effective_force:
        prestress_contribution = summarize_effective_prestress_for_sls(
            analysis_input.prestress_elements,
            include_unbonded=False,
            centroid_x_mm=centroid_x_mm,
            centroid_y_mm=centroid_y_mm,
            Ix_mm4=ix_mm4,
            Iy_mm4=iy_mm4,
            Ixy_mm4=ixy_mm4,
            basis_name=basis_name,
        )
        warnings.extend(prestress_contribution.warnings)
        info.extend(prestress_contribution.info)
        warnings.append("Prestress effective force contribution uses the selected section basis.")
        warnings.append("Prestress losses are not calculated in this SLS check; existing effective values are used.")
    elif analysis_input.prestress_elements:
        warnings.append("Prestress elements are present but effective prestress force contribution is disabled.")

    default_points = default_stress_check_points(gross_section_properties)
    check_points = merge_default_and_custom_stress_check_points(
        default_points,
        custom_stress_check_points or [],
        include_default_points=include_default_stress_check_points,
    )
    if serviceability_settings.critical_point_filter == "extreme_fibers_only":
        info.append("Critical point filter is extreme_fibers_only; only extreme-fiber points govern summary results.")
    if not include_default_stress_check_points:
        info.append("Default stress check points are excluded from this SLS stress check.")
    sls_load_cases = get_active_sls_load_cases(analysis_input.load_cases)
    if not sls_load_cases:
        warnings.append("No active SLS load cases are available.")

    limits = build_serviceability_limit_set(analysis_input.concrete_material.fc_MPa, serviceability_settings)
    warnings.extend(limits.warnings)
    info.extend(limits.info)
    stress_results: list[ServiceStressPointResult] = []
    for load_case in sls_load_cases:
        for point in check_points:
            stress_parts = elastic_concrete_stress_section_basis_with_prestress(
                Pu_N=load_case.Pu_N,
                Mux_Nmm=load_case.Mux_Nmm,
                Muy_Nmm=load_case.Muy_Nmm,
                x_mm=point.x_mm,
                y_mm=point.y_mm,
                area_mm2=area_mm2,
                centroid_x_mm=centroid_x_mm,
                centroid_y_mm=centroid_y_mm,
                Ix_mm4=ix_mm4,
                Iy_mm4=iy_mm4,
                Ixy_mm4=ixy_mm4,
                prestress_contribution=prestress_contribution,
            )
            stress = stress_parts["total_stress_MPa"]
            status, message, utilization, stress_type = check_service_stress_point(stress, limits)
            limit = _limit_for_stress_type(stress_type, limits)
            stress_results.append(
                ServiceStressPointResult(
                    combo_name=load_case.name,
                    point_name=point.name,
                    x_mm=point.x_mm,
                    y_mm=point.y_mm,
                    section_basis=basis_name,
                    section_area_mm2=area_mm2,
                    section_centroid_x_mm=centroid_x_mm,
                    section_centroid_y_mm=centroid_y_mm,
                    point_type=point.point_type,
                    point_source=point.source,
                    include_in_governing=point.include_in_governing,
                    external_stress_MPa=stress_parts["external_stress_MPa"],
                    prestress_stress_MPa=stress_parts["prestress_stress_MPa"],
                    total_stress_MPa=stress,
                    stress_MPa=stress,
                    limit_MPa=limit,
                    utilization=utilization,
                    stress_type=stress_type,
                    status=status,
                    message=message,
                )
            )

    metrics = summarize_serviceability_results(stress_results, serviceability_settings.critical_point_filter)
    info.append(f"Checked {len(sls_load_cases)} active SLS load case(s) at {len(check_points)} stress point(s).")
    return ServiceabilitySummary(
        enabled=serviceability_settings.enabled,
        settings=serviceability_settings,
        section_properties=gross_section_properties,
        gross_section_properties=gross_section_properties,
        section_basis_used=basis_name,
        check_points=check_points,
        sls_load_cases=sls_load_cases,
        stress_results=stress_results,
        transformed_section_properties=transformed_section_properties,
        prestress_contribution=prestress_contribution,
        prestress_included=prestress_contribution is not None and prestress_contribution.total_pe_eff_N > 0.0,
        bonded_prestress_count=0 if prestress_contribution is None else prestress_contribution.bonded_count,
        unbonded_prestress_ignored_count=0 if prestress_contribution is None else prestress_contribution.unbonded_ignored_count,
        total_pe_eff_N=0.0 if prestress_contribution is None else prestress_contribution.total_pe_eff_N,
        Mpe_x_Nmm=0.0 if prestress_contribution is None else prestress_contribution.Mpe_x_Nmm,
        Mpe_y_Nmm=0.0 if prestress_contribution is None else prestress_contribution.Mpe_y_Nmm,
        overall_status=str(metrics["overall_status"]),
        max_compression_MPa=metrics["max_compression_MPa"],
        max_tension_MPa=metrics["max_tension_MPa"],
        governing_combo=metrics["governing_combo"],
        governing_point=metrics["governing_point"],
        max_utilization=metrics["max_utilization"],
        governing_status=metrics["governing_status"],
        no_tension_violation_count=int(metrics["no_tension_violation_count"]),
        decompression_violation_count=int(metrics["decompression_violation_count"]),
        compression_failure_count=int(metrics["compression_failure_count"]),
        tension_failure_count=int(metrics["tension_failure_count"]),
        pass_count=int(metrics["pass_count"]),
        fail_count=int(metrics["fail_count"]),
        warning_count=int(metrics["warning_count"]),
        warnings=warnings,
        info=info,
    )


def run_gross_section_sls_stress_check(
    analysis_input: AnalysisInput,
    serviceability_settings: ServiceabilitySettings,
) -> ServiceabilitySummary:
    """Backward-compatible wrapper for the elastic SLS stress check runner."""

    return run_elastic_sls_stress_check(analysis_input, serviceability_settings)


def service_stress_results_to_dataframe(summary: ServiceabilitySummary) -> pd.DataFrame:
    """Return SLS stress results as a display/export dataframe."""

    rows = []
    for result in summary.stress_results:
        stress = result.stress_MPa
        rows.append(
            {
                "Combo": result.combo_name,
                "Point": result.point_name,
                "x_mm": result.x_mm,
                "y_mm": result.y_mm,
                "Section Basis": result.section_basis,
                "Section Area_mm2": result.section_area_mm2,
                "Section cx_mm": result.section_centroid_x_mm,
                "Section cy_mm": result.section_centroid_y_mm,
                "Point Type": result.point_type,
                "Source": result.point_source,
                "Include in Governing": result.include_in_governing,
                "External Stress_MPa": result.external_stress_MPa,
                "Prestress Stress_MPa": result.prestress_stress_MPa,
                "Total Stress_MPa": result.total_stress_MPa,
                "Stress_MPa": stress,
                "Stress Type": result.stress_type or ("Not checked" if stress is None else _stress_type(stress)),
                "Limit_MPa": result.limit_MPa,
                "Utilization": result.utilization,
                "Status": result.status,
                "Message": result.message,
            }
        )
    return pd.DataFrame(rows)
