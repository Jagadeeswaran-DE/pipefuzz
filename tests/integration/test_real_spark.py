from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import find

import pipefuzz.cli as cli_module
import pipefuzz.runner as runner_module
from pipefuzz.config import load_config
from pipefuzz.loader import load_transformation
from pipefuzz.models import (
    ColumnConfig,
    GeneratedCase,
    InputConfig,
    InvariantConfig,
    PipeFuzzConfig,
)
from pipefuzz.runner import run_fuzz
from pipefuzz.spark import create_input_dataframe
from pipefuzz.strategies import case_strategy


ROOT = Path(__file__).resolve().parents[2]


def run_project(relative: str, spark, *, seed: int = 20260820, max_examples: int = 1):
    directory = ROOT / relative
    config_path = directory / "pipefuzz.yaml"
    target = f"{directory / 'pipeline.py'}::transform"
    config = load_config(config_path)
    transformation = load_transformation(target, tuple(config.inputs), ROOT)
    return run_fuzz(
        target,
        config_path,
        config,
        transformation,
        max_examples=max_examples,
        seed=seed,
        spark_session=spark,
    )


@pytest.mark.integration
def test_broken_join_is_generated_executed_and_minimized(spark) -> None:
    result = run_project("examples/broken_join", spark)

    assert result.classification == "INVARIANT_VIOLATION"
    assert result.failure is not None
    assert result.failure.invariant == "no_join_amplification"
    customer_keys = [row["customer_id"] for row in result.failure.records["customers"]]
    order_keys = {row["customer_id"] for row in result.failure.records["orders"]}
    assert len(customer_keys) >= 2
    assert len(set(customer_keys)) == 1
    assert set(customer_keys) == order_keys
    assert float(result.failure.context["output_absolute_total"]) > float(
        result.failure.context["input_absolute_total"]
    )


@pytest.mark.integration
def test_safe_join_receives_duplicates_without_false_positive(spark) -> None:
    result = run_project("examples/safe_join", spark, max_examples=2)

    assert result.passed
    assert 1 <= result.generated_examples <= 2


@pytest.mark.integration
def test_null_sensitive_transformation_finds_null_violation(spark) -> None:
    result = run_project("tests/integration/fixtures/null_sensitive", spark)

    assert result.classification == "INVARIANT_VIOLATION"
    assert result.failure is not None
    assert result.failure.invariant == "no_unexpected_nulls"
    assert result.failure.context["null_counts"] == {"required_value": 1}


@pytest.mark.integration
def test_nondeterministic_transformation_fails_semantic_comparison(spark) -> None:
    result = run_project("tests/integration/fixtures/nondeterministic", spark)

    assert result.classification == "INVARIANT_VIOLATION"
    assert result.failure is not None
    assert result.failure.invariant == "deterministic_output"


@pytest.mark.integration
def test_value_dependent_join_bug_is_not_hidden_by_fixed_demo_data(spark) -> None:
    directory = ROOT / "tests/integration/fixtures/nonzero_broken_join"
    config = load_config(directory / "pipefuzz.yaml")
    transformation = load_transformation(
        f"{directory / 'pipeline.py'}::transform", tuple(config.inputs), ROOT
    )
    case = find(
        case_strategy(config, "join_amplification"),
        lambda candidate: candidate.records["orders"][0]["customer_id"] != 0,
    )

    with pytest.raises(runner_module._InvariantCaseFailure):
        runner_module._execute_case(spark, transformation, config, case)


@pytest.mark.integration
def test_value_dependent_nondeterminism_is_discovered(spark) -> None:
    directory = ROOT / "tests/integration/fixtures/conditional_nondeterministic"
    config = load_config(directory / "pipefuzz.yaml")
    transformation = load_transformation(
        f"{directory / 'pipeline.py'}::transform", tuple(config.inputs), ROOT
    )
    case = find(
        case_strategy(config, "determinism"),
        lambda candidate: candidate.records["events"][0]["id"] != 0,
    )

    with pytest.raises(runner_module._InvariantCaseFailure):
        runner_module._execute_case(spark, transformation, config, case)


@pytest.mark.integration
def test_transformation_exception_is_not_called_a_pipeline_bug(spark) -> None:
    result = run_project("tests/integration/fixtures/raising", spark)

    assert result.classification == "TRANSFORMATION_EXCEPTION"
    assert result.failure is not None
    assert "deliberate transformation failure" in result.failure.reason


@pytest.mark.integration
def test_real_spark_user_analysis_error_is_a_transformation_exception(spark) -> None:
    directory = ROOT / "tests/integration/fixtures/nondeterministic"
    config_path = directory / "pipefuzz.yaml"
    config = load_config(config_path)

    result = run_fuzz(
        "inline::missing_column",
        config_path,
        config,
        lambda events: events.select("missing_column"),
        max_examples=1,
        seed=20260820,
        spark_session=spark,
    )

    assert result.classification == "TRANSFORMATION_EXCEPTION"
    assert result.failure is not None
    assert "AnalysisException" in result.failure.reason


@pytest.mark.integration
def test_legitimate_duplicates_nulls_and_cardinality_growth_do_not_false_positive(spark) -> None:
    events = InputConfig(
        "events",
        (
            ColumnConfig("id", "integer", False),
            ColumnConfig("note", "string", True),
        ),
        min_rows=2,
        max_rows=2,
    )
    config = PipeFuzzConfig(
        1,
        {"events": events},
        (),
        ("duplicates",),
        (InvariantConfig("no_unexpected_nulls", dataset="output", columns=("id",)),),
    )
    case = GeneratedCase(
        "duplicates",
        {"events": [{"id": 1, "note": None}, {"id": 1, "note": None}]},
    )

    runner_module._execute_case(
        spark,
        lambda events: events.unionByName(events),
        config,
        case,
    )


@pytest.mark.integration
def test_supported_scalar_values_materialize_in_real_spark(spark) -> None:
    values = InputConfig(
        "values",
        (
            ColumnConfig("text", "string", True),
            ColumnConfig("integer_value", "integer", False),
            ColumnConfig("long_value", "long", False),
            ColumnConfig("float_value", "float", False),
            ColumnConfig("double_value", "double", False),
            ColumnConfig("decimal_value", "decimal(5,2)", False),
            ColumnConfig("flag", "boolean", False),
            ColumnConfig("occurred_at", "timestamp", False),
        ),
        min_rows=0,
        max_rows=2,
    )
    records = [
        {
            "text": "",
            "integer_value": -2_147_483_648,
            "long_value": 9_223_372_036_854_775_807,
            "float_value": float("nan"),
            "double_value": float("inf"),
            "decimal_value": Decimal("999.99"),
            "flag": False,
            "occurred_at": datetime(2026, 8, 20, 12, 30),
        },
        {
            "text": "தமிழ் 🚀",
            "integer_value": 0,
            "long_value": -1,
            "float_value": float("-inf"),
            "double_value": -0.0,
            "decimal_value": Decimal("-999.99"),
            "flag": True,
            "occurred_at": datetime(2000, 1, 1),
        },
    ]

    collected = create_input_dataframe(spark, values, records).collect()
    empty = create_input_dataframe(spark, values, [])

    assert len(collected) == 2
    assert math.isnan(collected[0]["float_value"])
    assert math.isinf(collected[0]["double_value"])
    assert collected[1]["text"] == "தமிழ் 🚀"
    assert empty.count() == 0


@pytest.mark.integration
def test_spark_managed_input_failure_is_classified_separately(
    spark, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_to_create(*args, **kwargs):
        raise RuntimeError("deliberate Spark boundary failure")

    monkeypatch.setattr(runner_module, "create_input_dataframe", fail_to_create)
    result = run_project("tests/integration/fixtures/null_sensitive", spark)

    assert result.classification == "SPARK_ERROR"
    assert result.failure is not None
    assert "deliberate Spark boundary failure" in result.failure.reason


@pytest.mark.integration
def test_cli_discovers_adjacent_config_and_reports_real_failure(
    spark,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original_run = cli_module.run_fuzz

    def shared_session_run(*args, **kwargs):
        return original_run(*args, **kwargs, spark_session=spark)

    directory = ROOT / "examples/broken_join"
    monkeypatch.setattr(cli_module, "run_fuzz", shared_session_run)
    monkeypatch.chdir(directory)

    code = cli_module.main(
        ["test", "pipeline.py::transform", "--max-examples", "1", "--seed", "20260820"]
    )
    output = capsys.readouterr().err

    assert code == 1
    assert "INVARIANT_VIOLATION" in output
    assert "Minimal failing case" in output
    assert "--seed 20260820" in output
