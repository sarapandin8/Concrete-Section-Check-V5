# PMM.FINAL.RC1.STATUS.READINESS1 - Production-Preview Readiness Audit

Milestone: `PMM.FINAL.RC1.STATUS.READINESS1`

This audit records the status decision after the ACI RC Flexural PMM evidence
gate gained executable checks for uniaxial reference behavior, biaxial reference
behavior, phi classification, and D/C no-overestimate behavior. It does not
change PMM equations, D/C extraction, prestress behavior, or UI/report wording.

## Decision

If `run_pmm_final_rc1_readiness_gate()` returns `PASS`, the ACI RC
Column/Pier/Wall/Pylon Flexural PMM workflow is ready for a separate
production-preview wording milestone.

Allowed future wording after a named UI/report milestone:

> ACI RC Flexural PMM validated production preview.

Current wording remains acceptable until that separate milestone:

> ACI RC Flexural PMM is implemented for engineering review with substantial
> validation evidence and a defined final-readiness gate.

Forbidden wording:

> Final code-certified ACI/AASHTO PMM design.

## Evidence Now Required By The Runner

| Gate item | Evidence |
|---|---|
| Scope | `PMM.FINAL.RC1.SCOPE` excludes prestress finalization, AASHTO LRFD PMM, shear, torsion, SLS, detailing, slenderness, and second-order effects. |
| Uniaxial RC reference | `VALID.RC1.PHI_PN_MAX`, `VALID.RC1.MX_C300_PN`, and `VALID.RC1.MX_C300_MNX`. |
| Biaxial RC reference | `VALID.RC1.BIAX_CDIAG_PN`, `VALID.RC1.BIAX_CDIAG_MNX`, and `VALID.RC1.BIAX_CDIAG_MNY`. |
| Phi behavior | `VALID.RC2` compression, transition, tension, solver phi match, and solver phi range checks. |
| D/C no-overestimate | `SOLVER.PMM.DC1` rectangular ray checks, non-star nearest-boundary guard, and RC rectangular primary no-overestimate guard. |
| Wording guard | `PMM.FINAL.RC1.WARNING` and `PMM.FINAL.RC1.STATUS.READINESS1`. |

## Remaining Limitations

- Published/reference PMM examples are still recommended before any final
  certification wording.
- Published/reference D/C examples and non-rectangular RC benchmark cases are
  still recommended before retiring all D/C limitation notes.
- AASHTO LRFD PMM remains unsupported for Column/Pier/Wall/Pylon.
- Prestressed PMM finalization remains outside this RC-only status decision.
- Shear, torsion, detailing, slenderness, and second-order effects remain
  outside this Flexural PMM decision.

## Do-Not-Change Rules

- Do not rename production-preview readiness as final code certification.
- Do not change solver equations or tolerances to make the gate pass.
- Do not let UI/report wording claim AASHTO LRFD PMM support for this member
  family.
- Do not treat Beam/Girder ULS or SLS readiness as Column/Pier PMM evidence.
- Do not remove diagnostic or limitation notes without a named warning-policy
  milestone.
