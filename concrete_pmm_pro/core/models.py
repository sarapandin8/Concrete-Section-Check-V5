"""Pydantic data models used across the application.

Internal units are mm, MPa, N, and N-mm.
"""

from __future__ import annotations

from math import sqrt
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AppBaseModel(BaseModel):
    """Base model with strict-ish project defaults."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Point2D(AppBaseModel):
    x: float
    y: float

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


class ConcreteMaterial(AppBaseModel):
    name: str = "Concrete"
    fc_MPa: float = Field(default=35.0, gt=0, description="Concrete compressive strength")
    ecu: float = Field(default=0.003, gt=0)
    density_kg_m3: float = Field(default=2400.0, gt=0)
    beta1: float | None = Field(default=None, gt=0, le=1.0)
    Ec_MPa: float | None = Field(default=None, gt=0, description="Manual concrete elastic modulus override")
    Ec_method: Literal["ACI auto", "Manual"] = "ACI auto"
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_names(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        legacy_map = {
            "fc_mpa": "fc_MPa",
            "eps_cu": "ecu",
            "lambda_factor": "beta1",
            "ec_mpa": "Ec_MPa",
            "ec_method": "Ec_method",
        }
        for old_name, new_name in legacy_map.items():
            if old_name in migrated and new_name not in migrated:
                migrated[new_name] = migrated.pop(old_name)
        ec_method = migrated.get("Ec_method")
        if isinstance(ec_method, str):
            normalized = ec_method.strip().lower()
            if normalized in {"aci", "aci_auto", "aci auto", "auto", ""}:
                migrated["Ec_method"] = "ACI auto"
            elif normalized in {"manual", "user", "override"}:
                migrated["Ec_method"] = "Manual"
        return migrated

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Concrete material name must not be blank")
        return stripped

    @property
    def fc_mpa(self) -> float:
        return self.fc_MPa

    @property
    def eps_cu(self) -> float:
        return self.ecu

    @property
    def lambda_factor(self) -> float | None:
        return self.beta1

    @property
    def effective_Ec_MPa(self) -> float:
        if self.Ec_method == "Manual" and self.Ec_MPa is not None and self.Ec_MPa > 0:
            return self.Ec_MPa
        return 4700.0 * sqrt(self.fc_MPa)


class RebarMaterial(AppBaseModel):
    name: str = "SD40"
    fy_MPa: float = Field(default=390.0, gt=0)
    Es_MPa: float = Field(default=200000.0, gt=0)
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_names(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        legacy_map = {
            "fy_mpa": "fy_MPa",
            "es_mpa": "Es_MPa",
        }
        for old_name, new_name in legacy_map.items():
            if old_name in migrated and new_name not in migrated:
                migrated[new_name] = migrated.pop(old_name)
        migrated.pop("eps_u", None)
        return migrated

    @property
    def fy_mpa(self) -> float:
        return self.fy_MPa

    @property
    def es_mpa(self) -> float:
        return self.Es_MPa


PrestressSteelType = Literal[
    "wire",
    "strand",
    "prestressing_bar",
    "tendon_group",
    "custom",
]


class PrestressSteelMaterial(AppBaseModel):
    name: str
    steel_type: PrestressSteelType = "strand"
    diameter_mm: float | None = Field(default=None, gt=0)
    area_mm2: float | None = Field(default=None, gt=0)
    grade: str | None = None
    fpy_MPa: float | None = Field(default=None, gt=0)
    fpu_MPa: float = Field(gt=0)
    Ep_MPa: float = Field(default=195000.0, gt=0)
    relaxation_class: str | None = None
    source: str | None = None
    area_source: str | None = None
    is_catalog_verified: bool = False
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_names(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        legacy_map = {
            "fpy_mpa": "fpy_MPa",
            "fpu_mpa": "fpu_MPa",
            "ep_mpa": "Ep_MPa",
            "es_mpa": "Ep_MPa",
        }
        for old_name, new_name in legacy_map.items():
            if old_name in migrated and new_name not in migrated:
                migrated[new_name] = migrated.pop(old_name)
        return migrated

    @model_validator(mode="after")
    def fpy_must_be_less_than_fpu(self) -> "PrestressSteelMaterial":
        if self.fpy_MPa is not None and self.fpy_MPa >= self.fpu_MPa:
            raise ValueError("fpy_MPa must be less than fpu_MPa when both are provided")
        return self

    @property
    def fpy_mpa(self) -> float | None:
        return self.fpy_MPa

    @property
    def fpu_mpa(self) -> float:
        return self.fpu_MPa

    @property
    def ep_mpa(self) -> float:
        return self.Ep_MPa

    @property
    def es_mpa(self) -> float:
        return self.Ep_MPa


class PrestressMaterial(PrestressSteelMaterial):
    """Backward-compatible name. Use PrestressSteelMaterial in new code."""


class SectionGeometry(AppBaseModel):
    name: str = "section"
    outer_polygon: list[Point2D] = Field(min_length=3)
    holes: list[list[Point2D]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("holes")
    @classmethod
    def holes_have_enough_points(cls, holes: list[list[Point2D]]) -> list[list[Point2D]]:
        for hole in holes:
            if len(hole) < 3:
                raise ValueError("Each hole must contain at least 3 points")
        return holes


class Rebar(AppBaseModel):
    x_mm: float
    y_mm: float
    diameter_mm: float = Field(gt=0)
    material_name: str = "SD40"
    label: str | None = None

    @property
    def area_mm2(self) -> float:
        return 3.141592653589793 * self.diameter_mm**2 / 4.0


class PrestressElement(AppBaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    x_mm: float
    y_mm: float
    area_mm2: float = Field(gt=0)
    steel_type: PrestressSteelType = "strand"
    material_name: str | None = None
    diameter_mm: float | None = Field(default=None, gt=0)
    fpy_mpa: float | None = Field(default=None, gt=0)
    fpu_mpa: float | None = Field(default=None, gt=0)
    ep_mpa: float = Field(default=195000.0, gt=0)
    pe_eff_n: float = Field(default=0.0, ge=0)
    bonded: bool = True
    count: int = Field(default=1, ge=1)
    initial_stress_mpa: float | None = Field(default=None, ge=0)
    initial_strain: float | None = None
    label: str | None = None

    @model_validator(mode="after")
    def fpy_must_be_less_than_fpu(self) -> "PrestressElement":
        if self.fpy_mpa is not None and self.fpu_mpa is not None and self.fpy_mpa >= self.fpu_mpa:
            raise ValueError("fpy_mpa must be less than fpu_mpa when both are provided")
        return self

    @property
    def total_area_mm2(self) -> float:
        return self.area_mm2 * self.count


class Tendon(PrestressElement):
    """Backward-compatible alias. Use PrestressElement in new code."""


LoadType = Literal["ULS", "SLS", "Extreme", "Construction", "Other"]
BeamGirderStage = Literal["transfer", "service", "strength", "construction", "fatigue", "other"]


class LoadCase(AppBaseModel):
    name: str = "LC1"
    Pu_N: float = 0.0
    Mux_Nmm: float = 0.0
    Muy_Nmm: float = 0.0
    load_type: LoadType = "ULS"
    active: bool = True
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_force_names(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        legacy_map = {
            "axial_n": "Pu_N",
            "Mx_Nmm": "Mux_Nmm",
            "My_Nmm": "Muy_Nmm",
            "mx_nmm": "Mux_Nmm",
            "my_nmm": "Muy_Nmm",
        }
        for old_name, new_name in legacy_map.items():
            if old_name in migrated and new_name not in migrated:
                migrated[new_name] = migrated.pop(old_name)
        return migrated

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Load case name cannot be blank")
        return value.strip()

    @field_validator("active", mode="before")
    @classmethod
    def active_must_be_boolean(cls, value: Any) -> bool:
        if not isinstance(value, bool):
            raise ValueError("active must be a boolean")
        return value

    @property
    def axial_n(self) -> float:
        return self.Pu_N

    @property
    def Mx_Nmm(self) -> float:
        return self.Mux_Nmm

    @property
    def My_Nmm(self) -> float:
        return self.Muy_Nmm

    @property
    def mx_nmm(self) -> float:
        return self.Mux_Nmm

    @property
    def my_nmm(self) -> float:
        return self.Muy_Nmm


class BeamGirderLoadCase(AppBaseModel):
    """Future beam/girder load placeholder.

    Not connected to the solver or UI calculations in Milestone A.1.
    """

    name: str = "BG-LC1"
    stage: BeamGirderStage = "service"
    Mu_Nmm: float = 0.0
    Vu_N: float = 0.0
    Tu_Nmm: float = 0.0
    Pu_N: float = 0.0
    active: bool = True
    note: str | None = None


class SectionModel(AppBaseModel):
    name: str = "Section Model"
    geometry: SectionGeometry
    concrete: ConcreteMaterial
    rebars: list[Rebar] = Field(default_factory=list)
    prestress_elements: list[PrestressElement] = Field(default_factory=list)
    loads: list[LoadCase] = Field(default_factory=list)


DimensionKind = Literal["horizontal", "vertical", "aligned", "radial", "diameter"]
DimensionLabelMode = Literal["symbol_value", "symbol", "value"]


class DimensionItem(AppBaseModel):
    label: str = ""
    symbol: str | None = None
    start: Point2D
    end: Point2D
    text_position: Point2D
    kind: DimensionKind = "aligned"
    value_mm: float | None = None
    unit: str = "mm"

    def display_label(self, mode: DimensionLabelMode = "symbol_value") -> str:
        value_text = f"{self.value_mm:g} {self.unit}" if self.value_mm is not None else self.label
        if mode == "symbol":
            return self.symbol or self.label or value_text
        if mode == "value":
            return value_text
        if self.symbol and self.value_mm is not None:
            return f"{self.symbol} = {value_text}"
        return self.label or value_text
