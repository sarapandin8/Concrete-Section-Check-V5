# PMM.FINAL.AUDIT1 - Flexural PMM Final-Readiness Audit

Milestone: `PMM.FINAL.AUDIT1`

This audit controls the path from the current Flexural PMM engineering-review
workflow toward a commercial final-status workflow. It does not change solver
equations, resistance factors, prestress stress logic, demand/capacity
extraction, or UI result status wording.

## Scope

- Member family: Column / Pier / Wall / Pylon - RC / Prestressed Member.
- Active subview: `Flexural (PMM)`.
- Checks covered: axial-biaxial PMM strength and ULS demand/capacity review.
- Checks not covered: shear, torsion, serviceability, detailing, development
  length, confinement detailing, second-order analysis, and construction-stage
  checks.

## Current implementation evidence

| Area | Current evidence | Readiness classification |
|---|---|---|
| PMM solver | `concrete_pmm_pro/analysis/pmm_solver.py` runs an ACI-oriented strain-compatibility PMM sweep. | Implemented, engineering-review |
| Demand/capacity | `concrete_pmm_pro/analysis/capacity_check.py` checks active ULS load cases against the PMM result. | Implemented, engineering-review |
| RC validation | `VALID.RC1`, `VALID.RC2`, hand checks, and PMM benchmark packs exist. | Strong candidate for next finalization milestone |
| Directional D/C | `VALID.PMM.DC1` and slice-envelope checks exist. | Implemented, still needs final reference cases |
| Prestress PMM | `VALID.PS1`, `VALID.PS2`, `SOLVER.PS.PASSIVE1`, `SOLVER.PS.STRESS1`, and `SOLVER.PS.COMP1` exist. | Implemented with retained prestress limitations |
| Axial cap | `QA.PO1` validates the prestress-aware ACI-style axial cap helper. | Candidate for method-note downgrade |
| AASHTO LRFD PMM | Project code routing says AASHTO LRFD PMM is planned and current PMM remains ACI-oriented. | Not implemented for final AASHTO use |

## Final-status blockers

The current Flexural PMM workflow must not be relabeled as final or
code-certified until these blockers are closed by named milestones:

1. Published or independently traceable reference examples are still needed for
   RC uniaxial and true biaxial PMM capacity.
2. Directional D/C extraction needs final reference cases showing that the
   selected method does not overestimate capacity for non-circular and
   non-symmetric PMM envelopes.
3. Prestressed PMM needs published/reference examples for bonded active
   prestress behavior, stress-state policy, and governing-region effects.
4. Prestress compression reversal is not fully modeled; current behavior is a
   documented limitation and cannot be hidden as a final solver assumption.
5. Unbonded prestress is ignored by the PMM solver and must remain a hard
   limitation until a separate unbonded model exists.
6. AASHTO LRFD Column/Pier PMM is not implemented. The existing PMM engine is
   ACI-oriented and must not be marketed as final AASHTO LRFD PMM.
7. Neutral-axis sweep resolution and irregular-section numerical robustness
   need final acceptance criteria before final certification wording.
8. Validation must be runnable in the delivery environment. In this Codex
   runtime, validation execution was blocked by missing `shapely`, even though
   `requirements.txt` lists `shapely>=2.0`.

## Allowed status after this audit

The safest commercial wording after `PMM.FINAL.AUDIT1` is:

> Flexural PMM is an implemented engineering-review strength workflow with
> substantial validation evidence. It is not yet a final code-certified solver.

For ACI 318 Column/Pier PMM, the next target may be:

> Validated production preview

This status is allowed only after `PMM.FINAL.RC1` and `PMM.FINAL.DC1` pass with
documented benchmark evidence.

For AASHTO LRFD Column/Pier PMM, the current status remains:

> Planned / guarded

No AASHTO LRFD final PMM claim is allowed until a separate AASHTO PMM route is
implemented and validated.

## Do-not-change rules

- Do not remove prototype or engineering-review wording solely to make the UI
  look final.
- Do not modify solver equations merely to make validation checks pass.
- Do not reuse Beam/Girder shear, torsion, or flexure readiness to certify
  Column/Pier PMM.
- Do not treat ACI-oriented PMM as final AASHTO LRFD PMM.
- Do not hide unbonded prestress, compression reversal, convex-hull fallback,
  or D/C interpolation limitations from report/readiness outputs.

## Recommended next milestones

1. `PMM.FINAL.RC1` - ACI 318 RC Column/Pier PMM final benchmark pack:
   published/reference uniaxial and biaxial cases, phi transition, axial cap,
   sign convention, and irregular-section numeric hygiene.
2. `PMM.FINAL.DC1` - Final demand/capacity extraction:
   ray-envelope D/C benchmark cases, no-overestimate checks, fallback policy,
   and report traceability.
3. `PMM.FINAL.PS1` - Bonded prestress final-readiness:
   active bonded prestress reference cases, compression-reversal policy, and
   prestress stress-state governance.
4. `PMM.AASHTO.PMM1` - AASHTO LRFD Column/Pier PMM route:
   code-specific resistance factors, axial/flexural assumptions, and validation.
5. `PMM.UI.STATUS1` - Commercial status wording:
   update UI/report labels only after the relevant route has passed benchmark
   milestones.

