"""Prestressing steel stress-strain helpers for PMM prototypes."""

from __future__ import annotations

PRESTRESS_COMPRESSION_REVERSAL_WARNING = (
    "Prestress compression reversal is not modeled; tensile strain was clamped to zero."
)
PRESTRESS_LINEAR_CAP_FALLBACK_WARNING = "fpy/proof stress missing; linear capped prestress model used."
PRESTRESS_FPU_CAP_WARNING = "Prestress stress reached fpu cap."

PrestressStressModel = str


def prestress_total_tensile_strain(initial_tensile_strain: float, section_strain: float) -> float:
    """Return total tendon tensile strain for bonded prestress prototypes.

    `initial_tensile_strain` is positive in tendon tension. `section_strain`
    follows the section convention where compression is positive and tension is
    negative.

    Compression strain at the tendon location reduces tendon tensile strain;
    tension strain increases it.
    """

    return initial_tensile_strain - section_strain


def prestress_stress_mpa(
    total_tensile_strain: float,
    Ep_MPa: float,
    fpu_MPa: float,
    fpy_MPa: float | None = None,
    model: str = "bilinear",
    post_yield_ratio: float = 0.02,
) -> tuple[float, list[str]]:
    """Return prestressing steel tensile stress magnitude and warnings.

    Supported prototype models:
    - ``linear_cap``: elastic stress capped between 0 and fpu.
    - ``bilinear``: elastic to fpy/proof stress, then a small post-yield slope,
      capped at fpu. If fpy is missing, the helper falls back to ``linear_cap``.

    Compression reversal is not modeled in this milestone; negative total
    tensile strain is clamped to zero and reported as a warning.
    """

    warnings: list[str] = []
    if model not in {"linear_cap", "bilinear"}:
        raise ValueError("prestress stress model must be linear_cap or bilinear.")
    if Ep_MPa <= 0.0:
        raise ValueError("Ep_MPa must be positive.")
    if fpu_MPa <= 0.0:
        raise ValueError("fpu_MPa must be positive.")
    if fpy_MPa is not None and fpy_MPa >= fpu_MPa:
        raise ValueError("fpy_MPa must be less than fpu_MPa.")

    eps = float(total_tensile_strain)
    if eps < 0.0:
        eps = 0.0
        warnings.append(PRESTRESS_COMPRESSION_REVERSAL_WARNING)

    if model == "linear_cap":
        fps = Ep_MPa * eps
    else:
        if fpy_MPa is None:
            warnings.append(PRESTRESS_LINEAR_CAP_FALLBACK_WARNING)
            fps = Ep_MPa * eps
        else:
            eps_y = fpy_MPa / Ep_MPa
            if eps <= eps_y:
                fps = Ep_MPa * eps
            else:
                fps = fpy_MPa + post_yield_ratio * Ep_MPa * (eps - eps_y)

    if fps > fpu_MPa:
        fps = fpu_MPa
        warnings.append(PRESTRESS_FPU_CAP_WARNING)

    return max(0.0, min(float(fps), fpu_MPa)), warnings
