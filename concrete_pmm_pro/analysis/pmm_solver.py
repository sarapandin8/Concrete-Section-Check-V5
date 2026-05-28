"""RC PMM solver prototype.

Prototype scope:
- Concrete + ordinary rebar.
- Bonded prestress elements are included when analysis settings request them.
- Unbonded prestress elements are ignored with a clear warning.
- ACI-style maximum axial strength cap is applied for axial compression display/checks.
- Ordinary rebar inside the Whitney compression block can subtract displaced
  concrete stress to avoid double counting compression block stress.
- No serviceability checks are performed.

Sign convention:
- Internal units are mm, MPa (= N/mm^2), N, and N-mm.
- Concrete and steel compression forces are positive.
- Steel and bonded prestress tension forces are negative.
- Active prestress stress is handled as a tensile stress magnitude.
  eps_ps,total = eps_pe - eps_section because positive section compression
  reduces tendon tensile strain and section tension increases it. The tensile
  strain is clamped from 0 before stress calculation, capped at fpu, then
  converted to a tension-negative section force. Compression reversal is not
  modeled yet for active prestress.
- Passive prestressing steel rows (Pe_eff/initial stress/initial strain = 0)
  are treated as bonded high-strength steel using ordinary strain
  compatibility with symmetric tension/compression force signs. They do not
  use active-prestress compression-reversal warnings.
- x-axis is positive to the right; y-axis is positive upward.
- Mnx is nominal moment about x: sum(F * (y - y_ref)).
- Mny is nominal moment about y: sum(F * (x - x_ref)).
"""

from __future__ import annotations

import math
from typing import Iterable

from concrete_pmm_pro.analysis.result_models import PMMPoint, PMMSolverResult
from concrete_pmm_pro.analysis.prestress_stress import (
    PRESTRESS_COMPRESSION_REVERSAL_WARNING,
    PRESTRESS_FPU_CAP_WARNING,
    PRESTRESS_LINEAR_CAP_FALLBACK_WARNING,
    prestress_stress_mpa,
    prestress_total_tensile_strain,
)
from concrete_pmm_pro.analysis.strain_compatibility import (
    compression_block_polygon,
    is_point_inside_compression_block,
    projection_frame,
    rebar_net_force_n,
    steel_strain_at_point,
)
from concrete_pmm_pro.analysis.warnings import (
    BONDED_PRESTRESS_PROTOTYPE_WARNING,
    RC_AXIAL_CAP_LIMITATION_WARNING,
    UNBONDED_PRESTRESS_IGNORED_WARNING,
    deduplicate_warnings,
)
from concrete_pmm_pro.code_checks import aci_beta1, aci_max_phiPn, aci_phi_and_strain_condition, nominal_po_rc_prestressed
from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.core.models import PrestressElement, Rebar, RebarMaterial
from concrete_pmm_pro.geometry.summary import to_shapely_polygon


def _angle_values(count: int) -> list[float]:
    return [2.0 * math.pi * index / count for index in range(count)]


def _depth_values(projected_depth_mm: float, count: int) -> list[float]:
    c_min, c_max = neutral_axis_depth_range(projected_depth_mm)
    if count == 1:
        return [c_max]
    step = (c_max - c_min) / (count - 1)
    return [c_min + step * index for index in range(count)]


def neutral_axis_depth_range(projected_depth_mm: float) -> tuple[float, float]:
    """Return robust neutral-axis sweep bounds for a projected section depth."""

    projected_depth = max(float(projected_depth_mm), 0.0)
    c_min = max(1.0, 0.001 * projected_depth)
    c_max = max(c_min, 5.0 * projected_depth)
    return c_min, c_max


def _rebar_material_for(rebar: Rebar, materials: Iterable[RebarMaterial]) -> RebarMaterial:
    material_list = list(materials)
    for material in material_list:
        if material.name == rebar.material_name:
            return material
    if material_list:
        return material_list[0]
    return RebarMaterial(name="Default", fy_MPa=400.0, Es_MPa=200000.0)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _element_label(element: PrestressElement) -> str:
    return element.label or element.material_name or element.id


def _prestress_phi_yield_reference_mpa(element: PrestressElement) -> float:
    """Return a yield/proof stress reference for phi strain transition.

    The phi calculation needs an eps_y reference for the element controlling
    net tensile strain. Prestressing rows normally provide fpy/proof stress;
    when missing, use a conservative high-strength reference rather than
    ordinary rebar defaults.
    """

    if element.fpy_mpa is not None:
        return float(element.fpy_mpa)
    if element.fpu_mpa is not None:
        return 0.9 * float(element.fpu_mpa)
    return 1670.0


def _has_active_prestress(element: PrestressElement) -> bool:
    """Return True when a bonded prestress row has nonzero initial prestress.

    Passive mode in the UI intentionally creates bonded high-strength steel
    rows with Pe_eff/fpe/initial_strain equal to zero. Those rows should still
    contribute to PMM strength through strain compatibility, but they should
    not trigger active-prestress model warnings such as compression reversal.
    """

    if element.initial_strain is not None and abs(float(element.initial_strain)) > 1.0e-12:
        return True
    if element.initial_stress_mpa is not None and float(element.initial_stress_mpa) > 1.0e-9:
        return True
    return float(element.pe_eff_n or 0.0) > 1.0e-6


def _initial_prestress_strain(element: PrestressElement, warnings: list[str]) -> float:
    if element.initial_strain is not None:
        return float(element.initial_strain)
    if element.initial_stress_mpa is not None:
        return element.initial_stress_mpa / element.ep_mpa
    if element.pe_eff_n > 0.0 and element.area_mm2 > 0.0:
        return (element.pe_eff_n / element.area_mm2) / element.ep_mpa
    return 0.0


def _passive_prestress_strength_reference_mpa(element: PrestressElement) -> float:
    """Return a symmetric passive-steel stress cap for prestressing steel rows."""

    if element.fpy_mpa is not None:
        return float(element.fpy_mpa)
    if element.fpu_mpa is not None:
        return 0.9 * float(element.fpu_mpa)
    # Last-resort value is only used for incomplete custom rows; validation
    # should normally ensure fpy/fpu are present.
    return 1670.0


def passive_prestress_steel_stress_mpa(element: PrestressElement, section_strain: float) -> float:
    """Return signed passive high-strength steel stress in MPa.

    Section strain follows the app convention: compression positive, tension
    negative. Passive prestressing steel follows the same sign convention as
    ordinary rebar, capped symmetrically at a proof/yield reference.
    """

    cap = _passive_prestress_strength_reference_mpa(element)
    return _clamp(element.ep_mpa * section_strain, -cap, cap)


def prestress_tensile_stress_mpa(
    element: PrestressElement,
    initial_strain: float,
    section_strain: float,
    model: str = "bilinear",
) -> float:
    """Return prototype prestress tensile stress magnitude in MPa.

    TODO: Compression reversal of prestressing steel is future work.
    """

    fpu = element.fpu_mpa if element.fpu_mpa is not None else 1.0e12
    total_tensile_strain = prestress_total_tensile_strain(initial_strain, section_strain)
    fps, _warnings = prestress_stress_mpa(total_tensile_strain, element.ep_mpa, fpu, element.fpy_mpa, model)
    return fps


def run_pmm_solver(analysis_input: AnalysisInput) -> PMMSolverResult:
    """Run the current PMM prototype implementation."""

    return run_rc_pmm_solver(analysis_input)


def run_rc_pmm_solver(analysis_input: AnalysisInput) -> PMMSolverResult:
    """Run a prototype RC PMM sweep using `AnalysisInput`.

    The function deliberately avoids any Streamlit dependency. Future solver
    milestones should continue to use typed analysis input models.
    """

    warnings: list[str] = []
    info: list[str] = []
    settings = analysis_input.settings
    prestress_stress_model = settings.prestress_stress_model
    concrete = analysis_input.concrete_material
    section_polygon = to_shapely_polygon(analysis_input.section_geometry)
    gross_centroid = section_polygon.centroid
    x_ref = float(gross_centroid.x)
    y_ref = float(gross_centroid.y)

    rebars = analysis_input.rebars if settings.include_rebars else []
    if not settings.include_rebars and analysis_input.rebars:
        warnings.append("Rebars are present but excluded by analysis settings.")

    all_prestress_elements = list(analysis_input.prestress_elements)
    bonded_prestress_elements: list[PrestressElement] = []
    unbonded_prestress_elements: list[PrestressElement] = []
    prestress_initial_strains: dict[str, float] = {}
    if settings.include_prestress:
        bonded_prestress_elements = [element for element in all_prestress_elements if element.bonded]
        unbonded_prestress_elements = [element for element in all_prestress_elements if not element.bonded]
        active_prestress_elements = [element for element in bonded_prestress_elements if _has_active_prestress(element)]
        passive_prestress_elements = [element for element in bonded_prestress_elements if not _has_active_prestress(element)]
        if active_prestress_elements:
            warnings.append(BONDED_PRESTRESS_PROTOTYPE_WARNING)
            warnings.append(
                f"Active prestress stress model: {prestress_stress_model}. Stress uses initial tensile strain minus "
                "section strain, is clamped from 0, capped at fpu, and converted to a tension-negative section force."
            )
            if prestress_stress_model == "bilinear":
                warnings.append("Bilinear active-prestress model uses fpy/proof stress when available with a prototype post-yield slope.")
        if passive_prestress_elements:
            info.append(
                "Passive bonded prestressing steel is included as high-strength steel using strain compatibility; "
                "no initial prestress force is applied."
            )
        if bonded_prestress_elements:
            for element in active_prestress_elements:
                if element.fpu_mpa is None:
                    warnings.append(f"Active prestress element {_element_label(element)} is missing fpu_mpa and is skipped in stress calculation.")
                if element.steel_type == "prestressing_bar" and element.fpy_mpa is None:
                    warnings.append(f"Prestressing_bar / PT Bar {_element_label(element)} is missing fpy/proof stress.")
            for element in passive_prestress_elements:
                if element.fpy_mpa is None and element.fpu_mpa is None:
                    warnings.append(
                        f"Passive prestressing steel {_element_label(element)} is missing fpy/fpu; "
                        "using a default high-strength stress cap for PMM review."
                    )
            warnings.append(RC_AXIAL_CAP_LIMITATION_WARNING)
        if unbonded_prestress_elements:
            warnings.append(UNBONDED_PRESTRESS_IGNORED_WARNING)
        for element in bonded_prestress_elements:
            prestress_initial_strains[element.id] = _initial_prestress_strain(element, warnings)
    elif all_prestress_elements:
        warnings.append("Prestress elements are present but excluded by analysis settings.")

    fc_MPa = concrete.fc_MPa
    ecu = concrete.ecu
    beta1 = concrete.beta1 if concrete.beta1 is not None else aci_beta1(fc_MPa)
    concrete_stress_MPa = 0.85 * fc_MPa
    transverse_reinforcement = settings.transverse_reinforcement
    default_rebar_material = analysis_input.rebar_materials[0] if analysis_input.rebar_materials else RebarMaterial(name="Default", fy_MPa=400.0)
    phi_compression = 1.0
    if settings.use_phi_factor:
        phi_compression = 0.75 if transverse_reinforcement == "spiral" else 0.65
    phiPn_max: float | None = None
    try:
        Po_N = nominal_po_rc_prestressed(
            fc_MPa,
            float(section_polygon.area),
            rebars,
            default_rebar_material,
            bonded_prestress_elements,
        )
        phiPn_max = aci_max_phiPn(Po_N, phi_compression, transverse_reinforcement)
        info.append(
            "ACI maximum axial strength cap is applied to axial compression display/checks. "
            "Moment capacity interpolation remains prototype."
        )
        info.append(f"Prototype nominal Po including bonded prestress steel = {Po_N:,.1f} N; capped max phiPn = {phiPn_max:,.1f} N.")
    except ValueError as exc:
        warnings.append(f"ACI axial cap could not be calculated: {exc}")

    strength_load_count = sum(
        1
        for load_case in analysis_input.load_cases
        if load_case.active and load_case.load_type == settings.strength_load_type
    )
    info.append(f"RC PMM prototype using {len(rebars)} ordinary rebar object(s).")
    bonded_prestress_count = sum(element.count for element in bonded_prestress_elements)
    unbonded_prestress_ignored_count = sum(element.count for element in unbonded_prestress_elements)
    active_bonded_prestress_count = sum(element.count for element in bonded_prestress_elements if _has_active_prestress(element))
    passive_bonded_prestress_count = bonded_prestress_count - active_bonded_prestress_count
    total_prestress_pe_eff = sum(element.pe_eff_n * element.count for element in bonded_prestress_elements)
    total_prestress_area = sum(element.area_mm2 * element.count for element in bonded_prestress_elements)
    info.append(f"Bonded prestress included: {bonded_prestress_count} element count(s).")
    info.append(f"Active prestress count: {active_bonded_prestress_count}; passive prestressing steel count: {passive_bonded_prestress_count}.")
    info.append(f"Unbonded prestress ignored: {unbonded_prestress_ignored_count} element count(s).")
    info.append(f"Included prestress Aps = {total_prestress_area:,.1f} mm^2; Pe_eff = {total_prestress_pe_eff:,.1f} N.")
    info.append(f"Strength load cases stored for future checks: {strength_load_count}.")
    if settings.subtract_rebar_displaced_concrete:
        info.append("Ordinary rebar inside the compression block uses net force As(fs - 0.85f'c).")
    else:
        warnings.append("Displaced concrete at ordinary rebar locations is not subtracted. Compression capacity may be overestimated.")
    info.append("Neutral-axis c_min uses relative lower bound for numerical robustness.")

    points: list[PMMPoint] = []
    for theta in _angle_values(settings.neutral_axis_angle_steps):
        frame = projection_frame(section_polygon, theta)
        for c_mm in _depth_values(frame.projected_depth_mm, settings.neutral_axis_depth_steps):
            block_depth_mm = beta1 * c_mm
            compression_region = compression_block_polygon(section_polygon, frame, block_depth_mm)
            concrete_area = max(0.0, float(compression_region.area))
            concrete_force = concrete_stress_MPa * concrete_area

            Pn = concrete_force
            if concrete_area > 0.0:
                concrete_centroid = compression_region.centroid
                Mnx = concrete_force * (float(concrete_centroid.y) - y_ref)
                Mny = concrete_force * (float(concrete_centroid.x) - x_ref)
            else:
                Mnx = 0.0
                Mny = 0.0

            eps_t: float | None = None
            eps_t_fy = 420.0
            eps_t_es = 200000.0
            rebar_displaced_concrete_subtracted = 0.0
            rebar_inside_compression_count = 0
            for rebar in rebars:
                material = _rebar_material_for(rebar, analysis_input.rebar_materials)
                eps_s = steel_strain_at_point(rebar.x_mm, rebar.y_mm, frame, c_mm, ecu)
                fs = _clamp(material.Es_MPa * eps_s, -material.fy_MPa, material.fy_MPa)
                inside_compression = is_point_inside_compression_block(rebar.x_mm, rebar.y_mm, compression_region)
                force, rebar_force_metadata = rebar_net_force_n(
                    rebar.area_mm2,
                    fs,
                    fc_MPa,
                    inside_compression,
                    settings.subtract_rebar_displaced_concrete,
                )
                if inside_compression:
                    rebar_inside_compression_count += 1
                rebar_displaced_concrete_subtracted += rebar.area_mm2 * float(
                    rebar_force_metadata["concrete_stress_subtracted_MPa"]
                )
                Pn += force
                Mnx += force * (rebar.y_mm - y_ref)
                Mny += force * (rebar.x_mm - x_ref)

                if eps_s < 0.0:
                    tensile_strain = -eps_s
                    if eps_t is None or tensile_strain > eps_t:
                        eps_t = tensile_strain
                        eps_t_fy = material.fy_MPa
                        eps_t_es = material.Es_MPa

            prestress_force = 0.0
            point_stress_warnings: list[str] = []
            point_max_prestress_stress = 0.0
            point_fpu_cap_count = 0
            point_compression_reversal_count = 0
            for element in bonded_prestress_elements:
                eps_section = steel_strain_at_point(element.x_mm, element.y_mm, frame, c_mm, ecu)
                if _has_active_prestress(element):
                    if element.fpu_mpa is None:
                        continue
                    total_tensile_strain = prestress_total_tensile_strain(prestress_initial_strains[element.id], eps_section)
                    try:
                        fps, stress_warnings = prestress_stress_mpa(
                            total_tensile_strain,
                            element.ep_mpa,
                            element.fpu_mpa,
                            element.fpy_mpa,
                            prestress_stress_model,
                        )
                    except ValueError as exc:
                        warnings.append(f"Active prestress element {_element_label(element)} stress calculation error: {exc}")
                        fps = 0.0
                        stress_warnings = []
                    # Reaching fpu is an expected material cap in some ultimate
                    # PMM failure states.  Keep it as per-point metadata for
                    # QA/governing-region checks, but do not emit it as a
                    # global engineering warning by itself.  Compression
                    # reversal and model fallback remain review warnings.
                    actionable_stress_warnings = [
                        stress_warning
                        for stress_warning in stress_warnings
                        if stress_warning != PRESTRESS_FPU_CAP_WARNING
                    ]
                    if actionable_stress_warnings:
                        point_stress_warnings.extend(actionable_stress_warnings)
                        for stress_warning in actionable_stress_warnings:
                            warnings.append(f"{_element_label(element)}: {stress_warning}")
                    if PRESTRESS_FPU_CAP_WARNING in stress_warnings:
                        point_fpu_cap_count += element.count
                    if PRESTRESS_COMPRESSION_REVERSAL_WARNING in stress_warnings:
                        point_compression_reversal_count += element.count
                    point_max_prestress_stress = max(point_max_prestress_stress, fps)
                    force = -element.area_mm2 * element.count * fps
                else:
                    fs_passive = passive_prestress_steel_stress_mpa(element, eps_section)
                    point_max_prestress_stress = max(point_max_prestress_stress, abs(fs_passive))
                    force = element.area_mm2 * element.count * fs_passive

                prestress_force += force
                Pn += force
                Mnx += force * (element.y_mm - y_ref)
                Mny += force * (element.x_mm - x_ref)

                if eps_section < 0.0:
                    tensile_strain = -eps_section
                    if eps_t is None or tensile_strain > eps_t:
                        eps_t = tensile_strain
                        eps_t_fy = _prestress_phi_yield_reference_mpa(element)
                        eps_t_es = element.ep_mpa

            if settings.use_phi_factor:
                phi, strain_condition = aci_phi_and_strain_condition(eps_t, eps_t_fy, eps_t_es, transverse_reinforcement)
            else:
                phi = 1.0
                strain_condition = "phi-not-applied"
            phiPn = phi * Pn
            phiPn_capped = min(phiPn, phiPn_max) if phiPn_max is not None else None

            points.append(
                PMMPoint(
                    theta_rad=theta,
                    c_mm=c_mm,
                    Pn_N=Pn,
                    Mnx_Nmm=Mnx,
                    Mny_Nmm=Mny,
                    phi=phi,
                    phiPn_N=phiPn,
                    phiPn_capped_N=phiPn_capped,
                    phiMnx_Nmm=phi * Mnx,
                    phiMny_Nmm=phi * Mny,
                    eps_t=eps_t,
                    strain_condition=strain_condition,
                    concrete_area_mm2=concrete_area,
                    concrete_force_N=concrete_force,
                    prestress_force_N=prestress_force,
                    prestress_count=bonded_prestress_count,
                    bonded_prestress_count=bonded_prestress_count,
                    active_prestress_count=active_bonded_prestress_count,
                    passive_prestress_count=passive_bonded_prestress_count,
                    unbonded_prestress_ignored_count=unbonded_prestress_ignored_count,
                    prestress_stress_model=prestress_stress_model if active_bonded_prestress_count else ("passive_high_strength_steel" if passive_bonded_prestress_count else None),
                    prestress_stress_warning_count=len(point_stress_warnings),
                    max_prestress_stress_MPa=point_max_prestress_stress,
                    prestress_reached_fpu_cap_count=point_fpu_cap_count,
                    prestress_compression_reversal_count=point_compression_reversal_count,
                    rebar_displaced_concrete_subtracted_N=rebar_displaced_concrete_subtracted,
                    rebar_inside_compression_count=rebar_inside_compression_count,
                )
            )

    info.append(f"Generated {len(points)} PMM point(s).")
    if any(PRESTRESS_LINEAR_CAP_FALLBACK_WARNING in warning for warning in warnings):
        info.append("Prestress linear_cap fallback occurred for at least one PMM point.")
    if any(PRESTRESS_COMPRESSION_REVERSAL_WARNING in warning for warning in warnings):
        info.append("Active prestress compression reversal clamp occurred for at least one PMM point.")
    if any(point.prestress_reached_fpu_cap_count > 0 for point in points):
        info.append("Active prestress stress reached fpu cap for at least one PMM point; retained as PMM stress-state metadata, not a standalone engineering warning.")
    return PMMSolverResult(points=points, warnings=deduplicate_warnings(warnings), info=info)
