# PMM.FINAL.RC1 - ACI RC Flexural PMM Final-Readiness Gate

Milestone: `PMM.FINAL.RC1`

This milestone defines the engineering gate for moving the ACI-oriented
Column/Pier/Wall/Pylon `Flexural (PMM)` workflow from prototype wording toward
validated production-preview wording. It does not certify the solver and does
not change PMM equations.

## Controlled scope

- Code route: ACI 318-style RC PMM only.
- Member family: Column / Pier / Wall / Pylon.
- Material scope: ordinary reinforced concrete without active prestress.
- Solver scope: axial load plus biaxial bending, `Pu`, `Mux`, and `Muy`.
- Excluded from this milestone: bonded prestress finalization, unbonded
  prestress, AASHTO LRFD PMM, shear, torsion, SLS, detailing, slenderness, and
  second-order effects.

## Existing evidence credited by this gate

| Evidence item | Existing source | Current gate credit |
|---|---|---|
| RC rectangular axial cap, uniaxial spot check, and diagonal biaxial spot check | `VALID.RC1` | Accepted as internal benchmark evidence |
| ACI-style phi transition | `VALID.RC2` | Accepted as implemented phi classification evidence |
| Directional D/C ray-envelope method | `VALID.PMM.DC1` | Accepted as internal D/C method evidence |
| D/C no-overestimate guard | `SOLVER.PMM.DC1.NONSTAR_NEAREST_RAY` and `SOLVER.PMM.DC1.RC_RECT_PRIMARY_NO_OVERESTIMATE` | Guards noisy/non-star envelope rays by using the nearest positive boundary and confirms an actual RC rectangular PMM route does not exceed its direct slice ray-boundary estimate |
| ACI axial cap helper | `VALID.RC.PO1` and `QA.PO1` | Accepted as axial-cap method evidence |
| Sign convention | `pmm_solver.py`, `strain_compatibility.py`, README method notes | Accepted as documented and test-guarded convention |
| Numeric hygiene | `VALID.RC1.NUMERIC_SCHEMA` and PMM result schema checks | Accepted as baseline numeric evidence |
| RC final-readiness aggregation | `concrete_pmm_pro/verification/pmm_final_rc1_benchmarks.py` | Executable gate using RC1/RC2/DC1 evidence; may pass only as finalized production-preview evidence, not final certification |
| Status readiness audit | `PMM.FINAL.RC1.STATUS.READINESS1` | Records that finalized production-preview wording is separate from final certification and remains guarded by `PMM.FINAL.RC1.CLOSEOUT` |

## Required final-readiness checks

These checks must be satisfied before ACI RC PMM wording can move beyond
engineering-review status:

| Gate ID | Requirement | Minimum acceptance |
|---|---|---|
| `PMM.FINAL.RC1.SCOPE` | Confirm the final-readiness scope is RC-only ACI PMM and excludes prestress/AASHTO/shear/torsion. | Scope is documented and regression guarded. |
| `PMM.FINAL.RC1.UNIAXIAL.REF` | Add at least one traceable external or independently derived ACI RC uniaxial column benchmark. | Solver axial and moment capacity match within documented tolerance. |
| `PMM.FINAL.RC1.BIAXIAL.REF` | Add at least one true biaxial `P-Mx-My` reference benchmark. | Solver nominal `Pn`, `Mnx`, and `Mny` match the independent rectangular clipping reference within documented tolerance. |
| `PMM.FINAL.RC1.PHI` | Preserve ACI tied/spiral phi transition checks. | `VALID.RC2` passes without solver/source mismatch. |
| `PMM.FINAL.RC1.AXIAL.CAP` | Preserve ACI maximum axial compression cap checks. | `VALID.RC.PO1`/`QA.PO1` evidence remains present. |
| `PMM.FINAL.RC1.SIGN` | Preserve compression-positive internal convention and demand/resistance naming separation. | Source and report wording keep the sign-convention guard. |
| `PMM.FINAL.RC1.DC` | Preserve ray-envelope D/C as the preferred capacity extraction path. | Fallbacks remain visible; no silent overestimate is allowed. |
| `PMM.FINAL.RC1.WARNING` | Prevent cosmetic removal of prototype/review wording. | UI/report wording may be downgraded only after benchmark evidence passes. |
| `PMM.FINAL.RC1.STATUS.READINESS1` | Decide whether benchmark evidence can support finalized production-preview wording. | PASS supports `PMM.FINAL.RC1.CLOSEOUT`; it is not final certification. |

## Current status after this milestone

The ACI RC Flexural PMM workflow is not final code-certified. `PMM.FINAL.RC1`
now has an executable readiness runner that aggregates `VALID.RC1`,
`VALID.RC2`, and `VALID.PMM.DC1`; `VALID.RC1` includes an independent diagonal
biaxial rectangular clipping reference for nonzero `Mnx` and `Mny`. The correct
finalized closeout wording is:

> ACI RC Flexural PMM: Finalized Production Preview.

The following wording is still not allowed:

> Final code-certified ACI/AASHTO PMM design.

## Engineering blockers before status upgrade

1. Add published/reference biaxial ACI RC PMM examples before any final
   certification wording is considered.
2. Add published/reference D/C examples and non-rectangular RC benchmark
   shapes beyond the current rectangular RC and synthetic non-star/noisy
   envelope checks.
3. Add published/reference uniaxial examples before any final certification
   wording is considered, even though an internal independent uniaxial gate is
   now executable.
4. Keep convex-hull and fallback warnings visible when fallback methods are
   used.
5. Keep AASHTO LRFD PMM guarded until a separate AASHTO route exists.
6. Keep prestress out of this RC-only finalization gate.

## Do-not-change rules

- Do not rename prototype warnings as final certification warnings.
- Do not weaken PMM validation tolerances to pass a benchmark.
- Do not modify solver equations merely to satisfy this readiness gate.
- Do not use Beam/Girder ULS readiness to certify Column/Pier PMM.
- Do not treat prestressed PMM validation evidence as RC-only final evidence.

## Next engineering work

The next safe implementation steps are:

1. Published/reference reinforcement of `PMM.FINAL.RC1.UNIAXIAL.REF`
2. Published/reference reinforcement of `PMM.FINAL.RC1.BIAXIAL.REF`
3. Published/reference or non-rectangular reinforcement of
   `PMM.FINAL.RC1.DC.NO_OVERESTIMATE`

`PMM.FINAL.RC1.CLOSEOUT` completes the RC-only production-preview status
communication. Any future change to PMM equations, D/C extraction, AASHTO,
prestress, shear, torsion, or final-certification wording requires a new named
solver/validation milestone.
