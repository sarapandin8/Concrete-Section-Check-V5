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
| RC rectangular axial cap and uniaxial spot check | `VALID.RC1` | Accepted as internal benchmark evidence |
| ACI-style phi transition | `VALID.RC2` | Accepted as implemented phi classification evidence |
| Directional D/C ray-envelope method | `VALID.PMM.DC1` | Accepted as internal D/C method evidence |
| D/C no-overestimate guard | `SOLVER.PMM.DC1.NONSTAR_NEAREST_RAY` | Guards noisy/non-star envelope rays by using the nearest positive boundary |
| ACI axial cap helper | `VALID.RC.PO1` and `QA.PO1` | Accepted as axial-cap method evidence |
| Sign convention | `pmm_solver.py`, `strain_compatibility.py`, README method notes | Accepted as documented and test-guarded convention |
| Numeric hygiene | `VALID.RC1.NUMERIC_SCHEMA` and PMM result schema checks | Accepted as baseline numeric evidence |
| RC final-readiness aggregation | `concrete_pmm_pro/verification/pmm_final_rc1_benchmarks.py` | Executable gate, currently expected to return `WARNING` until true biaxial reference evidence is added |

## Required final-readiness checks

These checks must be satisfied before ACI RC PMM wording can move beyond
engineering-review status:

| Gate ID | Requirement | Minimum acceptance |
|---|---|---|
| `PMM.FINAL.RC1.SCOPE` | Confirm the final-readiness scope is RC-only ACI PMM and excludes prestress/AASHTO/shear/torsion. | Scope is documented and regression guarded. |
| `PMM.FINAL.RC1.UNIAXIAL.REF` | Add at least one traceable external or independently derived ACI RC uniaxial column benchmark. | Solver axial and moment capacity match within documented tolerance. |
| `PMM.FINAL.RC1.BIAXIAL.REF` | Add at least one true biaxial `P-Mx-My` reference benchmark. | Directional capacity is not overestimated and D/C path is traceable. |
| `PMM.FINAL.RC1.PHI` | Preserve ACI tied/spiral phi transition checks. | `VALID.RC2` passes without solver/source mismatch. |
| `PMM.FINAL.RC1.AXIAL.CAP` | Preserve ACI maximum axial compression cap checks. | `VALID.RC.PO1`/`QA.PO1` evidence remains present. |
| `PMM.FINAL.RC1.SIGN` | Preserve compression-positive internal convention and demand/resistance naming separation. | Source and report wording keep the sign-convention guard. |
| `PMM.FINAL.RC1.DC` | Preserve ray-envelope D/C as the preferred capacity extraction path. | Fallbacks remain visible; no silent overestimate is allowed. |
| `PMM.FINAL.RC1.WARNING` | Prevent cosmetic removal of prototype/review wording. | UI/report wording may be downgraded only after benchmark evidence passes. |

## Current status after this milestone

The ACI RC Flexural PMM workflow is not final yet. `PMM.FINAL.RC1` now has an
executable readiness runner that aggregates `VALID.RC1`, `VALID.RC2`, and
`VALID.PMM.DC1`, but the gate remains blocked by the missing true biaxial
reference case. The correct current wording is:

> ACI RC Flexural PMM is implemented for engineering review with substantial
> validation evidence and a defined final-readiness gate.

The target wording after the missing reference checks pass may be:

> ACI RC Flexural PMM validated production preview.

The following wording is still not allowed:

> Final code-certified ACI/AASHTO PMM design.

## Engineering blockers before status upgrade

1. Add true biaxial ACI RC benchmark evidence for nonzero `Mux` and `Muy`.
2. Confirm D/C extraction does not overestimate capacity for RC benchmark
   shapes beyond the current synthetic rectangular and non-star/noisy envelope
   checks.
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

The next safe implementation step is to add executable reference cases for:

1. `PMM.FINAL.RC1.BIAXIAL.REF`
2. `PMM.FINAL.RC1.DC.NO_OVERESTIMATE` using RC-specific shapes beyond the
   synthetic `SOLVER.PMM.DC1.NONSTAR_NEAREST_RAY` guard
3. Published/reference reinforcement of `PMM.FINAL.RC1.UNIAXIAL.REF`

Only after those pass should UI/report status wording be updated by a separate
`PMM.UI.STATUS1` milestone.
