"""PMM prestressed/custom-shape published benchmark readiness inventory.

PMM.BENCH.PS.CUSTOM1 is a benchmark governance layer, not a solver change.
It records which prestressed and custom-shape PMM topics already have
executable internal evidence and which topics still need traceable published
references before the project can claim final code-certified PMM behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


BenchmarkFamily = Literal[
    "RC baseline",
    "Prestress PMM",
    "Custom shape PMM",
    "Demand/Capacity",
]
ReferenceClass = Literal["internal", "independent_derived", "published_required", "published_reference"]
Readiness = Literal["implemented", "partial", "missing"]


@dataclass(frozen=True)
class PMMPublishedBenchmarkItem:
    """One benchmark-library row for prestressed/custom-shape PMM readiness."""

    benchmark_id: str
    title: str
    family: BenchmarkFamily
    reference_class: ReferenceClass
    readiness: Readiness
    current_evidence: str
    published_reference_need: str
    acceptance_gate: str
    next_action: str
    solver_scope: str


@dataclass(frozen=True)
class PMMPublishedBenchmarkInventorySummary:
    """Compact status summary for the benchmark inventory."""

    items: list[PMMPublishedBenchmarkItem]
    implemented_count: int
    partial_count: int
    missing_count: int
    published_reference_count: int
    published_required_count: int
    overall_status: str

    def to_dataframe(self) -> pd.DataFrame:
        return pmm_published_benchmark_inventory_to_dataframe(self.items)


def build_pmm_published_benchmark_inventory() -> list[PMMPublishedBenchmarkItem]:
    """Return the current PMM benchmark-library readiness inventory.

    ``published_required`` means no published/reference source is credited yet.
    Internal or independently derived checks may still be implemented, but they
    must not be described as published benchmarks.
    """

    return [
        PMMPublishedBenchmarkItem(
            benchmark_id="PMM.BENCH.RC.RECT.INTERNAL",
            title="Rectangular RC PMM internal reference pack",
            family="RC baseline",
            reference_class="independent_derived",
            readiness="implemented",
            current_evidence="VALID.RC1, VALID.RC2, VALID.PMM.DC1, and PMM.FINAL.RC1 internal/derived checks are executable.",
            published_reference_need="Add at least one published RC uniaxial and biaxial PMM example before final certification wording.",
            acceptance_gate="Current evidence supports guarded ACI RC production-preview, not final code certification.",
            next_action="Keep RC benchmarks as baseline controls while adding published reference examples.",
            solver_scope="ACI RC flexural PMM baseline.",
        ),
        PMMPublishedBenchmarkItem(
            benchmark_id="PMM.BENCH.PS.PO.APS",
            title="Bonded prestress axial-cap and Aps bookkeeping",
            family="Prestress PMM",
            reference_class="independent_derived",
            readiness="implemented",
            current_evidence="QA.PO1 validates RC-only, PS-only, RC+PS, fpu fallback, count, phiPn cap, and unbonded exclusion behavior.",
            published_reference_need="Add published prestressed column/section axial-cap example that documents bonded Aps treatment.",
            acceptance_gate="Pe_eff and product breaking-load metadata must not drive nominal Po; bonded Aps uses fpy or 0.90fpu policy.",
            next_action="Find or create a traceable design example with ordinary rebar plus bonded prestressing steel.",
            solver_scope="ACI-style nominal Po and phiPn,max helper.",
        ),
        PMMPublishedBenchmarkItem(
            benchmark_id="PMM.BENCH.PS.RECT.INTERNAL",
            title="Rectangular bonded prestress PMM internal benchmark",
            family="Prestress PMM",
            reference_class="internal",
            readiness="implemented",
            current_evidence="VALID.PS1 and VALID.PS2 exercise PS-only, RC+PS, Pe_eff-to-fpe, eps_t, fpu metadata, compression-reversal metadata, and governing-region traceability.",
            published_reference_need="Add published prestressed PMM section example with documented tendon eccentricity, fps/fpe assumptions, phi policy, and P-M result values.",
            acceptance_gate="Internal trend and metadata checks must pass before comparing against external numeric references.",
            next_action="Select a published/reference rectangular prestressed column or section example before changing solver status wording.",
            solver_scope="Bonded active prestress in PMM strain compatibility.",
        ),
        PMMPublishedBenchmarkItem(
            benchmark_id="PMM.BENCH.PS.PASSIVE",
            title="Passive PT bar / passive prestressing steel PMM behavior",
            family="Prestress PMM",
            reference_class="internal",
            readiness="implemented",
            current_evidence="SOLVER.PS.PASSIVE1 confirms Pe_eff=0 rows contribute as passive high-strength bonded steel without active-prestress stress warnings.",
            published_reference_need="Add a reference case for high-strength passive PT bars or strands in a column section if final wording must cover this route.",
            acceptance_gate="Passive rows must not trigger active-prestress fpu/compression-reversal warnings.",
            next_action="Keep passive PS as guarded high-strength steel until an external reference case is available.",
            solver_scope="Bonded passive prestressing steel / PT bar rows.",
        ),
        PMMPublishedBenchmarkItem(
            benchmark_id="PMM.BENCH.CUSTOM.HOLLOW",
            title="Custom hollow section PMM geometry integration",
            family="Custom shape PMM",
            reference_class="published_required",
            readiness="partial",
            current_evidence="Geometry and section-property tests cover hollow shapes; PMM-specific hollow/custom strain-compatibility benchmarks are not yet a dedicated pack.",
            published_reference_need="Add published or independently reproduced hollow-wall / box / wall section PMM examples with known P-Mx-My values.",
            acceptance_gate="Concrete compression integration must exclude holes/voids and rebar/prestress must be verified to lie in concrete material regions.",
            next_action="Build a custom-shape PMM benchmark pack after selecting reference geometries and acceptance tolerances.",
            solver_scope="Void-aware and custom-polygon strain compatibility.",
        ),
        PMMPublishedBenchmarkItem(
            benchmark_id="PMM.BENCH.CUSTOM.IRREGULAR",
            title="Irregular / user-defined polygon PMM benchmark",
            family="Custom shape PMM",
            reference_class="published_required",
            readiness="missing",
            current_evidence="No dedicated PMM benchmark pack for user-defined irregular polygon sections is credited yet.",
            published_reference_need="Add external/reference irregular section examples or independently derived polygon-clipping references for nonrectangular PMM states.",
            acceptance_gate="Nonrectangular compression block clipping, centroid/moment sign convention, and P-Mx-My output must match a separate reference implementation.",
            next_action="Implement independent polygon-clipping reference checks before claiming custom-shape PMM final readiness.",
            solver_scope="General custom polygon sections.",
        ),
        PMMPublishedBenchmarkItem(
            benchmark_id="PMM.BENCH.PS.CUSTOM",
            title="Prestressed custom-shape PMM benchmark",
            family="Prestress PMM",
            reference_class="published_required",
            readiness="missing",
            current_evidence="No published/reference prestressed custom-shape PMM case is credited yet.",
            published_reference_need="Add a traceable prestressed I/box/wall/custom section benchmark with tendon coordinates, fpe/fps assumptions, material model, and P-Mx-My result values.",
            acceptance_gate="Both custom concrete geometry integration and bonded prestress stress-strain response must pass before final acceptance.",
            next_action="Choose reference case sources before any solver equation or status wording change.",
            solver_scope="Bonded active prestress plus custom concrete polygon PMM.",
        ),
        PMMPublishedBenchmarkItem(
            benchmark_id="PMM.BENCH.DC.PUBLISHED",
            title="Published/reference demand-capacity extraction benchmark",
            family="Demand/Capacity",
            reference_class="published_required",
            readiness="partial",
            current_evidence="VALID.PMM.DC1 includes synthetic ray-envelope checks and an RC rectangular no-overestimate guard.",
            published_reference_need="Add published/reference biaxial demand point examples so D/C extraction can be checked against accepted PMM capacities.",
            acceptance_gate="Selected-Pu slice and directional ray capacity must not overestimate the reference envelope.",
            next_action="Pair each future published PMM benchmark with a demand point and expected D/C extraction result.",
            solver_scope="PMM demand/capacity post-processing.",
        ),
    ]


def pmm_published_benchmark_inventory_to_dataframe(
    items: list[PMMPublishedBenchmarkItem] | None = None,
) -> pd.DataFrame:
    """Return an export-friendly benchmark inventory table."""

    rows = items if items is not None else build_pmm_published_benchmark_inventory()
    return pd.DataFrame(
        [
            {
                "Benchmark ID": item.benchmark_id,
                "Title": item.title,
                "Family": item.family,
                "Reference Class": item.reference_class,
                "Readiness": item.readiness,
                "Current Evidence": item.current_evidence,
                "Published Reference Need": item.published_reference_need,
                "Acceptance Gate": item.acceptance_gate,
                "Next Action": item.next_action,
                "Solver Scope": item.solver_scope,
            }
            for item in rows
        ],
        columns=[
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
        ],
    )


def summarize_pmm_published_benchmark_inventory(
    items: list[PMMPublishedBenchmarkItem] | None = None,
) -> PMMPublishedBenchmarkInventorySummary:
    """Return the current benchmark-readiness counts and overall gate status."""

    rows = items if items is not None else build_pmm_published_benchmark_inventory()
    implemented = sum(item.readiness == "implemented" for item in rows)
    partial = sum(item.readiness == "partial" for item in rows)
    missing = sum(item.readiness == "missing" for item in rows)
    published_reference_count = sum(item.reference_class == "published_reference" for item in rows)
    published_required_count = sum(item.reference_class == "published_required" for item in rows)
    if missing:
        overall = "BLOCKED_FOR_FINAL_CERTIFICATION"
    elif partial or published_required_count:
        overall = "PUBLISHED_REFERENCES_REQUIRED"
    else:
        overall = "READY_FOR_DETAILED_NUMERIC_BENCHMARKS"
    return PMMPublishedBenchmarkInventorySummary(
        items=rows,
        implemented_count=implemented,
        partial_count=partial,
        missing_count=missing,
        published_reference_count=published_reference_count,
        published_required_count=published_required_count,
        overall_status=overall,
    )
