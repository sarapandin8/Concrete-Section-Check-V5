"""Prestressing tendon product database helpers.

The records in this module describe tendons assembled from 15.2 mm
prestressing strands. Breaking load and duct data are reference information
only; effective prestress remains a user-controlled input.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt
from typing import Any


DEFAULT_STRAND_DIAMETER_MM = 15.2
DEFAULT_STRAND_AREA_MM2 = 140.0
DEFAULT_STRAND_FPY_MPA = 1580.0
DEFAULT_STRAND_FPU_MPA = 1860.0
DEFAULT_STRAND_EP_MPA = 195000.0
DEFAULT_BREAKING_LOAD_PER_STRAND_KN = 260.0


@dataclass(frozen=True)
class TendonProduct:
    label: str
    description: str
    strand_count: int
    strand_diameter_mm: float = DEFAULT_STRAND_DIAMETER_MM
    strand_area_mm2: float = DEFAULT_STRAND_AREA_MM2
    tendon_area_mm2: float = DEFAULT_STRAND_AREA_MM2
    breaking_load_kN: float = DEFAULT_BREAKING_LOAD_PER_STRAND_KN
    fpy_MPa: float = DEFAULT_STRAND_FPY_MPA
    fpu_MPa: float = DEFAULT_STRAND_FPU_MPA
    Ep_MPa: float = DEFAULT_STRAND_EP_MPA
    duct_type: str | None = None
    duct_id_mm: float | None = None
    typical_use: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "description": self.description,
            "strand_count": self.strand_count,
            "strand_diameter_mm": self.strand_diameter_mm,
            "strand_area_mm2": self.strand_area_mm2,
            "tendon_area_mm2": self.tendon_area_mm2,
            "breaking_load_kN": self.breaking_load_kN,
            "fpy_MPa": self.fpy_MPa,
            "fpu_MPa": self.fpu_MPa,
            "Ep_MPa": self.Ep_MPa,
            "duct_type": self.duct_type,
            "duct_id_mm": self.duct_id_mm,
            "typical_use": self.typical_use,
        }


def standard_tendon_label(strand_count: int) -> str:
    """Return the user-facing standard 15.2 mm tendon product label."""

    return f"Tendon 6-{int(strand_count)}"


def legacy_tendon_label(strand_count: int) -> str:
    """Return the old project-file label kept for backward compatibility."""

    return f"6-{int(strand_count)}"


def tendon_product_display_label(label: str | None) -> str:
    """Normalize legacy tendon labels to the current user-facing label.

    Older project files and tests may contain labels such as ``6-12``. The UI
    now displays ``Tendon 6-12`` for clarity, but the database lookup must keep
    accepting the legacy form so old projects continue to load safely.
    """

    count = _parse_tendon_6n_count(label)
    return standard_tendon_label(count) if count is not None else str(label or "").strip()


def _parse_tendon_6n_count(label: str | None) -> int | None:
    text = str(label or "").strip()
    if not text:
        return None
    if text.lower().startswith("tendon "):
        text = text.split(None, 1)[1].strip()
    if not text.startswith("6-"):
        return None
    try:
        count = int(text.split("-", 1)[1])
    except (TypeError, ValueError):
        return None
    return count if count >= 1 else None


def is_tendon_6n_label(label: str | None) -> bool:
    return _parse_tendon_6n_count(label) is not None


def _standard_product(
    strand_count: int,
    description: str = "Round",
    duct_type: str | None = "Round duct",
    duct_id_mm: float | None = None,
    typical_use: str | None = None,
) -> TendonProduct:
    return TendonProduct(
        label=standard_tendon_label(strand_count),
        description=description,
        strand_count=strand_count,
        tendon_area_mm2=strand_count * DEFAULT_STRAND_AREA_MM2,
        breaking_load_kN=strand_count * DEFAULT_BREAKING_LOAD_PER_STRAND_KN,
        duct_type=duct_type,
        duct_id_mm=duct_id_mm,
        typical_use=typical_use,
    )


_SPECIAL_STANDARD_TENDON_METADATA: dict[int, dict[str, Any]] = {
    1: {
        "description": "Monostrand",
        "duct_type": "Flat duct",
        "duct_id_mm": None,
        "typical_use": "Flat slab / lightweight structure / external prestressing",
    },
    2: {"description": "Flat", "duct_type": "Flat duct", "duct_id_mm": None},
    3: {"description": "Flat/Round", "duct_type": "Round duct if used", "duct_id_mm": 50.0},
    4: {"description": "Flat/Round", "duct_type": "Round duct if used", "duct_id_mm": 55.0},
    7: {"duct_id_mm": 85.0},
    9: {"duct_id_mm": 70.0},
    12: {"duct_id_mm": 80.0},
    15: {"duct_id_mm": 90.0},
    19: {"duct_id_mm": 100.0},
    22: {"duct_id_mm": 105.0},
    27: {"duct_id_mm": 115.0},
    31: {"duct_id_mm": 120.0},
    37: {"duct_id_mm": 130.0},
    43: {"duct_id_mm": 140.0},
    55: {"description": "Special", "duct_id_mm": 160.0},
}


def _make_standard_tendon_products() -> tuple[TendonProduct, ...]:
    products: list[TendonProduct] = []
    for strand_count in range(1, 56):
        metadata = _SPECIAL_STANDARD_TENDON_METADATA.get(strand_count, {})
        products.append(_standard_product(strand_count, **metadata))
    return tuple(products)


STANDARD_TENDON_PRODUCTS: tuple[TendonProduct, ...] = _make_standard_tendon_products()

def list_tendon_products() -> list[TendonProduct]:
    return list(STANDARD_TENDON_PRODUCTS)


def tendon_product_options() -> list[str]:
    return [product.label for product in STANDARD_TENDON_PRODUCTS]


def get_tendon_product(label: str) -> TendonProduct | None:
    normalized = str(label or "").strip()
    requested_count = _parse_tendon_6n_count(normalized)
    for product in STANDARD_TENDON_PRODUCTS:
        if product.label == normalized:
            return product
        if requested_count is not None and product.strand_count == requested_count:
            return product
    return None


def equivalent_steel_diameter_mm(area_mm2: float | None) -> float | None:
    if area_mm2 is None or area_mm2 <= 0:
        return None
    return sqrt(4.0 * area_mm2 / pi)


def make_custom_tendon_product(
    strand_count: int,
    label: str | None = None,
    strand_area_mm2: float = DEFAULT_STRAND_AREA_MM2,
    breaking_load_per_strand_kN: float = DEFAULT_BREAKING_LOAD_PER_STRAND_KN,
    strand_diameter_mm: float = DEFAULT_STRAND_DIAMETER_MM,
    fpy_MPa: float = DEFAULT_STRAND_FPY_MPA,
    fpu_MPa: float = DEFAULT_STRAND_FPU_MPA,
    Ep_MPa: float = DEFAULT_STRAND_EP_MPA,
    duct_id_mm: float | None = None,
    duct_type: str | None = None,
) -> TendonProduct:
    if strand_count < 1:
        raise ValueError("strand_count must be at least 1")
    if strand_area_mm2 <= 0:
        raise ValueError("strand_area_mm2 must be positive")
    if breaking_load_per_strand_kN <= 0:
        raise ValueError("breaking_load_per_strand_kN must be positive")
    if strand_diameter_mm <= 0:
        raise ValueError("strand_diameter_mm must be positive")
    if fpy_MPa <= 0:
        raise ValueError("fpy_MPa must be positive")
    if fpu_MPa <= 0:
        raise ValueError("fpu_MPa must be positive")
    if fpy_MPa >= fpu_MPa:
        raise ValueError("fpy_MPa must be less than fpu_MPa")
    if Ep_MPa <= 0:
        raise ValueError("Ep_MPa must be positive")
    resolved_label = str(label).strip() if label and str(label).strip() else standard_tendon_label(strand_count)
    return TendonProduct(
        label=resolved_label,
        description="Custom tendon",
        strand_count=strand_count,
        strand_diameter_mm=strand_diameter_mm,
        strand_area_mm2=strand_area_mm2,
        tendon_area_mm2=strand_count * strand_area_mm2,
        breaking_load_kN=strand_count * breaking_load_per_strand_kN,
        fpy_MPa=fpy_MPa,
        fpu_MPa=fpu_MPa,
        Ep_MPa=Ep_MPa,
        duct_type=duct_type,
        duct_id_mm=duct_id_mm,
    )


def apply_tendon_product_to_row(row: dict[str, Any], product_label_or_product: str | TendonProduct) -> dict[str, Any]:
    product = get_tendon_product(product_label_or_product) if isinstance(product_label_or_product, str) else product_label_or_product
    if product is None:
        raise ValueError(f"Unknown tendon product: {product_label_or_product}")
    updated = dict(row)
    updated["Steel Type"] = "tendon_group"
    updated["Product"] = product.label
    updated["Area_mm2"] = product.tendon_area_mm2
    updated["Diameter_mm"] = None
    updated["Eq Steel Dia_mm"] = equivalent_steel_diameter_mm(product.tendon_area_mm2)
    updated["fpy_MPa"] = product.fpy_MPa
    updated["fpu_MPa"] = product.fpu_MPa
    updated["Ep_MPa"] = product.Ep_MPa
    updated.setdefault("Count", 1)
    updated["Strand Count"] = product.strand_count
    updated["Strand Diameter_mm"] = product.strand_diameter_mm
    updated["Strand Area_mm2"] = product.strand_area_mm2
    updated["Breaking Load_kN"] = product.breaking_load_kN
    updated["Duct Type"] = product.duct_type or ""
    updated["Duct ID_mm"] = product.duct_id_mm
    updated["Tendon Description"] = product.description
    updated["Typical Use"] = product.typical_use or ""
    note = str(updated.get("Note") or "").strip()
    product_note = (
        f"Tendon product {product.label}: {product.strand_count} x {product.strand_diameter_mm:g} mm strands; "
        f"Aps={product.tendon_area_mm2:g} mm2; breaking load={product.breaking_load_kN:g} kN reference only; "
        "duct ID is reference only, not steel diameter."
    )
    updated["Note"] = f"{note} | {product_note}" if note else product_note
    return updated
