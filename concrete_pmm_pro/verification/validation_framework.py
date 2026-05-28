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

        statuses = {self.hand_checks.overall_status, self.pmm_checks.overall_status}
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
            case_id="VALID.RC.MX1",
            title="RC rectangular uniaxial bending spot check",
            category="RC-only PMM",
            status="implemented",
            purpose="Compare a selected rectangular RC neutral-axis state against an independent concrete-block plus rebar-force hand calculation.",
            acceptance="Pn and Mnx are within benchmark tolerance for the selected neutral-axis state.",
            source="Independent hand spot calculation.",
            current_location="concrete_pmm_pro/verification/hand_checks.py",
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
            case_id="VALID.PS.STRESS1",
            title="Prestress fpu cap and compression reversal classification",
            category="Prestress PMM",
            status="partial",
            purpose="Detect fpu-cap and compression-reversal events and classify whether they are background PMM-surface events or governing-impact events.",
            acceptance="Warnings are actionable and governing-impact classification tests pass; root stress model remains documented.",
            source="Current warning guidance and governing-impact UI tests.",
            current_location="concrete_pmm_pro/ui/analysis_page.py; tests/test_analysis_runtime.py",
            next_action="Develop solver-level stress-state metadata per PMM point, then validate against prestress stress-strain reference cases.",
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
    )
