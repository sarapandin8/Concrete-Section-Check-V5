"""Central prototype warning text used by analysis and UI modules."""

PMM_PROTOTYPE_WARNING = (
    "PMM results are prototype results for engineering review. Final production-grade validation is future work."
)
DCR_PROTOTYPE_WARNING = (
    "Demand/capacity check uses cleaned Pu-slice PMM capacity extraction with ray-intersection; benchmark validation remains in progress."
)
BONDED_PRESTRESS_PROTOTYPE_WARNING = (
    "Bonded prestress is included using the current prototype strain compatibility model."
)
UNBONDED_PRESTRESS_IGNORED_WARNING = (
    "Unbonded prestress is not included in the current solver and is ignored."
)
SERVICEABILITY_NOT_IMPLEMENTED_WARNING = "Serviceability / SLS checks are not implemented yet."
REPORT_EXPORT_NOT_IMPLEMENTED_WARNING = "Engineering report export is not implemented yet."
CONVEX_HULL_FALLBACK_WARNING = (
    "Convex hull fallback was used. This may overestimate capacity for non-convex interaction shapes."
)
RC_AXIAL_CAP_LIMITATION_WARNING = (
    "ACI axial cap uses the QA.PO1-validated prestress-aware Po helper including ordinary rebar "
    "and bonded prestress steel. Unbonded prestress is excluded from the axial-cap helper by solver policy; "
    "review code-specific axial-compression limits before final design."
)


def deduplicate_warnings(warnings: list[str]) -> list[str]:
    """Return unique warnings while preserving first-seen order."""

    return list(dict.fromkeys(warning for warning in warnings if warning))
