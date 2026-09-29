"""Hypothesis strategies for small, adversarial PySpark input datasets."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from hypothesis import strategies as st

from pipefuzz.models import ColumnConfig, GeneratedCase, InputConfig, PipeFuzzConfig
from pipefuzz.schema import decimal_parts, is_numeric


def _decimal_value(unscaled: int, scale: int) -> Decimal:
    return Decimal(unscaled).scaleb(-scale)


def value_strategy(
    column: ColumnConfig,
    *,
    allow_null: bool | None = None,
    edge_only: bool = False,
    positive: bool = False,
):
    """Return values representable by the configured Spark primitive type."""
    type_name = column.type_name
    if type_name == "string":
        base = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=12)
    elif type_name == "integer":
        if positive:
            base = st.integers(min_value=1, max_value=1_000)
        else:
            edges = st.sampled_from([0, 1, -1, -2_147_483_648, 2_147_483_647])
            base = edges if edge_only else st.one_of(edges, st.integers(-10_000, 10_000))
    elif type_name == "long":
        if positive:
            base = st.integers(min_value=1, max_value=1_000_000)
        else:
            edges = st.sampled_from([0, 1, -1, -9_223_372_036_854_775_808, 9_223_372_036_854_775_807])
            base = edges if edge_only else st.one_of(edges, st.integers(-1_000_000, 1_000_000))
    elif type_name in {"float", "double"}:
        if positive:
            base = st.floats(
                min_value=1.0,
                max_value=1_000.0,
                allow_nan=False,
                allow_infinity=False,
                width=32 if type_name == "float" else 64,
            )
        else:
            edges = st.sampled_from([0.0, 1.0, -1.0, -1_000_000.0, 1_000_000.0])
            base = edges if edge_only else st.one_of(
                edges,
                st.floats(
                    min_value=-1_000_000.0,
                    max_value=1_000_000.0,
                    allow_nan=False,
                    allow_infinity=False,
                    width=32 if type_name == "float" else 64,
                ),
            )
    elif decimal := decimal_parts(type_name):
        precision, scale = decimal
        maximum = min((10**precision) - 1, 1_000_000)
        if positive:
            unscaled = st.integers(min_value=1, max_value=maximum)
        elif edge_only:
            unscaled = st.sampled_from([0, 1, -1, -maximum, maximum])
        else:
            unscaled = st.one_of(
                st.sampled_from([0, 1, -1, -maximum, maximum]),
                st.integers(min_value=-maximum, max_value=maximum),
            )
        base = unscaled.map(lambda value: _decimal_value(value, scale))
    elif type_name == "boolean":
        base = st.booleans()
    elif type_name == "timestamp":
        base = st.datetimes(
            min_value=datetime(2000, 1, 1),
            max_value=datetime(2035, 12, 31, 23, 59, 59),
            timezones=st.just(timezone.utc),
        )
    else:  # pragma: no cover - configuration validation prevents this branch
        raise AssertionError(f"Unsupported type {type_name}")
    nullable = column.nullable if allow_null is None else allow_null
    return st.one_of(st.none(), base) if nullable else base


def _join_value_strategy(
    column: ColumnConfig,
    *,
    allow_null: bool | None = None,
    positive: bool = False,
):
    """Compact values for join-structure exploration; numeric edges run separately."""
    decimal = decimal_parts(column.type_name)
    if column.type_name == "string":
        base = st.sampled_from(["a", ""])
    elif column.type_name in {"integer", "long"}:
        base = (
            st.integers(1, 3)
            if positive
            else st.sampled_from([1, -1])
        )
    elif column.type_name in {"float", "double"}:
        base = st.sampled_from([1.0, 2.0, 3.0]) if positive else st.sampled_from([1.0, -1.0])
    elif decimal:
        _, scale = decimal
        values = [1, 2, 3] if positive else [1, -1]
        base = st.sampled_from([_decimal_value(value, scale) for value in values])
    elif column.type_name == "boolean":
        base = st.booleans()
    elif column.type_name == "timestamp":
        base = st.sampled_from(
            [
                datetime(2020, 1, 1, tzinfo=timezone.utc),
                datetime(2020, 1, 2, tzinfo=timezone.utc),
            ]
        )
    else:  # pragma: no cover - configuration validation prevents this branch
        raise AssertionError(f"Unsupported type {column.type_name}")
    nullable = column.nullable if allow_null is None else allow_null
    return st.one_of(st.none(), base) if nullable else base


def row_strategy(input_config: InputConfig):
    return st.fixed_dictionaries(
        {column.name: value_strategy(column) for column in input_config.schema}
    )


def _default_value(column: ColumnConfig):
    decimal = decimal_parts(column.type_name)
    if column.type_name == "string":
        return ""
    if column.type_name in {"integer", "long"}:
        return 0
    if column.type_name in {"float", "double"}:
        return 0.0
    if decimal:
        return _decimal_value(0, decimal[1])
    if column.type_name == "boolean":
        return False
    if column.type_name == "timestamp":
        return datetime(2020, 1, 1, tzinfo=timezone.utc)
    raise AssertionError(f"Unsupported type {column.type_name}")  # pragma: no cover


def _default_row(input_config: InputConfig) -> dict[str, Any]:
    return {column.name: _default_value(column) for column in input_config.schema}


def _positive_unit(column: ColumnConfig):
    decimal = decimal_parts(column.type_name)
    if column.type_name in {"integer", "long"}:
        return 1
    if column.type_name in {"float", "double"}:
        return 1.0
    if decimal:
        return _decimal_value(1, decimal[1])
    raise AssertionError(f"Positive unit requested for non-numeric type {column.type_name}")


def _records_strategy(input_config: InputConfig, minimum: int | None = None):
    return st.lists(
        row_strategy(input_config),
        min_size=input_config.min_rows if minimum is None else max(input_config.min_rows, minimum),
        max_size=input_config.max_rows,
    )


def _minimal_records(
    config: PipeFuzzConfig,
    required_rows: dict[str, int] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    required = required_rows or {}
    return {
        name: [
            _default_row(input_config)
            for _ in range(max(input_config.min_rows, required.get(name, 0)))
        ]
        for name, input_config in config.inputs.items()
    }


def _compact_row_strategy(input_config: InputConfig):
    return st.fixed_dictionaries(
        {
            column.name: _join_value_strategy(column, allow_null=False)
            for column in input_config.schema
        }
    )


def _schemas(config: PipeFuzzConfig) -> dict[str, list[dict[str, Any]]]:
    return {
        name: [
            {"name": column.name, "type": column.type_name, "nullable": column.nullable}
            for column in input_config.schema
        ]
        for name, input_config in config.inputs.items()
    }


@st.composite
def _null_case(draw, config: PipeFuzzConfig):
    candidates = [
        (name, column)
        for name, input_config in config.inputs.items()
        if input_config.max_rows >= 1
        for column in input_config.schema
        if column.nullable
    ]
    selected_name, selected_column = draw(st.sampled_from(candidates))
    records = _minimal_records(config, {selected_name: 1})
    selected_row = draw(_compact_row_strategy(config.inputs[selected_name]))
    selected_row[selected_column.name] = None
    records[selected_name][0] = selected_row
    return GeneratedCase("nulls", records)


@st.composite
def _duplicate_case(draw, config: PipeFuzzConfig):
    candidates = [name for name, item in config.inputs.items() if item.max_rows >= 2]
    selected_name = draw(st.sampled_from(candidates))
    records = _minimal_records(config, {selected_name: 2})
    duplicated = draw(_compact_row_strategy(config.inputs[selected_name]))
    records[selected_name][0] = duplicated
    records[selected_name][1] = dict(duplicated)
    return GeneratedCase("duplicates", records)


@st.composite
def _numeric_case(draw, config: PipeFuzzConfig):
    candidates = [
        (name, column)
        for name, input_config in config.inputs.items()
        if input_config.max_rows >= 1
        for column in input_config.schema
        if is_numeric(column.type_name)
    ]
    selected_name, selected_column = draw(st.sampled_from(candidates))
    records = _minimal_records(config, {selected_name: 1})
    records[selected_name][0][selected_column.name] = draw(
        value_strategy(selected_column, allow_null=False, edge_only=True)
    )
    return GeneratedCase("numeric_edges", records)


@st.composite
def _join_case(draw, config: PipeFuzzConfig):
    relationship = draw(st.sampled_from(list(config.relationships)))
    source_config = config.inputs[relationship.from_input]
    target_config = config.inputs[relationship.to_input]
    source_count = max(1, source_config.min_rows)
    target_count = max(2, target_config.min_rows)
    source_prototype = _default_row(source_config)
    target_prototype = _default_row(target_config)
    source_overrides: dict[str, Any] = {}
    target_overrides: dict[str, Any] = {}
    for source_column, target_column in zip(
        relationship.from_columns, relationship.to_columns, strict=True
    ):
        value = draw(
            _join_value_strategy(source_config.column(source_column), allow_null=False)
        )
        source_overrides[source_column] = value
        target_overrides[target_column] = value

    for invariant in config.invariants:
        if invariant.type != "no_join_amplification" or invariant.relationship != relationship.name:
            continue
        measure = invariant.input_column or ""
        measure_column = source_config.column(measure)
        value = _positive_unit(measure_column)
        source_overrides[measure] = value
        if measure in relationship.from_columns:
            index = relationship.from_columns.index(measure)
            target_overrides[relationship.to_columns[index]] = value

    source_prototype.update(source_overrides)
    target_prototype.update(target_overrides)
    source_rows = [dict(source_prototype) for _ in range(source_count)]
    target_rows = [dict(target_prototype) for _ in range(target_count)]

    records = {
        name: [_default_row(input_config) for _ in range(input_config.min_rows)]
        for name, input_config in config.inputs.items()
        if name not in {relationship.from_input, relationship.to_input}
    }
    records[relationship.from_input] = source_rows
    records[relationship.to_input] = target_rows
    return GeneratedCase("join_amplification", records)


@st.composite
def _determinism_case(draw, config: PipeFuzzConfig):
    selected = next(name for name, item in config.inputs.items() if item.max_rows >= 1)
    records = _minimal_records(config, {selected: 1})
    records[selected][0] = draw(_compact_row_strategy(config.inputs[selected]))
    return GeneratedCase("determinism", records)


def case_strategy(config: PipeFuzzConfig, scenario: str):
    if scenario == "nulls":
        return _null_case(config)
    if scenario == "duplicates":
        return _duplicate_case(config)
    if scenario == "join_amplification":
        return _join_case(config)
    if scenario == "numeric_edges":
        return _numeric_case(config)
    return _determinism_case(config)


__all__ = ["case_strategy", "row_strategy", "value_strategy", "_schemas"]
