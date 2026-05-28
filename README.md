# Concrete PMM Pro

Professional Streamlit engineering application foundation for reinforced concrete and prestressed concrete PMM analysis.

This repository is at Milestone PS.DB1.2 plus P.1.1, V.PS1.1 visualization cleanup, and R.FIG.1.1 figure-export deployment hotfix. The PMM solver and ULS demand/capacity workflow are still prototypes. The app navigation is grouped into engineering workspaces, and the Analysis workspace has real subtabs for ULS / PMM, SLS / Stress & Cracking, and Report / QA. Analysis now includes runtime controls, stable engineering-input hashes, cache status indicators, and lightweight timing diagnostics around expensive UI-triggered operations. Existing Project, Materials, Section Builder, Rebar, Prestress, Loads, PMM, SLS, cracking, report export, and report QA tools remain reachable without changing calculation logic. Bonded prestress contribution is included in the PMM prototype with refined prestressing steel stress-strain models, ordinary rebar displaced-concrete refinement, independent hand-calculation spot checks, engineering verification safeguards, benchmark-style solver checks, refined PMM slice interpolation, slice envelope robustness checks, clearer warning/reporting text, numerical cleanup, elastic SLS stress checks using either gross or uncracked transformed section properties, optional effective bonded prestress contribution, no-tension/decompression serviceability judgement, SLS stress sign benchmark checks, cracking/tension-zone classification from existing SLS stress results, custom SLS stress check points with geometry validation, SLS stress visualization on the section, context-aware engineering limitation filtering, report manifest JSON, draft Word report export, and Word report QA; unbonded prestress, full cracked-section stress redistribution, crack-width checks, Beam/Girder flexure/shear/torsion checks, PDF export, and production-grade design certification are intentionally not implemented yet.



## Current Validation Direction

Latest validation milestones add a traceable path from prototype PMM results toward commercial-grade engineering QA:

- `QA.VALIDATION1` establishes the validation matrix and report runner.
- `VALID.RC1` adds rectangular RC axial/bending/symmetry benchmark checks.
- `VALID.RC2` adds ACI-style phi transition and tension-control benchmark checks.
- `VALID.PS1` adds bonded-prestress PS-only and RC+PS benchmark checks for `eps_t`, `Pe_eff/fpe`, `Po + Aps`, stress-warning metadata, and RC+PS numeric schema.
- `VALID.PS2` adds prestress stress-state governing-region checks so fpu-cap and compression-reversal warnings can be classified as governing-related or background PMM-surface events.
- `SOLVER.PS.PASSIVE1` separates Pe_eff=0/fpe=0 passive PT bars/strands from active prestress, so passive high-strength steel contributes to PMM strength without active-prestress fpu-cap or compression-reversal warnings.
- `SOLVER.PS.STRESS1` treats active-prestress fpu-cap events as PMM stress-state metadata rather than standalone global warnings, with escalation reserved for governing-region impact.

These validation packs do not hide solver warnings.  They provide the evidence needed to later downgrade prototype wording into documented method notes or keep true governing-impact warnings visible.


## Milestone SOLVER.PS.STRESS1 Scope

- Keeps active-prestress fpu-cap events in PMM point metadata for QA and governing-region checks.
- Stops promoting background fpu-cap events from ultimate PMM surface generation into standalone engineering warnings.
- Keeps active-prestress compression-reversal and fallback warnings as engineering-review items.
- Updates warning guidance so fpu-cap events are usually QA/numerical notes unless governing-impact classification escalates them.
- Does not change PMM force equilibrium, material stress calculation, D/C equations, load import, report export, or prestress input behavior.

## Milestone SOLVER.PS.PASSIVE1 Scope

- Separates passive prestressing-steel rows from active prestress rows.
- Treats rows with Pe_eff/fpe/initial strain equal to zero as bonded high-strength passive steel.
- Keeps passive PS bars/strands in strain compatibility and phi eps_t tracking.
- Prevents passive rows from emitting active-prestress compression-reversal or fpu-cap warnings.
- Adds passive-PS benchmark checks and regression tests.
- Does not remove active-prestress warnings for rows with nonzero Pe_eff/fpe/initial strain.

## Milestone VALID.PS2 Scope

- Adds prestress stress-state governing-region benchmark pack.
- Adds per-PMM-point compression-reversal metadata alongside existing fpu-cap metadata.
- Checks that fpu-cap events can be separated into global PMM-surface events and events near the governing Pu region.
- Checks that compression-reversal events are traceable by PMM region for later warning-policy refinement.
- Does not change PMM solver equations, D/C equations, load import, report export, or prestress input behavior.

## Milestone VALID.RC2 Scope

- Adds RC phi transition / tension-control benchmark pack.
- Directly checks tied-column ACI-style phi behavior for compression-controlled, transition, tension-controlled, and no-tensile-strain cases.
- Verifies the rectangular RC PMM sweep samples all phi regions.
- Verifies every RC PMM point phi value and strain-condition label matches the independent phi helper.
- Does not change solver equations, PMM D/C logic, prestress behavior, load import, report export, or UI warning display.

## Milestone QA.VALIDATION1 Scope

- Added a formal PMM solver validation framework instead of relying on UI warning cleanup.
- Added `concrete_pmm_pro/verification/validation_framework.py` with a validation matrix covering RC-only PMM, prestress PMM, demand/capacity interpolation, numerical robustness, and warning policy.
- Added validation tests that confirm solver warning families are tied to root-cause validation items rather than being hidden from the user.
- Added `docs/validation/pmm_solver_validation.md` to document the path from prototype warnings toward benchmark-supported commercial-grade behavior.
- Existing PMM solver equations, D/C logic, prestress stress model, load import, report export, and UI result values are unchanged.

## Internal Units

- Length: mm
- Stress: MPa
- Force: N
- Moment: N-mm

## Milestone PS.DB1 Scope

- Added an explicit 15.2 mm strand tendon product database for standard products including `6-1`, `6-7`, `6-12`, `6-19`, and `6-55`.
- Tendon product records include strand count, strand diameter, strand steel area, tendon steel area, nominal breaking load, fpu, duct type, duct ID reference, and typical use where available.
- Added custom tendon generation by strand count, such as `6-25`, using default 15.2 mm strands, 140 mm2 per strand, 1860 MPa fpu, and 260 kN breaking load per strand.
- The Prestress tab can append standard or custom tendon products to the manual table while preserving existing manual/custom prestress entry behavior.
- Product selection sets `Area_mm2` to total tendon steel area, leaves `Diameter_mm` blank for tendon groups, and keeps effective prestress `Pe_eff_kN` / `fpe_MPa` user-controlled.
- Breaking load and duct information are shown as reference metadata only and are not treated as effective prestress or steel diameter.
- Section preview remains V.PS1.1 true-scale circular steel area based on tendon steel area, not duct diameter.
- Section Builder geometry parameters remain inside Sections -> Section Builder, not in `st.sidebar`.
- Existing PMM/SLS solver formulas, prestress sign convention, D/C algorithm, runtime cache logic, report export, report QA, and engineering limitations are unchanged.

## Milestone PS.DB1.1 Scope

- Simplified tendon product creation to two modes: Standard tendon product and Custom tendon.
- Manual prestress editing remains available in the Advanced Prestress Table instead of as a separate product creation mode.
- Product dropdown options include standard tendon products, prestress database products, and custom labels already present in the current table.
- Project save/load preserves or safely reconstructs tendon product metadata such as strand count, breaking-load reference, duct type, and duct ID.
- Product breaking load remains reference-only, `Count` remains the number of identical tendon elements, and `Strand Count` remains product metadata.

## Milestone PS.DB1.2 Scope

- Standard and custom 15.2 mm tendon products now populate `fpy_MPa = 1580`, `fpu_MPa = 1860`, and `Ep_MPa = 195000`.
- Tendon group `Diameter_mm` is normalized to blank/null because tendon groups are governed by total steel area, not a single steel diameter.
- Added display-only `Eq Steel Dia_mm` based on `sqrt(4A/pi)` for tendon group preview/readability; it is not stored as engineering diameter.
- Project save/load reconstructs missing tendon material defaults for clear 15.2 mm tendon group rows without inventing duct data.
- Duct ID remains reference-only and is not used as steel diameter or true-scale display diameter.

## Milestone V.PS1.1 Scope

- Section preview prestress, PT bar, and tendon group steel areas are drawn as Plotly circle shapes in section coordinate units.
- True-scale circle bounds use `x0/x1/y0/y1` from element coordinates and radius = display steel diameter / 2.
- Display steel diameter uses nominal steel diameter for single strand/PT bar when available, or equivalent steel-area diameter from `sqrt(4A/pi)`.
- Tendon group display diameter uses total steel area equivalent diameter and does not use duct or pipe diameter.
- Small circular scatter markers remain only for hover text and legend entries.
- Existing PMM/SLS solver formulas, prestress sign convention, D/C algorithm, material models, load interpretation, report export, report QA, and engineering limitations are unchanged.

## Milestone V.PS1 Scope

- Section preview prestress markers now use circular markers for strand, tendon, wire, PT bar, and custom prestress steel.
- Rebar remains circular and keeps its existing visual style.
- Prestressing strand/tendon and PT bars are distinguished by color and legend group instead of marker shape.
- Prestress marker sizing is based on nominal steel diameter when available for single steel elements, or equivalent steel-area diameter when diameter is unavailable.
- Tendon group preview diameter is based on total steel area equivalent diameter, not a duct or pipe diameter.
- Hover text shows true nominal diameter, display steel diameter, display basis, per-element steel area, total steel area, Pe_eff, and bonded status.
- Existing PMM/SLS solver formulas, prestress sign convention, D/C algorithm, material models, load interpretation, report export, report QA, and engineering limitations are unchanged.

## Milestone P.1.1 Scope

- Demand/capacity summary caching now uses a dedicated D/C input hash instead of reusing only the PMM result hash.
- The D/C hash combines the PMM result/input hash with active ULS demand case data used by the prototype D/C check.
- D/C cache reuse is invalidated when active ULS `Pu`, `Mux`, `Muy`, load activity, or the PMM result hash changes.
- UI-only load-case notes remain excluded from the D/C cache hash.
- Existing session-state cache keys are preserved where possible while also storing the dedicated D/C input hash.
- Existing PMM/SLS solver formulas, prestress sign convention, D/C algorithm, material models, load interpretation, report export, report QA, and engineering limitations are unchanged.

## Milestone R.FIG.1.1 Scope

- Plotly is constrained to `plotly>=5.22,<6` and Kaleido is pinned to `kaleido==0.2.1` for deployment-friendly Plotly PNG export compatibility with Plotly 5.x environments.
- Draft Word reports continue to embed export-ready Plotly figures as PNG images when local static image export succeeds.
- If PNG export fails, the Word report still generates with the existing figure placeholder and Kaleido/detail warning.
- HTML export fallback remains available.
- Report export still uses stored results and does not rerun solvers.
- Existing PMM/SLS solver formulas, sign conventions, D/C logic, report QA, warning propagation, and engineering limitations are unchanged.

## Milestone R.FIG.1 Scope

- Plotly static PNG export for Word report figures now depends on `kaleido>=1.1`.
- Draft Word reports embed export-ready Plotly figures as PNG images when the local Kaleido/Chrome backend can render them.
- PMM interaction surface figure export uses an existing stored dashboard figure and does not rerun the PMM solver.
- If PNG export fails, the Word report still generates with the existing figure placeholder and Kaleido/detail warning.
- Existing PMM/SLS solver formulas, sign conventions, D/C logic, report QA, warning propagation, and engineering limitations are unchanged.

## Milestone P.1 Scope

- ULS / PMM includes an `Analysis Runtime Control` panel with Fast, Standard, and High Accuracy presets.
- Fast, Standard, and High Accuracy wire to existing neutral-axis angle/depth resolution controls; Standard matches the previous default resolution.
- PMM analysis uses a stable engineering-input hash and reuses cached PMM results when the hash is unchanged.
- Hash inputs include section geometry, holes, materials, rebar, prestress/PT bar data, bonded/unbonded flags, effective prestress values, load cases, relevant analysis settings, and the selected accuracy preset.
- Hash inputs intentionally exclude UI-only notes, labels, generated prestress ids, section metadata, selected tabs, report preview options, and plot display state.
- D/C summaries are cached against the PMM result hash to avoid silent recomputation on UI reruns.
- SLS stress checks store a serviceability input hash and can reuse cached SLS results when serviceability inputs are unchanged.
- Runtime diagnostics record elapsed time for PMM interaction generation, D/C evaluation, SLS stress calculation, PMM/SLS figure generation, and Word/report export.
- Stale PMM/SLS results are warned when engineering inputs change after the last run.
- Existing PMM/SLS formulas, prestress sign convention, D/C algorithm, report export/QA logic, engineering limitations, warning propagation, materials, loads, and result values for the same settings are unchanged.

## Milestone UI.1 Scope

- Analysis now has real subtabs: ULS / PMM, SLS / Stress & Cracking, and Report / QA.
- ULS / PMM contains the existing analysis mode controls, analysis settings, readiness panel, PMM run workflow, PMM plots, D/C output, PMM warnings, and PMM verification/hand checks.
- SLS / Stress & Cracking contains the existing serviceability settings, transformed/gross SLS stress check, custom stress points, no-tension/decompression checks, cracking classification, SLS visualization, and SLS benchmark checks.
- Report / QA contains the existing pre-report traceability, readiness, engineering warnings, limitations, report manifest, figure export registry, draft Word export, and Word report QA tools.
- Results remains a future workspace placeholder only.
- Existing PMM/SLS calculations, prestress sign convention, D/C algorithm, report export/QA logic, engineering limitations, warning propagation, materials, loads, and session state data are unchanged.

## Milestone UI.A0 Scope

- Top-level navigation is grouped into Setup, Sections, Loads, Analysis, and Results.
- Setup contains Project and Materials.
- Sections contains Section Builder, Rebar, and Prestress.
- Loads contains the existing Loads workspace.
- Analysis contains subtabs for ULS / PMM, SLS / Stress & Cracking, and Report / QA.
- The existing mixed Analysis workspace is preserved intact under ULS / PMM for this UI-only milestone.
- SLS / Stress & Cracking and Report / QA subtabs currently show placeholder routing notes; existing SLS, cracking, report export, and report QA outputs remain available under ULS / PMM.
- Results remains a future workspace placeholder only.
- Existing PMM/SLS calculations, prestress sign convention, D/C algorithm, report QA/export logic, limitations, warnings, materials, loads, and session state data are unchanged.

## Milestone 5.5 Scope

- Word report QA validates generated draft `.docx` content before future PDF/final template work.
- Required report section checks verify headings for executive summary, traceability, readiness, warnings, limitations, units, terminology, tables, figures, and generation notes.
- Draft disclaimer validation checks that the report says it is a draft engineering report, generated from current/stored results, and not final design certification.
- Engineering limitation validation checks that HIGH/CRITICAL limitations in the `ReportManifest` are disclosed.
- Engineering warning validation checks that warnings are present when recorded, or explicitly absent when none are recorded.
- Unit convention and terminology checks cover Force/kN, Moment/kN-m, Stress/MPa, Length/mm, Area/mm2, `Pu`, `Mux`, `Muy`, `Pe_eff`, No-Tension, and Decompression.
- Traceability/readiness QA checks readiness status, generated status, analysis mode, ULS/SLS availability, warning count, and limitation count.
- Table/figure QA checks report table and figure sections, figure placeholders, and duplicate SLS bar-chart caption risk.
- Misleading certification language checks flag overstatements such as fully validated, guaranteed safe, or certified design language without draft/prototype context.
- Word Report QA results can be downloaded as `word_report_qa.csv` from the Analysis tab.
- Existing PMM/SLS calculations are unchanged, and PDF export remains future work.

## Milestone 5.4 Scope

- Word report styling and content polish improves cover page, executive summary, headings, compact tables, and footer note.
- `ReportExportOptions` controls appendices, figures, max table rows, terminology, and registries.
- High/Critical engineering limitations are emphasized and sorted ahead of lower-risk limitations.
- Engineering warnings are shown clearly, including the no-warning case.
- Long tables are truncated with a clear note that full CSV export remains available.
- Draft figures include captions, selected context, source, limitations, and PNG-unavailable placeholders.
- Report generation notes state that export uses stored results, does not rerun solvers, does not change calculations, and PDF export remains future work.
- Existing PMM/SLS calculations are unchanged.

## Milestone 5.3 Scope

- Draft Word report export creates `.docx` bytes from the existing `ReportManifest`.
- The draft report includes cover metadata, executive summary, analysis scope, result traceability, readiness, engineering warnings, engineering limitations, unit conventions, terminology, table registry, figure registry, figures where available, and appendices.
- High/Critical limitations remain prominent in the report.
- Figure embedding uses PNG export when available; missing `kaleido` produces a report warning/placeholder instead of failing.
- Report generation reads current stored results and does not rerun analyses.
- Draft Word report download is available from the Analysis tab.
- PDF export remains future work.
- Existing PMM/SLS calculations are unchanged.

## Milestone 5.2 Scope

- Fixed duplicated SLS bar chart export readiness: `sls_stress_bar_diagram` is the single SLS bar chart export key.
- `sls_stress_visualization` is retained only as a compatibility/summary registry key and no longer exports the same bar chart.
- PMM figure export readiness is more context-aware.
- PMM Mux-Muy slice figures can be exported when stored selected slice dataframe data exists.
- PMM slice envelope figures can be exported when stored selected envelope dataframe data exists.
- PMM demand/capacity overlay returns a clear warning when demand point data is missing.
- PMM 3D surface export is not recreated during report export unless an existing dashboard figure state is available.
- PMM figure export uses existing stored result data and does not rerun the PMM solver.
- PMM figure export items carry limitations and warnings, including directional D/C prototype and convex hull fallback overestimation risk where detectable.
- Existing PMM/SLS calculations are unchanged.
- Final Word/PDF report export remains future work.

## Milestone 5.1 Scope

- Report figure export preparation adds `ReportFigureContext` and `ReportFigureExportItem`.
- Figure export registry captures availability, export readiness, selected combo/context, suggested PNG/HTML filenames, warnings, and limitations.
- Safe filename helper normalizes report figure filenames for future exports.
- Plotly HTML export helper returns downloadable HTML bytes.
- Optional Plotly PNG export helper returns PNG bytes when `kaleido` is available and a clear warning when it is not.
- Exportable SLS stress bar and SLS section stress point figures can be rebuilt from existing SLS summary/session data without rerunning solvers.
- Report manifest now includes figure context and figure export items while remaining JSON serializable.
- Analysis tab shows figure export context and registry, plus figure registry CSV export.
- Existing PMM/SLS calculations are unchanged.
- Final Word/PDF report export remains future work.

## Milestone 5.0 Scope

- Report Export Foundation creates `ReportManifest`, `ReportMetadata`, `ReportSection`, `ReportTableInfo`, and report figure registry foundations.
- Report manifest collection reads existing session results only and does not rerun PMM, SLS, cracking, verification, or hand-check solvers.
- Report section plan covers executive summary, metadata, analysis scope, geometry/materials, reinforcement/prestress, ULS PMM, ULS D/C, SLS stress, cracking classification, SLS visualization, verification, warnings/limitations, unit conventions, terminology, and appendices.
- Report table registry lists traceability, readiness, warnings, limitations, unit conventions, terminology, ULS/PMM, SLS, cracking, custom stress point, verification, and visualization tables.
- Report figure registry lists section layout, PMM surface/slices/envelope, SLS stress point/bar figures, cracking overlay, transformed preview, and custom stress point layout for future image export.
- Draft report outline helper produces text only; final Word/PDF generation remains future work.
- Manifest JSON, report section CSV, report table CSV, report figure CSV, and draft outline TXT downloads are available from the Pre-Report QA section.
- Engineering warnings and all engineering limitations are included in the report manifest, including high/critical limitation visibility.
- Existing PMM/SLS calculations are unchanged.
- Word/PDF report export remains future work.
- Beam/Girder flexure/shear/torsion calculations remain future work.
- Cracked-section solver, crack-width checks, and unbonded prestress model remain future work.

## Milestone A.3.2.2 Scope

- Limitations filtering hotfix ensures `collect_limitations_for_report(include_all=False)` always retains every HIGH and CRITICAL engineering limitation.
- Added branch coverage for Beam/Girder limitations filtering.
- Added coverage for alternate PMM/D-C context keys: `dc_summary`, `demand_capacity_summary`, and `rc_demand_capacity_result`.
- Added coverage for cracking context through `crack_classification_summary`.
- Context detection now fails closed when an object's `__bool__` raises `TypeError` or `ValueError`.
- Filtered MEDIUM limitations are context-aware rather than included wholesale.
- `neutral_axis_sweep_resolution` is included when PMM or D/C context exists.
- `prestress_compression_reversal` is included when prestress context exists.
- `crack_width_check` is included when SLS or cracking context exists.
- `beam_girder_shear_torsion` is included when Beam/Girder mode is selected.
- Filtered limitations now retain critical convex hull fallback risk plus high-risk `Ixy` coupling, directional D/C method, prestress axial cap, cracked section, and unbonded prestress limitations.
- Duplicate limitation keys are removed while preserving order.
- Added tests for the `include_all=False` limitations path.
- Shapely defensive exception handling was narrowed where practical around compression block membership, self-crossing checks, convex hull fallback, and stress check point validation.
- Invalid/sparse geometry inputs remain safe and do not crash the app.
- Existing PMM/SLS calculations are unchanged.
- Report export remains future work.
- Pre-report engineering limitations registry lists implemented/prototype/simplified/ignored/future-work items.
- Significant `Ixy` in transformed serviceability properties is now reported as an engineering warning because current SLS stress checks use an uncoupled `Ix`/`Iy` formula.
- D/C directional slice/envelope interpolation limitation is listed as high risk.
- Convex hull PMM slice fallback overestimation risk is listed as critical and shown more prominently in the PMM dashboard.
- Neutral-axis sweep resolution limitation is listed for engineering review.
- Cracked section SLS remains future work.
- Prestress axial cap limitation remains listed: ACI axial cap currently uses RC `Po` only.
- Prestress compression reversal remains a simplification; negative tensile strain is clamped to zero, but SOLVER.PS.COMP1 retains reversal events as PMM metadata and escalates them only when detected near the governing region.
- Unbonded prestress is still ignored with warning.
- Lightweight concrete Ec warning is available when the normal-weight ACI Ec estimate is used with low density.
- Ultimate concrete strain `ecu` default/code-basis note is listed for non-ACI/AASHTO workflow review.
- UI/lint cleanup before report export includes clearer readiness text, unbonded prestress count visibility, and obvious unused import/parameter cleanup.
- Existing PMM/SLS calculations are unchanged.
- Word/PDF report export remains future work.
- Pre-report QA and result traceability foundation is available in the Analysis tab.
- `ResultTraceabilitySnapshot` summarizes project metadata, analysis mode, section/material availability, ULS PMM/D-C status, SLS status, crack classification, verification status, warning count, and custom stress point counts.
- Report readiness checks classify report preparation as READY, PARTIAL, or NOT_READY.
- Engineering warnings are consolidated and de-duplicated without rerunning solvers.
- Standard terminology is available for demand, capacity, SLS, prestress, and analysis mode naming.
- Unit conventions are available for force, moment, stress, length, area, inertia, strain, angle, reinforcement area, and prestress force.
- Available report figures are listed for future export, including PMM dashboard, PMM slice/envelope, SLS stress visualization, cracking classification, transformed properties, and custom stress points.
- CSV exports are available for result traceability snapshot, report readiness, engineering warnings, unit conventions, terminology, and available report figures.
- Word/PDF report export remains future work.
- Existing PMM solver logic, SLS stress formulas, prestress eccentric sign logic, transformed section logic, and cracked-section assumptions are unchanged.
- Project JSON persists `analysis_mode_settings`, including member type and workflow metadata.
- Project JSON persists `custom_stress_check_points`, including name, coordinates, point type, active flag, governing flag, source, and note.
- Project JSON persists `include_default_stress_check_points`.
- Loaded custom SLS stress check points restore into the Custom Stress Check Points UI table.
- Inactive custom stress points are preserved in the project file but excluded from SLS stress analysis.
- Non-governing custom stress points remain visible in SLS results but do not govern summaries.
- Existing PMM solver logic, SLS stress formulas, prestress eccentric sign logic, and `LoadCase` `Pu` / `Mux` / `Muy` fields are unchanged.
- Analysis Mode / Member Type framework adds Column / Pier / Wall / Pylon PMM Mode, Beam / Girder Future Mode, and General Section Mode.
- Column / Pier / Wall / Pylon PMM Mode is the current primary workflow and continues to use `Pu`, `Mux`, and `Muy` with PMM interaction, ULS D/C review, and SLS stress tools.
- Beam / Girder Mode is a placeholder for future flexure, shear, torsion, transfer-stage, service-stage, and tendon-profile workflows. Beam/Girder calculations are not implemented yet.
- General Section Mode keeps the existing PMM and SLS tools available for section review when the member type is not yet classified.
- Existing PMM solver behavior, existing SLS stress formulas, and existing LoadCase `Pu` / `Mux` / `Muy` fields are unchanged.
- Prestress should not be double-counted by entering effective prestress `Pe` as `Pu` demand when prestress elements are already defined.
- PMM interaction is not the primary design method for typical Beam/Girder flexural design; dedicated Beam/Girder checks are future work.
- Metadata-driven Section Builder with category filtering and generated parameter controls.
- Geometry generators that convert every preset into `SectionGeometry`.
- Shapely-backed section validation for outer polygons, holes, area, rebar locations, and prestress element locations.
- Safer generator-side validation for hollow, box, girder, and voided sections.
- Plotly section preview with equal aspect ratio, centroid marker, holes, and dimension labels.
- Dimension labels support symbol + value, symbol only, and value only display modes.
- `PrestressElement` remains the primary model for prestressing steel, including wire, strand, prestressing bar, tendon group, and custom steel.
- Unified prestressing steel database in `data/prestress_steel_database.csv`.
- Loads tab foundation with editable `Pu`, `Mux`, and `Muy` demand values.
- `Pu`, `Mux`, and `Muy` are intended primarily for future ULS PMM strength checks.
- SLS load cases can be stored now, and active SLS load cases can be checked using either gross-section or uncracked transformed-section elastic concrete stress with optional effective bonded prestress contribution, cracking/tension-zone classification, custom stress check points, and selected-combo stress visualization.
- User-facing load units for force (`kN`, `N`, `tonf`) and moment (`kN-m`, `N-mm`, `tonf-m`).
- Internal load storage in `LoadCase` uses `Pu_N`, `Mux_Nmm`, and `Muy_Nmm`.
- Backward compatibility is maintained for older `Mx_Nmm` / `My_Nmm` and `mx_nmm` / `my_nmm` project data.
- Sign convention panel for axial load, biaxial moment, and x-y coordinates.
- Serviceability settings are stored in `ServiceabilitySettings`, including section-basis selection, SLS load type, compression limit ratio, tension limit mode, no-tension check, decompression check, critical point filter, and effective-prestress-force inclusion flag.
- Active SLS load cases are filtered and displayed in engineering units using `Pu`, `Mux`, and `Muy`.
- Gross section properties are calculated from `SectionGeometry` using net concrete area for hollow sections: area, centroid, `Ix`, `Iy`, `Ixy`, bounds, and section moduli.
- Default serviceability stress check points are generated at the top fiber, bottom fiber, left fiber, right fiber, and centroid.
- Elastic SLS stress checks calculate concrete stress at default stress check points for active SLS load cases using the selected section basis.
- SLS stress display uses compression negative and tension positive, intentionally separate from the ULS PMM compression-positive force convention.
- Concrete compression and tension limit checks support compression limit ratio, user-defined tension limit, `sqrt(f'c)` ratio mode, no-tension checks, and decompression checks.
- Milestone 4.5 decompression check is implemented as a no-tension stress check at selected concrete stress points; member-level tendon-zone decompression and cracked-section analysis are future work.
- SLS stress result tables report stress type, limit, utilization, PASS/FAIL status, message, and section basis.
- SLS summaries identify overall status, governing combo, governing point, maximum compression/tension stress, maximum utilization, no-tension violations, decompression violations, compression failures, and tension failures.
- Critical point filtering supports checking all default points or extreme fibers only.
- SLS Verification / Stress Sign Benchmarks run deterministic checks for axial compression sign, Mux/Muy bending signs, eccentric prestress signs, transformed-section stress behavior, no-tension/decompression judgement, and governing SLS result selection.
- SLS verification results can be exported as `sls_verification_results.csv`.
- Cracking / tension-zone classification uses existing elastic SLS stress results to identify compression, zero stress, tension within limit, tension limit exceedance, no-tension violation, and decompression violation.
- Crack classification summaries report overall classification, governing combo, governing point, maximum tension stress, and tension point count.
- Critical point filtering is respected by the crack classification workflow; `extreme_fibers_only` excludes centroid/reference points from governing classification.
- Cracking classification results can be exported as `sls_cracking_classification.csv`.
- Milestone 4.7 does not perform cracked-section stress redistribution, cracked transformed neutral-axis iteration, or crack-width checks.
- Users can define additional SLS stress check points beyond the default top, bottom, left, right, and centroid/reference points.
- Custom stress point types include tendon zone, web-flange junction, reentrant corner, construction joint, segmental joint, and custom.
- Custom stress check points are validated against the concrete section geometry; points outside concrete or inside voids are rejected for analysis until fixed.
- Custom points can be included or excluded from governing serviceability summaries while still appearing in stress result tables.
- Custom stress check point metadata is included in SLS stress results and cracking/tension classification tables.
- Stress check point lists can be exported as `sls_stress_check_points.csv`.
- SLS stress visualization plots the concrete section outline, holes/voids, default stress check points, and custom stress check points for a selected SLS combo.
- Stress plot markers are colored by PASS/FAIL status, compression/tension state, and cracking/tension classification overlay.
- Stress point hover text reports total, external, and prestress stress, status, utilization, point type/source, governing flag, and classification message.
- A selected-combo SLS stress bar diagram shows compression as negative and tension as positive with a zero-stress reference line.
- Selected combo visualization data can be exported as `sls_stress_visualization_selected_combo.csv`.
- SLS stress visualization is based on selected stress check points, not a full stress contour.
- Effective bonded prestress can be included in elastic SLS stress using existing `Pe_eff`, initial stress, or initial strain values from `PrestressElement`.
- Elastic SLS stress output reports section basis, external stress, prestress stress, and total stress separately; status and utilization use total stress.
- Prestress effective force is treated as compression on the concrete/member, with eccentricity moments from tendon location relative to the selected section-basis centroid.
- SLS prestress eccentric moment signs follow `Mpe_x = -sum(Pe * (y_ps - cy))` and `Mpe_y = -sum(Pe * (x_ps - cx))`, so a tendon located near a fiber increases compression at that same fiber.
- Unbonded prestress is ignored in SLS stress checks with a clear warning.
- Prestress losses, secondary effects, tendon profile variation along the member length, cracking, and crack widths are not calculated in the SLS check.
- Prestress service contribution summary and CSV export report bonded count, ignored unbonded count, total `Pe_eff`, prestress centroid, and `Mpe_x` / `Mpe_y`.
- Elastic SLS stress results can be exported as `sls_elastic_stress_results.csv`.
- Concrete elastic modulus can be estimated with `Ec = 4700 * sqrt(f'c)` for normal-weight concrete or overridden with a user-defined Ec.
- Modular ratio helpers compute `n_s = Es/Ec` for ordinary rebar and `n_p = Ep/Ec` for prestressing steel.
- Uncracked transformed section properties are available for concrete + ordinary rebar + bonded prestress using the `net_steel` transformed area convention.
- Ordinary rebar transformed contribution uses `(n_s - 1) * As`; bonded prestress contribution uses `(n_p - 1) * Aps`.
- Transformed section output includes transformed area, centroid, `Ix`, `Iy`, `Ixy`, rebar contribution, prestress contribution, counts, warnings, and CSV export.
- User can choose gross section basis or uncracked transformed section basis for elastic SLS stress checks.
- Transformed SLS stress uses transformed area, centroid, `Ix`, and `Iy`; full unsymmetric `Ixy` stress coupling is still a future refinement.
- Cracked section analysis, crack-width checks, and unbonded prestress serviceability modeling are future work.
- Rebar tab foundation with manual coordinate input.
- Rebar database in `data/rebar_database.csv`.
- Rebar validation against the current `SectionGeometry`, including outside-concrete and inside-void checks.
- Rebar summary with active bar count and total `As`.
- Rebar hotfix behavior: database Bar Size takes precedence over manual diameter, while `Custom` uses manual `Diameter_mm`.
- `st.session_state["rebars_valid_for_analysis"]` indicates whether parsed rebars are free of parse and geometry errors.
- Prestress tab foundation with manual input for wire, strand, prestressing bar/PT bar, tendon group, and custom prestress steel.
- Prestress input modes: Passive, Effective Force Pe, Effective Stress fpe, and Jacking Stress + Losses.
- `Pe_eff_kN` is the user-facing prestress force input for Effective Force Pe mode.
- Internal prestress force remains stored as `pe_eff_n` in N.
- Effective Force Pe is checked against `fpu_MPa`; values that create initial stress greater than `fpu_MPa` are rejected.
- Prestress elements store `pe_eff_n`, initial stress, and initial strain for future PMM analysis.
- Bonded defaults to `True`; select `False` only for unbonded prestressing steel.
- Bonded prestress can be included in the PMM prototype; unbonded prestress is still ignored with a clear warning.
- Project tab foundation for project-level information, JSON save, JSON load, and project summary.
- `ProjectModel` stores section preset data, generated section geometry, materials when available, load cases, rebars, and prestress elements.
- Project JSON loading restores core model objects into `st.session_state` for review in the existing tabs.
- Materials tab foundation for concrete, rebar, and prestressing steel material input.
- Concrete material input includes `f'c`, `ecu`, density, and beta1 with ACI auto/manual modes.
- Rebar material input supports project material lists such as SD40 and SD50.
- Prestressing steel material input supports wire, strand, prestressing bar/PT Bar, tendon group, and custom steel.
- PT Bar / Prestressing Bar material properties include `fpu`, optional `fpy`, `Ep`, area, diameter, grade, source, and catalog verification metadata.
- `aci_beta1(fc_MPa)` helper is available for future ACI 318 workflows.
- Analysis settings are captured for the future PMM workflow, including code, strength load type, inclusion flags, phi-factor flag, and neutral-axis step counts.
- Analysis readiness / preflight checks validate that section geometry, concrete material, ULS load cases, rebars, prestress elements, and material lists are ready enough for future analysis.
- `AnalysisInput` is the intended future PMM solver input container. Future solver code should consume `AnalysisInput`, not direct Streamlit session data.
- PMM Solver Prototype generates a nominal and phi-reduced PMM point cloud from concrete, ordinary reinforcing bars, and optional bonded prestress.
- The solver consumes `AnalysisInput`; it does not read Streamlit `session_state`.
- Concrete compression uses a Whitney stress block with Shapely polygon clipping for arbitrary section geometry.
- Ordinary rebar uses linear strain compatibility with elastic-perfectly-plastic stress capped at `fy`.
- Ordinary rebar inside the Whitney compression block can use net replacement force `As(fs - 0.85f'c)` to avoid double counting concrete compression already included in the stress block.
- Ordinary rebar outside the compression block remains `As*fs`.
- Analysis Settings includes a toggle, `Subtract displaced concrete at rebar locations`, which is enabled by default and preserved in Project JSON.
- PMM results include rebar displaced-concrete subtraction and inside-compression-block counts for engineering review.
- Prestressing steel / PT Bar displaced concrete subtraction is not included yet; this refinement applies to ordinary rebar only.
- Bonded prestress contribution prototype supports wire, strand, prestressing bar/PT Bar, tendon group, and custom `PrestressElement` through the same common interface.
- Bonded prestress uses stored `initial_strain`, or converts `initial_stress_mpa` / `pe_eff_n` to initial strain when needed.
- Prototype prestress stress uses `eps_ps,total = eps_pe - eps_section`, where positive section compression reduces tendon tensile strain and section tension increases tendon tensile strain.
- Prestress stress models are selectable in Analysis settings: `bilinear` and `linear_cap`.
- `linear_cap` uses elastic `Ep * eps` stress capped between zero and `fpu`.
- `bilinear` uses `fpy` / proof stress when available, then a prototype post-yield slope before capping at `fpu`.
- If `fpy` / proof stress is missing for the bilinear model, the solver falls back to the linear capped prestress model with a clear warning.
- PT Bar / `prestressing_bar` inputs warn when `fpy_MPa` / proof stress is missing, close to `fpu_MPa`, or lower than initial prestress stress.
- Compression reversal of prestressing steel is still not fully modeled; negative total tensile strain is clamped to zero with a warning.
- PMM result data includes prestress stress model, stress warning count, maximum prestress stress, and fpu-cap count where applicable.
- Prestress sign convention checks verify that section compression strain reduces tendon tensile strain and section tension strain increases tendon tensile strain.
- Prestress PMM verification tools check bonded/unbonded status, material strengths, initial stress/strain, `Pe_eff`, and PT Bar proof stress availability before analysis review.
- Prestress Analysis Check Table is available in the Analysis tab with OK, WARNING, ERROR, and IGNORED statuses.
- PT Bar / `prestressing_bar` analysis checks warn when proof/yield stress (`fpy_MPa`) is missing.
- RC-only versus RC + bonded prestress comparison is generated when bonded prestress is included.
- Prestress contribution summary reports included bonded count, ignored unbonded count, total bonded `Aps`, total `Pe_eff`, max absolute prestress force, and mean absolute prestress force.
- Compression reversal of prestressing steel, bonded prestress production validation, and unbonded prestress models are future work.
- ACI axial cap still uses RC `Po` only; prestress contribution to axial cap is future work.
- Report export and advanced serviceability checks remain future milestones.
- Analysis settings include tied or spiral transverse reinforcement for prototype phi-factor and axial-cap behavior.
- RC PMM axial strength cap refinement adds ACI-style tied and spiral cap factors.
- Tied columns use a prototype maximum axial cap factor of 0.80 with compression-controlled phi of 0.65.
- Spiral columns use a prototype maximum axial cap factor of 0.85 with compression-controlled phi of 0.75.
- PMM results include capped `phiPn` values for axial compression display and axial-only checks.
- RC PMM visualization displays engineering-unit summaries in kN and kN-m.
- Analysis results include P-Mnx, P-Mny, Mnx-Mny, and 3D point-cloud Plotly charts.
- Active ULS demand points are displayed and overlaid for visual reference only.
- RC PMM result CSV export is available with both internal-unit and display-unit columns.
- Lightweight solver verification helpers summarize point count, phi range, NaN/Inf status, and envelope extremes.
- RC ULS demand/capacity prototype checks active ULS load cases using `Pu`, `Mux`, and `Muy`.
- The prototype estimates directional moment capacity from the PMM point cloud at the demand axial load.
- D/C ratio is reported as demand moment magnitude divided by estimated phi-reduced directional moment capacity.
- Results include PASS, FAIL, OUT_OF_RANGE, or NOT_CHECKED status plus governing combo and maximum D/C ratio.
- Axial-only ULS D/C checks use capped maximum axial capacity when available.
- Directional moment D/C still uses prototype point-cloud interpolation and does not apply a full axial-cap interaction modification yet.
- PMM Slice Dashboard adds an active ULS load case selector for reviewing a Mux-Muy capacity slice at the selected Pu.
- The dashboard shows the selected demand point, demand vector, and load case D/C status on the Mux-Muy slice.
- A 3D PMM interaction dashboard displays the PMM point cloud, active ULS load points, selected load point, and current Pu slice.
- PMM Summary Card reports selected combo, Pu, Mux, Muy, resultant Mu, available phiMn at Pu, status, D/C ratio, analysis mode, and prestress inclusion state.
- Load case D/C ranking sorts governing demand cases for engineering review.
- PMM slice visualization is based on the current prototype PMM point-cloud interpolation; final production interpolation and validation remain future work.
- PMM verification / benchmark suite builds rectangular RC benchmark cases directly as `AnalysisInput` objects.
- Benchmark cases include base RC, higher `f'c`, higher `As`, RC + bonded PT Bar, and matching RC-only cases.
- Verification checks confirm finite PMM results, positive axial capacity, higher `f'c` capacity increase, higher `As` non-reduction, and symmetric positive/negative bending balance.
- Verification checks include rebar displaced-concrete behavior, including net force reduction inside the compression block, unchanged force outside the block, and PMM comparison with the toggle enabled/disabled.
- Independent PMM hand-calculation spot checks are available for engineering review.
- Hand checks include RC axial compression `Po` and `phiPn,max`, rebar displaced-concrete spot checks, prestress strain convention checks, prestress stress model checks, a simplified uniaxial RC strain compatibility point, and symmetry sanity checks.
- Hand check results can be displayed and exported to CSV from the Analysis tab verification expander.
- Hand checks are simplified spot checks and do not replace full independent validation or code-certified design software.
- RC-only versus RC + bonded PT Bar benchmark comparison confirms bonded prestress changes the PMM result and produces nonzero prestress force.
- Unbonded prestress ignore behavior is checked to preserve current solver scope.
- Analysis tab includes a compact `PMM Verification / Benchmark Checks` expander with PASS / WARNING / FAIL results.
- Verification suite results support engineering review but do not replace independent validation or final design certification.
- Refined PMM slice interpolation builds selected-Pu Mux-Muy slices by interpolating along each neutral-axis `theta_rad` / `c_mm` PMM point family.
- The previous tolerance-based `pmm_slice_at_pu_tolerance()` method remains available as a fallback when interpolation data is missing or too sparse.
- Preferred `pmm_slice_at_pu()` now attempts `pmm_slice_at_pu_interpolated()` first and records slice method, skipped theta count, interpolated theta count, and warnings in dataframe attrs.
- Directional ULS D/C prototype now prefers capacity from the interpolated PMM slice at demand `Pu`, then falls back to the previous point-cloud interpolation when needed.
- PMM dashboard slice plots display whether the selected Pu slice is interpolated or a tolerance fallback.
- PMM Summary Card includes slice method and D/C method so users can see how the prototype value was obtained.
- Verification suite checks that interpolated slices are available for benchmark results and that directional capacity from the slice is finite.
- PMM slice envelope processing cleans duplicate/noisy Mux-Muy slice points before plotting and directional D/C checks.
- `SliceEnvelopeResult` reports input/output point counts, envelope method, validity, warnings, self-crossing detection, and convex-hull fallback state.
- Envelope cleanup computes polar angle/radius, removes near-duplicate angles while keeping the largest radius, and checks angular coverage, radius jumps, and self-crossing risk.
- Convex hull fallback is available for visualization safety and always warns that it may overestimate non-convex interaction shapes.
- Directional ULS D/C now prefers the cleaned PMM slice envelope, then falls back to direct interpolated slice and point-cloud directional methods when needed.
- PMM dashboard plots raw slice points lightly and the cleaned envelope boundary as the main curve.
- PMM Summary Card now reports envelope method, envelope validity, convex hull fallback state, and boundary warning count.
- Verification suite includes envelope availability, finite radius, directional envelope capacity, envelope D/C, and convex hull fallback checks.
- Numerical cleanup removes pandas downcasting `FutureWarning` risk in PMM result display conversion by using explicit numeric handling.
- Neutral-axis depth sweep now uses a relative lower bound, `c_min = max(1 mm, 0.001 * projected depth)`, for improved numerical robustness.
- PMM result numerical summaries use vectorized NaN/Inf checks instead of flattening all numeric values into Python lists.
- Slice envelope angular coverage warnings are tuned: limited coverage and moderate coverage are warnings for review, not automatic invalidation by themselves.
- Code-quality cleanup keeps slice duplicate checks readable and avoids repeated lazy imports inside active load-case loops.
- Standardized prototype warning constants centralize PMM prototype, D/C prototype, bonded prestress, unbonded prestress, serviceability, report export, convex hull fallback, and RC axial cap limitation wording.
- D/C result rows include method metadata: capacity method, slice method, envelope method, fallback state, and warning count.
- ULS D/C result CSV export is available for engineering-unit review.
- Selected PMM slice and selected slice envelope CSV exports are available from the PMM Slice Dashboard.
- Analysis tab groups engineering warnings from PMM results, prestress checks, D/C checks, and selected slice/envelope review while preserving warning order and removing duplicates.
- Lightweight PMM dataframe numerical checks report row count, NaN/Inf columns, envelope magnitude summaries, and warnings without changing solver output.
- Active SLS load cases can be checked with gross-section or uncracked transformed-section elastic concrete stress, including no-tension/decompression judgement, SLS sign benchmark verification, and cracking/tension-zone classification from selected check points; cracked-section redistribution remains future work.
- Final production PMM interpolation and design certification are future work.

## Prestressing Steel Database

`data/prestress_steel_database.csv` is the single prestressing steel database. It includes strand rows and generated high-strength prestressing bar rows with metadata columns:

- `source`
- `area_source`
- `is_catalog_verified`

Prestressing bar areas are initially generated from `pi*d^2/4`. Manufacturer catalog values should override generated areas when available.

## Run

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Test

```powershell
python -m pytest -q
```

## Architecture Notes

The Section Builder does not hard-code parameter inputs per section type. It reads category, preset, and parameter definitions from `data/section_presets.json` and generates controls dynamically.

All section presets are converted to `SectionGeometry` before future analysis. Future PMM solver code should consume `SectionGeometry` or `SectionModel` only, not preset names or UI metadata.

Load cases are stored in internal units before analysis. `Pu_N`, `Mux_Nmm`, and `Muy_Nmm` are the primary names for new data. Older project JSON using `Mx_Nmm` / `My_Nmm` is migrated on load.

Rebars are stored as `Rebar` objects in `st.session_state["rebars"]`. They are previewed on the current section geometry and used by the PMM prototype when included in analysis settings.

Prestress elements are stored as `PrestressElement` objects in `st.session_state["prestress_elements"]`. `Pe_eff_kN` from the UI is converted to internal `pe_eff_n`, and initial strain is stored for PMM analysis. Bonded prestress is included by the current PMM prototype when `include_prestress = True`; unbonded prestress is ignored with warning because its separate model is future work.

Project files are serialized through `ProjectModel` as JSON. Save/load is intended to preserve the current data foundation for later analysis milestones, including `analysis_settings` and `serviceability_settings`; it does not automatically trigger capacity or serviceability stress calculation.

Analysis mode settings are stored as `AnalysisModeSettings` and persisted in Project JSON. The Analysis tab can identify the current workflow as Column / Pier / Wall / Pylon PMM Mode, Beam / Girder Future Mode, or General Section Mode. Column/Pier mode keeps the existing PMM interaction workflow as the primary path. Beam/Girder mode is only a placeholder and warns that future flexure, shear, torsion, transfer-stage, service-stage, and tendon-profile checks are not implemented yet. General Section mode keeps PMM and SLS tools available for careful section-level review. The helper module `concrete_pmm_pro/core/analysis_modes.py` centralizes labels, descriptions, workflow flags, and warnings, including the reminder not to double-count prestress as `Pu`.

Pre-report QA helpers live in `concrete_pmm_pro/reporting/`. Milestone A.3 adds result traceability snapshots, report readiness checks, engineering warning consolidation, standard terminology, unit convention tables, and an available figure registry foundation. Milestone A.3.1 adds `reporting/limitations.py`, an engineering limitations registry covering `Ixy` coupling, directional D/C interpolation, convex hull fallback, neutral-axis sweep resolution, cracked-section future work, prestress axial cap limitation, prestress compression reversal, unbonded prestress, crack width future work, beam/girder future checks, lightweight concrete Ec, and ultimate concrete strain code-basis review. Milestone A.3.2 fixes filtered limitations so HIGH and CRITICAL items remain visible when `include_all=False`, and narrows defensive Shapely exception handling without changing geometry behavior. Milestone A.3.2.1 adds branch coverage for Beam/Girder filtering and clarifies filtered MEDIUM limitation rules. Milestone A.3.2.2 adds coverage for alternate D/C context keys, cracking context through `crack_classification_summary`, and defensive truthiness handling that does not infer context when `bool(value)` raises. Milestone 5.0 adds report foundation files for metadata, section planning, table registry, figure registry, manifest JSON, and draft outline generation. Milestone 5.1 adds report figure export preparation through `ReportFigureContext`, `ReportFigureExportItem`, safe filenames, Plotly HTML export, optional `kaleido` PNG export, and export-ready SLS figure reconstruction from existing session results. Milestone 5.2 removes the duplicate SLS bar-chart export path, improves PMM figure context/readiness, and enables PMM Mux-Muy slice and slice-envelope export when stored dashboard dataframes already exist. Milestone 5.3 adds draft Word report export using `ReportManifest`, with metadata, traceability, readiness, warnings, limitations, units, terminology, tables, and export-ready figures when PNG export is available. Milestone 5.4 polishes the Word report with improved cover/executive summary styling, high/critical limitation emphasis, warning presentation, table truncation policy, figure captions/placeholders, report generation notes, and `ReportExportOptions`. Milestone 5.5 adds `reporting/report_qa.py` for Word report QA, including heading, disclaimer, limitation, warning, unit, terminology, traceability, figure/table, and misleading-certification wording checks. The Analysis tab can export CSV files for `result_traceability_snapshot.csv`, `report_readiness.csv`, `engineering_warnings.csv`, `engineering_limitations.csv`, `unit_conventions.csv`, `standard_terminology.csv`, `available_report_figures.csv`, `report_section_plan.csv`, `report_tables.csv`, `report_figures.csv`, `report_figure_export_registry.csv`, and `word_report_qa.csv`, plus `report_manifest.json`, `draft_report_outline.txt`, and `concrete_pmm_pro_draft_report.docx`. These helpers summarize existing session results only; they do not recalculate PMM/SLS results and do not generate PDF reports yet.

Materials are stored as `ConcreteMaterial`, `RebarMaterial`, and `PrestressSteelMaterial` objects. Project JSON preserves the active concrete material, rebar material list, prestressing steel material list, and active material names. PT Bar / Prestressing Bar elements are supported through `PrestressElement`; effective prestress force is defined in the Prestress tab.

Analysis settings are stored as `AnalysisSettings`, including tied/spiral transverse reinforcement and the `include_prestress` flag. Preflight builds an `AnalysisInput` object only when readiness errors are resolved. The Analysis tab can run the RC-only prototype or the RC + bonded prestress prototype, show point-cloud plots, export CSV results, run a prototype ULS demand/capacity check, review selected ULS cases in the PMM Slice Dashboard, and run benchmark-style verification checks.

Serviceability settings are stored as `ServiceabilitySettings`. The Analysis tab includes a `Serviceability / SLS Foundation` expander that prepares active SLS load tables, gross section properties, transformed section properties, default/custom stress check points, and elastic SLS stress checks. Milestone A.2 persists custom SLS stress check points through Project JSON, including inactive rows and non-governing flags, and restores them into the editable table after project load. The SLS display convention is compression negative and tension positive. Users can select gross section basis or uncracked transformed section basis; transformed stress uses the selected basis area, centroid, `Ix`, and `Iy`. Effective prestress is treated as compressive action on concrete. When enabled, effective bonded prestress contributes elastic SLS stress using the same selected section-basis centroid and inertia plus existing `Pe_eff`, initial stress, or initial strain from the Prestress tab; losses are not recalculated in the SLS check. Eccentric prestress induces equivalent service moments `Mpe_x = -sum(Pe * (y_ps - cy_basis))` and `Mpe_y = -sum(Pe * (x_ps - cx_basis))`, which means a tendon located near a fiber increases compression at that same fiber. No-tension and decompression checks fail when tensile stress is greater than the selected zero-stress tolerance. Decompression in Milestone 4.5 is a no-tension point-stress check, not a full tendon-zone or cracked-section decompression analysis. Milestone 4.6 adds `concrete_pmm_pro/verification/sls_benchmarks.py` for SLS sign and benchmark checks covering axial compression, biaxial bending sign, eccentric prestress sign, transformed section behavior, no-tension/decompression judgement, and governing SLS result selection; results can be exported as `sls_verification_results.csv`. Milestone 4.7 adds `concrete_pmm_pro/serviceability/cracking.py` for tension/cracking risk classification from existing SLS stress results, including tension-limit exceedance, no-tension violation, decompression violation, critical point filtering, and `sls_cracking_classification.csv` export. Milestone 4.8 adds `concrete_pmm_pro/serviceability/points.py` for custom SLS stress check point parsing, section/void validation, default/custom point merging, governing inclusion metadata, and `sls_stress_check_points.csv` export. Milestone 4.9 adds `concrete_pmm_pro/visualization/sls_stress.py` for selected-combo SLS section stress plots, stress point hover data, cracking/tension overlay fields, stress bar diagrams, and `sls_stress_visualization_selected_combo.csv` export. The current serviceability workflow does not perform full cracked-section stress redistribution, crack-width checks, unbonded prestress serviceability modeling, full unsymmetric `Ixy` stress coupling, full stress contours, or report export yet.

The PMM prototype uses this sign convention: compression force is positive, steel/prestress tension force is negative, x is positive to the right, y is positive upward, `Mnx = sum(F * (y - y_ref))`, and `Mny = sum(F * (x - x_ref))`. Section strain is positive in compression and negative in tension. Prestress initial strain is positive in tendon tension. Bonded prestress total tensile strain is modeled as `eps_ps,total = eps_pe - eps_section`, so compression strain at the tendon reduces tendon tensile strain and tension strain increases it. Prestressing steel stress is modeled as a tensile magnitude, then converted to tension-negative section force. Compression reversal of prestressing steel is future work. Demand naming remains separate: `Mux` and `Muy` are demand inputs, while `Mnx` and `Mny` are nominal resistance outputs.

PMM result display helpers convert internal `N` and `N-mm` values to `kN` and `kN-m` for review. The display dataframe includes `phiPn_capped_N`, `phiPn_capped_kN`, `prestress_force_N`, `prestress_force_kN`, prestress included/ignored counts, `rebar_displaced_concrete_subtracted_N`, `rebar_displaced_concrete_subtracted_kN`, and `rebar_inside_compression_count`. Ordinary rebar inside the Whitney compression block uses `As(fs - 0.85f'c)` when the Analysis Settings toggle is enabled, while prestressing steel still uses its separate prototype stress-strain path without displaced-concrete subtraction. The ULS D/C prototype now prefers a cleaned selected-Pu slice envelope built from interpolated theta-family PMM slice points, then estimates directional capacity in polar Mux-Muy space. If envelope capacity cannot be used, the workflow falls back to direct interpolated-slice and point-cloud methods with warnings. Axial-only D/C uses capped maximum phiPn. D/C display tables and CSV export identify capacity method, slice method, envelope method, fallback state, and warning count. The PMM Slice Dashboard reuses the same prototype point cloud to show raw slice points, cleaned envelope boundary, demand vector, 3D PMM interaction view, PMM summary card, D/C ranking table, selected slice CSV export, and selected envelope CSV export. The PMM verification suite in `concrete_pmm_pro/verification/pmm_benchmarks.py` runs benchmark-style sanity checks on rectangular RC and RC + bonded PT Bar cases, including interpolated slice availability, envelope robustness, directional capacity checks, and displaced-concrete toggle comparisons. The independent hand-check suite in `concrete_pmm_pro/verification/hand_checks.py` compares selected solver behavior against simplified hand calculations for axial compression, rebar displaced concrete, prestress strain/stress conventions, uniaxial RC strain compatibility, and symmetry sanity; results can be exported as `pmm_hand_check_results.csv` from the Analysis tab. The SLS benchmark suite in `concrete_pmm_pro/verification/sls_benchmarks.py` verifies compression-negative/tension-positive stress signs, gross/transformed stress behavior, eccentric prestress sign, no-tension/decompression judgement, governing SLS selection, crack classification checks, and custom SLS stress point behavior; results can be exported as `sls_verification_results.csv`. Cracking classification uses existing SLS stress results only, supports `all` or `extreme_fibers_only` critical point filtering, and exports `sls_cracking_classification.csv`. Custom SLS stress check points can represent tendon zones, web-flange junctions, segmental joints, construction joints, reentrant corners, or general custom review points; invalid geometry is reported before analysis and governing inclusion can be disabled per point. SLS stress visualization plots selected-combo stress check points on the section outline with holes/voids, custom point metadata, status/classification marker colors, hover details, and an optional stress bar diagram; visualization data exports as `sls_stress_visualization_selected_combo.csv`. Directional moment D/C, warning summaries, numerical checks, benchmark checks, hand checks, SLS verification checks, cracking classification, custom SLS point checks, SLS stress visualization, and elastic SLS stress/no-tension/decompression checks remain prototype engineering review tools only; final production validation, unbonded prestress, report export, cracked-section stress redistribution, crack-width checks, full transformed/cracked serviceability refinements, and prestress loss/profile effects are future work.


## Solver validation direction

Concrete PMM Pro now includes a PMM solver validation framework and the first executable RC-only benchmark pack:

- `QA.VALIDATION1` — validation matrix / report structure
- `VALID.RC1` — rectangular RC PMM benchmark pack with axial-cap, uniaxial bending, symmetry, and numeric-schema checks

These validation assets are not a final certification. They are the project control system for reducing prototype warnings only when benchmark evidence supports the change.
