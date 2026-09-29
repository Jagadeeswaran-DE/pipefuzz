"""Typed models shared by configuration, generation, execution, and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class ColumnConfig:
    name: str
    type_name: str
    nullable: bool


@dataclass(frozen=True)
class InputConfig:
    name: str
    schema: tuple[ColumnConfig, ...]
    primary_key: tuple[str, ...] = ()
    min_rows: int = 0
    max_rows: int = 4

    def column(self, name: str) -> ColumnConfig:
        for column in self.schema:
            if column.name == name:
                return column
        raise KeyError(name)


@dataclass(frozen=True)
class RelationshipConfig:
    name: str
    from_input: str
    from_columns: tuple[str, ...]
    to_input: str
    to_columns: tuple[str, ...]


@dataclass(frozen=True)
class InvariantConfig:
    type: str
    dataset: str | None = None
    columns: tuple[str, ...] = ()
    relationship: str | None = None
    input_name: str | None = None
    input_column: str | None = None
    output_column: str | None = None
    rtol: float = 1e-9
    atol: float = 1e-12


@dataclass(frozen=True)
class PipeFuzzConfig:
    version: int
    inputs: dict[str, InputConfig]
    relationships: tuple[RelationshipConfig, ...]
    scenarios: tuple[str, ...]
    invariants: tuple[InvariantConfig, ...]

    def relationship(self, name: str) -> RelationshipConfig:
        for relationship in self.relationships:
            if relationship.name == name:
                return relationship
        raise KeyError(name)


@dataclass(frozen=True)
class GeneratedCase:
    scenario: str
    records: dict[str, list[dict[str, Any]]]


@dataclass(frozen=True)
class DatasetSnapshot:
    schema: dict[str, Any]
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class InvariantResult:
    name: str
    passed: bool
    reason: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FailureDetails:
    scenario: str
    records: dict[str, list[dict[str, Any]]]
    reason: str
    invariant: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    schemas: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass(frozen=True)
class RunResult:
    classification: str
    target: str
    config_path: Path
    seed: int
    max_examples: int
    generated_examples: int
    hypothesis_version: str
    scenarios: tuple[str, ...]
    failure: FailureDetails | None = None
    error: str | None = None
    traceback: str | None = None

    @property
    def passed(self) -> bool:
        return self.classification == "PASSED"


Transformation = Callable[..., Any]
