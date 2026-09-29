"""Strict parser for the PipeFuzz YAML version 1 configuration."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml

from pipefuzz.errors import ConfigurationError
from pipefuzz.models import (
    ColumnConfig,
    InputConfig,
    InvariantConfig,
    PipeFuzzConfig,
    RelationshipConfig,
)
from pipefuzz.schema import is_numeric, schema_columns, validate_type_name


SCENARIOS = {
    "nulls",
    "duplicates",
    "join_amplification",
    "numeric_edges",
    "determinism",
}
INVARIANTS = {
    "unique_key",
    "no_unexpected_nulls",
    "no_join_amplification",
    "deterministic_output",
}


def _mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{context} must be a mapping")
    return value


def _sequence(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigurationError(f"{context} must be a list")
    return value


def _only(mapping: dict[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ConfigurationError(f"Unknown {context} keys: {', '.join(unknown)}")


def _names(value: Any, context: str) -> tuple[str, ...]:
    values = _sequence(value, context)
    if not values or not all(isinstance(item, str) and item for item in values):
        raise ConfigurationError(f"{context} must contain one or more non-empty names")
    if len(values) != len(set(values)):
        raise ConfigurationError(f"{context} contains duplicate names")
    return tuple(values)


def _parse_input(name: str, raw: Any) -> InputConfig:
    data = _mapping(raw, f"input {name!r}")
    _only(data, {"schema", "primary_key", "rows"}, f"input {name!r}")
    raw_schema = _sequence(data.get("schema"), f"input {name!r} schema")
    if not raw_schema:
        raise ConfigurationError(f"input {name!r} schema cannot be empty")
    columns: list[ColumnConfig] = []
    for index, raw_column in enumerate(raw_schema):
        column = _mapping(raw_column, f"input {name!r} schema item {index}")
        _only(column, {"name", "type", "nullable"}, f"input {name!r} column")
        column_name = column.get("name")
        type_name = column.get("type")
        nullable = column.get("nullable")
        if not isinstance(column_name, str) or not column_name:
            raise ConfigurationError(f"input {name!r} has an invalid column name")
        if not isinstance(type_name, str):
            raise ConfigurationError(f"column {name}.{column_name} type must be a string")
        if not isinstance(nullable, bool):
            raise ConfigurationError(f"column {name}.{column_name} nullable must be boolean")
        columns.append(ColumnConfig(column_name, validate_type_name(type_name), nullable))
    column_names = [column.name for column in columns]
    if len(column_names) != len(set(column_names)):
        raise ConfigurationError(f"input {name!r} contains duplicate column names")

    primary_key = ()
    if "primary_key" in data:
        primary_key = _names(data["primary_key"], f"input {name!r} primary_key")
        missing = sorted(set(primary_key) - set(column_names))
        if missing:
            raise ConfigurationError(f"input {name!r} primary_key columns not in schema: {', '.join(missing)}")

    rows = _mapping(data.get("rows", {}), f"input {name!r} rows")
    _only(rows, {"min", "max"}, f"input {name!r} rows")
    minimum, maximum = rows.get("min", 0), rows.get("max", 4)
    if not isinstance(minimum, int) or isinstance(minimum, bool):
        raise ConfigurationError(f"input {name!r} rows.min must be an integer")
    if not isinstance(maximum, int) or isinstance(maximum, bool):
        raise ConfigurationError(f"input {name!r} rows.max must be an integer")
    if not 0 <= minimum <= maximum <= 20:
        raise ConfigurationError(f"input {name!r} rows must satisfy 0 <= min <= max <= 20")
    return InputConfig(name, tuple(columns), primary_key, minimum, maximum)


def _endpoint(raw: Any, context: str) -> tuple[str, tuple[str, ...]]:
    data = _mapping(raw, context)
    _only(data, {"input", "columns"}, context)
    input_name = data.get("input")
    if not isinstance(input_name, str) or not input_name:
        raise ConfigurationError(f"{context}.input must be a non-empty string")
    return input_name, _names(data.get("columns"), f"{context}.columns")


def _parse_relationship(raw: Any, inputs: dict[str, InputConfig]) -> RelationshipConfig:
    data = _mapping(raw, "relationship")
    _only(data, {"name", "from", "to", "cardinality"}, "relationship")
    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise ConfigurationError("relationship.name must be a non-empty string")
    if data.get("cardinality") != "many_to_one":
        raise ConfigurationError(f"relationship {name!r} cardinality must be 'many_to_one'")
    from_input, from_columns = _endpoint(data.get("from"), f"relationship {name!r}.from")
    to_input, to_columns = _endpoint(data.get("to"), f"relationship {name!r}.to")
    if from_input == to_input:
        raise ConfigurationError(f"relationship {name!r} must connect two different inputs")
    if from_input not in inputs or to_input not in inputs:
        raise ConfigurationError(f"relationship {name!r} references an unknown input")
    if len(from_columns) != len(to_columns):
        raise ConfigurationError(f"relationship {name!r} endpoints must have the same number of columns")
    for side_input, columns in ((from_input, from_columns), (to_input, to_columns)):
        missing = sorted(set(columns) - set(schema_columns(inputs[side_input])))
        if missing:
            raise ConfigurationError(
                f"relationship {name!r} columns missing from {side_input}: {', '.join(missing)}"
            )
    for source, target in zip(from_columns, to_columns, strict=True):
        if inputs[from_input].column(source).type_name != inputs[to_input].column(target).type_name:
            raise ConfigurationError(f"relationship {name!r} key column types must match")
    return RelationshipConfig(name, from_input, from_columns, to_input, to_columns)


def _float_option(data: dict[str, Any], name: str, default: float, context: str) -> float:
    value = data.get(name, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigurationError(f"{context}.{name} must be a finite non-negative number")
    try:
        converted = float(value)
    except (OverflowError, ValueError) as exc:
        raise ConfigurationError(
            f"{context}.{name} must be a finite non-negative number"
        ) from exc
    if not math.isfinite(converted) or converted < 0:
        raise ConfigurationError(f"{context}.{name} must be a finite non-negative number")
    return converted


def _parse_invariant(
    raw: Any,
    inputs: dict[str, InputConfig],
    relationships: dict[str, RelationshipConfig],
) -> InvariantConfig:
    data = _mapping(raw, "invariant")
    _only(
        data,
        {"type", "dataset", "columns", "relationship", "input", "input_column", "output_column", "rtol", "atol"},
        "invariant",
    )
    invariant_type = data.get("type")
    if invariant_type not in INVARIANTS:
        raise ConfigurationError(f"Unknown invariant type: {invariant_type!r}")
    rtol = _float_option(data, "rtol", 1e-9, f"invariant {invariant_type}")
    atol = _float_option(data, "atol", 1e-12, f"invariant {invariant_type}")
    if invariant_type in {"unique_key", "no_unexpected_nulls"}:
        dataset = data.get("dataset")
        if dataset != "output" and dataset not in inputs:
            raise ConfigurationError(f"invariant {invariant_type} has an unknown dataset")
        columns = _names(data.get("columns"), f"invariant {invariant_type}.columns")
        if dataset in inputs:
            missing = sorted(set(columns) - set(schema_columns(inputs[dataset])))
            if missing:
                raise ConfigurationError(
                    f"invariant {invariant_type} columns missing from {dataset}: {', '.join(missing)}"
                )
        return InvariantConfig(invariant_type, dataset=dataset, columns=columns, rtol=rtol, atol=atol)
    if invariant_type == "no_join_amplification":
        relationship = data.get("relationship")
        input_name = data.get("input")
        input_column = data.get("input_column")
        output_column = data.get("output_column")
        if relationship not in relationships:
            raise ConfigurationError("no_join_amplification references an unknown relationship")
        relation = relationships[relationship]
        if input_name != relation.from_input:
            raise ConfigurationError("no_join_amplification input must match relationship.from.input")
        if not isinstance(input_column, str) or not isinstance(output_column, str):
            raise ConfigurationError("no_join_amplification requires input_column and output_column")
        if input_column not in schema_columns(inputs[input_name]):
            raise ConfigurationError(f"no_join_amplification input column {input_column!r} does not exist")
        if not is_numeric(inputs[input_name].column(input_column).type_name):
            raise ConfigurationError("no_join_amplification input_column must be numeric")
        return InvariantConfig(
            invariant_type,
            relationship=relationship,
            input_name=input_name,
            input_column=input_column,
            output_column=output_column,
            rtol=rtol,
            atol=atol,
        )
    return InvariantConfig(invariant_type, rtol=rtol, atol=atol)


def load_config(path: Path) -> PipeFuzzConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Configuration file does not exist: {path}") from exc
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Could not read configuration {path}: {exc}") from exc
    data = _mapping(raw, "configuration root")
    _only(data, {"version", "inputs", "relationships", "scenarios", "invariants"}, "configuration")
    if data.get("version") != 1:
        raise ConfigurationError("PipeFuzz configuration version must be 1")
    raw_inputs = _mapping(data.get("inputs"), "inputs")
    if not raw_inputs:
        raise ConfigurationError("At least one input is required")
    if not all(isinstance(name, str) and name for name in raw_inputs):
        raise ConfigurationError("Input names must be non-empty strings")
    inputs = {name: _parse_input(name, value) for name, value in raw_inputs.items()}

    relationships_list = [
        _parse_relationship(item, inputs)
        for item in _sequence(data.get("relationships", []), "relationships")
    ]
    relationship_names = [relationship.name for relationship in relationships_list]
    if len(relationship_names) != len(set(relationship_names)):
        raise ConfigurationError("Relationship names must be unique")
    relationships = {relationship.name: relationship for relationship in relationships_list}

    scenarios = _names(data.get("scenarios"), "scenarios")
    unknown_scenarios = sorted(set(scenarios) - SCENARIOS)
    if unknown_scenarios:
        raise ConfigurationError(f"Unknown scenarios: {', '.join(unknown_scenarios)}")
    if "join_amplification" in scenarios:
        if not relationships_list:
            raise ConfigurationError("join_amplification requires at least one relationship")
        for relationship in relationships_list:
            if inputs[relationship.from_input].max_rows < 1 or inputs[relationship.to_input].max_rows < 2:
                raise ConfigurationError(
                    f"join_amplification relationship {relationship.name!r} requires from max rows >= 1 and to max rows >= 2"
                )
    if "nulls" in scenarios and not any(
        input_config.max_rows >= 1 and column.nullable
        for input_config in inputs.values()
        for column in input_config.schema
    ):
        raise ConfigurationError("nulls scenario requires a nullable column on an input with max rows >= 1")
    if "duplicates" in scenarios and not any(input_config.max_rows >= 2 for input_config in inputs.values()):
        raise ConfigurationError("duplicates scenario requires an input with max rows >= 2")
    if "numeric_edges" in scenarios and not any(
        input_config.max_rows >= 1 and is_numeric(column.type_name)
        for input_config in inputs.values()
        for column in input_config.schema
    ):
        raise ConfigurationError("numeric_edges scenario requires a numeric column on an input with max rows >= 1")
    if "determinism" in scenarios and not any(input_config.max_rows >= 1 for input_config in inputs.values()):
        raise ConfigurationError("determinism scenario requires an input with max rows >= 1")

    invariants = tuple(
        _parse_invariant(item, inputs, relationships)
        for item in _sequence(data.get("invariants"), "invariants")
    )
    if not invariants:
        raise ConfigurationError("At least one invariant is required")
    if any(item.type == "deterministic_output" for item in invariants) and "determinism" not in scenarios:
        raise ConfigurationError("deterministic_output requires the determinism scenario")
    return PipeFuzzConfig(1, inputs, tuple(relationships_list), scenarios, invariants)
