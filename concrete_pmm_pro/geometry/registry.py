"""Registry for section geometry and dimension generator functions."""

from __future__ import annotations

from collections.abc import Callable

from concrete_pmm_pro.core.models import DimensionItem, SectionGeometry

GeometryGenerator = Callable[..., SectionGeometry]
DimensionGenerator = Callable[..., list[DimensionItem]]


class GeometryRegistry:
    def __init__(self) -> None:
        self._geometry_generators: dict[str, GeometryGenerator] = {}
        self._dimension_generators: dict[str, DimensionGenerator] = {}

    def register_geometry(self, name: str, func: GeometryGenerator) -> None:
        self._geometry_generators[name] = func

    def register_dimensions(self, name: str, func: DimensionGenerator) -> None:
        self._dimension_generators[name] = func

    def geometry(self, name: str) -> GeometryGenerator:
        try:
            return self._geometry_generators[name]
        except KeyError as exc:
            raise KeyError(f"Geometry generator is not registered: {name}") from exc

    def dimensions(self, name: str) -> DimensionGenerator:
        try:
            return self._dimension_generators[name]
        except KeyError as exc:
            raise KeyError(f"Dimension generator is not registered: {name}") from exc

    def geometry_names(self) -> list[str]:
        return sorted(self._geometry_generators)

    def dimension_names(self) -> list[str]:
        return sorted(self._dimension_generators)


default_registry = GeometryRegistry()
