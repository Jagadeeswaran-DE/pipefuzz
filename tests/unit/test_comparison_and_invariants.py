from datetime import datetime, timedelta, timezone
from decimal import Decimal

from pipefuzz.comparison import snapshots_equal, values_equal
from pipefuzz.invariants import (
    evaluate_deterministic_output,
    evaluate_no_join_amplification,
    evaluate_no_unexpected_nulls,
    evaluate_unique_key,
)
from pipefuzz.models import DatasetSnapshot, InvariantConfig


def snapshot(rows, fields=None) -> DatasetSnapshot:
    fields = fields or [(name, "string") for name in (rows[0].keys() if rows else [])]
    return DatasetSnapshot(
        {
            "type": "struct",
            "fields": [
                {"name": name, "type": type_name, "nullable": True, "metadata": {}}
                for name, type_name in fields
            ],
        },
        rows,
    )


def test_snapshot_comparison_is_unordered_and_duplicate_aware() -> None:
    left = snapshot([{"id": "1"}, {"id": "2"}, {"id": "2"}])
    reordered = snapshot([{"id": "2"}, {"id": "1"}, {"id": "2"}])
    missing_duplicate = snapshot([{"id": "2"}, {"id": "1"}])

    assert snapshots_equal(left, reordered)
    assert not snapshots_equal(left, missing_duplicate)


def test_snapshot_comparison_finds_a_valid_non_greedy_float_matching() -> None:
    left = snapshot([{"value": 0.0}, {"value": 0.1}], [("value", "double")])
    right = snapshot([{"value": 0.05}, {"value": -0.05}], [("value", "double")])

    assert snapshots_equal(left, right, rtol=0.0, atol=0.06)


def test_value_comparison_handles_float_decimal_null_and_utc() -> None:
    assert values_equal(1.0, 1.0 + 1e-10, 1e-9, 1e-12)
    assert not values_equal(1.0, 1.1, 1e-9, 1e-12)
    assert values_equal(Decimal("1.00"), Decimal("1.00"), 0, 0)
    assert not values_equal(Decimal("1.00"), 1.0, 0, 0)
    assert values_equal(None, None, 0, 0)
    assert values_equal(
        datetime(2026, 1, 1, 0, 0),
        datetime(2026, 1, 1, 5, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        0,
        0,
    )


def test_unique_key_counts_repeated_null_tuple_as_duplicate() -> None:
    data = snapshot([{"id": None}, {"id": None}], [("id", "integer")])
    invariant = InvariantConfig("unique_key", dataset="input", columns=("id",))

    result = evaluate_unique_key(invariant, {"input": data}, snapshot([]))

    assert not result.passed
    assert result.context["duplicate_keys"] == [(None,)]


def test_unique_key_handles_compound_output_values() -> None:
    data = snapshot(
        [{"key": [1, 2]}, {"key": [1, 2]}],
        [("key", {"type": "array", "elementType": "integer", "containsNull": False})],
    )
    invariant = InvariantConfig("unique_key", dataset="output", columns=("key",))

    result = evaluate_unique_key(invariant, {}, data)

    assert not result.passed
    assert result.context["duplicate_keys"] == [([1, 2],)]


def test_no_unexpected_nulls_reports_counts() -> None:
    data = snapshot([{"value": None}, {"value": "ok"}], [("value", "string")])
    invariant = InvariantConfig(
        "no_unexpected_nulls", dataset="output", columns=("value",)
    )

    result = evaluate_no_unexpected_nulls(invariant, {}, data)

    assert not result.passed
    assert result.context["null_counts"] == {"value": 1}


def test_join_amplification_compares_absolute_measure_totals() -> None:
    inputs = {"orders": snapshot([{"amount": -100.0}], [("amount", "double")])}
    amplified = snapshot([{"total_amount": -200.0}], [("total_amount", "double")])
    safe = snapshot([{"total_amount": -100.0}], [("total_amount", "double")])
    invariant = InvariantConfig(
        "no_join_amplification",
        relationship="orders_customer",
        input_name="orders",
        input_column="amount",
        output_column="total_amount",
    )

    failed = evaluate_no_join_amplification(invariant, inputs, amplified)
    passed = evaluate_no_join_amplification(invariant, inputs, safe)

    assert not failed.passed
    assert failed.context["input_absolute_total"] == "100.0"
    assert failed.context["output_absolute_total"] == "200.0"
    assert passed.passed


def test_deterministic_output_uses_semantic_comparison() -> None:
    first = snapshot([{"value": 1.0}, {"value": 2.0}], [("value", "double")])
    equivalent = snapshot([{"value": 2.0}, {"value": 1.0 + 1e-10}], [("value", "double")])
    changed = snapshot([{"value": 2.0}, {"value": 3.0}], [("value", "double")])
    invariant = InvariantConfig("deterministic_output")

    assert evaluate_deterministic_output(invariant, first, equivalent).passed
    assert not evaluate_deterministic_output(invariant, first, changed).passed
