from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_pmm_final_rc1_document_defines_rc_only_gate() -> None:
    doc = _read("docs/design/pmm_final_rc1.md")

    assert "PMM.FINAL.RC1" in doc
    assert "ACI 318-style RC PMM only" in doc
    assert "ordinary reinforced concrete without active prestress" in doc
    assert "bonded prestress finalization" in doc
    assert "AASHTO LRFD PMM" in doc
    assert "shear, torsion, SLS" in doc


def test_pmm_final_rc1_validation_matrix_tracks_reference_cases() -> None:
    source = _read("concrete_pmm_pro/verification/validation_framework.py")
    runner = _read("concrete_pmm_pro/verification/pmm_final_rc1_benchmarks.py")
    rc1 = _read("concrete_pmm_pro/verification/rc_rectangular_benchmarks.py")
    dc1 = _read("concrete_pmm_pro/verification/dc_directional_benchmarks.py")

    assert 'case_id="PMM.FINAL.RC1.SCOPE"' in source
    assert 'case_id="PMM.FINAL.RC1.UNIAXIAL.REF"' in source
    assert 'case_id="PMM.FINAL.RC1.BIAXIAL.REF"' in source
    assert 'case_id="PMM.FINAL.RC1.DC.NO_OVERESTIMATE"' in source
    assert 'case_id="PMM.FINAL.RC1.STATUS.READINESS1"' in source
    assert "run_pmm_final_rc1_readiness_gate" in source
    assert "run_pmm_final_rc1_readiness_gate" in runner
    assert "VALID.RC1.BIAX_CDIAG_PN" in rc1
    assert "VALID.RC1.BIAX_CDIAG_MNX" in rc1
    assert "VALID.RC1.BIAX_CDIAG_MNY" in rc1
    assert "SOLVER.PMM.DC1.RC_RECT_PRIMARY_NO_OVERESTIMATE" in dc1
    assert "SOLVER.PMM.DC1.RC_RECT_PRIMARY_NO_OVERESTIMATE" in runner


def test_pmm_final_rc1_keeps_current_rc_evidence_connected() -> None:
    doc = _read("docs/design/pmm_final_rc1.md")
    validation_doc = _read("docs/validation/pmm_solver_validation.md")
    rc1 = _read("concrete_pmm_pro/verification/rc_rectangular_benchmarks.py")
    rc2 = _read("concrete_pmm_pro/verification/rc_phi_transition_benchmarks.py")
    dc1 = _read("concrete_pmm_pro/verification/dc_directional_benchmarks.py")

    assert "VALID.RC1" in doc and "VALID.RC1.PHI_PN_MAX" in rc1
    assert "VALID.RC2" in doc and "VALID.RC2.SOLVER_PHI_MATCH" in rc2
    assert "VALID.PMM.DC1" in doc and "SOLVER.PMM.DC1.DC_SUMMARY_PRIMARY" in dc1
    assert "SOLVER.PMM.DC1.RC_RECT_PRIMARY_NO_OVERESTIMATE" in dc1
    assert "PMM.FINAL.RC1 ACI RC final-readiness gate" in validation_doc
    assert "It must not be described as final code-certified ACI/AASHTO PMM design" in validation_doc
    assert "`PMM.FINAL.RC1.BIAXIAL.REF` is no longer a hard-coded missing-reference" in validation_doc
    assert "`PMM.FINAL.RC1.STATUS.READINESS1` records the status decision" in validation_doc


def test_pmm_final_rc1_blocks_cosmetic_final_status_upgrade() -> None:
    doc = _read("docs/design/pmm_final_rc1.md")
    audit = _read("docs/design/pmm_final_audit1.md")
    status_audit = _read("docs/design/pmm_final_rc1_status_readiness1.md")

    assert "not final code-certified" in doc
    assert "Final code-certified ACI/AASHTO PMM design" in doc
    assert "Do not modify solver equations merely to satisfy this readiness gate" in doc
    assert "not yet a final code-certified solver" in audit
    assert "Final code-certified ACI/AASHTO PMM design" in status_audit
    assert "PMM.FINAL.RC1.CLOSEOUT" in status_audit
    assert "does not change PMM equations" in status_audit
