# Concrete PMM Pro — PMM Solver Validation Framework

Milestone: **QA.VALIDATION1 — PMM Solver Validation Framework**

This document defines the validation direction for the RC / bonded-prestress PMM solver.  It is not a final certification report.  It is the project-level framework used to move Concrete PMM Pro from a prototype engineering-review solver toward a commercial-grade, benchmark-supported solver.

## Why this milestone exists

The app currently reports several engineering review warnings, including prototype PMM wording, prestress stress reaching `fpu`, compression-reversal clamp notes, directional D/C fallback notes, and `eps_t` numerical notes.  Those warnings should not be hidden merely to make the UI look clean.  They should be removed, downgraded, or retained only after validation evidence supports that decision.

Commercial software usually appears quieter because its internal numerical warnings are filtered by governing impact, documented in method notes/manuals, or backed by validation benchmarks.  Concrete PMM Pro must follow the same direction.

## Validation principles

1. **Do not hide solver warnings without engineering evidence.**
2. **Separate UI warning policy from solver correctness.**
3. **Validate RC-only behavior before relying on RC + prestress behavior.**
4. **Validate prestress steel stress and strain behavior before removing prestress model warnings.**
5. **Tie every future warning reduction to a benchmark, test, or documented assumption.**
6. **Preserve sign convention and unit consistency: mm, MPa, N, N-mm internally.**

## Current validation layers

The validation framework combines existing checks with a formal validation matrix:

- Independent hand-calculation spot checks: `concrete_pmm_pro/verification/hand_checks.py`
- PMM benchmark-style checks: `concrete_pmm_pro/verification/pmm_benchmarks.py`
- RC phi transition benchmarks: `concrete_pmm_pro/verification/rc_phi_transition_benchmarks.py`
- Validation matrix and report runner: `concrete_pmm_pro/verification/validation_framework.py`
- Tests: `tests/test_validation_framework.py`

## Validation matrix categories

| Category | Purpose |
|---|---|
| RC-only PMM | Establish baseline strain compatibility, axial cap, bending, and symmetry behavior. |
| Prestress PMM | Validate bonded prestress strain, `eps_t`, `Po + Aps`, and stress model behavior. |
| Demand/Capacity | Validate directional PMM capacity extraction at demand `Pu` and moment direction. |
| Numerical robustness | Distinguish expected numerical notes from invalid capacity results. |
| Warning policy | Ensure warnings are actionable and tied to governing-impact classification. |

## Implemented coverage in QA.VALIDATION1

The milestone introduces a formal validation matrix with implemented, partial, and planned coverage status.  It does not change PMM solver equations.  It gives the project a stable engineering QA structure.


## VALID.RC1 — Rectangular RC PMM benchmark pack

Milestone **VALID.RC1** adds the first executable RC-only benchmark pack under:

- `concrete_pmm_pro/verification/rc_rectangular_benchmarks.py`
- `tests/test_valid_rc1_benchmarks.py`

The pack checks a simple rectangular RC section using independent rectangular stress-block formulas and solver comparisons:

| Check | Purpose | Current acceptance |
|---|---|---|
| `VALID.RC1.PHI_PN_MAX` | Compare solver capped axial compression strength against independent ACI-style tied-column `phiPn,max`. | Within documented prototype tolerance. |
| `VALID.RC1.MX_C300_PN` | Compare solver `Pn` near a uniaxial neutral-axis depth `c ≈ 300 mm` against hand calculation. | Within documented prototype tolerance. |
| `VALID.RC1.MX_C300_MNX` | Compare solver `Mnx` near the same neutral-axis state against hand calculation. | Within documented prototype tolerance. |
| `VALID.RC1.MX_SYMMETRY` | Check positive/negative `Mx` envelope balance for a symmetric section. | Within discretization tolerance. |
| `VALID.RC1.NUMERIC_SCHEMA` | Confirm capacity-critical PMM result fields contain no NaN/Inf values. | No invalid values in critical columns. |

This benchmark pack is still not a full commercial certification.  It gives the project traceable RC-only evidence before reducing prototype wording.  Published reference examples and biaxial reference checks are still required before fully retiring general PMM prototype notes.

## VALID.RC2 — RC phi transition / tension-control benchmark pack

Milestone **VALID.RC2** adds executable checks for the ACI-style phi transition used by the RC PMM solver:

- `concrete_pmm_pro/verification/rc_phi_transition_benchmarks.py`
- `tests/test_valid_rc2_phi_transition.py`

The pack checks both the direct phi helper and the PMM solver points for a rectangular RC section.

| Check | Purpose | Current acceptance |
|---|---|---|
| `VALID.RC2.PHI_COMPRESSION_EDGE` | Verify compression-controlled phi at the yield-strain boundary. | `phi = 0.65` and condition = compression-controlled. |
| `VALID.RC2.PHI_TRANSITION_MID` | Verify linear transition interpolation halfway to the tension-controlled threshold. | `phi = 0.775` for tied reinforcement. |
| `VALID.RC2.PHI_TENSION_EDGE` | Verify tension-controlled phi at `eps_y + 0.003`. | `phi = 0.90` and condition = tension-controlled. |
| `VALID.RC2.PHI_NONE_COMPRESSION` | Verify missing tensile strain defaults to compression-controlled behavior. | `phi = 0.65`. |
| `VALID.RC2.SOLVER_REGION_COVERAGE` | Confirm the rectangular RC PMM sweep samples compression-controlled, transition, and tension-controlled regions. | All three strain regions are present. |
| `VALID.RC2.SOLVER_PHI_MATCH` | Confirm every RC PMM point matches the independent phi helper for `phi` and strain-condition label. | No mismatches. |
| `VALID.RC2.SOLVER_PHI_RANGE` | Confirm solver phi range remains within tied-column ACI limits. | `0.65 <= phi <= 0.90`, currently spanning both endpoints. |

VALID.RC2 strengthens confidence in `eps_t` interpretation and phi classification before the project attempts prestress-specific phi and stress-model validation.


Implemented or partially implemented items include:

- RC concentric axial compression / `phiPn` cap checks.
- Rectangular RC uniaxial hand spot check.
- RC phi transition and tension-control checks.
- Symmetry sanity checks for positive/negative `Mnx` and `Mny`.
- Prestress strain convention spot checks.
- Prestress-aware `Po` helper tests.
- Directional D/C and slice-envelope regression coverage.
- Actionable warning guidance and governing-impact classification coverage.

## Warnings and how they should be retired

| Warning family | Current status | Required path before retiring or downgrading |
|---|---|---|
| PMM prototype result | Limitation / note | Add published/reference PMM benchmark cases and validation tolerances. |
| ACI axial cap prototype | Limitation / note | Add independent RC-only, PS-only, and RC+PS axial cap benchmark cases. |
| Demand/capacity prototype interpolation | Engineering review | Add robust directional capacity benchmark cases and fallback governance tests. |
| Prestress reached `fpu` cap | Engineering review | Add solver-level stress-state metadata and governing-region classification. |
| Prestress compression reversal clamp | Engineering review | Define/validate compression-side prestress behavior or retain a documented limitation. |
| NaN `eps_t` | Numerical note | Confirm no capacity-critical fields are invalid and document expected compression-controlled missingness. |

## Recommended next milestones

1. **VALID.RC1 — Rectangular RC PMM benchmark pack** — initial executable pack added.
   - Keep expanding with published reference examples.
   - Add stronger biaxial reference points and published reference examples.

2. **VALID.RC2 — RC phi transition / tension-control benchmark pack** — executable pack added.
   - Use as the baseline before prestress-only and RC+PS phi validation.
   - Add published examples documenting ACI phi transition behavior where available.

3. **SOLVER.PMM.DC1 — Robust directional PMM capacity check**
   - Strengthen capacity extraction at governing `Pu` and moment direction.
   - Reduce fallback usage and document fallback only when needed.

4. **VALID.PS1 — Bonded prestress PMM benchmark pack**
   - Validate PS-only and RC+PS behavior.
   - Validate `fpe`, `Pe_eff`, `eps_t`, `fpu` cap, and compression reversal treatment.

5. **UI.WARN.POLICY1 — Commercial warning policy**
   - Move validated method assumptions into report notes/manuals.
   - Show only result-affecting warnings in the main ULS summary.

## Current limitation statement

Until validation benchmarks are expanded, PMM output should be described as:

> ULS PMM results are engineering-review results based on the current strain compatibility solver and documented assumptions.  Governing D/C may be used for internal review, but final design should be independently checked until the relevant validation cases are completed.
