"""Runtime state helpers for Concrete PMM Pro."""

from .dirty_state import (
    ANALYSIS_STATUS_KEY,
    CHANGED_GROUPS_KEY,
    CURRENT_INPUT_HASH_KEY,
    LAST_ANALYSIS_HASH_KEY,
    ProjectDirtyStatus,
    current_project_dirty_status,
    mark_analysis_current,
    update_dirty_state_from_session,
)

__all__ = [
    "ANALYSIS_STATUS_KEY",
    "CHANGED_GROUPS_KEY",
    "CURRENT_INPUT_HASH_KEY",
    "LAST_ANALYSIS_HASH_KEY",
    "ProjectDirtyStatus",
    "current_project_dirty_status",
    "mark_analysis_current",
    "update_dirty_state_from_session",
]
