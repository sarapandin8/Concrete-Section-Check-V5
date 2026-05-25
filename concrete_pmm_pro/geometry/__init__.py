"""Geometry generation, validation, and summary utilities."""

from concrete_pmm_pro.geometry.generators import register_builtin_generators
from concrete_pmm_pro.geometry.registry import GeometryRegistry, default_registry

register_builtin_generators(default_registry)

__all__ = ["GeometryRegistry", "default_registry", "register_builtin_generators"]
