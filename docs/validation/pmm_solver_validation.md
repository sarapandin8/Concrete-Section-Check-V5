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


## VALID.PS1 — Bonded prestress PMM benchmark pack

Milestone **VALID.PS1** adds the first executable bonded-prestress PMM benchmark pack under:

- `concrete_pmm_pro/verification/ps_bonded_benchmarks.py`
- `tests/test_valid_ps1_bonded_prestress.py`

The pack is deliberately benchmark-oriented.  It does not change the solver equation.  It creates deterministic PS-only and RC+PS sections so prestress warnings can be interpreted against evidence rather than hidden from the UI.

| Check | Purpose | Current acceptance |
|---|---|---|
| `VALID.PS1.PS_ONLY_EPST` | Confirm a bonded prestress-only section can provide the controlling tensile strain `eps_t` for phi evaluation. | PS-only PMM sweep produces transition or tension-controlled points. |
| `VALID.PS1.PE_EFF_TO_FPE` | Confirm `Pe_eff` converts to `fpe` and initial strain using only area and `Ep`. | `fpe = Pe_eff / Aps`; no product breaking load is used. |
| `VALID.PS1.PO_INCLUDES_APS` | Confirm prestress-aware nominal `Po` includes bonded `Aps` with `fpy` and deducts displaced concrete area. | Delta relative to RC-only equals `Aps(fpy - 0.85fc')`. |
| `VALID.PS1.RCPS_CAPACITY_TREND` | Confirm RC+PS benchmark produces nonzero prestress force and a changed Mx capacity trend relative to RC-only control. | RC+PS envelope changes in the expected direction for the deterministic tendon layout. |
| `VALID.PS1.STRESS_WARNING_METADATA` | Confirm high-prestress cases expose fpu-cap events in PMM point metadata. | fpu-cap warnings are traceable to PMM points for future governing-impact classification. |
| `VALID.PS1.NUMERIC_SCHEMA` | Confirm RC+PS capacity-critical PMM result fields are finite. | No NaN/Inf in `Pn`, `Mnx`, `Mny`, `phi`, `phiPn`, `phiMn`, prestress force, or max prestress stress fields. |

VALID.PS1 is not final prestress solver certification.  It is the first executable evidence pack for PS-only and RC+PS behavior.  Published prestressed section examples and stress-state governing-region checks remain required before retiring prestress prototype warnings.


## VALID.PS2 — Prestress stress-state governing-region benchmark pack

Milestone **VALID.PS2** adds executable checks for classifying prestress stress-state warnings by their relationship to the governing demand region.  It is still a validation/QA layer and does not change prestress stress equations.

Added files:

- `concrete_pmm_pro/verification/ps_stress_region_benchmarks.py`
- `tests/test_valid_ps2_stress_region.py`

| Check | Purpose | Current acceptance |
|---|---|---|
| `VALID.PS2.METADATA_SCHEMA` | Confirm PMM point data exposes `prestress_reached_fpu_cap_count`, `prestress_compression_reversal_count`, and `prestress_stress_warning_count`. | Metadata exists and is numeric for every PMM point. |
| `VALID.PS2.GOVERNING_TRACE_AVAILABLE` | Confirm a governing D/C result has capacity method metadata for impact review. | Governing combo, D/C, capacity, and capacity method are available. |
| `VALID.PS2.FPU_BACKGROUND_CLASSIFICATION` | Distinguish global fpu-cap events from events near the governing Pu slice. | Deterministic RC+PS benchmark has fpu-cap events globally but none near the governing Pu region. |
| `VALID.PS2.COMPRESSION_REVERSAL_REGION` | Confirm compression-reversal events are traceable to PMM point regions. | Compression-reversal counts are available globally and near governing Pu for benchmark review. |
| `VALID.PS2.PS_ONLY_REGION_SLICE` | Confirm PS-only PMM data can be sliced near governing Pu. | PS-only benchmark has PMM points near governing Pu for stress-warning impact review. |

VALID.PS2 is the first step toward reducing prestress warnings based on evidence.  It does not remove fpu-cap or compression-reversal warnings; it gives the app a testable basis to decide whether those warnings are governing-related or background PMM-surface events.

## SOLVER.PS.PASSIVE1 — Passive prestressing steel separation

Milestone **SOLVER.PS.PASSIVE1** separates passive prestressing-steel rows from active prestress rows.

A prestress row is treated as **active prestress** only when it has nonzero `Pe_eff`, `initial_stress_mpa`, or `initial_strain`.  Rows with `Pe_eff = 0`, `fpe = 0`, and no initial strain/stress are treated as **passive bonded high-strength steel**.  This distinction matters because passive PT bars/strands should still contribute to PMM strength through strain compatibility, but they should not trigger active-prestress stress warnings such as compression reversal or fpu-cap warnings.

Added files/checks:

- `concrete_pmm_pro/verification/ps_passive_benchmarks.py`
- `tests/test_valid_ps_passive1.py`

| Check | Purpose | Current acceptance |
|---|---|---|
| `SOLVER.PS.PASSIVE1.NO_ACTIVE_WARNINGS` | Confirm passive PS rows do not emit active-prestress compression-reversal, fpu-cap, or active stress-model warnings. | No active-prestress warnings are emitted for Pe_eff = 0 passive rows. |
| `SOLVER.PS.PASSIVE1.SIGNED_FORCE` | Confirm passive PS rows contribute signed strain-compatible steel force. | PMM sweep includes both tension and compression force states for the passive row. |
| `SOLVER.PS.PASSIVE1.EPST_PHI` | Confirm passive PS rows can control tensile strain for phi evaluation. | At least one PMM point has `eps_t`, with transition or tension-controlled behavior available. |
| `SOLVER.PS.PASSIVE1.METADATA` | Confirm passive PS rows retain display/report metadata without active event counts. | Prestress force/stress columns exist and active event counts remain zero. |

This milestone does not validate every commercial prestressing-steel constitutive model.  It fixes the important engineering classification error where passive high-strength steel was being routed through the active prestress warning path.


Implemented or partially implemented items include:

- RC concentric axial compression / `phiPn` cap checks.
- Rectangular RC uniaxial hand spot check.
- RC phi transition and tension-control checks.
- Symmetry sanity checks for positive/negative `Mnx` and `Mny`.
- Prestress strain convention spot checks.
- Bonded prestress PS-only and RC+PS benchmark checks.
- Prestress stress-state governing-region benchmark checks.
- Active-prestress fpu-cap metadata policy checks.
- Prestress-aware `Po` helper tests.
- Directional D/C and slice-envelope regression coverage.
- Actionable warning guidance and governing-impact classification coverage.

## Warnings and how they should be retired

| Warning family | Current status | Required path before retiring or downgrading |
|---|---|---|
| PMM prototype result | Limitation / note | Add published/reference PMM benchmark cases and validation tolerances. |
| ACI axial cap method note | Documented method note | `QA.PO1` now provides independent RC-only, PS-only, and RC+PS axial-cap benchmark cases; retain code-specific axial-limit review notes. |
| Demand/capacity prototype interpolation | Engineering review | Add robust directional capacity benchmark cases and fallback governance tests. |
| Prestress reached `fpu` cap | Numerical / QA metadata unless governing-related | Active prestress keeps fpu-cap events as PMM point metadata. Background cap events are not standalone engineering warnings; they are escalated only when governing-region checks indicate possible impact. |
| Prestress compression reversal clamp | Governing-region review only | Active prestress compression-reversal events are retained as PMM point metadata by SOLVER.PS.COMP1. They are escalated to engineering review only when detected near the governing demand region; background PMM-surface events remain QA metadata. |
| NaN `eps_t` | Numerical note | Confirm no capacity-critical fields are invalid and document expected compression-controlled missingness. |

## Recommended next milestones

1. **VALID.RC1 — Rectangular RC PMM benchmark pack** — initial executable pack added.
   - Keep expanding with published reference examples.
   - Add stronger biaxial reference points and published reference examples.

2. **VALID.RC2 — RC phi transition / tension-control benchmark pack** — executable pack added.
   - Use as the baseline before prestress-only and RC+PS phi validation.
   - Add published examples documenting ACI phi transition behavior where available.

3. **SOLVER.PMM.DC1 — Robust directional PMM capacity check** — implemented.
   - Uses cleaned selected-Pu slice envelopes with ray-intersection capacity extraction as the primary D/C path.
   - Adds analytic rectangular slice benchmarks to prevent polar-radius interpolation from overestimating faceted envelopes.
   - Remaining work: add published/reference biaxial PMM D/C examples before retiring all D/C validation limitation notes.

4. **VALID.PS1 — Bonded prestress PMM benchmark pack** — executable pack added.
   - Validate PS-only and RC+PS behavior.
   - Validate `fpe`, `Pe_eff`, `eps_t`, `fpu` cap metadata, and numeric schema.
   - Add published prestressed reference examples before lowering prestress prototype wording.

5. **VALID.PS2 — Prestress stress-state governing-region benchmark** — executable pack added.
   - Classifies `fpu` cap and compression reversal events against the governing demand region.
   - Distinguishes background PMM-surface stress events from result-affecting warnings.

6. **SOLVER.PS.PASSIVE1 — Passive prestressing steel separation** — implemented.
   - Treats Pe_eff=0/fpe=0 PS rows as passive high-strength steel.
   - Prevents passive PT bars/strands from producing active-prestress fpu-cap or compression-reversal warnings.
   - Next: retain active prestress stress-state validation for rows with nonzero initial prestress.

7. **SOLVER.PS.STRESS1 — Active prestress fpu-cap metadata policy** — implemented.
   - Keeps fpu-cap events as PMM point metadata instead of standalone global warnings when they occur on background ultimate envelope points.
   - Escalates fpu-cap guidance only when governing-region classification indicates possible direct impact.
   - Next: develop compression-reversal handling/reference cases.

8. **UI.WARN.POLICY1 — Commercial warning policy**
   - Move validated method assumptions into report notes/manuals.
   - Show only result-affecting warnings in the main ULS summary.

## Current limitation statement

Until validation benchmarks are expanded, PMM output should be described as:

> ULS PMM results are engineering-review results based on the current strain compatibility solver and documented assumptions.  Governing D/C may be used for internal review, but final design should be independently checked until the relevant validation cases are completed.


### SOLVER.PS.COMP1 compression-reversal warning policy

Active prestress compression reversal is still modeled conservatively by clamping negative total tensile strain to zero.  The event is no longer emitted as a standalone global engineering warning for every PMM surface point.  Instead, `prestress_compression_reversal_count` is retained per PMM point and the Analysis diagnostics escalate it only when the event is detected near the governing Pu region.  This keeps the ULS summary focused on governing-impact items while preserving the QA trail for future prestress stress-model validation.

### QA.PO1 prestress-aware axial cap validation

`QA.PO1` adds an executable benchmark pack for the ACI-style nominal axial compression helper used by the PMM axial cap.  The checks are intentionally independent of the Streamlit UI and verify area bookkeeping supporting reduced axial-cap prototype wording.

Covered cases:

- RC-only `Po = 0.85 fc(Ag - Ast) + fy Ast`.
- PS-only `Po = 0.85 fc(Ag - Aps) + fpy Aps`.
- RC + bonded prestress `Po = 0.85 fc(Ag - Ast - Aps) + fy Ast + fps_ref Aps`.
- Missing `fpy` uses `0.90 fpu` and does not use `Pe_eff`.
- `count` multiplies `area_mm2` exactly once.
- Tied-column maximum axial cap uses `0.80 * phi * Po`.
- Unbonded prestress is excluded upstream before the Po helper receives the bonded strain-compatible element list.

This milestone does not change the axial-cap equations.  It provides benchmark evidence so the ACI axial-cap diagnostic can be treated as a documented method note rather than a broad prototype warning.

## UI.VALIDATION.STATUS1 — Commercial Validation Status Panel

The Analysis workspace now summarizes method validation status separately from solver diagnostics.  The result heading no longer relies on broad `Prototype Result` wording.  Instead, the UI displays a validation-status table that separates implemented benchmark evidence from validation-in-progress and planned checks.

Current commercial-facing status areas include RC PMM strain compatibility, ACI phi transition, directional PMM demand/capacity extraction, prestress-aware axial cap, passive PS/high-strength steel behavior, active bonded prestress model behavior, prestress stress-state policies, and SLS future work.

This is a UI/method-status milestone only.  It does not certify unvalidated solver behavior or remove QA diagnostics.  Remaining limitation notes continue to be retained in Diagnostics / QA and reports until the related validation milestones are completed.

## UI.VALIDATION.STATUS1.1 — Validation Evidence Detail Polish

The commercial validation-status panel now includes a compact overview table and a separate detailed evidence table.  The compact table is intended for first-screen review and includes:

- method / validation area
- validation status
- design-use guidance
- validation case ID

The detailed table keeps benchmark evidence and remaining engineering limitations available in an expander for QA review.  This is a communication and traceability improvement only; it does not change PMM equations, prestress stress-strain assumptions, axial-cap equations, or demand/capacity extraction.

## UI.ANALYSIS3.9 — Result Hierarchy and Solver Info Cleanup

The Analysis diagnostics now separate designer-facing result information from solver-internal QA metadata. The PMM diagnostics panel shows only a compact set of first-screen solver QA essentials, while detailed capacity envelope extrema, reinforcement/prestress metadata, prestress stress-state details, and RC-only vs RC+PS comparisons are kept in collapsed expanders.

This milestone does not change PMM equations, D/C extraction, prestress stress-strain assumptions, axial-cap equations, or validation status. It only improves result hierarchy so the ULS workspace reads like an engineering result page rather than a debug dashboard.

### UI.ANALYSIS4 — Governing PMM Slice Visualization

The PMM Check tab now emphasizes the governing Mux-Muy slice at the selected Pu.  The figure shows the cleaned PMM slice envelope, the demand vector, the capacity ray, and the ray/envelope intersection used to compute available phiMn and D/C.  Selected-case cards also show capacity margin and reserve ratio.  This milestone does not change PMM equations or D/C extraction; it makes the existing SOLVER.PMM.DC1 ray-intersection result traceable to the user visually.


### UI.ANALYSIS4.1 — Clean PMM Slice Plot Interaction

The governing PMM slice plot now defaults to a selected-case-only view, keeps D/C and margin values in the side detail panel, and provides optional controls for chart annotations and all active ULS point overlays. This keeps the PMM slice readable when many load cases are present while preserving hover details and traceability.

### UI.ANALYSIS4.2 — Governing Slice Plot Minimal Mode

The governing PMM slice visualization defaults to the governing ULS load point only with annotation callouts off.  This is a display-policy refinement only; it does not change the PMM surface, SOLVER.PMM.DC1 ray-intersection D/C extraction, load cases, or validation status.  Detailed numerical values remain in the Selected/Governing Case Details panel and plot hover text.

## UI.ANALYSIS4.3 — Result Confidence / Design Decision Banner

This UI milestone adds a decision-oriented banner above the ULS/PMM result workspace. It does not change solver equations. The intent is commercial-style communication: show whether the current ULS PMM strength check passes, whether any diagnostic directly affects the governing result, and which QA notes remain for final engineering review. SLS remains outside the ULS PMM decision and is reported as a separate planned/check workflow.

### UI.ANALYSIS4.4 — Final Analysis Workspace Polish

The ULS / PMM Analysis workspace now separates result communication into two levels:

- a compact workspace header showing governing case, D/C, active ULS/SLS counts, fallback count, and D/C warning count; and
- a Design Decision banner that presents Decision, Confidence, and Scope / Exclusions as separate blocks.

This reduces duplicate PASS / governing / D/C messaging and clarifies that the current decision applies to ULS PMM strength only.  SLS / Stress & Cracking remains outside this ULS decision and is reported as a separate planned workflow.  No solver equation, PMM generation, prestress model, axial-cap logic, or D/C extraction behavior is changed by this milestone.

## SECTION.PRESET1A — Parametric I-Girder Geometry

A parametric bridge I-Girder section preset has been added as an analysis-ready geometry generator. The first version supports symmetric solid I-Girder sections using B1/B2 flange widths, D1 total depth, D2/D5 flange thicknesses, D3/D6 haunch depths, T1/T2 web widths, and optional C1 outside chamfer. The preset validates basic geometric compatibility before storing the section for downstream analysis.

## UI.SECTION.PRESET1.1 — Simplified section preset selection

The section preset UI was simplified so users choose the actual section type directly. Category remains metadata for organization only; this reduces confusion when selecting parametric girder presets and does not change geometry generation, solver equations, or PMM analysis behavior.

## SECTION.PRESET1A.1 — Parametric I-Girder Geometry QA

The Parametric I-Girder preset remains a symmetric solid polygon generator using B1, B2, D1, D2, D3, D5, D6, T1, T2, and optional C1. The Section Builder now exposes a dimension QA panel so users can review the depth stack, web clear zone, transition widths, chamfer state, and analysis-compatibility tags before running PMM analysis.

### SECTION.PROP1 — Parametric Section Properties Calculation

- Added gross section property calculation for generated section polygons, including net area, centroid, centroidal Ix/Iy, extreme-fiber distances, and top/bottom section modulus.
- Parametric I-Girder section properties now display analysis-ready Ix/Iy instead of placeholder values.
- These properties provide the basis for future prestressed bridge girder SLS stress checks and station-based Beam/Girder workflows.


## SECTION.PRESET1B — Parametric Plank Girder Geometry

Parametric plank girder presets have been added for Interior and Exterior bridge plank sections.  These presets generate precast-only concrete polygons and calculate gross section properties through the existing SECTION.PROP1 summary path.  Composite slab/effective-width data are stored as metadata only in this milestone:

- `Tslab` is retained as deck/topping thickness metadata.
- `Be` is currently manual/project-defined.
- `n = Edeck / Ebeam` is calculated automatically.
- `Btransformed = n * Be` is calculated automatically.
- AASHTO LRFD automatic effective flange width calculation remains a future code-profile milestone.

No PMM solver, D/C extraction, prestress model, or service-stress equation is changed by this section-preset milestone.
