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

ValidationStatus = Literal["implemented", "partial", "planned"]
ValidationCategory = Literal[
    "RC-only PMM",
    "Prestress PMM",
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
            purpose="Validate a simple rectangular RC section against independent axial-cap, uniaxial bending, symmetry, and numeric-schema checks before lowering RC-only prototype warnings.",
            acceptance="All VALID.RC1 checks pass or remain within documented prototype tolerances; capacity-critical columns contain no NaN/Inf values.",
            source="Independent rectangular stress-block hand formulas plus PMM solver benchmark runner.",
            current_location="concrete_pmm_pro/verification/rc_rectangular_benchmarks.py; tests/test_valid_rc1_benchmarks.py",
            next_action="Add published-code reference examples for uniaxial and biaxial bending before retiring general PMM prototype wording.",
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
            next_action="Add true biaxial hand/reference benchmark with known P-Mx-My capacity point.",
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
            next_action="Add independent hand examples and code-reference notes before lowering axial-cap prototype note.",
            warnings_addressed=("ACI axial cap", "bonded prestress Aps"),
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
            case_id="VALID.PS.STRESS1",
            title="Prestress fpu cap and compression reversal classification",
            category="Prestress PMM",
            status="partial",
            purpose="Detect fpu-cap and compression-reversal events and classify whether they are background PMM-surface events or governing-impact events.",
            acceptance="Warnings are actionable and governing-impact classification tests pass; root stress model remains documented.",
            source="VALID.PS2 stress-region benchmark pack plus current warning guidance and governing-impact UI tests.",
            current_location="concrete_pmm_pro/verification/ps_stress_region_benchmarks.py; concrete_pmm_pro/ui/analysis_page.py; tests/test_valid_ps2_stress_region.py; tests/test_analysis_runtime.py",
            next_action="Develop solver-level stress-strain reference cases for compression reversal handling before removing stress-model warnings.",
            warnings_addressed=("fpu cap", "compression reversal"),
        ),
        ValidationCaseSpec(
            case_id="VALID.PMM.DC1",
            title="Directional PMM demand/capacity interpolation",
            category="Demand/Capacity",
            status="partial",
            purpose="Check capacity extraction at a demand Pu and moment direction using cleaned slice envelope and fallback methods.",
            acceptance="Known benchmark demand points return stable D/C, and fallback is not used silently for governing cases.",
            source="Slice envelope and dashboard regression tests.",
            current_location="tests/test_slice_envelope.py; tests/test_pmm_dashboard.py; tests/test_capacity_check.py",
            next_action="Add analytic/reference D/C benchmark cases and require governing fallback reason in report.",
            warnings_addressed=("directional D/C", "PMM interpolation", "fallback"),
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
    )
