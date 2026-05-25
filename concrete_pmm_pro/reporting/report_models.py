"""Shared report foundation models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReportMetadata:
    report_title: str = "Concrete PMM Pro Engineering Report"
    project_name: str | None = None
    prepared_by: str | None = None
    checked_by: str | None = None
    organization: str | None = None
    project_number: str | None = None
    revision: str = "Draft"
    report_date: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class ReportSection:
    section_id: str
    title: str
    level: int = 1
    include: bool = True
    status: str = "AVAILABLE"
    summary: str | None = None
    warnings: list[str] = field(default_factory=list)
    table_keys: list[str] = field(default_factory=list)
    figure_keys: list[str] = field(default_factory=list)
    limitation_keys: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReportTableInfo:
    table_key: str
    title: str
    available: bool
    source: str
    description: str
    recommended_for_report: bool = True
    row_count: int | None = None
    warning: str | None = None


def default_report_metadata(project_name: str | None = None) -> ReportMetadata:
    return ReportMetadata(project_name=project_name)
