# Contributing to PipeFuzz

Thank you for helping improve property-based testing for PySpark pipelines.

## Development setup

PipeFuzz v0.1 supports Python 3.10–3.13, PySpark 4.2, and Java 17 or later. Create an isolated environment, make sure `java -version` succeeds, then install the project from the repository root:

```bash
python -m pip install -e ".[dev]"
python -m pip check
```

Verify the foundation before changing behavior:

```bash
pipefuzz --help
python -m pytest tests/unit
python -m pytest tests/integration
python -m pytest
```

The integration tests start a real local SparkSession. Do not replace their core Spark execution with mocks.

## Making changes

- Keep v0.1 focused on Python and PySpark DataFrame transformations.
- Add type hints and concise docstrings where behavior is not self-evident.
- Keep schemas, relationships, and invariant semantics explicit.
- Add unit coverage for pure logic and real-Spark coverage for execution behavior.
- Preserve failure classification and reproduction information.
- Do not weaken, skip, or mark a failing core test as expected merely to make CI pass.
- Avoid dependencies and abstractions that do not directly support the MVP.

Bug fixes should include a regression test. New scenario or invariant proposals should define their data-engineering meaning, required configuration, false-positive risks, and expected failure report before implementation.

## Pull requests

Keep changes reviewable and describe:

1. The problem and intended behavior.
2. Public configuration or CLI changes.
3. Commands actually run and their results.
4. Compatibility or performance considerations.
5. Known limitations.

By participating, you agree to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

