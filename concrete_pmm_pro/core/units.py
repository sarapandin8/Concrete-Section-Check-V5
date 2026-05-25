"""Unit conversion helpers.

Internal force and moment units are N and N-mm.
"""

TONF_TO_KN = 9.80665


def kN_to_N(x: float) -> float:
    return float(x) * 1000.0


def N_to_kN(x: float) -> float:
    return float(x) / 1000.0


def kNm_to_Nmm(x: float) -> float:
    return float(x) * 1_000_000.0


def Nmm_to_kNm(x: float) -> float:
    return float(x) / 1_000_000.0


def tonf_to_N(x: float) -> float:
    return kN_to_N(float(x) * TONF_TO_KN)


def N_to_tonf(x: float) -> float:
    return N_to_kN(x) / TONF_TO_KN


def tonfm_to_Nmm(x: float) -> float:
    return kNm_to_Nmm(float(x) * TONF_TO_KN)


def Nmm_to_tonfm(x: float) -> float:
    return Nmm_to_kNm(x) / TONF_TO_KN
