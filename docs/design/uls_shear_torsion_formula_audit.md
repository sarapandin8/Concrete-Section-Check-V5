# Beam/Girder ULS Shear and Torsion Formula Audit

Milestone: `ULS.CODEVERIFY1`

This document is a QA gate before expanding the Beam/Girder ULS shear, torsion, and combined shear-torsion engines.  It does not replace the licensed code text.  It records what the app may safely claim, what is only first-pass, and what must remain `REVIEW` until benchmarked.

## 1. Source hierarchy

1. Licensed project code text and errata control the implementation.
2. Official publisher previews/product pages are used only to verify edition, chapter structure, and applicability.
3. User-supplied summaries are useful as checklists only; any item that conflicts with the official code structure, unit system, or current project basis is not implemented.
4. The active workflow controls the design route:
   - Bridge Beam/Girder -> AASHTO LRFD
   - Building Beam/Girder -> ACI 318

## 2. Non-negotiable QA findings

### 2.1 ACI 318-19 chapter route

ACI 318-19 organizes strength reduction factors in Chapter 21 and sectional strength in Chapter 22.  One-way shear is under Section 22.5 and torsional strength is under Section 22.7.  Any reference that treats ACI 318-19 beam shear/torsion as Chapter 11 / Sections 11.2, 11.5, and 11.6 is treated as an older-code or mixed-version reference until checked against the licensed code.

### 2.2 Unit system guard

The app stores dimensions in mm and concrete strength in MPa.  Therefore metric ACI shear expressions must use the metric coefficient route.  The US customary expression using `2 sqrt(f'c) bw d` must not be used directly with MPa-mm inputs.

Current app guard:

```text
ACI metric simplified one-way Vc coefficient = 0.17
ACI US customary simplified one-way Vc coefficient = 2.0  (not allowed in MPa-mm calculations)
```

### 2.3 AASHTO edition route

Bridge Beam/Girder remains locked to the project-specified AASHTO LRFD 9th Edition basis unless the project setup is explicitly changed.  Do not mix later AASHTO edition concrete changes into the engine without a separate migration milestone.

## 3. Current app implementation matrix

| Route | Check item | Current app status | Risk | Action before final PASS |
|---|---|---|---|---|
| ACI RC | One-way shear Vc/Vs | Partial: uses SI 0.17 simplified concrete contribution and provided stirrup Vs | Medium | Add complete ACI 318-19 member-condition/size-effect route and benchmark |
| ACI PSC | One-way shear Vc/Vp | Missing final route | High | Implement PSC Vci/Vcw/Vp input path and benchmark |
| ACI RC | Torsion φTn | Partial: transverse closed-hoop first-pass only | High | Add threshold logic, section sizing, longitudinal steel, hoop detailing, V+T |
| ACI PSC | Torsion | Missing dedicated PSC route | High | Define PSC torsion basis and benchmark |
| AASHTO RC | Shear MCFT β/θ | Partial: first-pass simplified sectional route | High | Implement section-type-specific LRFD 9th + errata β/θ route |
| AASHTO PSC | Shear with prestress/end region | Partial: d/dv source exists, final prestress/end-region route missing | Critical | Add PSC dv/strain/prestress/end-region checks and benchmark |
| AASHTO RC | Torsion φTn | Partial: first-pass closed-hoop θ=45 route | High | Add θ consistency, section-size/crushing, longitudinal steel, V+T |
| AASHTO PSC | Combined V+T | Missing | Critical | Do not issue combined PASS until full route and benchmark exist |

## 4. Implementation gates

The app must not issue an overall Beam/Girder ULS `PASS` until all active checks for the workflow are either implemented and benchmarked or explicitly declared not applicable.

The next safe engineering milestones are:

1. `ULS.SHEAR.CODE2` — audited ACI RC shear route and benchmark guards.
2. `ULS.TORSION2` — audited torsion threshold / φTn / longitudinal review output.
3. `ULS.VT1` — combined shear-torsion section-size and reinforcement interaction.
4. `ULS.BENCH1` — hand-calc / commercial-software benchmark cases.

## 5. User reference handling

The uploaded user reference remains useful for variable naming and checklist coverage, but it is not a controlling source.  The most important rejected items for implementation are:

- ACI 318-19 Chapter 11 / Section 11.x references for beam shear/torsion.
- Direct use of the US customary ACI `2 sqrt(f'c)` coefficient with MPa-mm input.
- Treating separate shear and torsion checks as a combined shear-torsion pass.
- Treating first-pass AASHTO θ=45 output as final MCFT calibration.

