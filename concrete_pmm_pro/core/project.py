"""Project-level data model for save/load workflows."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from concrete_pmm_pro.core.analysis import AnalysisModeSettings, AnalysisSettings
from concrete_pmm_pro.core.concrete_materials import c45_precast_material, ensure_concrete_material_library
from concrete_pmm_pro.core.design_code import default_project_design_code_for_workflow, normalize_project_code_edition, normalize_project_design_code
from concrete_pmm_pro.core.models import (
    ConcreteMaterial,
    LoadCase,
    PrestressElement,
    PrestressSteelMaterial,
    Rebar,
    RebarMaterial,
    SectionGeometry,
)
from concrete_pmm_pro.serviceability.models import ServiceabilitySettings
from concrete_pmm_pro.serviceability.models import StressCheckPoint


class ProjectModel(BaseModel):
    """Serializable project container.

    The PMM solver intentionally consumes none of this yet. The model is a
    stable envelope for UI/session data that already exists in Milestone 1.
    """

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    project_name: str = "Untitled Project"
    designer: str | None = None
    description: str | None = None
    unit_system: str = "mm-MPa-N"
    code: str = "ACI 318"
    code_edition: str | None = None
    version: str = "PS.DB1.2"

    section_preset_key: str | None = None
    section_preset_name: str | None = None
    section_parameters: dict[str, Any] = Field(default_factory=dict)
    section_geometry: SectionGeometry | None = None

    concrete_material: ConcreteMaterial = Field(default_factory=c45_precast_material)
    concrete_materials: list[ConcreteMaterial] = Field(default_factory=list)
    active_concrete_material_name: str | None = None
    deck_topping_material_name: str | None = None
    rebar_materials: list[RebarMaterial] = Field(default_factory=list)
    prestress_materials: list[PrestressSteelMaterial] = Field(default_factory=list)
    active_rebar_material_name: str | None = None
    active_prestress_material_name: str | None = None

    loads: list[LoadCase] = Field(default_factory=list)
    rebars: list[Rebar] = Field(default_factory=list)
    prestress_elements: list[PrestressElement] = Field(default_factory=list)
    analysis_mode_settings: AnalysisModeSettings | None = Field(default_factory=AnalysisModeSettings)
    analysis_settings: AnalysisSettings | None = Field(default_factory=AnalysisSettings)
    serviceability_settings: ServiceabilitySettings | None = Field(default_factory=ServiceabilitySettings)
    custom_stress_check_points: list[StressCheckPoint] = Field(default_factory=list)
    include_default_stress_check_points: bool = True

    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_material_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        concrete_materials = migrated.get("concrete_materials")
        if "concrete_material" not in migrated and isinstance(concrete_materials, list) and concrete_materials:
            migrated["concrete_material"] = concrete_materials[0]
        return migrated

    @model_validator(mode="after")
    def normalize_concrete_material_library(self) -> "ProjectModel":
        workflow_member_type = getattr(self.analysis_mode_settings, "member_type", None) if self.analysis_mode_settings is not None else None
        normalized_code = default_project_design_code_for_workflow(workflow_member_type, normalize_project_design_code(self.code))
        object.__setattr__(self, "code", normalized_code)
        object.__setattr__(self, "code_edition", normalize_project_code_edition(normalized_code, self.code_edition))
        library_state = ensure_concrete_material_library(
            concrete_material=self.concrete_material,
            concrete_materials=self.concrete_materials,
            active_concrete_material_name=self.active_concrete_material_name,
            deck_topping_material_name=self.deck_topping_material_name,
            preserve_existing_primary=bool(self.concrete_materials) is False,
        )
        object.__setattr__(self, "concrete_materials", library_state.materials)
        object.__setattr__(self, "active_concrete_material_name", library_state.active_concrete_material_name)
        object.__setattr__(self, "deck_topping_material_name", library_state.deck_topping_material_name)
        object.__setattr__(self, "concrete_material", library_state.active_material)
        return self
