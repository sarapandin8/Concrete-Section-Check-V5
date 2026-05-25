"""Analysis mode/member type helper functions."""

from __future__ import annotations

from concrete_pmm_pro.core.analysis import AnalysisModeSettings


def analysis_mode_label(settings: AnalysisModeSettings) -> str:
    if settings.member_type == "column_pier_pmm":
        return "Column / Pier / Wall / Pylon - PMM Mode"
    if settings.member_type == "beam_girder":
        return "Beam / Girder - Flexure Mode Future"
    if settings.member_type == "general_section":
        return "General Section"
    return "Unknown Analysis Mode"


def analysis_mode_description(settings: AnalysisModeSettings) -> str:
    if settings.description:
        return settings.description
    if settings.member_type == "column_pier_pmm":
        return (
            "Current workflow for members primarily reviewed with Pu, Mux, and Muy. "
            "PMM interaction, ULS D/C prototype, and SLS stress tools are available."
        )
    if settings.member_type == "beam_girder":
        return (
            "Future workflow placeholder for beam/girder flexure, shear, torsion, transfer-stage, "
            "service-stage, and prestress beam checks. Existing SLS section stress tools remain available."
        )
    if settings.member_type == "general_section":
        return (
            "General section review mode keeps PMM and SLS tools available when the member type "
            "has not been classified yet."
        )
    return "Analysis mode is not recognized."


def is_pmm_primary_workflow(settings: AnalysisModeSettings) -> bool:
    return settings.member_type == "column_pier_pmm"


def is_beam_girder_future_workflow(settings: AnalysisModeSettings) -> bool:
    return settings.member_type == "beam_girder"


def analysis_mode_warnings(settings: AnalysisModeSettings) -> list[str]:
    warnings: list[str] = []
    if settings.member_type == "beam_girder":
        warnings.extend(
            [
                "Beam/Girder design checks are not implemented yet.",
                "Do not double-count prestress by entering Pe as Pu when prestress elements are defined.",
                "PMM interaction is not the primary method for typical beam/girder flexural design.",
            ]
        )
    elif settings.member_type == "general_section":
        warnings.append("General Section mode requires careful interpretation of Pu, Mux, and Muy.")
    return warnings
