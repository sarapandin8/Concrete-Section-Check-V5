from __future__ import annotations

import math

import pandas as pd
import pytest

from concrete_pmm_pro.analysis.capacity_check import check_uls_demands_against_rc_pmm
from concrete_pmm_pro.analysis.result_models import PMMPoint, PMMSolverResult
from concrete_pmm_pro.analysis.slice_envelope import (
    SliceEnvelopeResult,
    build_convex_hull_envelope,
    build_slice_envelope,
    compute_polar_angle_and_radius,
    detect_self_crossing_boundary,
    estimate_directional_capacity_from_envelope,
    remove_near_duplicate_slice_points,
)
from concrete_pmm_pro.core.models import LoadCase


def _circular_slice(radius_kNm: float = 100.0, count: int = 16) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "phiMnx_kNm": radius_kNm * math.cos(2.0 * math.pi * index / count),
                "phiMny_kNm": radius_kNm * math.sin(2.0 * math.pi * index / count),
                "theta_rad": 2.0 * math.pi * index / count,
                "phiPn_kN": 1000.0,
                "source_method": "test",
            }
            for index in range(count)
        ]
    )


def _synthetic_result() -> PMMSolverResult:
    points = []
    for index in range(12):
        theta = 2.0 * math.pi * index / 12
        for p_kN, radius, c_mm in ((900.0, 90.0, 100.0), (1100.0, 110.0, 200.0)):
            mx = radius * math.cos(theta)
            my = radius * math.sin(theta)
            points.append(
                PMMPoint(
                    theta_rad=theta,
                    c_mm=c_mm,
                    Pn_N=p_kN * 1000.0,
                    Mnx_Nmm=mx * 1_000_000.0,
                    Mny_Nmm=my * 1_000_000.0,
                    phi=0.65,
                    phiPn_N=p_kN * 1000.0,
                    phiPn_capped_N=p_kN * 1000.0,
                    phiMnx_Nmm=mx * 1_000_000.0,
                    phiMny_Nmm=my * 1_000_000.0,
                    eps_t=None,
                    strain_condition="compression-controlled",
                    concrete_area_mm2=1.0,
                    concrete_force_N=1.0,
                )
            )
    return PMMSolverResult(points=points)


def test_compute_polar_angle_and_radius_adds_columns() -> None:
    df = compute_polar_angle_and_radius(pd.DataFrame([{"phiMnx_kNm": 3.0, "phiMny_kNm": 4.0}]))

    assert df.loc[0, "radius_kNm"] == pytest.approx(5.0)
    assert df.loc[0, "angle_rad"] == pytest.approx(math.atan2(4.0, 3.0))


def test_remove_near_duplicate_slice_points_keeps_larger_radius() -> None:
    df = pd.DataFrame(
        [
            {"phiMnx_kNm": 10.0, "phiMny_kNm": 0.0},
            {"phiMnx_kNm": 20.0, "phiMny_kNm": 0.0001},
            {"phiMnx_kNm": 0.0, "phiMny_kNm": 10.0},
        ]
    )

    cleaned = remove_near_duplicate_slice_points(df, angle_tol_rad=1.0e-3)

    assert len(cleaned) == 2
    assert cleaned["radius_kNm"].max() == pytest.approx(20.0, rel=1.0e-4)


def test_build_slice_envelope_returns_valid_envelope_for_circular_slice() -> None:
    envelope = build_slice_envelope(_circular_slice())

    assert envelope.is_valid
    assert envelope.method == "polar_max"
    assert envelope.point_count_output == 16


def test_build_slice_envelope_sorts_points_by_angle() -> None:
    envelope = build_slice_envelope(_circular_slice().sample(frac=1.0, random_state=1))
    angles = envelope.envelope_df["angle_rad"].to_list()

    assert angles == sorted(angles)


def test_detect_self_crossing_boundary_detects_bow_tie_polygon() -> None:
    bow_tie = pd.DataFrame(
        [
            {"phiMnx_kNm": -1.0, "phiMny_kNm": -1.0},
            {"phiMnx_kNm": 1.0, "phiMny_kNm": 1.0},
            {"phiMnx_kNm": -1.0, "phiMny_kNm": 1.0},
            {"phiMnx_kNm": 1.0, "phiMny_kNm": -1.0},
        ]
    )

    assert detect_self_crossing_boundary(bow_tie)


def test_build_convex_hull_envelope_returns_hull_for_scattered_points() -> None:
    hull = build_convex_hull_envelope(_circular_slice(count=8))

    assert hull.used_convex_hull
    assert hull.is_valid
    assert any("Convex hull fallback was used" in warning for warning in hull.warnings)


def test_build_slice_envelope_uses_convex_hull_fallback_when_sparse() -> None:
    envelope = build_slice_envelope(_circular_slice(count=6))

    assert envelope.used_convex_hull
    assert any("Convex hull fallback was used" in warning for warning in envelope.warnings)


def test_moderate_angular_coverage_warns_without_forcing_invalidity() -> None:
    partial = pd.DataFrame(
        [
            {
                "phiMnx_kNm": 100.0 * math.cos(angle),
                "phiMny_kNm": 100.0 * math.sin(angle),
                "theta_rad": angle,
                "phiPn_kN": 1000.0,
            }
            for angle in [0.0, 0.35, 0.7, 1.05, 1.4, 1.75, 2.1, 2.45, 2.8, 3.15]
        ]
    )

    envelope = build_slice_envelope(partial)

    assert any("Angular coverage is moderate" in warning or "Angular coverage is limited" in warning for warning in envelope.warnings)
    assert not any("Angular coverage is incomplete" in warning for warning in envelope.warnings)


def test_estimate_directional_capacity_from_envelope_returns_expected_radius_for_circle() -> None:
    envelope = build_slice_envelope(_circular_slice(radius_kNm=100.0))

    estimate = estimate_directional_capacity_from_envelope(envelope, Mux_kNm=50.0, Muy_kNm=0.0)

    assert estimate["capacity_phiMn_kNm"] == pytest.approx(100.0)
    assert estimate["dcr"] == pytest.approx(0.5)


def test_estimate_directional_capacity_from_envelope_handles_angle_wrapping() -> None:
    radius = 100.0
    slice_df = pd.DataFrame(
        [
            {"phiMnx_kNm": radius * math.cos(math.radians(170.0)), "phiMny_kNm": radius * math.sin(math.radians(170.0))},
            {"phiMnx_kNm": radius * math.cos(math.radians(-170.0)), "phiMny_kNm": radius * math.sin(math.radians(-170.0))},
            {"phiMnx_kNm": -radius, "phiMny_kNm": 0.0},
        ]
    )
    envelope = build_convex_hull_envelope(slice_df)

    estimate = estimate_directional_capacity_from_envelope(
        envelope,
        Mux_kNm=50.0 * math.cos(math.radians(179.0)),
        Muy_kNm=50.0 * math.sin(math.radians(179.0)),
    )

    assert estimate["capacity_phiMn_kNm"] is not None
    assert estimate["dcr"] is not None


def test_estimate_directional_capacity_uses_nearest_boundary_for_multiple_ray_intersections() -> None:
    envelope_df = pd.DataFrame(
        [
            {"phiMnx_kNm": -100.0, "phiMny_kNm": -100.0},
            {"phiMnx_kNm": 200.0, "phiMny_kNm": -100.0},
            {"phiMnx_kNm": 200.0, "phiMny_kNm": 100.0},
            {"phiMnx_kNm": -100.0, "phiMny_kNm": 100.0},
            {"phiMnx_kNm": -100.0, "phiMny_kNm": 60.0},
            {"phiMnx_kNm": 100.0, "phiMny_kNm": 60.0},
            {"phiMnx_kNm": 100.0, "phiMny_kNm": 20.0},
            {"phiMnx_kNm": 20.0, "phiMny_kNm": 20.0},
            {"phiMnx_kNm": 20.0, "phiMny_kNm": -20.0},
            {"phiMnx_kNm": 100.0, "phiMny_kNm": -20.0},
            {"phiMnx_kNm": 100.0, "phiMny_kNm": -60.0},
            {"phiMnx_kNm": -100.0, "phiMny_kNm": -60.0},
        ]
    )
    envelope = SliceEnvelopeResult(
        envelope_df=envelope_df,
        method="manual_non_star_guard",
        point_count_input=len(envelope_df),
        point_count_output=len(envelope_df),
        is_valid=True,
    )

    estimate = estimate_directional_capacity_from_envelope(envelope, Mux_kNm=50.0, Muy_kNm=0.0)

    assert estimate["capacity_phiMn_kNm"] == pytest.approx(20.0)
    assert any("nearest boundary" in warning for warning in estimate["warnings"])


def test_dc_check_uses_slice_envelope_method_when_possible() -> None:
    summary = check_uls_demands_against_rc_pmm(
        _synthetic_result(),
        [LoadCase(name="ULS-ENV", Pu_N=1_000_000.0, Mux_Nmm=50_000_000.0, Muy_Nmm=0.0)],
    )

    assert summary.results[0].dcr == pytest.approx(0.5)
    assert "PMM slice envelope" in summary.results[0].message
