# PipeFuzz

**Stop testing data pipelines only with happy data.**

PipeFuzz is a property-based testing tool for PySpark DataFrame transformations. It uses Hypothesis to generate small adversarial datasets, runs the real transformation in a local SparkSession, and evaluates explicit Data Engineering invariants.

PipeFuzz v0.1 is intentionally narrow: Python functions in, PySpark DataFrames out, local execution only.

## Documentation

Read the [PipeFuzz documentation website](https://jagadeeswaran-de.github.io/pipefuzz-docs/)
for a guided quickstart, a broken-versus-safe join walkthrough, the complete YAML
reference, scenario and invariant semantics, CLI help, architecture, and limitations.
The documentation is public; access to this package repository is still required
to clone and install it. See [docs/README.md](docs/README.md) to build or update the site.

## Installation from a checkout

PipeFuzz is not represented as published on PyPI. From a project checkout, use Python 3.10–3.13 and Java 17 or later:

```bash
python -m pip install .
```

For development:

```bash
python -m pip install -e ".[dev]"
```

## Quick start

The broken-join example accepts an `orders` fact DataFrame and a `customers` dimension DataFrame. PipeFuzz generates matching keys and duplicate dimension rows, then checks whether the amount measure was amplified:

```bash
pipefuzz test examples/broken_join/pipeline.py::transform \
  --config examples/broken_join/pipefuzz.yaml
```

The configuration is explicit. PipeFuzz does not attempt to infer arbitrary transformation semantics:

```yaml
version: 1
inputs:
  orders:
    schema:
      - name: customer_id
        type: integer
        nullable: false
      - name: amount
        type: double
        nullable: false
    rows: {min: 1, max: 4}
  customers:
    schema:
      - name: customer_id
        type: integer
        nullable: false
      - name: country
        type: string
        nullable: false
    primary_key: [customer_id]
    rows: {min: 1, max: 4}
relationships:
  - name: orders_customer
    from: {input: orders, columns: [customer_id]}
    to: {input: customers, columns: [customer_id]}
    cardinality: many_to_one
scenarios: [join_amplification]
invariants:
  - type: no_join_amplification
    relationship: orders_customer
    input: orders
    input_column: amount
    output_column: total_amount
```

When `--config` is omitted for a file target, PipeFuzz looks for `pipefuzz.yaml` beside the Python file. Use `--seed` with the value printed in a failure report to reproduce the same Hypothesis run.

## CLI

```text
pipefuzz test <file-or-module>::<function> [options]

--config PATH       explicit YAML configuration
--max-examples N    Hypothesis examples per enabled scenario (default: 10)
--seed N            reproducible Hypothesis seed
--verbose           Spark diagnostics and tracebacks
```

Exit codes distinguish outcomes: `0` pass, `1` invariant violation, `2` configuration error, `3` transformation exception, `4` Spark error, and `5` internal PipeFuzz error.

## Supported scenarios

- `nulls` forces a NULL into a nullable column.
- `duplicates` generates repeated records and keys.
- `join_amplification` coordinates matching fact/dimension keys and duplicates the dimension side of a declared many-to-one relationship.
- `numeric_edges` generates zero, negative, positive, decimal, and type-boundary-oriented values that fit the declared Spark type.
- `determinism` executes the same transformation twice against equivalent inputs.

Generated datasets are deliberately small and use the smallest valid row count needed for each adversarial scenario. Hypothesis explores compact schema-valid values and shrinks failures; PipeFuzz guarantees each enabled scenario's structure. Join relationship keys are generated and coordinated rather than fixed to a demonstration value.

## Invariants

- `unique_key` rejects repeated key tuples, including repeated tuples containing NULL.
- `no_unexpected_nulls` counts NULL values in configured columns.
- `no_join_amplification` asserts that the absolute output measure total does not exceed the absolute input measure total beyond the configured tolerance. It should only be used for transformations expected to conserve that measure.
- `deterministic_output` compares repeated outputs as unordered multisets. Duplicate counts matter; NULL and Decimal values compare exactly, timestamps normalize to UTC, and floats use configurable relative and absolute tolerances.

Determinism is not stateful pipeline idempotency. PipeFuzz v0.1 does not execute persisted sinks or validate state changes.

## Architecture

```text
YAML schema and invariants
          ↓
Hypothesis Python records
          ↓
real local Spark DataFrames
          ↓
user transformation
          ↓
materialized snapshots and invariant results
          ↓
minimal failure report and reproduction seed
```

One SparkSession is reused for a CLI run. Inputs and outputs are collected to the driver because v0.1 is a logical-testing tool for small generated datasets, not a load-testing system.

## Privacy and security

PipeFuzz runs locally. It does not upload data or code, emit telemetry, use API keys, or call external AI services. Failure reports intentionally print the minimized generated input records plus configured schema and column names to the local terminal; treat captured logs as potentially sensitive project metadata. Tested transformations are ordinary Python and may perform their own network or filesystem activity, which PipeFuzz does not sandbox. See [SECURITY.md](SECURITY.md) for reporting guidance once this project is hosted.

## Limitations

- Only PySpark DataFrame transformations are supported.
- Input schemas are limited to the documented primitive types.
- Relationships and invariants must be configured explicitly.
- Join amplification is a measure-conservation assertion, not automatic Python or query-plan analysis.
- Generated outputs must remain small enough to collect locally.
- SQL parsing, dbt, Pandas, Polars, cloud services, streaming, and stateful sink testing are not supported.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The next recommended milestone is carefully scoped SQL transformation support; it is not part of v0.1.
