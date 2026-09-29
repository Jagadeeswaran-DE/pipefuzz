"""PipeFuzz command-line interface."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from pipefuzz import __version__
from pipefuzz.config import load_config
from pipefuzz.errors import ConfigurationError, ExitCode
from pipefuzz.loader import discover_config_path, load_transformation
from pipefuzz.reporting import format_classified_error, format_result
from pipefuzz.runner import run_fuzz


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _seed(value: str) -> int:
    parsed = int(value)
    if not 0 <= parsed <= (2**64 - 1):
        raise argparse.ArgumentTypeError("must be between 0 and 2^64-1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipefuzz",
        description="Property-based testing for PySpark DataFrame transformations",
    )
    parser.add_argument("--version", action="version", version=f"PipeFuzz {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    test = commands.add_parser("test", help="fuzz a PySpark transformation")
    test.add_argument("target", help="<file-or-module>::<function>")
    test.add_argument("--config", type=Path, help="PipeFuzz YAML configuration")
    test.add_argument("--max-examples", type=_positive_integer, default=10, help="examples per scenario (default: 10)")
    test.add_argument("--seed", type=_seed, help="Hypothesis seed for reproduction")
    test.add_argument("--verbose", action="store_true", help="show detailed diagnostics and tracebacks")
    return parser


def _exit_code(classification: str) -> ExitCode:
    return {
        "PASSED": ExitCode.OK,
        "INVARIANT_VIOLATION": ExitCode.INVARIANT_VIOLATION,
        "PIPEFUZZ_CONFIGURATION_ERROR": ExitCode.CONFIGURATION_ERROR,
        "TRANSFORMATION_EXCEPTION": ExitCode.TRANSFORMATION_EXCEPTION,
        "SPARK_ERROR": ExitCode.SPARK_ERROR,
        "PIPEFUZZ_INTERNAL_ERROR": ExitCode.INTERNAL_ERROR,
    }[classification]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cwd = Path.cwd()
    try:
        config_path = (args.config or discover_config_path(args.target, cwd)).resolve()
        config = load_config(config_path)
        transformation = load_transformation(args.target, tuple(config.inputs), cwd)
    except ConfigurationError as exc:
        print(
            format_classified_error(
                "PIPEFUZZ_CONFIGURATION_ERROR",
                str(exc),
                traceback.format_exc() if getattr(args, "verbose", False) else None,
            ),
            file=sys.stderr,
        )
        return int(ExitCode.CONFIGURATION_ERROR)
    try:
        result = run_fuzz(
            args.target,
            config_path,
            config,
            transformation,
            max_examples=args.max_examples,
            seed=args.seed,
            verbose=args.verbose,
        )
    except Exception as exc:  # final boundary: runner defects must never look like pipeline bugs
        print(
            format_classified_error(
                "PIPEFUZZ_INTERNAL_ERROR",
                f"Unexpected PipeFuzz failure: {type(exc).__name__}: {exc}",
                traceback.format_exc() if args.verbose else None,
            ),
            file=sys.stderr,
        )
        return int(ExitCode.INTERNAL_ERROR)
    stream = sys.stdout if result.passed else sys.stderr
    print(format_result(result, verbose=args.verbose), file=stream)
    return int(_exit_code(result.classification))


def entrypoint() -> None:
    raise SystemExit(main())


__all__ = ["build_parser", "entrypoint", "main"]

