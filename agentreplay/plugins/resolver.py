"""Dependency resolution for AgentReplay plugins."""

from __future__ import annotations

from agentreplay.exceptions import PluginError
from agentreplay.plugins.compatibility import satisfies_version_constraint
from agentreplay.plugins.models import PluginRecord


class PluginDependencyResolver:
    """Resolve plugin load order from declared plugin dependencies."""

    def resolve(self, records: tuple[PluginRecord, ...]) -> tuple[PluginRecord, ...]:
        """Return records in dependency-safe order."""
        by_name = {record.metadata.name: record for record in records}
        resolved: list[PluginRecord] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(record: PluginRecord) -> None:
            name = record.metadata.name
            if name in visited:
                return
            if name in visiting:
                msg = f"Cyclic AgentReplay plugin dependency involving {name!r}."
                raise PluginError(msg)
            visiting.add(name)
            for dependency in record.metadata.dependencies:
                dependency_record = by_name.get(dependency.name)
                if dependency_record is None:
                    if dependency.optional:
                        continue
                    msg = (
                        f"Plugin {name!r} depends on missing plugin "
                        f"{dependency.name!r}."
                    )
                    raise PluginError(msg)
                if not satisfies_version_constraint(
                    dependency_record.metadata.version,
                    dependency.version_constraint,
                ):
                    msg = (
                        f"Plugin {name!r} requires {dependency.name!r} "
                        f"{dependency.version_constraint}; found "
                        f"{dependency_record.metadata.version}."
                    )
                    raise PluginError(msg)
                visit(dependency_record)
            visiting.remove(name)
            visited.add(name)
            resolved.append(record)

        for record in records:
            visit(record)
        return tuple(resolved)


__all__ = ["PluginDependencyResolver"]
