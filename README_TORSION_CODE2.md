# ULS.TORSION.CODE2 — Final Torsion Strength + Detailing Gate

This milestone promotes the Beam/Girder torsion check from a strength-only review screen to a code-routed torsion strength + reinforcement/detailing gate.

## Scope

- Torsion status can now become `PASS` when the following gates pass:
  - torsion threshold / demand gate
  - transverse closed-hoop strength `Tu <= φTn`
  - longitudinal torsion `Al` from the ordinary rebar source-of-truth
  - active closed-hoop zone coverage at the station
  - compact torsion spacing check `s <= min(ph/8, 300 mm)`
- Combined Shear + Torsion can report `PASS` when:
  - combined stress interaction passes
  - combined transverse `(Av + 2At)/s` passes
  - longitudinal `Al` passes
  - separate source strength gate is clear (`Shear = PASS`, `Torsion = PASS` or below threshold/no demand)
- UI wording now distinguishes source-gate review/blocking from final pass-capable gates.

## Not changed

- Flexure solver and PMM capacity.
- Shear formulas and shear detailing guard.
- Torsion formula core and demand/capacity units.
- Loads / ProjectModel schema.
- Report workflow.

## Engineering note

This milestone makes the app decision logic final-pass capable for the implemented torsion gates. Project drawings still need normal engineering review for hook anchorage, constructability, local end-zone detailing, development lengths, and any project-specific code exceptions.
