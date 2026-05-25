"""Report table registry for future export."""

from __future__ import annotations

from typing import Any

import pandas as pd

from concrete_pmm_pro.reporting.limitations import collect_limitations_for_report, engineering_limitations_to_dataframe
from concrete_pmm_pro.reporting.readiness import check_report_readiness, report_readiness_to_dataframe
from concrete_pmm_pro.reporting.report_models import ReportTableInfo
from concrete_pmm_pro.reporting.terminology import terminology_to_dataframe
from concrete_pmm_pro.reporting.traceability import build_result_traceability_snapshot, result_traceability_snapshot_to_dataframe
from concrete_pmm_pro.reporting.units import unit_conventions_to_dataframe


def _get(mapping: Any, key: str, default: Any = None) -> Any:
    if mapping is None:
        return default
    if hasattr(mapping, "get"):
        try:
            return mapping.get(key, default)
        except (AttributeError, TypeError, ValueError):
            return default
    return getattr(mapping, key, default)


def _has_any(session_state: Any, keys: list[str]) -> bool:
    return any(_get(session_state, key) is not None for key in keys)


def _row_count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, pd.DataFrame):
        return len(value)
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    for attr in ("results", "checks", "points", "stress_results"):
        values = getattr(value, attr, None)
        if values is not None:
            try:
                return len(values)
            except TypeError:
                return None
    return None


def collect_available_report_tables(session_state: Any) -> list[ReportTableInfo]:
    """Collect table availability from existing state without recalculation."""

    snapshot = build_result_traceability_snapshot(session_state)
    readiness = check_report_readiness(snapshot)
    limitations = collect_limitations_for_report(session_state, include_all=True)

    standard_tables = [
        ReportTableInfo(
            "result_traceability_snapshot",
            "Result Traceability Snapshot",
            True,
            "build_result_traceability_snapshot",
            "Project, workflow, ULS, SLS, cracking, verification, warning, and limitation summary.",
            row_count=len(result_traceability_snapshot_to_dataframe(snapshot)),
        ),
        ReportTableInfo(
            "report_readiness",
            "Report Readiness",
            True,
            "check_report_readiness",
            "Pre-report readiness status and missing/optional items.",
            row_count=len(report_readiness_to_dataframe(readiness)),
        ),
        ReportTableInfo(
            "engineering_warnings",
            "Engineering Warnings",
            True,
            "collect_engineering_warnings",
            "Consolidated engineering warnings.",
            row_count=len(snapshot.warnings),
        ),
        ReportTableInfo(
            "engineering_limitations",
            "Engineering Limitations",
            True,
            "collect_limitations_for_report",
            "Engineering limitations and prototype/future-work disclosures.",
            row_count=len(engineering_limitations_to_dataframe(limitations)),
        ),
        ReportTableInfo(
            "unit_conventions",
            "Unit Conventions",
            True,
            "get_unit_conventions",
            "Internal, display, and future report units.",
            row_count=len(unit_conventions_to_dataframe()),
        ),
        ReportTableInfo(
            "terminology",
            "Standard Terminology",
            True,
            "get_standard_terminology",
            "Engineering term glossary for report consistency.",
            row_count=len(terminology_to_dataframe()),
        ),
    ]

    pmm_value = _get(session_state, "rc_pmm_result")
    if pmm_value is None:
        pmm_value = _get(session_state, "pmm_result")
    dc_value = _get(session_state, "rc_demand_capacity_result")
    if dc_value is None:
        dc_value = _get(session_state, "demand_capacity_summary")
    serviceability = _get(session_state, "serviceability_summary")
    crack = _get(session_state, "crack_classification_summary")
    custom_points = _get(session_state, "custom_stress_check_points")

    standard_tables.extend(
        [
            ReportTableInfo("pmm_summary", "PMM Summary", pmm_value is not None, "rc_pmm_result", "ULS PMM result summary.", row_count=_row_count(getattr(pmm_value, "points", None))),
            ReportTableInfo("uls_demand_capacity_result", "ULS Demand / Capacity Result", dc_value is not None, "rc_demand_capacity_result", "ULS demand/capacity prototype results.", row_count=_row_count(dc_value)),
            ReportTableInfo("pmm_slice", "PMM Slice", pmm_value is not None, "rc_pmm_result", "Selected PMM slice data when generated.", row_count=None),
            ReportTableInfo("pmm_slice_envelope", "PMM Slice Envelope", pmm_value is not None, "rc_pmm_result", "Selected PMM envelope data when generated.", row_count=None),
            ReportTableInfo("pmm_verification", "PMM Verification", _get(session_state, "pmm_verification_summary") is not None, "pmm_verification_summary", "PMM benchmark checks.", row_count=_row_count(_get(session_state, "pmm_verification_summary"))),
            ReportTableInfo("hand_check_results", "Independent Hand Checks", _get(session_state, "pmm_hand_check_summary") is not None, "pmm_hand_check_summary", "Independent PMM hand-check results.", row_count=_row_count(_get(session_state, "pmm_hand_check_summary"))),
            ReportTableInfo("sls_stress_results", "SLS Stress Results", serviceability is not None, "serviceability_summary", "Gross/transformed elastic SLS stress results.", row_count=_row_count(getattr(serviceability, "stress_results", None))),
            ReportTableInfo("sls_prestress_contribution", "SLS Prestress Contribution", bool(getattr(serviceability, "prestress_contribution", None)), "serviceability_summary", "Effective bonded prestress contribution to SLS stress.", row_count=1 if getattr(serviceability, "prestress_contribution", None) else None),
            ReportTableInfo("transformed_section_properties", "Transformed Section Properties", bool(getattr(serviceability, "transformed_section_properties", None)), "serviceability_summary", "Uncracked transformed section properties.", row_count=1 if getattr(serviceability, "transformed_section_properties", None) else None),
            ReportTableInfo("cracking_classification", "Cracking Classification", crack is not None, "crack_classification_summary", "Tension/cracking classification from SLS stress results.", row_count=_row_count(getattr(crack, "points", None))),
            ReportTableInfo("custom_stress_check_points", "Custom Stress Check Points", bool(custom_points), "custom_stress_check_points", "User-defined SLS stress check points.", row_count=_row_count(custom_points)),
            ReportTableInfo("sls_verification_results", "SLS Verification Results", _get(session_state, "sls_verification_summary") is not None, "sls_verification_summary", "SLS stress sign benchmark checks.", row_count=_row_count(_get(session_state, "sls_verification_summary"))),
            ReportTableInfo("sls_visualization_selected_combo", "Selected SLS Visualization Data", _has_any(session_state, ["sls_visualization_dataframe", "sls_stress_visualization_selected_combo"]), "sls_visualization_dataframe", "Selected-combo SLS stress visualization source data.", row_count=_row_count(_get(session_state, "sls_visualization_dataframe"))),
        ]
    )
    return standard_tables


def report_tables_to_dataframe(tables: list[ReportTableInfo]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Table Key": table.table_key,
                "Title": table.title,
                "Available": table.available,
                "Source": table.source,
                "Recommended": table.recommended_for_report,
                "Row Count": table.row_count,
                "Description": table.description,
                "Warning": table.warning or "",
            }
            for table in tables
        ],
        columns=["Table Key", "Title", "Available", "Source", "Recommended", "Row Count", "Description", "Warning"],
    )
