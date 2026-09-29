"""Supported schema parsing and PySpark schema construction."""

from __future__ import annotations

import re

from pipefuzz.errors import ConfigurationError
from pipefuzz.models import ColumnConfig, InputConfig


_SIMPLE_TYPES = {
    "string",
    "integer",
    "long",
    "float",
    "double",
    "boolean",
    "timestamp",
}
_DECIMAL_RE = re.compile(r"^decimal\((\d+),(\d+)\)$")
NUMERIC_TYPES = {"integer", "long", "float", "double"}


def validate_type_name(type_name: str) -> str:
    normalized = type_name.strip().lower().replace(" ", "")
    if normalized in _SIMPLE_TYPES:
        return normalized
    match = _DECIMAL_RE.fullmatch(normalized)
    if not match:
        raise ConfigurationError(f"Unsupported Spark type: {type_name!r}")
    precision, scale = (int(value) for value in match.groups())
    if not 1 <= precision <= 38:
        raise ConfigurationError("Decimal precision must be between 1 and 38")
    if not 0 <= scale <= precision:
        raise ConfigurationError("Decimal scale must be between 0 and its precision")
    return f"decimal({precision},{scale})"


def decimal_parts(type_name: str) -> tuple[int, int] | None:
    match = _DECIMAL_RE.fullmatch(type_name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def is_numeric(type_name: str) -> bool:
    return type_name in NUMERIC_TYPES or decimal_parts(type_name) is not None


def to_spark_schema(input_config: InputConfig):
    """Translate a validated input schema into a PySpark StructType."""
    from pyspark.sql.types import (
        BooleanType,
        DecimalType,
        DoubleType,
        FloatType,
        IntegerType,
        LongType,
        StringType,
        StructField,
        StructType,
        TimestampType,
    )

    simple = {
        "string": StringType,
        "integer": IntegerType,
        "long": LongType,
        "float": FloatType,
        "double": DoubleType,
        "boolean": BooleanType,
        "timestamp": TimestampType,
    }
    fields = []
    for column in input_config.schema:
        decimal = decimal_parts(column.type_name)
        data_type = DecimalType(*decimal) if decimal else simple[column.type_name]()
        fields.append(StructField(column.name, data_type, column.nullable))
    return StructType(fields)


def schema_columns(input_config: InputConfig) -> tuple[str, ...]:
    return tuple(column.name for column in input_config.schema)

