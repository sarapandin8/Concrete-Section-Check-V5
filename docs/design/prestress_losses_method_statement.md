# GIRDER.LOSS0 — Prestress Loss Method Statement and Implementation Scope Freeze

**Status:** Method statement / scope freeze only. No prestress-loss solver is implemented in this milestone.

**Applies to:** Concrete PMM Pro precast pretensioned girder workflows, including Precast I-Girder, Precast Plank Girder, and Precast Box Beam / Adjacent Box Beam workflows.

**Does not apply to:** Post-tensioned tendon friction/anchorage-loss workflows, cast-in-place post-tensioned boxes, external tendon systems, or final code-certified project authority calculations.

---

## 1. Purpose

This document freezes the intended engineering architecture for future prestress-loss implementation before adding calculation code. It is a QA gate to prevent premature formulas from being mixed into UI, SLS stress checks, or PMM logic.

The next implementation milestones must treat this document as the controlling scope until it is deliberately superseded.

---

## 2. Structural engineering basis

For precast pretensioned girders, the primary loss components are:

1. **Elastic Shortening / Elastic Effect** at transfer.
2. **Creep of concrete**.
3. **Shrinkage of concrete**.
4. **Relaxation of prestressing steel**.

For ordinary precast pretensioned girders, **friction loss** and **anchorage set loss** are not part of the normal loss model. Those are post-tensioned tendon effects and must not be silently introduced into this workflow.

---

## 3. Required stage force states

Future loss calculation must produce or preserve separate force states instead of a single generic `Pe_eff`:

| Force state | Intended meaning | Preliminary app status |
|---|---|---|
| `P_jack` / `f_jack` | Jacking force/stress before transfer effects | Future input/model field |
| `P_initial` / `f_initial` | Initial strand stress immediately before/at transfer basis | Future input/model field |
| `P_transfer(x)` / `f_transfer(x)` | Effective prestress at transfer after immediate loss and debonding active-strand logic | Future calculated or manually overridden state |
| `P_deck(x)` / `f_deck(x)` | Prestress state at deck placement / construction stage | Future calculated or manually overridden state |
| `P_service(x)` / `f_service(x)` | Final service prestress after long-term losses | Future calculated or manually overridden state |

The `(x)` suffix is intentional. Once debonding is connected, active strand count and force are station-dependent.

---

## 4. Mandatory manual override workflow

Before automatic AASHTO/ACI loss formulas are used by SLS checks, the app must support a safe manual force-state workflow:

- User may enter `P_transfer`, `P_deck`, and `P_service` directly.
- User may choose whether calculated losses overwrite, seed, or remain separate from manual values.
- User-entered values must be clearly labeled as **Manual / User-defined**.
- Calculated values must be clearly labeled as **Preview calculated** until validated against benchmarks.
- Final design reports must identify whether prestress force states came from user input or app calculation.

This avoids blocking users who already have force states from a girder design sheet or supplier calculation.

---

## 5. AASHTO LRFD path — future default for bridge girders

AASHTO must be the primary bridge-girder path for future implementation.

### 5.1 AASHTO approximate method

Use as the first automatic preview method after the force-state data model exists.

Planned purpose:

- Preliminary bridge-girder loss estimate.
- Standard precast pretensioned girder checks.
- Fast sanity check against user-entered `P_service`.

Required guardrails:

- Clearly mark as **AASHTO approximate loss preview**.
- Do not use as final code-certified loss without project-specific review.
- Show required assumptions such as humidity, low-relaxation strand, concrete unit weight, and applicable section type.
- Use explicit unit conversion; internal app values should remain MPa, mm, kN unless a module deliberately converts to ksi/in.

### 5.2 AASHTO refined/staged method

Use after the approximate method and stage data model are stable.

Required stages:

```text
Transfer / Release  ->  Deck Placement / Construction  ->  Final Service
```

Required components:

- Elastic shortening at transfer.
- Transfer-to-deck shrinkage / creep / relaxation.
- Deck-to-final shrinkage / creep / relaxation.
- Composite-section transformed coefficients where required.
- Deck shrinkage effect where applicable.

Required section bases:

| Stage | Section basis |
|---|---|
| Transfer / Release | Precast gross section |
| Girder self-weight at release | Precast gross section |
| Wet deck / topping before composite action | Precast gross section, construction basis |
| SDL after composite | Composite transformed section |
| Final service | Composite transformed section |

---

## 6. ACI / PCI path — future optional method

ACI 318 + PCI-style losses must be an optional cross-check path, not the default bridge-girder path.

Planned purpose:

- Building/precast office workflow.
- Cross-check against AASHTO losses.
- User-selected alternative where the project authority requires it.

Required guardrails:

- Clearly label as **ACI/PCI loss preview**.
- State that ACI 318 identifies loss effects to consider but does not provide the same bridge-specific staged refined method as AASHTO.
- Do not silently replace AASHTO bridge-girder workflow with ACI/PCI values.

---

## 7. Elastic shortening policy

Elastic shortening is not optional for pretensioned girder transfer checks.

Future implementation must either:

1. Use an iterative method for concrete stress at prestress centroid, or
2. Use a recognized one-step approximation with the equation and limitations exposed.

Do not compute transfer prestress using final service `Pe_eff` without a review warning.

---

## 8. Debonding and station dependency

Prestress loss calculation must not be treated as a single section-only scalar once strand debonding is active.

Minimum future behavior:

- Determine active strands by station `x`.
- Compute or scale `Aps_active(x)`.
- Compute strand centroid/eccentricity by active group at station `x`.
- Produce `P_transfer(x)`, `P_deck(x)`, and `P_service(x)`.
- Show warning if a station uses a force state that is inconsistent with active strand count.

---

## 9. Not allowed in LOSS0 or early LOSS1 milestones

Do not implement these in LOSS0:

- Automatic creep/shrinkage calculation in SLS stress checks.
- Automatic overwrite of `Pe_eff` used by existing preview stress cards.
- Changes to PMM solver equations. Do not change solver equations in loss-method milestones.
- Changes to bonded/unbonded prestress PMM behavior.
- Changes to rebar logic.
- Changes to load table schema unless explicitly scoped.
- Final PASS/FAIL based on calculated losses.

Do not hide uncertainty. Use **Preview**, **Review**, or **Manual** labels until benchmark validation is complete.

---

## 10. Recommended milestone sequence

```text
GIRDER.PS4A   Strand layout / void-aware validation
GIRDER.PS5A   Debonding -> active strand groups by station
GIRDER.LOSS1A Prestress force-state data model and manual inputs
GIRDER.LOSS1B AASHTO approximate loss preview, isolated from SLS solver
GIRDER.LOSS1C Manual override / calculated value reconciliation and warnings
GIRDER.LOSS2A AASHTO refined staged loss preview
GIRDER.LOSS2B Station-based Pe_stage(x) integration
GIRDER.SLS4A  Station-based SLS stress graphs using staged Pe(x)
ACI/PCI.LOSS  Optional ACI/PCI preview and cross-check
```

---

## 11. Acceptance criteria for implementing LOSS1A later

Before formulas are implemented, LOSS1A must add a data model capable of storing:

- Code method selection: Manual, AASHTO Approximate Preview, AASHTO Refined Preview, ACI/PCI Preview.
- Concrete strength at transfer `f_ci` and final `f_c`.
- Strand material: `fpu`, `fpy`, `Ep`, strand type / relaxation class.
- Relative humidity.
- Time at transfer, deck placement, and final service.
- Gross section properties and composite section properties.
- Active strand group summary by station.
- Manual and calculated values kept as separate fields.

LOSS1A should not yet use automatic losses in final SLS checks.

---

## 12. QA notes

- All automatic loss formulas must be implemented in a dedicated engineering module, not inside Streamlit UI functions.
- Unit conversion must be centralized and tested.
- AASHTO formulas in ksi/in and internal MPa/mm/kN values must not be mixed.
- Benchmarks must include at least one simple pretensioned girder hand-check and one composite service-stage example.
- Any discrepancy must be reported as a warning; do not tune formulas just to satisfy UI expectations.

---

## 13. Current limitation statement

As of this milestone, Concrete PMM Pro does **not** automatically calculate prestress losses. Existing prestress values remain manual / preview inputs. Future SLS checks using transfer or service prestress must clearly state whether `Pe` is user-defined or preview-calculated.
