"""Prototype ACI-style strength reduction factor helpers."""

from __future__ import annotations


def aci_phi_from_tensile_strain(
    eps_t: float,
    fy_MPa: float = 420,
    Es_MPa: float = 200000,
    transverse_reinforcement: str = "tied",
) -> float:
    """Return prototype ACI phi from net tensile strain.

    `eps_t` is positive in tension. If no tension reinforcement controls, pass
    zero and the function returns the compression-controlled phi.
    """

    phi, _condition = aci_phi_and_strain_condition(eps_t, fy_MPa, Es_MPa, transverse_reinforcement)
    return phi


def aci_phi_and_strain_condition(
    eps_t: float | None,
    fy_MPa: float = 420,
    Es_MPa: float = 200000,
    transverse_reinforcement: str = "tied",
) -> tuple[float, str]:
    if fy_MPa <= 0:
        raise ValueError("fy_MPa must be positive.")
    if Es_MPa <= 0:
        raise ValueError("Es_MPa must be positive.")

    if transverse_reinforcement == "tied":
        compression_phi = 0.65
    elif transverse_reinforcement == "spiral":
        compression_phi = 0.75
    else:
        raise ValueError("transverse_reinforcement must be tied or spiral.")
    tension_phi = 0.90
    eps_y = fy_MPa / Es_MPa
    eps_t_value = 0.0 if eps_t is None else max(0.0, float(eps_t))
    tension_threshold = eps_y + 0.003

    if eps_t_value <= eps_y:
        return compression_phi, "compression-controlled"
    if eps_t_value >= tension_threshold:
        return tension_phi, "tension-controlled"

    ratio = (eps_t_value - eps_y) / (tension_threshold - eps_y)
    phi = compression_phi + ratio * (tension_phi - compression_phi)
    return phi, "transition"
