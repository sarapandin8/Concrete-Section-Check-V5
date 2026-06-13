from __future__ import annotations

from concrete_pmm_pro.reporting import collect_available_report_tables, default_report_section_plan, get_engineering_limitations
from concrete_pmm_pro.reporting.readiness import check_report_readiness
from concrete_pmm_pro.reporting.traceability import build_result_traceability_snapshot
from concrete_pmm_pro.verification.pmm_published_benchmark_inventory import (
    build_pmm_published_benchmark_inventory,
    pmm_published_benchmark_inventory_to_dataframe,
    summarize_pmm_published_benchmark_inventory,
)
from concrete_pmm_pro.verification.validation_framework import build_pmm_solver_validation_matrix


def test_pmm_bench_ps_custom1_inventory_separates_internal_and_published_gaps() -> None:
    items = build_pmm_published_benchmark_inventory()
    by_id = {item.benchmark_id: item for item in items}

    assert "PMM.BENCH.PS.RECT.INTERNAL" in by_id
    assert "PMM.BENCH.CUSTOM.HOLLOW" in by_id
    assert "PMM.BENCH.CUSTOM.IRREGULAR" in by_id
    assert "PMM.BENCH.PS.CUSTOM" in by_id
    assert by_id["PMM.BENCH.PS.RECT.INTERNAL"].reference_class == "internal"
    assert by_id["PMM.BENCH.PS.CUSTOM"].reference_class == "published_required"
    assert by_id["PMM.BENCH.PS.CUSTOM"].readiness == "missing"
    assert "No published/reference" in by_id["PMM.BENCH.PS.CUSTOM"].current_evidence


def test_pmm_bench_ps_custom1_inventory_summary_blocks_final_certification() -> None:
    summary = summarize_pmm_published_benchmark_inventory()

    assert summary.implemented_count >= 4
    assert summary.partial_count >= 2
    assert summary.missing_count >= 2
    assert summary.published_reference_count == 0
    assert summary.published_required_count >= 4
    assert summary.overall_status == "BLOCKED_FOR_FINAL_CERTIFICATION"


def test_pmm_bench_ps_custom1_inventory_dataframe_is_export_friendly() -> None:
    df = pmm_published_benchmark_inventory_to_dataframe()

    expected = {
        "Benchmark ID",
        "Title",
        "Family",
        "Reference Class",
        "Readiness",
        "Current Evidence",
        "Published Reference Need",
        "Acceptance Gate",
        "Next Action",
        "Solver Scope",
    }
    assert expected.issubset(df.columns)
    assert not df.empty
    assert "PMM.BENCH.PS.CUSTOM" in set(df["Benchmark ID"])


def test_pmm_bench_ps_custom1_is_linked_to_validation_matrix() -> None:
    cases = build_pmm_solver_validation_matrix()
    by_id = {case.case_id: case for case in cases}

    case = by_id["PMM.BENCH.PS.CUSTOM1"]
    assert case.status == "partial"
    assert case.category == "Custom shape PMM"
    assert "published" in case.next_action.lower()
    assert "final certification guard" in case.warnings_addressed


def test_pmm_published_benchmark_inventory_is_available_to_report_registry() -> None:
    tables = collect_available_report_tables({})
    by_key = {table.table_key: table for table in tables}

    table = by_key["pmm_published_benchmark_inventory"]
    assert table.available is True
    assert table.row_count == len(build_pmm_published_benchmark_inventory())
    assert "final certification" in (table.warning or "")


def test_pmm_published_benchmark_inventory_is_in_verification_report_section() -> None:
    snapshot = build_result_traceability_snapshot({})
    sections = default_report_section_plan(snapshot, check_report_readiness(snapshot), [], get_engineering_limitations())
    by_id = {section.section_id: section for section in sections}

    assert "pmm_published_benchmark_inventory" in by_id["verification"].table_keys
