from __future__ import annotations

from pathlib import Path


DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "design" / "prestress_losses_method_statement.md"


def test_prestress_loss_method_statement_exists_and_freezes_scope() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")

    required_phrases = [
        "GIRDER.LOSS0",
        "No prestress-loss solver is implemented",
        "Precast I-Girder",
        "Precast Plank Girder",
        "Precast Box Beam",
        "friction loss",
        "anchorage set loss",
        "P_transfer(x)",
        "P_service(x)",
        "AASHTO approximate loss preview",
        "AASHTO refined/staged method",
        "ACI/PCI loss preview",
        "Manual / User-defined",
        "Do not implement these in LOSS0",
        "Do not change solver equations",
    ]

    missing = [phrase for phrase in required_phrases if phrase not in text]
    assert not missing


def test_prestress_loss_method_statement_keeps_future_sequence_conservative() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")

    sequence = [
        "GIRDER.PS4A",
        "GIRDER.PS5A",
        "GIRDER.LOSS1A",
        "GIRDER.LOSS1B",
        "GIRDER.LOSS2A",
        "GIRDER.SLS4A",
    ]
    positions = [text.index(item) for item in sequence]

    assert positions == sorted(positions)
    assert "LOSS1A should not yet use automatic losses in final SLS checks." in text
