"""Serviceability / SLS preflight assembly."""

from __future__ import annotations

from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.serviceability.loads import get_active_sls_load_cases
from concrete_pmm_pro.serviceability.models import ServiceabilitySettings, ServiceabilitySummary, StressCheckPoint
from concrete_pmm_pro.serviceability.points import merge_default_and_custom_stress_check_points
from concrete_pmm_pro.serviceability.section_properties import compute_gross_section_properties, default_stress_check_points
from concrete_pmm_pro.serviceability.transformed import compute_uncracked_transformed_section_properties


def build_serviceability_summary_from_analysis_input(
    analysis_input: AnalysisInput,
    serviceability_settings: ServiceabilitySettings,
    custom_stress_check_points: list[StressCheckPoint] | None = None,
    include_default_stress_check_points: bool = True,
) -> ServiceabilitySummary:
    """Build serviceability preflight data before optional elastic SLS checks."""

    warnings: list[str] = []
    info: list[str] = []
    section_properties = None
    transformed_section_properties = None
    check_points = []

    try:
        section_properties = compute_gross_section_properties(analysis_input.section_geometry)
        check_points = merge_default_and_custom_stress_check_points(
            default_stress_check_points(section_properties),
            custom_stress_check_points or [],
            include_default_points=include_default_stress_check_points,
        )
        info.append("Gross section properties are available.")
        if not include_default_stress_check_points:
            info.append("Default stress check points are excluded from the serviceability point list.")
        if custom_stress_check_points:
            info.append(f"{len([point for point in custom_stress_check_points if point.active])} active custom stress check point(s) are available.")
        warnings.extend(section_properties.warnings)
        if serviceability_settings.use_transformed_section:
            transformed_section_properties = compute_uncracked_transformed_section_properties(
                section_properties,
                analysis_input.concrete_material,
                analysis_input.rebars,
                analysis_input.rebar_materials,
                analysis_input.prestress_elements,
                analysis_input.prestress_materials,
                serviceability_settings,
            )
            warnings.extend(transformed_section_properties.warnings)
            info.extend(transformed_section_properties.info)
            info.append("Transformed section properties are available.")
            info.append("Uncracked transformed section basis is available for elastic SLS stress checks.")
    except ValueError as exc:
        warnings.append(f"Section properties could not be calculated: {exc}")

    sls_load_cases = get_active_sls_load_cases(analysis_input.load_cases)
    if not sls_load_cases:
        warnings.append("No active SLS load cases are available.")

    if analysis_input.prestress_elements and not serviceability_settings.include_prestress_effective_force:
        warnings.append("Prestress elements exist, but effective prestress contribution is disabled for the elastic SLS stress check.")
    if serviceability_settings.include_prestress_effective_force:
        info.append("Effective prestress force will be included when the elastic SLS stress check is run.")

    warnings.append("Cracked section analysis is not implemented yet.")
    info.append("Gross-section SLS stress calculation is available from the Analysis tab.")
    info.append("Compression is negative and tension is positive for future SLS stress output.")

    return ServiceabilitySummary(
        enabled=serviceability_settings.enabled,
        settings=serviceability_settings,
        section_properties=section_properties,
        gross_section_properties=section_properties,
        check_points=check_points,
        sls_load_cases=sls_load_cases,
        stress_results=[],
        transformed_section_properties=transformed_section_properties,
        warnings=warnings,
        info=info,
    )
