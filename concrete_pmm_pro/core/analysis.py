"""Analysis input models for future solver milestones."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from concrete_pmm_pro.core.models import (
    ConcreteMaterial,
    LoadCase,
    PrestressElement,
    PrestressSteelMaterial,
    Rebar,
    RebarMaterial,
    SectionGeometry,
)

AnalysisType = Literal["PMM Surface"]
StrengthLoadType = Literal["ULS", "Extreme", "Construction", "Other"]
TransverseReinforcement = Literal["tied", "spiral"]
PrestressStressModel = Literal["linear_cap", "bilinear"]
# ``general_section`` is kept as a legacy input value so old project/session
# data can be normalized without crashing. It is no longer exposed as an active
# workflow in the UI.
MemberType = Literal["column_pier_pmm", "beam_girder", "building_beam_girder", "general_section"]
AnalysisWorkflow = Literal["pmm_section", "beam_girder_future", "bridge_beam_girder", "building_beam_girder", "general_section"]


class AnalysisModeSettings(BaseModel):
    """Member type and workflow routing metadata.

    This framework is intentionally descriptive. It does not change the PMM
    solver, SLS stress formulas, or load case data model. ``general_section``
    is accepted only as a legacy value and is normalized to Column/Pier PMM.
    """

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    member_type: MemberType = "column_pier_pmm"
    analysis_workflow: AnalysisWorkflow = "pmm_section"
    description: str | None = None
    allow_pmm_workflow: bool = True
    allow_sls_workflow: bool = True
    allow_beam_girder_placeholder: bool = False
    note: str | None = None

    @model_validator(mode="after")
    def apply_member_type_defaults(self) -> "AnalysisModeSettings":
        if self.member_type == "column_pier_pmm":
            object.__setattr__(self, "analysis_workflow", "pmm_section")
            object.__setattr__(self, "allow_pmm_workflow", True)
            object.__setattr__(self, "allow_sls_workflow", False)
            object.__setattr__(self, "allow_beam_girder_placeholder", False)
        elif self.member_type == "beam_girder":
            # WORKFLOW.TYPE2: keep the legacy internal value ``beam_girder``
            # as the Bridge Beam/Girder workflow so old project JSON and
            # existing girder SLS/prestress modules continue to route safely.
            object.__setattr__(self, "analysis_workflow", "bridge_beam_girder")
            object.__setattr__(self, "allow_pmm_workflow", False)
            object.__setattr__(self, "allow_sls_workflow", True)
            object.__setattr__(self, "allow_beam_girder_placeholder", True)
        elif self.member_type == "building_beam_girder":
            object.__setattr__(self, "analysis_workflow", "building_beam_girder")
            object.__setattr__(self, "allow_pmm_workflow", False)
            object.__setattr__(self, "allow_sls_workflow", False)
            object.__setattr__(self, "allow_beam_girder_placeholder", True)
        elif self.member_type == "general_section":
            # MEMBER.TYPE1.3 removes General Section from the active workflow UI.
            # Preserve old project/session data by migrating it to the safe,
            # explicit PMM workflow instead of keeping an ambiguous third mode.
            object.__setattr__(self, "member_type", "column_pier_pmm")
            object.__setattr__(self, "analysis_workflow", "pmm_section")
            object.__setattr__(self, "allow_pmm_workflow", True)
            object.__setattr__(self, "allow_sls_workflow", False)
            object.__setattr__(self, "allow_beam_girder_placeholder", False)
        return self


class AnalysisSettings(BaseModel):
    """Settings collected before future PMM analysis."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    code: str = "ACI 318"
    analysis_type: AnalysisType = "PMM Surface"
    strength_load_type: StrengthLoadType = "ULS"
    include_rebars: bool = True
    include_prestress: bool = True
    use_phi_factor: bool = True
    transverse_reinforcement: TransverseReinforcement = "tied"
    prestress_stress_model: PrestressStressModel = "bilinear"
    subtract_rebar_displaced_concrete: bool = True
    neutral_axis_angle_steps: int = Field(default=72, ge=12)
    neutral_axis_depth_steps: int = Field(default=120, ge=10)
    compression_positive: bool = True
    note: str | None = None


class AnalysisInput(BaseModel):
    """Validated container for the future PMM solver input."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    section_geometry: SectionGeometry
    concrete_material: ConcreteMaterial
    rebar_materials: list[RebarMaterial] = Field(default_factory=list)
    prestress_materials: list[PrestressSteelMaterial] = Field(default_factory=list)
    rebars: list[Rebar] = Field(default_factory=list)
    prestress_elements: list[PrestressElement] = Field(default_factory=list)
    load_cases: list[LoadCase] = Field(default_factory=list)
    settings: AnalysisSettings = Field(default_factory=AnalysisSettings)
