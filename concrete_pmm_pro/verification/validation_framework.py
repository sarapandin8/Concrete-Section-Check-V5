"""Validation framework metadata and runners for Concrete PMM Pro.

This module is intentionally separate from the Streamlit UI.  It records the
engineering validation matrix that must be satisfied before PMM warnings can be
reclassified from prototype/development warnings to documented method notes.

The framework does not certify the solver.  It gives the project a stable,
testable structure for growing from prototype checks toward commercial-grade
verification discipline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from concrete_pmm_pro.verification.hand_checks import HandCheckSummary, run_independent_hand_check_suite
from concrete_pmm_pro.verification.pmm_benchmarks import PMMVerificationSummary, run_pmm_verification_suite
from concrete_pmm_pro.verification.rc_rectangular_benchmarks import RCBenchmarkSummary, run_valid_rc1_benchmark_pack
from concrete_pmm_pro.verification.rc_phi_transition_benchmarks import run_valid_rc2_phi_transition_benchmark_pack
from concrete_pmm_pro.verification.ps_bonded_benchmarks import PSBenchmarkSummary, run_valid_ps1_bonded_prestress_benchmark_pack
from concrete_pmm_pro.verification.ps_stress_region_benchmarks import (
    PSStressRegionSummary,
    run_valid_ps2_stress_region_benchmark_pack,
)
from concrete_pmm_pro.verification.ps_passive_benchmarks import (
    PSPassiveBenchmarkSummary,
    run_valid_ps_passive_benchmark_pack,
)
from concrete_pmm_pro.verification.dc_directional_benchmarks import (
    DCDirectionalBenchmarkSummary,
    run_valid_dc1_directional_benchmark_pack,
)
from concrete_pmm_pro.verification.po_axial_cap_benchmarks import (
    POAxialCapSummary,
    run_valid_po1_axial_cap_benchmark_pack,
)
from concrete_pmm_pro.verification.pmm_final_rc1_benchmarks import (
    PMMFinalRC1Summary,
    run_pmm_final_rc1_readiness_gate,
)

ValidationStatus = Literal["implemented", "partial", "planned"]
ValidationCategory = Literal[
    "RC-only PMM",
    "Prestress PMM",
    "Custom shape PMM",
    "Demand/Capacity",
    "Numerical robustness",
    "Warning policy",
]


@dataclass(frozen=True)
class ValidationCaseSpec:
    """A documented validation case or validation gap.

    ``status`` describes validation coverage, not solver pass/fail.  A case can
    be implemented while its latest numeric result is PASS/WARNING/FAIL in the
    underlying test runner.
    """

    case_id: str
    title: str
    category: ValidationCategory
    status: ValidationStatus
    purpose: str
    acceptance: str
    source: str
    current_location: str
    next_action: str = ""
    warnings_addressed: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PMMSolverValidationReport:
    """Combined PMM validation report assembled from current validation runners."""

    validation_cases: list[ValidationCaseSpec]
    hand_checks: HandCheckSummary
    pmm_checks: PMMVerificationSummary
    rc_benchmarks: RCBenchmarkSummary
    rc_phi_transition: RCBenchmarkSummary
    ps_benchmarks: PSBenchmarkSummary
    ps_stress_regions: PSStressRegionSummary
    ps_passive: PSPassiveBenchmarkSummary
    dc_directional: DCDirectionalBenchmarkSummary
    po_axial_cap: POAxialCapSummary
    pmm_final_rc1: PMMFinalRC1Summary

    @property
    def implemented_case_count(self) -> int:
        return sum(case.status == "implemented" for case in self.validation_cases)

    @property
    def partial_case_count(self) -> int:
        return sum(case.status == "partial" for case in self.validation_cases)

    @property
    def planned_case_count(self) -> int:
        return sum(case.status == "planned" for case in self.validation_cases)

    @property
    def overall_execution_status(self) -> str:
        """Return the worst current status from executable validation runners."""

        statuses = {
            self.hand_checks.overall_status,
            self.pmm_checks.overall_status,
            self.rc_benchmarks.overall_status,
            self.rc_phi_transition.overall_status,
            self.ps_benchmarks.overall_status,
            self.ps_stress_regions.overall_status,
            self.ps_passive.overall_status,
            self.dc_directional.overall_status,
            self.po_axial_cap.overall_status,
            self.pmm_final_rc1.overall_status,
        }
        if "FAIL" in statuses:
            return "FAIL"
        if "WARNING" in statuses:
            return "WARNING"
        return "PASS"


def build_pmm_solver_validation_matrix() -> list[ValidationCaseSpec]:
    """Return the project-level PMM solver validation matrix.

    The matrix deliberately includes implemented, partial, and planned cases so
    warning cleanup remains tied to engineering evidence instead of cosmetic UI
    changes.
    """

    return [
        ValidationCaseSpec(
            case_id="VALID.RC.PO1",
            title="RC concentric axial compression and phiPn cap",
            category="RC-only PMM",
            status="implemented",
            purpose="Check ordinary RC Po, maximum phiPn cap, and rebar displaced-concrete subtraction against independent hand formulas.",
            acceptance="Hand Po / phiPn values match within documented tolerance; solver max capped phiPn is positive and below Po-like upper bound.",
            source="Independent hand formulas and PMM benchmark suite.",
            current_location="concrete_pmm_pro/verification/hand_checks.py; tests/test_pmm_benchmarks.py",
            next_action="Add published-code benchmark examples before removing prototype wording from reports.",
            warnings_addressed=("ACI axial cap", "rebar displaced concrete"),
        ),
        ValidationCaseSpec(
            case_id="VALID.RC1",
            title="Rectangular RC PMM benchmark pack",
            category="RC-only PMM",
            status="implemented",
            purpose="Validate a simple rectangular RC section against independent axial-cap, uniaxial bending, biaxial bending, symmetry, and numeric-schema checks before lowering RC-only prototype warnings.",
            acceptance="All VALID.RC1 checks pass or remain within documented prototype tolerances; capacity-critical columns contain no NaN/Inf values.",
            source="Independent rectangular stress-block hand formulas plus PMM solver benchmark runner.",
            current_location="concrete_pmm_pro/verification/rc_rectangular_benchmarks.py; tests/test_valid_rc1_benchmarks.py",
            next_action="Add published-code reference examples for uniaxial and biaxial bending before any final certification wording is considered.",
            warnings_addressed=("PMM prototype", "RC strain compatibility", "NaN capacity fields"),
        ),
        ValidationCaseSpec(
            case_id="VALID.RC.MX1",
            title="RC rectangular uniaxial bending spot check",
            category="RC-only PMM",
            status="implemented",
            purpose="Compare a selected rectangular RC neutral-axis state against an independent concrete-block plus rebar-force hand calculation.",
            acceptance="Pn and Mnx are within benchmark tolerance for the selected neutral-axis state.",
            source="Independent hand spot calculation and VALID.RC1 benchmark pack.",
            current_location="concrete_pmm_pro/verification/hand_checks.py; concrete_pmm_pro/verification/rc_rectangular_benchmarks.py",
            next_action="Add at least one published reference example for Mx and My bending.",
            warnings_addressed=("PMM prototype", "strain compatibility"),
        ),
        ValidationCaseSpec(
            case_id="VALID.RC.BIAX1",
            title="RC rectangular biaxial symmetry sanity",
            category="RC-only PMM",
            status="partial",
            purpose="Check that symmetric geometry/rebar layout produces reasonably balanced positive/negative Mx and My envelopes.",
            acceptance="Positive/negative capacity imbalance remains within discretization tolerance.",
            source="Benchmark symmetry checks.",
            current_location="concrete_pmm_pro/verification/pmm_benchmarks.py",
            next_action="Add published biaxial PMM reference examples and RC-specific directional D/C checks.",
            warnings_addressed=("PMM point cloud", "directional capacity"),
        ),

        ValidationCaseSpec(
            case_id="VALID.RC2",
            title="RC phi transition and tension-control benchmark pack",
            category="RC-only PMM",
            status="implemented",
            purpose="Validate ACI-style phi classification for compression-controlled, transition, and tension-controlled RC section states before reducing phi/prototype warnings.",
            acceptance="Direct phi helper spot checks pass; the rectangular RC PMM sweep samples all phi regions; each solver point matches the independent phi helper classification.",
            source="ACI-style phi helper reference and rectangular RC PMM sweep.",
            current_location="concrete_pmm_pro/verification/rc_phi_transition_benchmarks.py; tests/test_valid_rc2_phi_transition.py",
            next_action="Add published-code examples documenting phi transition behavior for final validation notes.",
            warnings_addressed=("phi transition", "tension-controlled", "compression-controlled", "eps_t"),
        ),
        ValidationCaseSpec(
            case_id="PMM.FINAL.RC1.SCOPE",
            title="ACI RC PMM final-readiness scope gate",
            category="RC-only PMM",
            status="implemented",
            purpose="Lock the ACI RC-only scope for Column/Pier/Wall/Pylon Flexural PMM final-readiness before any UI/report wording is upgraded.",
            acceptance="The gate explicitly excludes prestress, AASHTO LRFD PMM, shear, torsion, SLS, detailing, slenderness, and second-order effects.",
            source="PMM.FINAL.RC1 design gate and existing analysis-mode capability guards.",
            current_location="docs/design/pmm_final_rc1.md; concrete_pmm_pro/core/design_code.py; concrete_pmm_pro/ui/analysis_page.py",
            next_action="Keep this gate in force after PMM.FINAL.RC1.CLOSEOUT; do not expand beyond ACI RC PMM without a new named solver/validation milestone.",
            warnings_addressed=("prototype wording", "AASHTO PMM guard", "scope control"),
        ),
        ValidationCaseSpec(
            case_id="PMM.FINAL.RC1.UNIAXIAL.REF",
            title="Traceable ACI RC uniaxial PMM reference benchmark",
            category="RC-only PMM",
            status="implemented",
            purpose="Promote the current internal rectangular RC spot checks into final-readiness evidence using at least one traceable external or independently derived uniaxial benchmark.",
            acceptance="Solver axial and uniaxial moment capacities match the reference case within documented tolerance without weakening solver equations or validation tolerances.",
            source="VALID.RC1 internal rectangular benchmark and PMM.FINAL.RC1 readiness gate.",
            current_location="concrete_pmm_pro/verification/rc_rectangular_benchmarks.py; concrete_pmm_pro/verification/pmm_final_rc1_benchmarks.py; docs/design/pmm_final_rc1.md",
            next_action="Add a published/reference uniaxial example before any final certification wording is considered.",
            warnings_addressed=("PMM prototype", "RC strain compatibility", "uniaxial benchmark"),
        ),
        ValidationCaseSpec(
            case_id="PMM.FINAL.RC1.BIAXIAL.REF",
            title="Traceable ACI RC biaxial PMM reference benchmark",
            category="RC-only PMM",
            status="implemented",
            purpose="Validate a true biaxial P-Mx-My point before the RC PMM workflow is treated as validated production-preview.",
            acceptance="Solver nominal Pn, Mnx, and Mny for a nonzero biaxial neutral-axis point match the independent rectangular clipping reference within documented tolerance.",
            source="Independent rectangular clipping biaxial PMM reference checks in VALID.RC1.",
            current_location="concrete_pmm_pro/verification/rc_rectangular_benchmarks.py; concrete_pmm_pro/verification/pmm_final_rc1_benchmarks.py; docs/design/pmm_final_rc1.md",
            next_action="Add published biaxial PMM reference examples before any final certification wording is considered.",
            warnings_addressed=("PMM prototype", "directional D/C", "biaxial benchmark"),
        ),
        ValidationCaseSpec(
            case_id="PMM.FINAL.RC1.DC.NO_OVERESTIMATE",
            title="ACI RC PMM D/C no-overestimate final-readiness guard",
            category="Demand/Capacity",
            status="implemented",
            purpose="Ensure the PMM demand/capacity extraction path does not silently overestimate moment capacity when moving toward production-preview wording.",
            acceptance="Ray-envelope D/C is the preferred method; fallback paths remain visible and benchmarked; actual RC rectangular PMM D/C capacity does not exceed the direct slice ray-boundary estimate.",
            source="VALID.PMM.DC1 synthetic ray-envelope checks plus RC rectangular PMM no-overestimate benchmark.",
            current_location="concrete_pmm_pro/analysis/slice_envelope.py; concrete_pmm_pro/verification/dc_directional_benchmarks.py; docs/design/pmm_final_rc1.md",
            next_action="Add published/reference biaxial PMM D/C examples and additional non-rectangular RC benchmark cases before final certification wording.",
            warnings_addressed=("directional D/C", "fallback", "convex hull", "prototype wording"),
        ),
        ValidationCaseSpec(
            case_id="PMM.FINAL.RC1.STATUS.READINESS1",
            title="ACI RC PMM production-preview readiness status audit",
            category="RC-only PMM",
            status="implemented",
            purpose="Decide whether the implemented ACI RC Flexural PMM evidence can support finalized production-preview wording without implying final code certification.",
            acceptance="The readiness gate may report finalized production-preview wording only when scope, uniaxial, biaxial, phi, D/C no-overestimate evidence, and PMM.FINAL.RC1.CLOSEOUT wording guards remain in place.",
            source="PMM.FINAL.RC1 readiness runner and status-readiness design audit.",
            current_location="concrete_pmm_pro/verification/pmm_final_rc1_benchmarks.py; docs/validation/pmm_solver_validation.md; tests/test_pmm_final_rc1_benchmarks.py",
            next_action="Keep PMM.FINAL.RC1.CLOSEOUT guards active; any PMM equation, prestress, AASHTO, shear, torsion, or final-certification change requires a new named milestone.",
            warnings_addressed=("prototype wording", "production-preview readiness", "final certification guard"),
        ),
        ValidationCaseSpec(
            case_id="VALID.PS.EPST1",
            title="Prestress strain convention and eps_t tracking",
            category="Prestress PMM",
            status="implemented",
            purpose="Check prestress initial strain minus section strain convention and ensure bonded prestress can control eps_t for phi evaluation.",
            acceptance="Prestress stress spot checks pass and PS-only/bonded-PS phi tracking regression tests remain green.",
            source="Independent strain spot check and prestress PMM regression tests.",
            current_location="concrete_pmm_pro/verification/hand_checks.py; tests/test_prestress_pmm_solver.py",
            next_action="Add published prestressed column/section example with documented fps and phi.",
            warnings_addressed=("eps_t NaN", "prestress phi", "bonded prestress"),
        ),
        ValidationCaseSpec(
            case_id="VALID.PS.PO1",
            title="Prestress-aware nominal Po helper",
            category="Prestress PMM",
            status="implemented",
            purpose="Check that nominal axial cap includes bonded Aps using fpy or 0.90fpu without using Pe_eff or breaking-load metadata.",
            acceptance="RC-only, PS-only, and RC+PS Po tests pass and unbonded prestress remains excluded from strain-compatible axial strength.",
            source="Unit tests for ACI axial cap helper.",
            current_location="tests/test_aci_axial_cap.py",
            next_action="Use QA.PO1 benchmark evidence to downgrade axial-cap prototype wording from engineering warning to documented method note.",
            warnings_addressed=("ACI axial cap", "bonded prestress Aps"),
        ),
        ValidationCaseSpec(
            case_id="QA.PO1",
            title="Prestress-aware axial cap validation pack",
            category="Prestress PMM",
            status="implemented",
            purpose="Validate ACI-style nominal Po and capped phiPn,max area bookkeeping for RC-only, PS-only, RC+PS, fpu-fallback, count, and unbonded-exclusion cases.",
            acceptance="Independent formula checks match nominal_po_rc_prestressed and aci_max_phiPn; Pe_eff and product breaking-load metadata are not used in nominal axial strength.",
            source="Independent axial-cap benchmark runner and ACI helper unit tests.",
            current_location="concrete_pmm_pro/verification/po_axial_cap_benchmarks.py; tests/test_valid_po1_axial_cap.py; tests/test_aci_axial_cap.py",
            next_action="After user review, reclassify the axial-cap prototype warning as a method note that references QA.PO1 validation coverage.",
            warnings_addressed=("ACI axial cap", "Po + Aps", "phiPn max", "Pe_eff not Po", "unbonded prestress exclusion"),
        ),
        ValidationCaseSpec(
            case_id="VALID.PS1",
            title="Bonded prestress PMM benchmark pack",
            category="Prestress PMM",
            status="implemented",
            purpose="Validate PS-only and RC+PS benchmark behavior before reducing bonded-prestress PMM warning severity.",
            acceptance="PS-only eps_t tracking, Pe_eff-to-fpe conversion, prestress-aware Po, RC+PS capacity trend, stress-warning metadata, and numeric-schema checks run without failures.",
            source="Deterministic bonded-prestress benchmark runner and PMM solver outputs.",
            current_location="concrete_pmm_pro/verification/ps_bonded_benchmarks.py; tests/test_valid_ps1_bonded_prestress.py",
            next_action="Add published prestressed section reference examples and governing-region stress-state checks before lowering prestress prototype wording.",
            warnings_addressed=("bonded prestress", "fpu cap", "compression reversal", "prestress Po", "prestress eps_t"),
        ),
        ValidationCaseSpec(
            case_id="VALID.PS2",
            title="Prestress stress-state governing-region benchmark pack",
            category="Prestress PMM",
            status="implemented",
            purpose="Validate that prestress fpu-cap and compression-reversal events are traceable per PMM point and can be separated into background PMM-surface events versus near-governing Pu events.",
            acceptance="Stress-state metadata columns exist; governing D/C trace is available; fpu-cap and compression-reversal event counts can be evaluated globally and near the governing Pu region.",
            source="Deterministic RC+PS and PS-only benchmark runners using PMM result metadata.",
            current_location="concrete_pmm_pro/verification/ps_stress_region_benchmarks.py; tests/test_valid_ps2_stress_region.py",
            next_action="Use VALID.PS2 evidence to refine governing-impact warning display, then develop stress-model reference cases for compression reversal behavior.",
            warnings_addressed=("fpu cap", "compression reversal", "governing impact", "prestress stress metadata"),
        ),
        ValidationCaseSpec(
            case_id="SOLVER.PS.PASSIVE1",
            title="Passive prestressing steel separated from active prestress",
            category="Prestress PMM",
            status="implemented",
            purpose="Treat Pe_eff=0/fpe=0 prestressing rows as bonded high-strength passive steel rather than active-prestress elements. This prevents passive PT bars/strands from emitting active-prestress fpu-cap or compression-reversal warnings.",
            acceptance="Passive bonded PS rows contribute signed strain-compatible force, can control eps_t/phi, retain reportable prestress-force metadata, and do not emit active-prestress stress-state warnings.",
            source="Passive prestressing steel benchmark pack and PMM solver regression tests.",
            current_location="concrete_pmm_pro/verification/ps_passive_benchmarks.py; tests/test_valid_ps_passive1.py; tests/test_prestress_pmm_solver.py",
            next_action="Use this separation in warning display policy so passive PS rows are documented as high-strength steel, not active prestress model limitations.",
            warnings_addressed=("passive prestress", "fpu cap", "compression reversal", "prestress warning classification"),
        ),
        ValidationCaseSpec(
            case_id="SOLVER.PS.STRESS1",
            title="Active prestress fpu-cap metadata warning policy",
            category="Prestress PMM",
            status="implemented",
            purpose="Treat fpu-cap events as PMM stress-state metadata rather than standalone global engineering warnings when they occur on background ultimate envelope points.",
            acceptance="Fpu-cap events remain traceable through PMM point metadata; background cap events are not emitted as global warnings; guidance escalates only when governing-region classification detects possible impact.",
            source="PMM solver stress-state metadata plus warning-guidance tests and VALID.PS1/PS2 benchmark packs.",
            current_location="concrete_pmm_pro/analysis/pmm_solver.py; concrete_pmm_pro/ui/analysis_page.py; tests/test_prestress_pmm_solver.py; tests/test_analysis_runtime.py",
            next_action="Develop solver-level reference cases for compression-reversal handling before removing compression-reversal model warnings.",
            warnings_addressed=("fpu cap", "governing impact", "prestress stress metadata"),
        ),
        ValidationCaseSpec(
            case_id="SOLVER.PS.COMP1",
            title="Prestress compression-reversal governing-region policy",
            category="Prestress PMM",
            status="implemented",
            purpose="Treat active-prestress compression-reversal events as PMM stress-state metadata unless they are detected near the governing demand region.",
            acceptance="Compression-reversal events remain traceable through PMM point metadata; background events are not emitted as global warnings; UI guidance escalates only when governing-region metadata indicates possible impact.",
            source="VALID.PS2 stress-region benchmark pack plus PMM solver metadata and governing-impact UI tests.",
            current_location="concrete_pmm_pro/analysis/pmm_solver.py; concrete_pmm_pro/ui/analysis_page.py; tests/test_prestress_pmm_solver.py; tests/test_analysis_runtime.py; tests/test_valid_ps2_stress_region.py",
            next_action="Develop refined prestress compression-side stress-strain reference cases before replacing the current tensile-strain clamp model.",
            warnings_addressed=("compression reversal", "governing impact", "prestress stress metadata"),
        ),
        ValidationCaseSpec(
            case_id="PMM.BENCH.PS.CUSTOM1",
            title="Prestressed/custom-shape PMM published benchmark inventory",
            category="Custom shape PMM",
            status="partial",
            purpose="Separate implemented internal/derived PMM evidence from missing published references for prestressed and custom-shape final-readiness.",
            acceptance="Inventory must identify implemented internal evidence, missing published/custom-shape references, acceptance gates, and next actions without claiming internal checks are published benchmarks.",
            source="PMM published benchmark readiness inventory and existing validation packs.",
            current_location="concrete_pmm_pro/verification/pmm_published_benchmark_inventory.py; tests/test_pmm_published_benchmark_inventory.py",
            next_action="Collect traceable published/reference PMM cases for bonded prestress, hollow/custom shapes, irregular polygons, and demand-capacity extraction.",
            warnings_addressed=("published benchmark", "prestressed PMM", "custom shape PMM", "final certification guard"),
        ),
        ValidationCaseSpec(
            case_id="VALID.PMM.DC1",
            title="Robust directional PMM demand/capacity extraction",
            category="Demand/Capacity",
            status="implemented",
            purpose="Use cleaned Pu-slice PMM envelopes with a boundary ray-intersection capacity method before any fallback method is considered.",
            acceptance="Analytic rectangular slice benchmarks match known ray capacities; governing D/C uses the primary slice-envelope path without silent fallback when the envelope is valid; an actual RC rectangular PMM route does not exceed its direct ray-boundary estimate.",
            source="Synthetic rectangular PMM slice benchmarks, non-star/noisy envelope guard, and RC rectangular PMM D/C regression tests.",
            current_location="concrete_pmm_pro/analysis/slice_envelope.py; concrete_pmm_pro/verification/dc_directional_benchmarks.py; tests/test_valid_dc1_directional_capacity.py",
            next_action="Add published/reference biaxial PMM demand-capacity examples before retiring all D/C validation limitation notes.",
            warnings_addressed=("directional D/C", "PMM interpolation", "fallback", "slice envelope"),
        ),
        ValidationCaseSpec(
            case_id="VALID.NUM1",
            title="PMM numerical result hygiene",
            category="Numerical robustness",
            status="partial",
            purpose="Separate expected missing eps_t values in compression-controlled states from true invalid numerical results.",
            acceptance="No NaN/Inf appears in capacity-critical fields; eps_t missingness is classified as a numerical note only when phi/D/C remain valid.",
            source="PMM result summary and warning-severity tests.",
            current_location="tests/test_pmm_benchmarks.py; tests/test_analysis_runtime.py",
            next_action="Add solver-result schema checks for capacity-critical columns and documented eps_t-missing rules.",
            warnings_addressed=("NaN eps_t", "numerical note"),
        ),
        ValidationCaseSpec(
            case_id="VALID.WARN1",
            title="Commercial warning policy",
            category="Warning policy",
            status="partial",
            purpose="Keep engineering warnings actionable and prevent background QA notes from being mistaken for failed ULS design checks.",
            acceptance="Warnings include meaning, possible cause, recommended action, where-to-check, and governing-impact classification.",
            source="Actionable warning guidance table.",
            current_location="concrete_pmm_pro/ui/analysis_page.py; tests/test_analysis_runtime.py",
            next_action="After validation benchmarks mature, move prototype statements from warnings to method notes/report limitations.",
            warnings_addressed=("prototype wording", "warning severity", "governing impact"),
        ),
    ]


def validation_matrix_to_dataframe(cases: list[ValidationCaseSpec] | None = None) -> pd.DataFrame:
    """Return a stable dataframe for report/UI export of the validation matrix."""

    items = cases if cases is not None else build_pmm_solver_validation_matrix()
    return pd.DataFrame(
        [
            {
                "Case ID": case.case_id,
                "Title": case.title,
                "Category": case.category,
                "Coverage Status": case.status,
                "Purpose": case.purpose,
                "Acceptance": case.acceptance,
                "Current Location": case.current_location,
                "Next Action": case.next_action,
                "Warnings Addressed": "; ".join(case.warnings_addressed),
            }
            for case in items
        ]
    )


def run_pmm_solver_validation_report() -> PMMSolverValidationReport:
    """Run the current PMM validation framework checks."""

    return PMMSolverValidationReport(
        validation_cases=build_pmm_solver_validation_matrix(),
        hand_checks=run_independent_hand_check_suite(),
        pmm_checks=run_pmm_verification_suite(),
        rc_benchmarks=run_valid_rc1_benchmark_pack(),
        rc_phi_transition=run_valid_rc2_phi_transition_benchmark_pack(),
        ps_benchmarks=run_valid_ps1_bonded_prestress_benchmark_pack(),
        ps_stress_regions=run_valid_ps2_stress_region_benchmark_pack(),
        ps_passive=run_valid_ps_passive_benchmark_pack(),
        dc_directional=run_valid_dc1_directional_benchmark_pack(),
        po_axial_cap=run_valid_po1_axial_cap_benchmark_pack(),
        pmm_final_rc1=run_pmm_final_rc1_readiness_gate(),
    )
