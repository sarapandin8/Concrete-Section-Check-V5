from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_pmm_final_audit_documents_safe_finalization_gate() -> None:
    audit = _read("docs/design/pmm_final_audit1.md")

    assert "PMM.FINAL.AUDIT1" in audit
    assert "does not change solver equations" in audit
    assert "not yet a final code-certified solver" in audit
    assert "PMM.FINAL.RC1" in audit
    assert "PMM.FINAL.RC1.STATUS.READINESS1" in audit
    assert "PMM.FINAL.RC1.CLOSEOUT" in audit
    assert "PMM.AASHTO.PMM1" in audit


def test_pmm_final_audit_keeps_aashto_pmm_guarded() -> None:
    audit = _read("docs/design/pmm_final_audit1.md")
    analysis_source = _read("concrete_pmm_pro/ui/analysis_page.py")
    design_code_source = _read("concrete_pmm_pro/core/design_code.py")

    assert "AASHTO LRFD Column/Pier PMM is not implemented" in audit
    assert "current PMM remains ACI-oriented" in analysis_source
    assert "AASHTO LRFD PMM for Column/Pier/Wall/Pylon is a future solver milestone" in design_code_source


def test_pmm_final_audit_retains_key_validation_and_limitation_evidence() -> None:
    audit = _read("docs/design/pmm_final_audit1.md")
    validation_source = _read("concrete_pmm_pro/verification/validation_framework.py")
    warnings_source = _read("concrete_pmm_pro/analysis/warnings.py")

    for token in [
        "VALID.RC1",
        "VALID.RC2",
        "VALID.PMM.DC1",
        "VALID.PS1",
        "VALID.PS2",
        "SOLVER.PS.PASSIVE1",
        "QA.PO1",
    ]:
        assert token in audit
        assert token in validation_source

    assert "PMM_PROTOTYPE_WARNING" in warnings_source
    assert "DCR_PROTOTYPE_WARNING" in warnings_source


def test_pmm_final_audit_blocks_cosmetic_final_labeling() -> None:
    audit = _read("docs/design/pmm_final_audit1.md")

    assert "Do not remove prototype or engineering-review wording solely to make the UI" in audit
    assert "Do not modify solver equations merely to make validation checks pass" in audit
    assert "Do not treat ACI-oriented PMM as final AASHTO LRFD PMM" in audit
