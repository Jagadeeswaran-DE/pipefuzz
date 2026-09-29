from pathlib import Path

import pytest

from pipefuzz.cli import main
from pipefuzz.errors import ConfigurationError, ExitCode
from pipefuzz.loader import discover_config_path, load_transformation, split_target
from pipefuzz.models import FailureDetails, RunResult
from pipefuzz.reporting import format_result


def test_loads_file_transformation_and_validates_keywords(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline.py"
    pipeline.write_text("def transform(orders, customers):\n    return orders\n", encoding="utf-8")

    transformation = load_transformation(
        f"{pipeline}::transform", ("orders", "customers"), tmp_path
    )

    assert transformation("orders", "customers") == "orders"


def test_file_transformation_can_import_a_sibling_module() -> None:
    fixture = Path(__file__).parent / "fixtures" / "sibling_import" / "pipeline.py"

    transformation = load_transformation(f"{fixture}::transform", ("events",))

    assert transformation("events") == "events"


def test_file_targets_isolate_same_named_sibling_imports(tmp_path: Path) -> None:
    for name, value in (("first", "first"), ("second", "second")):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "pipefuzz_collision_helper.py").write_text(
            f"VALUE = {value!r}\n", encoding="utf-8"
        )
        (directory / "pipeline.py").write_text(
            "from pipefuzz_collision_helper import VALUE\n"
            "def transform(events):\n    return VALUE\n"
            "def dynamic(events):\n"
            "    import pipefuzz_collision_helper\n"
            "    return pipefuzz_collision_helper.VALUE\n",
            encoding="utf-8",
        )

    first = load_transformation(
        f"{tmp_path / 'first' / 'pipeline.py'}::transform", ("events",), tmp_path
    )
    second = load_transformation(
        f"{tmp_path / 'second' / 'pipeline.py'}::transform", ("events",), tmp_path
    )
    first_dynamic = load_transformation(
        f"{tmp_path / 'first' / 'pipeline.py'}::dynamic", ("events",), tmp_path
    )
    second_dynamic = load_transformation(
        f"{tmp_path / 'second' / 'pipeline.py'}::dynamic", ("events",), tmp_path
    )

    assert first("events") == "first"
    assert second("events") == "second"
    assert first_dynamic("events") == "first"
    assert second_dynamic("events") == "second"


def test_rejects_bad_target_and_signature(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline.py"
    pipeline.write_text("def transform(orders):\n    return orders\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="keyword arguments"):
        load_transformation(f"{pipeline}::transform", ("orders", "customers"), tmp_path)
    with pytest.raises(ConfigurationError, match="must use"):
        split_target("pipeline.py")


def test_discovers_file_adjacent_configuration(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "pipeline.py"

    assert discover_config_path(f"{target}::transform", tmp_path) == target.parent / "pipefuzz.yaml"


def test_reports_minimal_case_and_reproduction_command(tmp_path: Path) -> None:
    failure = FailureDetails(
        scenario="join_amplification",
        records={"orders": [{"customer_id": 1, "amount": DecimalValue("1.0")}]},
        reason="amplified",
        invariant="no_join_amplification",
        context={"input_absolute_total": "1.0", "output_absolute_total": "2.0"},
        schemas={
            "orders": [
                {"name": "customer_id", "type": "integer", "nullable": False},
                {"name": "amount", "type": "double", "nullable": False},
            ]
        },
    )
    result = RunResult(
        classification="INVARIANT_VIOLATION",
        target="pipeline.py::transform",
        config_path=tmp_path / "pipefuzz.yaml",
        seed=42,
        max_examples=10,
        generated_examples=7,
        hypothesis_version="6.test",
        scenarios=("join_amplification",),
        failure=failure,
    )

    report = format_result(result)

    assert "Minimal failing case" in report
    assert "no_join_amplification" in report
    assert "--seed 42" in report
    assert "INVARIANT_VIOLATION" in report
    assert "Failing scenario\n  join_amplification" in report
    assert "customer_id: integer (required)" in report


class DecimalValue:
    """Non-primitive value used to exercise the report's safe string fallback."""

    def __init__(self, value: str):
        self.value = value

    def __str__(self) -> str:
        return self.value


def test_cli_missing_config_is_classified_without_starting_spark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    code = main(["test", "missing.py::transform"])

    assert code == ExitCode.CONFIGURATION_ERROR
    assert "PIPEFUZZ_CONFIGURATION_ERROR" in capsys.readouterr().err


def test_exit_code_contract() -> None:
    assert int(ExitCode.OK) == 0
    assert int(ExitCode.INVARIANT_VIOLATION) == 1
    assert int(ExitCode.CONFIGURATION_ERROR) == 2
    assert int(ExitCode.TRANSFORMATION_EXCEPTION) == 3
    assert int(ExitCode.SPARK_ERROR) == 4
    assert int(ExitCode.INTERNAL_ERROR) == 5
