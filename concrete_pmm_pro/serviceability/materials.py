"""Material modulus helpers for serviceability calculations."""

from __future__ import annotations

import math


def estimate_concrete_ec_mpa(
    fc_MPa: float,
    density_kg_m3: float = 2400,
    method: str = "aci_normal_weight",
) -> float:
    """Estimate concrete elastic modulus in MPa.

    The Ec estimate is preliminary. User-defined Ec values will be
    supported more broadly in future serviceability milestones.
    """

    if fc_MPa <= 0:
        raise ValueError("fc_MPa must be greater than zero.")
    if density_kg_m3 <= 0:
        raise ValueError("density_kg_m3 must be greater than zero.")
    if method != "aci_normal_weight":
        raise ValueError("Only aci_normal_weight Ec estimation is supported.")
    return 4700.0 * math.sqrt(fc_MPa)


def estimate_concrete_ec_warnings(
    fc_MPa: float,
    density_kg_m3: float = 2400,
    method: str = "aci_normal_weight",
) -> list[str]:
    """Return engineering warnings for preliminary Ec estimates."""

    warnings: list[str] = []
    if fc_MPa <= 0 or density_kg_m3 <= 0:
        return warnings
    if method == "aci_normal_weight" and density_kg_m3 < 2000:
        warnings.append(
            "Concrete density is below normal-weight range; aci_normal_weight Ec = 4700√fc may overestimate Ec for lightweight concrete."
        )
    return warnings


def modular_ratio(steel_E_MPa: float, concrete_E_MPa: float) -> float:
    """Return modular ratio n = Es / Ec."""

    if steel_E_MPa <= 0:
        raise ValueError("steel_E_MPa must be greater than zero.")
    if concrete_E_MPa <= 0:
        raise ValueError("concrete_E_MPa must be greater than zero.")
    return steel_E_MPa / concrete_E_MPa
