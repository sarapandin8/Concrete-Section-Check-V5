"""Pre-report readiness checks."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from concrete_pmm_pro.reporting.traceability import ResultTraceabilitySnapshot

READY = "READY"
MISSING = "MISSING"
WARNING = "WARNING"
OPTIONAL = "OPTIONAL"


@dataclass(frozen=True)
class ReportReadinessItem:
    category: str
    item: str
    status: str
    message: str


@dataclass(frozen=True)
class ReportReadinessSummary:
    overall_status: str
    ready_count: int
    missing_count: int
    warning_count: int
    optional_count: int
    items: list[ReportReadinessItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def _item(category: str, item: str, status: str, message: str) -> ReportReadinessItem:
    return ReportReadinessItem(category=category, item=item, status=status, message=message)


def check_report_readiness(snapshot: ResultTraceabilitySnapshot) -> ReportReadinessSummary:
    items: list[ReportReadinessItem] = []
    items.append(
        _item(
            "Project",
            "Section geometry",
            READY if snapshot.section_available else MISSING,
            "Section geometry is available." if snapshot.section_available else "Section geometry is required.",
        )
    )
    items.append(
        _item(
            "Project",
            "Materials",
            READY if snapshot.materials_available else MISSING,
            "Material data is available." if snapshot.materials_available else "Concrete/material data is required.",
        )
    )
    items.append(
        _item(
            "Workflow",
            "Analysis mode",
            READY if snapshot.member_type and snapshot.analysis_workflow else MISSING,
            "Analysis mode metadata is available." if snapshot.member_type else "Analysis mode metadata is required.",
        )
    )
    has_result = snapshot.pmm_result_available or snapshot.sls_result_available
    items.append(
        _item(
            "Results",
            "At least one analysis result",
            READY if has_result else MISSING,
            "At least one ULS PMM or SLS result is available." if has_result else "Run ULS PMM or SLS checks before report export.",
        )
    )
    items.append(
        _item(
            "Results",
            "ULS PMM result",
            READY if snapshot.pmm_result_available else OPTIONAL,
            "ULS PMM result is available." if snapshot.pmm_result_available else "ULS PMM result is optional for SLS-only review.",
        )
    )
    items.append(
        _item(
            "Results",
            "SLS stress result",
            READY if snapshot.sls_result_available else OPTIONAL,
            "SLS stress result is available." if snapshot.sls_result_available else "SLS result is optional for ULS-only review.",
        )
    )
    items.append(
        _item(
            "Verification",
            "Verification / hand checks",
            READY if any([snapshot.pmm_verification_status, snapshot.hand_check_status, snapshot.sls_verification_status]) else OPTIONAL,
            "At least one verification suite has run." if any([snapshot.pmm_verification_status, snapshot.hand_check_status, snapshot.sls_verification_status]) else "Verification checks are recommended before report export.",
        )
    )
    if snapshot.warning_count:
        items.append(
            _item(
                "Warnings",
                "Engineering warnings",
                WARNING,
                f"{snapshot.warning_count} engineering warning(s) should be reviewed.",
            )
        )
    if snapshot.high_or_critical_limitation_count:
        items.append(
            _item(
                "Limitations",
                "High/Critical engineering limitations",
                WARNING,
                f"{snapshot.high_or_critical_limitation_count} high or critical engineering limitation(s) require review.",
            )
        )

    ready_count = sum(item.status == READY for item in items)
    missing_count = sum(item.status == MISSING for item in items)
    warning_count = sum(item.status == WARNING for item in items)
    optional_count = sum(item.status == OPTIONAL for item in items)
    critical_missing = any(item.status == MISSING for item in items[:4])
    if critical_missing and not has_result:
        overall_status = "NOT_READY"
    elif critical_missing:
        overall_status = "NOT_READY"
    elif snapshot.pmm_result_available and snapshot.sls_result_available:
        overall_status = "READY"
    else:
        overall_status = "PARTIAL"
    return ReportReadinessSummary(
        overall_status=overall_status,
        ready_count=ready_count,
        missing_count=missing_count,
        warning_count=warning_count,
        optional_count=optional_count,
        items=items,
        warnings=list(snapshot.warnings),
        info=["Draft Word export is available; PDF export remains future work."],
    )


def report_readiness_to_dataframe(summary: ReportReadinessSummary) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Category": item.category,
                "Item": item.item,
                "Status": item.status,
                "Message": item.message,
            }
            for item in summary.items
        ],
        columns=["Category", "Item", "Status", "Message"],
    )
