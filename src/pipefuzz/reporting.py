"""Readable terminal reporting for Data Engineers."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pipefuzz.models import FailureDetails, RunResult


def _value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return aware.isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str, sort_keys=True)
    return str(value)


def _table(records: list[dict[str, Any]], schema: list[dict[str, Any]]) -> list[str]:
    columns = [column["name"] for column in schema]
    if not records:
        return ["  (empty)"]
    rendered = [[_value(row.get(column)) for column in columns] for row in records]
    widths = [
        min(40, max(len(column), *(len(row[index]) for row in rendered)))
        for index, column in enumerate(columns)
    ]

    def line(character: str = "-") -> str:
        return "  +" + "+".join(character * (width + 2) for width in widths) + "+"

    def row(values: list[str]) -> str:
        clipped = [value if len(value) <= width else value[: width - 1] + "…" for value, width in zip(values, widths, strict=True)]
        return "  | " + " | ".join(value.ljust(width) for value, width in zip(clipped, widths, strict=True)) + " |"

    return [line(), row(columns), line("="), *(row(values) for values in rendered), line()]


def _failure_lines(failure: FailureDetails) -> list[str]:
    lines = [
        "",
        "Failing scenario",
        f"  {failure.scenario}",
        "",
        "Minimal failing case",
        "",
    ]
    for input_name, records in failure.records.items():
        lines.append(input_name)
        schema = failure.schemas.get(input_name, [])
        lines.append("  Schema")
        for column in schema:
            nullability = "nullable" if column["nullable"] else "required"
            lines.append(f"    {column['name']}: {column['type']} ({nullability})")
        lines.append("  Records")
        lines.extend(_table(records, schema))
        lines.append("")
    lines.extend(["Reason", f"  {failure.reason}"])
    if failure.context:
        lines.extend(["", "Context"])
        for name, value in failure.context.items():
            lines.append(f"  {name}: {_value(value)}")
    return lines


def format_result(result: RunResult, *, verbose: bool = False) -> str:
    lines = [
        "PipeFuzz",
        "",
        "Transformation",
        f"  {result.target}",
        "",
        "Scenarios",
        *[f"  {scenario}" for scenario in result.scenarios],
        "",
        f"Generated examples: {result.generated_examples}",
        f"Hypothesis: {result.hypothesis_version}",
        f"Seed: {result.seed}",
        "",
    ]
    if result.passed:
        lines.extend(["PASSED", "", "No configured invariant was violated."])
        return "\n".join(lines)

    lines.extend(["FAILED", "", f"Classification: {result.classification}"])
    if result.failure:
        if result.failure.invariant:
            lines.extend(["", "Invariant", f"  {result.failure.invariant}"])
        lines.extend(_failure_lines(result.failure))
    elif result.error:
        lines.extend(["", "Reason", f"  {result.error}"])
    arguments = [
        "pipefuzz",
        "test",
        result.target,
        "--config",
        str(result.config_path),
        "--max-examples",
        str(result.max_examples),
        "--seed",
        str(result.seed),
    ]
    reproduce = subprocess.list2cmdline(arguments) if os.name == "nt" else shlex.join(arguments)
    lines.extend(["", "Reproduce", f"  {reproduce}"])
    if verbose and result.traceback:
        lines.extend(["", "Traceback", result.traceback.rstrip()])
    return "\n".join(lines)


def format_classified_error(classification: str, reason: str, traceback: str | None = None) -> str:
    lines = ["PipeFuzz", "", "FAILED", "", f"Classification: {classification}", "", "Reason", f"  {reason}"]
    if traceback:
        lines.extend(["", "Traceback", traceback.rstrip()])
    return "\n".join(lines)
