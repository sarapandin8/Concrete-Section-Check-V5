from __future__ import annotations

import math

import pandas as pd

from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, Rebar
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.ui.analysis_page import _column_pier_combined_vt_check_dataframe
from concrete_pmm_pro.verification.column_pier_vt_benchmarks import (
    PASS,
    benchmark_cases,
    make_benchmark_check,
    reference_values,
    summarize_checks,
)


def _analysis_input_for_vt_case(case) -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=case.width_mm, height_mm=case.height_mm),
        concrete_material=ConcreteMaterial(name="C35", fc_MPa=case.fc_MPa, ecu=0.003, beta1=0.80),
        rebars=[
            Rebar(x_mm=-150.0, y_mm=-250.0, diameter_mm=25.0, material_name="SD40", label="B1"),
            Rebar(x_mm=150.0, y_mm=250.0, diameter_mm=25.0, material_name="SD40", label="B2"),
        ],
        load_cases=[LoadCase(name=case.case_id, Pu_N=0.0, Mux_Nmm=0.0, Muy_Nmm=0.0, load_type="ULS")],
        settings=AnalysisSettings(neutral_axis_angle_steps=12, neutral_axis_depth_steps=10),
    )


def _state_for_vt_case(case, analysis_input: AnalysisInput) -> dict[str, object]:
    return {
        "design_code": "ACI 318",
        "code_edition": "ACI 318-19",
        "rebars": analysis_input.rebars,
        "column_uls_loads_table": pd.DataFrame(
            [
                {
                    "Active": True,
                    "Case Name": case.case_id,
                    "Pu": 0.0,
                    "Mux": 0.0,
                    "Muy": 0.0,
                    "Vux": case.vu_kN if case.direction == "Vux" else 0.0,
                    "Vuy": case.vu_kN if case.direction == "Vuy" else 0.0,
                    "Tu": case.tu_kNm,
                    "Note": "ULS.COL.VT.QA1 benchmark",
                }
            ]
        ),
        "column_pier_transverse_reinforcement_table": pd.DataFrame(
            [
                {
                    "Active": True,
                    "Zone": "Control section",
                    "x_start_m": 0.0,
                    "x_end_m": 0.0,
                    "Bar Size": f"DB{int(case.transverse_diameter_mm)}",
                    "Diameter_mm": case.transverse_diameter_mm,
                    "Legs": case.transverse_legs,
                    "Spacing_mm": case.transverse_spacing_mm,
                    "fy_MPa": case.transverse_fy_MPa,
                    "Note": "closed control section hoop",
                }
            ]
        ),
        "column_pier_transverse_reinforcement_settings": {
            "closed_tie_layout": "Closed ties / hoops",
            "torsion_core_basis": "Auto from section and tie offset",
            "tie_center_offset_mm": case.tie_offset_mm,
        },
    }


def _result_row_for_case(case) -> tuple[dict[str, object], dict[str, float | str]]:
    analysis_input = _analysis_input_for_vt_case(case)
    state = _state_for_vt_case(case, analysis_input)
    df = _column_pier_combined_vt_check_dataframe(state, analysis_input)
    row_df = df[df["Direction"].astype(str) == case.direction]
    assert len(row_df) == 1
    return row_df.iloc[0].to_dict(), reference_values(case)


def _assert_close(actual: object, expected: object, *, rel_tol: float = 1.0e-9, abs_tol: float = 1.0e-9) -> None:
    assert math.isclose(float(actual), float(expected), rel_tol=rel_tol, abs_tol=abs_tol)


def test_column_pier_vt_qa1_reference_cases_cover_expected_routes() -> None:
    cases = benchmark_cases()
    ids = {case.case_id for case in cases}

    assert "ULS.COL.VT.QA1.VUY_MODERATE" in ids
    assert "ULS.COL.VT.QA1.VUX_MODERATE" in ids
    assert "ULS.COL.VT.QA1.ZERO_SHEAR_TORSION_ONLY" in ids
    assert "ULS.COL.VT.QA1.THRESHOLD_ONLY" in ids
    assert len(ids) == len(cases)


def test_column_pier_vt_qa1_geometry_reference_is_traceable_for_rectangular_control_section() -> None:
    reference = reference_values(benchmark_cases()[0])

    assert reference["aoh_mm2"] == 150_000.0
    assert reference["ao_mm2"] == 127_500.0
    assert reference["ph_mm"] == 1_600.0
    assert reference["bw_mm"] == 400.0
    assert reference["d_mm"] == 480.0


def test_column_pier_vt_qa1_app_matches_independent_reference_values() -> None:
    checks = []
    for case in benchmark_cases():
        if case.case_id.endswith("THRESHOLD_ONLY"):
            continue
        row, reference = _result_row_for_case(case)
        assert row["Status"] == "PASS"
        assert row["Interaction form"] == "root-sum-square for solid section"
        for label, app_column, ref_key in [
            ("overall D/C", "Overall D/C value", "overall_dc"),
            ("stress D/C", "Stress D/C value", "stress_dc"),
            ("transverse D/C", "Transverse D/C value", "transverse_dc"),
            ("longitudinal D/C", "Longitudinal D/C value", "longitudinal_dc"),
            ("shear stress", "Shear stress MPa", "shear_stress_MPa"),
            ("torsion stress", "Torsion stress MPa", "torsion_stress_MPa"),
            ("interaction stress", "Interaction stress MPa", "interaction_stress_MPa"),
            ("stress limit", "Stress limit MPa", "stress_limit_MPa"),
            ("Av shear req", "Av shear req mm2/mm", "shear_req_mm2_per_mm"),
            ("At torsion req", "At torsion req mm2/mm", "torsion_req_mm2_per_mm"),
            ("combined transverse req", "Combined transverse req mm2/mm", "combined_req_mm2_per_mm"),
            ("provided Av+2At", "Provided Av+2At per s mm2/mm", "provided_av_2at_per_s"),
            ("Al req", "Al V+T req mm2", "al_req_mm2"),
        ]:
            _assert_close(row[app_column], reference[ref_key])
            checks.append(
                make_benchmark_check(
                    check_id=f"{case.case_id}.{ref_key}",
                    title=f"{case.title} - {label}",
                    reference_value=float(reference[ref_key]),
                    solver_value=float(row[app_column]),
                    message=f"Analysis {app_column} matches independent ULS.COL.VT.QA1 reference.",
                )
            )
    summary = summarize_checks(checks)

    assert summary.overall_status == PASS
    assert summary.fail_count == 0
    assert summary.pass_count >= 30
    assert set(summary.to_dataframe()["Status"]) == {PASS}


def test_column_pier_vt_qa1_threshold_case_uses_source_shear_gate_without_vt_reinforcement() -> None:
    case = next(item for item in benchmark_cases() if item.case_id.endswith("THRESHOLD_ONLY"))
    row, reference = _result_row_for_case(case)

    assert row["Status"] == "PASS"
    assert row["Source torsion status"] == "BELOW THRESHOLD"
    assert row["Interaction form"] == "torsion below threshold"
    assert row["Transverse status"] == "THRESHOLD OK"
    assert row["Longitudinal status"] == "NOT REQUIRED"
    _assert_close(row["Overall D/C value"], reference["overall_dc"])
    _assert_close(row["Provided Av+2At per s mm2/mm"], reference["provided_av_2at_per_s"])


def test_column_pier_vt_qa1_dataframe_is_exportable() -> None:
    case = benchmark_cases()[0]
    row, reference = _result_row_for_case(case)
    summary = summarize_checks(
        [
            make_benchmark_check(
                check_id=f"{case.case_id}.OVERALL_DC",
                title="Overall D/C export check",
                reference_value=float(reference["overall_dc"]),
                solver_value=float(row["Overall D/C value"]),
                message="Export dataframe keeps the key QA values visible.",
            )
        ]
    )
    df = summary.to_dataframe()

    assert not df.empty
    assert {"Check ID", "Title", "Status", "Reference", "Solver", "Difference (%)", "Message"}.issubset(df.columns)
