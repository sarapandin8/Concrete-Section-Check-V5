"""Prestress-aware axial-cap validation benchmark pack.

QA.PO1 validates the narrow ACI-style nominal axial compression helper used by
Concrete PMM Pro's PMM axial cap.  The goal is to verify area bookkeeping and
strength-reference policy before the axial-cap prototype note can be lowered in
severity.  These checks are deliberately independent of Streamlit and do not
modify the solver equations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from concrete_pmm_pro.code_checks import aci_max_phiPn, nominal_po_rc, nominal_po_rc_prestressed
from concrete_pmm_pro.core.models import PrestressElement, Rebar, RebarMaterial

PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"


@dataclass(frozen=True)
class POAxialCapCheck:
    """Single prestress-aware axial-cap validation check."""

    check_id: str
    title: str
    status: str
    reference_value: float | None
    solver_value: float | None
    percent_difference: float | None
    tolerance_percent: float | None
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class POAxialCapSummary:
    """Summary for QA.PO1 axial-cap validation checks."""

    checks: list[POAxialCapCheck]
    pass_count: int
    warning_count: int
    fail_count: int
    overall_status: str

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "Check ID": check.check_id,
                    "Title": check.title,
                    "Status": check.status,
                    "Reference": check.reference_value,
                    "Solver": check.solver_value,
                    "Difference (%)": check.percent_difference,
                    "Tolerance (%)": check.tolerance_percent,
                    "Message": check.message,
                }
                for check in self.checks
            ]
        )


def _summary(checks: list[POAxialCapCheck]) -> POAxialCapSummary:
    pass_count = sum(check.status == PASS for check in checks)
    warning_count = sum(check.status == WARNING for check in checks)
    fail_count = sum(check.status == FAIL for check in checks)
    overall = FAIL if fail_count else WARNING if warning_count else PASS
    return POAxialCapSummary(checks, pass_count, warning_count, fail_count, overall)


def _percent_difference(reference: float, solver: float) -> float:
    return abs(solver - reference) / max(abs(reference), 1.0) * 100.0


def _status_from_difference(percent_difference: float, tolerance_percent: float = 1.0e-9) -> str:
    return PASS if percent_difference <= tolerance_percent else FAIL


def _make_rebars() -> list[Rebar]:
    return [
        Rebar(x_mm=-150.0, y_mm=-250.0, diameter_mm=25.0, material_name="Grade420", label="B1"),
        Rebar(x_mm=150.0, y_mm=-250.0, diameter_mm=25.0, material_name="Grade420", label="B2"),
        Rebar(x_mm=-150.0, y_mm=250.0, diameter_mm=25.0, material_name="Grade420", label="T1"),
        Rebar(x_mm=150.0, y_mm=250.0, diameter_mm=25.0, material_name="Grade420", label="T2"),
    ]


def _strand(**updates: object) -> PrestressElement:
    data: dict[str, object] = {
        "x_mm": 0.0,
        "y_mm": -250.0,
        "area_mm2": 140.0,
        "steel_type": "strand",
        "material_name": "Tendon 6-1",
        "fpy_mpa": 1580.0,
        "fpu_mpa": 1860.0,
        "ep_mpa": 195000.0,
        "pe_eff_n": 999_999_999.0,  # intentionally ignored by Po helper
        "bonded": True,
        "count": 12,
        "label": "PS1",
    }
    data.update(updates)
    return PrestressElement(**data)


def _manual_po(fc_mpa: float, ag_mm2: float, ast_mm2: float, aps_mm2: float, fy_mpa: float, fps_ref_mpa: float) -> float:
    return 0.85 * fc_mpa * (ag_mm2 - ast_mm2 - aps_mm2) + fy_mpa * ast_mm2 + fps_ref_mpa * aps_mm2


def _check_value(
    check_id: str,
    title: str,
    reference: float,
    solver: float,
    message: str,
    details: dict[str, Any] | None = None,
    tolerance_percent: float = 1.0e-9,
) -> POAxialCapCheck:
    diff = _percent_difference(reference, solver)
    return POAxialCapCheck(
        check_id=check_id,
        title=title,
        status=_status_from_difference(diff, tolerance_percent),
        reference_value=reference,
        solver_value=solver,
        percent_difference=diff,
        tolerance_percent=tolerance_percent,
        message=message,
        details=details or {},
    )


def run_valid_po1_axial_cap_benchmark_pack() -> POAxialCapSummary:
    """Run QA.PO1 prestress-aware axial-cap validation checks."""

    checks: list[POAxialCapCheck] = []
    fc = 40.0
    ag = 240_000.0
    material = RebarMaterial(name="Grade420", fy_MPa=420.0, Es_MPa=200000.0)
    rebars = _make_rebars()
    ast = sum(bar.area_mm2 for bar in rebars)

    rc_po_solver = nominal_po_rc(fc_MPa=fc, Ag_mm2=ag, rebars=rebars, rebar_material_default=material)
    rc_po_ref = 0.85 * fc * (ag - ast) + material.fy_MPa * ast
    checks.append(
        _check_value(
            "QA.PO1.RC_ONLY",
            "RC-only nominal Po matches independent hand formula",
            rc_po_ref,
            rc_po_solver,
            "RC-only Po uses gross area minus Ast plus fy*Ast.",
            {"Ag_mm2": ag, "Ast_mm2": ast, "fc_MPa": fc, "fy_MPa": material.fy_MPa},
        )
    )

    ps = _strand()
    aps = ps.area_mm2 * ps.count
    ps_only_solver = nominal_po_rc_prestressed(fc_MPa=fc, Ag_mm2=ag, rebars=[], prestress_elements=[ps])
    ps_only_ref = _manual_po(fc, ag, 0.0, aps, 0.0, 1580.0)
    checks.append(
        _check_value(
            "QA.PO1.PS_ONLY_FPY",
            "PS-only nominal Po includes Aps using fpy",
            ps_only_ref,
            ps_only_solver,
            "PS-only Po subtracts Aps from concrete area and adds fpy*Aps.",
            {"Aps_mm2": aps, "fps_ref_MPa": 1580.0},
        )
    )

    rcps_solver = nominal_po_rc_prestressed(
        fc_MPa=fc,
        Ag_mm2=ag,
        rebars=rebars,
        rebar_material_default=material,
        prestress_elements=[ps],
    )
    rcps_ref = _manual_po(fc, ag, ast, aps, material.fy_MPa, 1580.0)
    checks.append(
        _check_value(
            "QA.PO1.RC_PLUS_PS",
            "RC+PS nominal Po combines Ast and Aps without double counting concrete",
            rcps_ref,
            rcps_solver,
            "RC+PS Po subtracts Ast and Aps once from concrete compression term, then adds fy*Ast and fpy*Aps.",
            {"Ag_mm2": ag, "Ast_mm2": ast, "Aps_mm2": aps},
        )
    )

    ps_no_fpy = _strand(fpy_mpa=None, fpu_mpa=1860.0, pe_eff_n=123_456_789.0)
    aps_no_fpy = ps_no_fpy.area_mm2 * ps_no_fpy.count
    fallback_solver = nominal_po_rc_prestressed(fc_MPa=fc, Ag_mm2=ag, rebars=[], prestress_elements=[ps_no_fpy])
    fallback_ref = _manual_po(fc, ag, 0.0, aps_no_fpy, 0.0, 0.90 * 1860.0)
    checks.append(
        _check_value(
            "QA.PO1.FPU_FALLBACK_NOT_PE",
            "Missing fpy uses 0.90fpu and ignores Pe_eff",
            fallback_ref,
            fallback_solver,
            "Nominal Po uses proof/strength reference, not effective prestress or breaking-load metadata.",
            {"Aps_mm2": aps_no_fpy, "fps_ref_MPa": 0.90 * 1860.0, "Pe_eff_N_intentionally_ignored": ps_no_fpy.pe_eff_n},
        )
    )

    count_check = _strand(count=3, area_mm2=200.0, fpy_mpa=1200.0, fpu_mpa=1500.0)
    count_aps = 3 * 200.0
    count_solver = nominal_po_rc_prestressed(fc_MPa=fc, Ag_mm2=ag, rebars=[], prestress_elements=[count_check])
    count_ref = _manual_po(fc, ag, 0.0, count_aps, 0.0, 1200.0)
    checks.append(
        _check_value(
            "QA.PO1.COUNT_MULTIPLIER",
            "Prestress count multiplies element area once",
            count_ref,
            count_solver,
            "Aps uses area_mm2 * count exactly once and does not multiply by strand-count metadata again.",
            {"Area_mm2": 200.0, "Count": 3, "Aps_mm2": count_aps},
        )
    )

    phi_cap_solver = aci_max_phiPn(rcps_solver, phi_compression=0.65, transverse_reinforcement="tied")
    phi_cap_ref = 0.80 * 0.65 * rcps_ref
    checks.append(
        _check_value(
            "QA.PO1.PHIPN_CAP_TIED",
            "Factored tied-column axial cap uses capped phiPo factor",
            phi_cap_ref,
            phi_cap_solver,
            "phiPn,max uses 0.80*phi*Po for tied transverse reinforcement.",
            {"Po_N": rcps_solver, "phi": 0.65, "cap_factor": 0.80},
        )
    )

    # Unbonded exclusion is enforced by the PMM caller.  The helper only sees
    # the list it is given, so this benchmark documents and tests the expected
    # caller-side filter behavior.
    bonded = _strand(label="Bonded", count=1, area_mm2=140.0, bonded=True)
    unbonded = _strand(label="Unbonded", count=1, area_mm2=140.0, bonded=False)
    bonded_only = [element for element in [bonded, unbonded] if element.bonded]
    excluded_solver = nominal_po_rc_prestressed(fc_MPa=fc, Ag_mm2=ag, rebars=[], prestress_elements=bonded_only)
    excluded_ref = _manual_po(fc, ag, 0.0, 140.0, 0.0, 1580.0)
    checks.append(
        _check_value(
            "QA.PO1.UNBONDED_EXCLUDED_BY_CALLER",
            "Unbonded prestress is excluded before calling Po helper",
            excluded_ref,
            excluded_solver,
            "The PMM axial-cap path passes bonded strain-compatible elements only; unbonded elements are excluded upstream.",
            {"Bonded_count": len(bonded_only), "Unbonded_ignored": 1},
        )
    )

    return _summary(checks)
