"""PMM.FINAL.RC1 readiness gate for ACI RC Flexural PMM.

This runner aggregates the existing RC-only validation evidence into a single
commercial-readiness gate. It deliberately does not change PMM equations. A
WARNING status means at least one final-readiness evidence item still needs
review. A PASS status supports the guarded ACI RC finalized production-preview
closeout; it is not final certification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from concrete_pmm_pro.verification.dc_directional_benchmarks import run_valid_dc1_directional_benchmark_pack
from concrete_pmm_pro.verification.rc_phi_transition_benchmarks import run_valid_rc2_phi_transition_benchmark_pack
from concrete_pmm_pro.verification.rc_rectangular_benchmarks import (
    FAIL,
    PASS,
    WARNING,
    run_valid_rc1_benchmark_pack,
)


@dataclass(frozen=True)
class PMMFinalRC1Check:
    """Single ACI RC PMM final-readiness gate check."""

    check_id: str
    title: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PMMFinalRC1Summary:
    """Summary for the PMM.FINAL.RC1 readiness gate."""

    checks: list[PMMFinalRC1Check]
    pass_count: int
    warning_count: int
    fail_count: int
    overall_status: str
    design_use_status: str

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "Check ID": check.check_id,
                    "Title": check.title,
                    "Status": check.status,
                    "Message": check.message,
                    "Details": check.details,
                }
                for check in self.checks
            ]
        )


def _summary(checks: list[PMMFinalRC1Check]) -> PMMFinalRC1Summary:
    pass_count = sum(check.status == PASS for check in checks)
    warning_count = sum(check.status == WARNING for check in checks)
    fail_count = sum(check.status == FAIL for check in checks)
    overall = FAIL if fail_count else WARNING if warning_count else PASS
    design_use = (
        "Do not use until failures are resolved."
        if overall == FAIL
        else "Engineering review with final-readiness blockers."
        if overall == WARNING
        else "Finalized production-preview for ACI RC PMM only; not final certification."
    )
    return PMMFinalRC1Summary(
        checks=checks,
        pass_count=pass_count,
        warning_count=warning_count,
        fail_count=fail_count,
        overall_status=overall,
        design_use_status=design_use,
    )


def _status_from_child_statuses(statuses: list[str]) -> str:
    if any(status == FAIL for status in statuses):
        return FAIL
    if any(status == WARNING for status in statuses):
        return WARNING
    return PASS


def _child_status_map(summary: object) -> dict[str, str]:
    return {str(check.check_id): str(check.status) for check in getattr(summary, "checks", [])}


def run_pmm_final_rc1_readiness_gate() -> PMMFinalRC1Summary:
    """Run the ACI RC Flexural PMM final-readiness gate."""

    rc1 = run_valid_rc1_benchmark_pack()
    rc2 = run_valid_rc2_phi_transition_benchmark_pack()
    dc1 = run_valid_dc1_directional_benchmark_pack()
    rc1_statuses = _child_status_map(rc1)
    rc2_statuses = _child_status_map(rc2)
    dc1_statuses = _child_status_map(dc1)

    uniaxial_ids = ["VALID.RC1.PHI_PN_MAX", "VALID.RC1.MX_C300_PN", "VALID.RC1.MX_C300_MNX"]
    uniaxial_status = _status_from_child_statuses([rc1_statuses.get(check_id, FAIL) for check_id in uniaxial_ids])
    biaxial_ids = ["VALID.RC1.BIAX_CDIAG_PN", "VALID.RC1.BIAX_CDIAG_MNX", "VALID.RC1.BIAX_CDIAG_MNY"]
    biaxial_status = _status_from_child_statuses([rc1_statuses.get(check_id, FAIL) for check_id in biaxial_ids])
    phi_ids = [
        "VALID.RC2.PHI_COMPRESSION_EDGE",
        "VALID.RC2.PHI_TRANSITION_MID",
        "VALID.RC2.PHI_TENSION_EDGE",
        "VALID.RC2.SOLVER_PHI_MATCH",
        "VALID.RC2.SOLVER_PHI_RANGE",
    ]
    phi_status = _status_from_child_statuses([rc2_statuses.get(check_id, FAIL) for check_id in phi_ids])
    dc_ids = [
        "SOLVER.PMM.DC1.RECT_X_RAY",
        "SOLVER.PMM.DC1.RECT_DIAGONAL_RAY",
        "SOLVER.PMM.DC1.DC_SUMMARY_PRIMARY",
        "SOLVER.PMM.DC1.NONSTAR_NEAREST_RAY",
        "SOLVER.PMM.DC1.RC_RECT_PRIMARY_NO_OVERESTIMATE",
    ]
    dc_status = _status_from_child_statuses([dc1_statuses.get(check_id, FAIL) for check_id in dc_ids])
    evidence_status = _status_from_child_statuses([uniaxial_status, biaxial_status, phi_status, dc_status])

    checks = [
        PMMFinalRC1Check(
            check_id="PMM.FINAL.RC1.SCOPE",
            title="ACI RC-only Flexural PMM scope is controlled",
            status=PASS,
            message="Scope excludes prestress finalization, AASHTO LRFD PMM, shear, torsion, SLS, detailing, slenderness, and second-order effects.",
            details={"design_gate": "docs/design/pmm_final_rc1.md"},
        ),
        PMMFinalRC1Check(
            check_id="PMM.FINAL.RC1.UNIAXIAL.REF",
            title="Independent rectangular RC uniaxial reference evidence",
            status=uniaxial_status,
            message=(
                "VALID.RC1 axial and uniaxial rectangular reference checks are available."
                if uniaxial_status != FAIL
                else "VALID.RC1 axial/uniaxial checks failed or are missing."
            ),
            details={check_id: rc1_statuses.get(check_id, "MISSING") for check_id in uniaxial_ids},
        ),
        PMMFinalRC1Check(
            check_id="PMM.FINAL.RC1.PHI",
            title="ACI phi transition evidence",
            status=phi_status,
            message=(
                "VALID.RC2 phi transition and solver phi-classification checks are available."
                if phi_status != FAIL
                else "VALID.RC2 phi transition checks failed or are missing."
            ),
            details={check_id: rc2_statuses.get(check_id, "MISSING") for check_id in phi_ids},
        ),
        PMMFinalRC1Check(
            check_id="PMM.FINAL.RC1.DC.NO_OVERESTIMATE",
            title="Directional D/C no-overestimate evidence",
            status=dc_status,
            message=(
                "VALID.PMM.DC1 ray-envelope checks guard against polar overestimate in synthetic slices and an actual RC rectangular PMM route."
                if dc_status != FAIL
                else "VALID.PMM.DC1 directional D/C checks failed or are missing."
            ),
            details={check_id: dc1_statuses.get(check_id, "MISSING") for check_id in dc_ids},
        ),
        PMMFinalRC1Check(
            check_id="PMM.FINAL.RC1.BIAXIAL.REF",
            title="True biaxial RC P-Mx-My reference benchmark",
            status=biaxial_status,
            message=(
                "VALID.RC1 diagonal biaxial reference checks are available for nonzero Mnx and Mny."
                if biaxial_status != FAIL
                else "VALID.RC1 diagonal biaxial reference checks failed or are missing."
            ),
            details={check_id: rc1_statuses.get(check_id, "MISSING") for check_id in biaxial_ids},
        ),
        PMMFinalRC1Check(
            check_id="PMM.FINAL.RC1.WARNING",
            title="Commercial wording remains guarded",
            status=PASS,
            message="ACI RC finalized production-preview wording is guarded by PMM.FINAL.RC1.CLOSEOUT and must not claim final code certification.",
            details={"target_status": "finalized production preview for ACI RC PMM only, not final code certification"},
        ),
        PMMFinalRC1Check(
            check_id="PMM.FINAL.RC1.STATUS.READINESS1",
            title="Production-preview status readiness decision",
            status=evidence_status,
            message=(
                "ACI RC Flexural PMM has production-preview readiness evidence and PMM.FINAL.RC1.CLOSEOUT finalizes guarded UI/report wording; it must not claim final certification."
                if evidence_status == PASS
                else "ACI RC Flexural PMM still has final-readiness evidence items requiring review before production-preview wording."
            ),
            details={
                "allowed_status": "ACI RC Flexural PMM finalized production preview",
                "forbidden_status": "Final code-certified ACI/AASHTO PMM design",
                "ui_report_milestone_required": "PMM.FINAL.RC1.CLOSEOUT",
                "scope": "ACI 318-style ordinary RC Column/Pier/Wall/Pylon PMM only",
                "excluded": "AASHTO LRFD PMM, prestress finalization, shear, torsion, SLS, detailing, slenderness, second-order effects",
            },
        ),
    ]
    return _summary(checks)
