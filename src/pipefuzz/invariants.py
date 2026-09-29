"""Pure invariant evaluation over materialized DataFrame snapshots."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any

from pipefuzz.comparison import snapshots_equal
from pipefuzz.errors import ConfigurationError
from pipefuzz.models import DatasetSnapshot, InvariantConfig, InvariantResult, PipeFuzzConfig


def _columns(snapshot: DatasetSnapshot) -> set[str]:
    return {field["name"] for field in snapshot.schema.get("fields", [])}


def _require_columns(snapshot: DatasetSnapshot, columns: tuple[str, ...], invariant: str) -> None:
    missing = sorted(set(columns) - _columns(snapshot))
    if missing:
        raise ConfigurationError(f"{invariant} output columns do not exist: {', '.join(missing)}")


def _snapshot_for(
    dataset: str,
    inputs: dict[str, DatasetSnapshot],
    output: DatasetSnapshot,
) -> DatasetSnapshot:
    return output if dataset == "output" else inputs[dataset]


def _hashable(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return ("float", "nan")
    if isinstance(value, Decimal) and value.is_nan():
        return ("decimal", "nan")
    if hasattr(value, "asDict"):
        value = value.asDict(recursive=True)
    if isinstance(value, dict):
        items = [(_hashable(key), _hashable(item)) for key, item in value.items()]
        return ("dict", tuple(sorted(items, key=repr)))
    if isinstance(value, list):
        return ("list", tuple(_hashable(item) for item in value))
    if isinstance(value, tuple):
        return ("tuple", tuple(_hashable(item) for item in value))
    if isinstance(value, set):
        return ("set", tuple(sorted((_hashable(item) for item in value), key=repr)))
    return value


def evaluate_unique_key(
    invariant: InvariantConfig,
    inputs: dict[str, DatasetSnapshot],
    output: DatasetSnapshot,
) -> InvariantResult:
    snapshot = _snapshot_for(invariant.dataset or "output", inputs, output)
    _require_columns(snapshot, invariant.columns, invariant.type)
    keys = [tuple(row[column] for column in invariant.columns) for row in snapshot.rows]
    counts: dict[Any, int] = {}
    originals: dict[Any, tuple[Any, ...]] = {}
    for key in keys:
        normalized = tuple(_hashable(value) for value in key)
        counts[normalized] = counts.get(normalized, 0) + 1
        originals.setdefault(normalized, key)
    duplicates = [originals[key] for key, count in counts.items() if count > 1]
    if duplicates:
        return InvariantResult(
            invariant.type,
            False,
            f"Dataset {invariant.dataset} contains duplicate key values",
            {"dataset": invariant.dataset, "columns": list(invariant.columns), "duplicate_keys": duplicates},
        )
    return InvariantResult(
        invariant.type,
        True,
        f"Dataset {invariant.dataset} key is unique",
        {"dataset": invariant.dataset, "columns": list(invariant.columns)},
    )


def evaluate_no_unexpected_nulls(
    invariant: InvariantConfig,
    inputs: dict[str, DatasetSnapshot],
    output: DatasetSnapshot,
) -> InvariantResult:
    snapshot = _snapshot_for(invariant.dataset or "output", inputs, output)
    _require_columns(snapshot, invariant.columns, invariant.type)
    counts = {
        column: sum(row[column] is None for row in snapshot.rows)
        for column in invariant.columns
    }
    failed = {column: count for column, count in counts.items() if count}
    if failed:
        return InvariantResult(
            invariant.type,
            False,
            f"Dataset {invariant.dataset} contains unexpected NULL values",
            {"dataset": invariant.dataset, "null_counts": failed},
        )
    return InvariantResult(
        invariant.type,
        True,
        f"Dataset {invariant.dataset} contains no unexpected NULL values",
        {"dataset": invariant.dataset, "null_counts": counts},
    )


def _absolute_total(rows: list[dict[str, Any]], column: str) -> Decimal:
    total = Decimal(0)
    for row in rows:
        value = row[column]
        if value is None:
            continue
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"column {column!r} contains a non-finite numeric value")
        try:
            total += abs(value if isinstance(value, Decimal) else Decimal(str(value)))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ConfigurationError(f"column {column!r} is not numeric at runtime") from exc
    return total


def evaluate_no_join_amplification(
    invariant: InvariantConfig,
    inputs: dict[str, DatasetSnapshot],
    output: DatasetSnapshot,
) -> InvariantResult:
    input_name = invariant.input_name or ""
    input_column = invariant.input_column or ""
    output_column = invariant.output_column or ""
    _require_columns(output, (output_column,), invariant.type)
    try:
        input_total = _absolute_total(inputs[input_name].rows, input_column)
        output_total = _absolute_total(output.rows, output_column)
    except ValueError as exc:
        return InvariantResult(invariant.type, False, str(exc), {"relationship": invariant.relationship})
    tolerance = Decimal(str(invariant.atol)) + abs(input_total) * Decimal(str(invariant.rtol))
    context = {
        "relationship": invariant.relationship,
        "input": input_name,
        "input_column": input_column,
        "output_column": output_column,
        "input_absolute_total": str(input_total),
        "output_absolute_total": str(output_total),
        "tolerance": str(tolerance),
    }
    if output_total > input_total + tolerance:
        return InvariantResult(
            invariant.type,
            False,
            "Output measure exceeds the input measure; a join may have amplified fact values",
            context,
        )
    return InvariantResult(invariant.type, True, "Output measure did not amplify the input measure", context)


def evaluate_deterministic_output(
    invariant: InvariantConfig,
    output: DatasetSnapshot,
    repeated_output: DatasetSnapshot | None,
) -> InvariantResult:
    if repeated_output is None:
        raise ConfigurationError("deterministic_output requires a repeated transformation result")
    passed = snapshots_equal(output, repeated_output, invariant.rtol, invariant.atol)
    return InvariantResult(
        invariant.type,
        passed,
        "Repeated executions produced semantically equivalent output"
        if passed
        else "Repeated executions produced different semantic output",
        {
            "first_row_count": len(output.rows),
            "second_row_count": len(repeated_output.rows),
            "rtol": invariant.rtol,
            "atol": invariant.atol,
        },
    )


def evaluate_invariants(
    config: PipeFuzzConfig,
    inputs: dict[str, DatasetSnapshot],
    output: DatasetSnapshot,
    repeated_output: DatasetSnapshot | None,
    scenario: str,
) -> list[InvariantResult]:
    results: list[InvariantResult] = []
    for invariant in config.invariants:
        if invariant.type == "unique_key":
            results.append(evaluate_unique_key(invariant, inputs, output))
        elif invariant.type == "no_unexpected_nulls":
            results.append(evaluate_no_unexpected_nulls(invariant, inputs, output))
        elif invariant.type == "no_join_amplification":
            results.append(evaluate_no_join_amplification(invariant, inputs, output))
        elif invariant.type == "deterministic_output" and scenario == "determinism":
            results.append(evaluate_deterministic_output(invariant, output, repeated_output))
    return results
