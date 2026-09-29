from datetime import datetime, timezone
from decimal import Decimal

from hypothesis import find

from pipefuzz.models import (
    ColumnConfig,
    InputConfig,
    InvariantConfig,
    PipeFuzzConfig,
    RelationshipConfig,
)
from pipefuzz.schema import decimal_parts, is_numeric, to_spark_schema, validate_type_name
from pipefuzz.strategies import case_strategy, value_strategy


def config() -> PipeFuzzConfig:
    orders = InputConfig(
        "orders",
        (
            ColumnConfig("customer_id", "integer", False),
            ColumnConfig("amount", "double", True),
            ColumnConfig("created_at", "timestamp", True),
        ),
        min_rows=1,
        max_rows=4,
    )
    customers = InputConfig(
        "customers",
        (
            ColumnConfig("customer_id", "integer", False),
            ColumnConfig("country", "string", False),
        ),
        primary_key=("customer_id",),
        min_rows=1,
        max_rows=4,
    )
    relationship = RelationshipConfig(
        "orders_customer", "orders", ("customer_id",), "customers", ("customer_id",)
    )
    invariant = InvariantConfig(
        "no_join_amplification",
        relationship="orders_customer",
        input_name="orders",
        input_column="amount",
        output_column="total_amount",
    )
    return PipeFuzzConfig(
        1,
        {"orders": orders, "customers": customers},
        (relationship,),
        ("nulls", "duplicates", "join_amplification", "numeric_edges", "determinism"),
        (invariant,),
    )


def test_schema_parser_and_spark_schema() -> None:
    input_config = InputConfig(
        "values",
        (
            ColumnConfig("id", "long", False),
            ColumnConfig("price", "decimal(12,3)", True),
            ColumnConfig("active", "boolean", False),
        ),
    )

    schema = to_spark_schema(input_config)

    assert schema.simpleString() == "struct<id:bigint,price:decimal(12,3),active:boolean>"
    assert validate_type_name(" Decimal(12, 3) ") == "decimal(12,3)"
    assert decimal_parts("decimal(12,3)") == (12, 3)
    assert is_numeric("decimal(12,3)")


def test_decimal_strategy_stays_within_precision_and_scale() -> None:
    column = ColumnConfig("price", "decimal(5,2)", False)
    value = find(value_strategy(column), lambda candidate: candidate != Decimal(0))

    assert isinstance(value, Decimal)
    assert abs(value) <= Decimal("999.99")
    assert -value.as_tuple().exponent <= 2


def test_timestamp_strategy_represents_utc_instant() -> None:
    from pyspark.sql.types import TimestampType

    value = find(
        value_strategy(ColumnConfig("occurred_at", "timestamp", False)),
        lambda candidate: candidate.tzinfo is not None,
    )

    assert value.tzinfo is timezone.utc
    assert TimestampType().toInternal(value) == int(value.timestamp() * 1_000_000)


def test_null_scenario_forces_a_schema_valid_null() -> None:
    case = find(case_strategy(config(), "nulls"), lambda _: True)

    assert any(
        row["amount"] is None or row["created_at"] is None
        for row in case.records["orders"]
    )


def test_duplicate_scenario_contains_an_actual_duplicate() -> None:
    case = find(case_strategy(config(), "duplicates"), lambda _: True)

    assert any(
        rows[index] == rows[other]
        for rows in case.records.values()
        for index in range(len(rows))
        for other in range(index + 1, len(rows))
    )


def test_join_scenario_coordinates_keys_and_positive_measure() -> None:
    case = find(case_strategy(config(), "join_amplification"), lambda _: True)
    order_keys = {row["customer_id"] for row in case.records["orders"]}
    customer_keys = [row["customer_id"] for row in case.records["customers"]]

    assert len(order_keys) == 1
    assert set(customer_keys) == order_keys
    assert len(customer_keys) >= 2
    assert len(set(customer_keys)) == 1
    assert all(row["amount"] > 0 for row in case.records["orders"])


def test_join_scenario_explores_relationship_values() -> None:
    case = find(
        case_strategy(config(), "join_amplification"),
        lambda candidate: candidate.records["orders"][0]["customer_id"] != 0,
    )

    assert case.records["orders"][0]["customer_id"] != 0


def test_determinism_scenario_explores_values() -> None:
    case = find(
        case_strategy(config(), "determinism"),
        lambda candidate: candidate.records["orders"][0]["customer_id"] != 0,
    )

    assert case.records["orders"][0]["customer_id"] != 0


def test_numeric_edge_scenario_injects_a_numeric_value() -> None:
    case = find(case_strategy(config(), "numeric_edges"), lambda _: True)

    assert case.records["orders"]
    assert isinstance(case.records["orders"][0]["customer_id"], int) or isinstance(
        case.records["orders"][0]["amount"], (int, float)
    )
