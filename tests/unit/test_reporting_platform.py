from pathlib import PurePosixPath

import pipefuzz.reporting as reporting
from pipefuzz.models import FailureDetails, RunResult


def test_posix_reproduction_command_quotes_paths_with_spaces(monkeypatch) -> None:
    config_path = PurePosixPath("some path/pipefuzz.yaml")
    result = RunResult(
        classification="INVARIANT_VIOLATION",
        target="some path/pipeline.py::transform",
        config_path=config_path,
        seed=42,
        max_examples=1,
        generated_examples=2,
        hypothesis_version="test",
        scenarios=("duplicates",),
        failure=FailureDetails("duplicates", {"data": []}, "duplicate key"),
    )
    monkeypatch.setattr(reporting.os, "name", "posix")

    report = reporting.format_result(result)

    assert "'some path/pipeline.py::transform'" in report
    assert "'some path/pipefuzz.yaml'" in report
