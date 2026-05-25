"""Pydantic models for the serviceability/SLS foundation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from concrete_pmm_pro.core.models import LoadCase

StressSignConvention = Literal["compression_negative"]
SectionBasis = Literal["gross"]
ServiceabilityLoadType = Literal["SLS"]
ConcreteTensionLimitMode = Literal["no_tension", "user_defined", "sqrt_fc_ratio"]
ServiceabilityStatus = Literal["NOT_CHECKED", "READY", "WARNING", "ERROR", "PASS", "FAIL"]
CriticalPointFilter = Literal["all", "extreme_fibers_only"]
StressCheckPointType = Literal[
    "extreme_fiber",
    "reference",
    "tendon_zone",
    "web_flange_junction",
    "reentrant_corner",
    "construction_joint",
    "segmental_joint",
    "custom",
]


class ServiceabilitySettings(BaseModel):
    """Settings stored now for future serviceability stress checks."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    enabled: bool = False
    stress_sign_convention: StressSignConvention = "compression_negative"
    section_basis: SectionBasis = "gross"
    check_load_type: ServiceabilityLoadType = "SLS"
    concrete_compression_limit_ratio: float = Field(default=0.45, gt=0)
    concrete_tension_limit_mode: ConcreteTensionLimitMode = "user_defined"
    concrete_tension_limit_MPa: float = Field(default=0.0, ge=0)
    concrete_tension_sqrt_fc_ratio: float = Field(default=0.5, ge=0)
    allow_tension: bool = True
    no_tension_check: bool = False
    decompression_check: bool = False
    stress_zero_tolerance_MPa: float = Field(default=1.0e-6, ge=0)
    critical_point_filter: CriticalPointFilter = "all"
    include_prestress_effective_force: bool = False
    use_transformed_section: bool = False
    concrete_Ec_MPa: float | None = Field(default=None, gt=0)
    Ec_method: Literal["aci_normal_weight"] = "aci_normal_weight"
    transformed_include_rebar: bool = True
    transformed_include_prestress: bool = True
    transformed_area_convention: Literal["net_steel"] = "net_steel"
    note: str | None = None

    @model_validator(mode="after")
    def apply_no_tension_limit(self) -> "ServiceabilitySettings":
        if self.no_tension_check or self.decompression_check or self.concrete_tension_limit_mode == "no_tension":
            object.__setattr__(self, "concrete_tension_limit_MPa", 0.0)
            object.__setattr__(self, "allow_tension", False)
        return self


class GrossSectionProperties(BaseModel):
    """Gross concrete section properties in internal mm-based units."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    area_mm2: float = Field(gt=0)
    centroid_x_mm: float
    centroid_y_mm: float
    Ix_mm4: float = Field(gt=0)
    Iy_mm4: float = Field(gt=0)
    Ixy_mm4: float
    x_min_mm: float
    x_max_mm: float
    y_min_mm: float
    y_max_mm: float
    section_modulus_top_mm3: float | None = None
    section_modulus_bottom_mm3: float | None = None
    section_modulus_left_mm3: float | None = None
    section_modulus_right_mm3: float | None = None
    warnings: list[str] = Field(default_factory=list)


class StressCheckPoint(BaseModel):
    """Named point for future serviceability stress checks."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    name: str
    x_mm: float
    y_mm: float
    point_type: StressCheckPointType = "custom"
    active: bool = True
    include_in_governing: bool = True
    source: str = "user"
    note: str | None = None


class ServiceStressPointResult(BaseModel):
    """Placeholder result model for future SLS stress calculations."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    combo_name: str
    point_name: str
    x_mm: float
    y_mm: float
    section_basis: str | None = None
    section_area_mm2: float | None = None
    section_centroid_x_mm: float | None = None
    section_centroid_y_mm: float | None = None
    point_type: str | None = None
    point_source: str | None = None
    include_in_governing: bool = True
    external_stress_MPa: float | None = None
    prestress_stress_MPa: float | None = None
    total_stress_MPa: float | None = None
    stress_MPa: float | None = None
    limit_MPa: float | None = None
    utilization: float | None = None
    stress_type: str | None = None
    status: ServiceabilityStatus = "NOT_CHECKED"
    message: str = ""


class PrestressServiceContribution(BaseModel):
    """Gross-section effective prestress contribution for SLS stress checks."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    bonded_count: int = 0
    unbonded_ignored_count: int = 0
    total_pe_eff_N: float = 0.0
    total_area_mm2: float = 0.0
    centroid_x_mm: float | None = None
    centroid_y_mm: float | None = None
    Mpe_x_Nmm: float = 0.0
    Mpe_y_Nmm: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    info: list[str] = Field(default_factory=list)


class ServiceabilitySummary(BaseModel):
    """Container assembled by serviceability preflight."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    enabled: bool
    settings: ServiceabilitySettings
    section_properties: GrossSectionProperties | None
    gross_section_properties: GrossSectionProperties | None = None
    section_basis_used: str = "gross"
    check_points: list[StressCheckPoint] = Field(default_factory=list)
    sls_load_cases: list[LoadCase] = Field(default_factory=list)
    stress_results: list[ServiceStressPointResult] = Field(default_factory=list)
    transformed_section_properties: Any | None = None
    prestress_contribution: PrestressServiceContribution | None = None
    prestress_included: bool = False
    bonded_prestress_count: int = 0
    unbonded_prestress_ignored_count: int = 0
    total_pe_eff_N: float = 0.0
    Mpe_x_Nmm: float = 0.0
    Mpe_y_Nmm: float = 0.0
    overall_status: ServiceabilityStatus = "NOT_CHECKED"
    max_compression_MPa: float | None = None
    max_tension_MPa: float | None = None
    governing_combo: str | None = None
    governing_point: str | None = None
    max_utilization: float | None = None
    governing_status: str | None = None
    no_tension_violation_count: int = 0
    decompression_violation_count: int = 0
    compression_failure_count: int = 0
    tension_failure_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    warning_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    info: list[str] = Field(default_factory=list)
