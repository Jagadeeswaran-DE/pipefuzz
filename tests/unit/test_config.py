from pathlib import Path

import pytest

from pipefuzz.config import load_config
from pipefuzz.errors import ConfigurationError


VALID = """
version: 1
inputs:
  orders:
    schema:
      - {name: order_id, type: long, nullable: false}
      - {name: customer_id, type: integer, nullable: false}
      - {name: amount, type: "decimal(10,2)", nullable: true}
    primary_key: [order_id]
    rows: {min: 1, max: 4}
  customers:
    schema:
      - {name: customer_id, type: integer, nullable: false}
      - {name: country, type: string, nullable: false}
    primary_key: [customer_id]
    rows: {min: 1, max: 4}
relationships:
  - name: orders_customer
    from: {input: orders, columns: [customer_id]}
    to: {input: customers, columns: [customer_id]}
    cardinality: many_to_one
scenarios: [nulls, duplicates, join_amplification, numeric_edges, determinism]
invariants:
  - {type: unique_key, dataset: customers, columns: [customer_id]}
  - {type: no_unexpected_nulls, dataset: output, columns: [total_amount]}
  - type: no_join_amplification
    relationship: orders_customer
    input: orders
    input_column: amount
    output_column: total_amount
  - {type: deterministic_output, rtol: 1.0e-8, atol: 1.0e-10}
"""


def write_config(tmp_path: Path, content: str = VALID) -> Path:
    path = tmp_path / "pipefuzz.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_strict_version_one_config_in_input_order(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path))

    assert tuple(config.inputs) == ("orders", "customers")
    assert config.inputs["orders"].column("amount").type_name == "decimal(10,2)"
    assert config.relationship("orders_customer").to_columns == ("customer_id",)
    assert config.invariants[-1].rtol == 1e-8


@pytest.mark.parametrize(
    ("before", "after", "message"),
    [
        ("version: 1", "version: 2", "version must be 1"),
        ("rows: {min: 1, max: 4}", "rows: {min: 5, max: 4}", "0 <= min <= max"),
        ("type: long", "type: array", "Unsupported Spark type"),
        ("cardinality: many_to_one", "cardinality: many_to_many", "cardinality must be"),
        ("scenarios: [nulls,", "scenarios: [unknown,", "Unknown scenarios"),
    ],
)
def test_rejects_invalid_configuration(
    tmp_path: Path, before: str, after: str, message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        load_config(write_config(tmp_path, VALID.replace(before, after, 1)))


def test_rejects_unknown_keys(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="Unknown configuration keys: surprise"):
        load_config(write_config(tmp_path, VALID + "\nsurprise: true\n"))


def test_determinism_invariant_requires_scenario(tmp_path: Path) -> None:
    content = VALID.replace(", determinism]", "]")
    with pytest.raises(ConfigurationError, match="requires the determinism scenario"):
        load_config(write_config(tmp_path, content))


def test_missing_file_is_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="does not exist"):
        load_config(tmp_path / "missing.yaml")


@pytest.mark.parametrize("value", [".inf", ".nan"])
def test_rejects_non_finite_invariant_tolerances(tmp_path: Path, value: str) -> None:
    content = VALID.replace("rtol: 1.0e-8", f"rtol: {value}")

    with pytest.raises(ConfigurationError, match="finite non-negative number"):
        load_config(write_config(tmp_path, content))
