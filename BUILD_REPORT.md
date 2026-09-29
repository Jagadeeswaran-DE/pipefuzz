# PipeFuzz v0.1 Build Report

> Historical pre-audit build evidence. See `RELEASE_AUDIT.md` for the current release verdict and post-audit verification once the adversarial audit is complete.

## Outcome

PipeFuzz `0.1.0` is implemented as a property-based PySpark testing package. The source checkout, built wheel, and real local Spark execution were verified on 2026-08-20. The broken join example produced a minimized invariant violation with exit code `1`; the equivalent safe join passed with exit code `0`.

The package has not been published to PyPI, committed, pushed, or exercised by a hosted CI runner. Installation instructions therefore use a local checkout or a locally built wheel.

## Build environment

All build and verification commands used the ignored workspace-local Conda environment at `.tools/runtime`.

| Component | Resolved version |
| --- | --- |
| PipeFuzz | 0.1.0 |
| Python | 3.13.15 |
| OpenJDK | 17.0.14 |
| PySpark | 4.2.0 |
| Hypothesis | 6.165.10 |
| PyYAML | 6.0.3 |
| pytest | 9.1.1 |
| build | 1.5.0 |
| Hatchling | 1.32.0 |
| pip | 26.1.2 |

The declared compatibility bounds are Python `>=3.10,<3.14`, PySpark `>=4.2,<4.3`, Hypothesis `>=6.158,<7`, and PyYAML `>=6.0.3,<7`.

### Complete resolved Python package inventory

This is the output of `.tools/runtime/python.exe -m pip list --format=freeze`. It includes packages supplied by the local Conda runtime in addition to PipeFuzz's declared dependencies.

```text
asttokens==3.0.1
build==1.5.0
cffi==2.1.1
colorama==0.4.6
comm==0.2.3
cryptography==50.0.0
debugpy==1.8.20
decorator==5.2.1
executing==2.2.1
hatchling==1.32.0
hypothesis==6.165.10
iniconfig==2.3.0
ipykernel==7.2.0
ipython==9.13.0
ipython_pygments_lexers==1.1.1
jedi==0.20.0
jupyter_client==8.8.0
jupyter_core==5.9.1
matplotlib-inline==0.2.2
nest-asyncio==1.6.0
packaging==26.2
parso==0.8.7
pathspec==1.1.1
pip==26.1.2
pipefuzz==0.1.0
platformdirs==4.9.6
pluggy==1.6.0
prompt_toolkit==3.0.52
psutil==7.2.2
psycopg==3.3.4
psycopg-binary==3.3.4
pure_eval==0.2.3
py4j==0.10.9.9
pycparser==3.0
Pygments==2.20.0
pyproject_hooks==1.2.0
pyspark==4.2.0
pytest==9.1.1
python-dateutil==2.9.0.post0
PyYAML==6.0.3
pyzmq==27.1.0
setuptools==83.0.0
six==1.17.0
sortedcontainers==2.4.0
stack-data==0.6.3
tomlkit==0.15.1
tornado==6.5.5
traitlets==5.15.0
trove-classifiers==2026.6.1.19
tzdata==2026.3
wcwidth==0.7.0
wheel==0.47.0
```

## Implemented features

### Packaging and command line

- `src/pipefuzz` package layout with Hatchling and Apache-2.0 metadata.
- `pipefuzz test <file-or-module>::<function>` with `--config`, `--max-examples`, `--seed`, and `--verbose`.
- Configuration discovery beside file targets and from the current directory for module targets.
- Stable classifications and exit codes: pass `0`, invariant violation `1`, configuration error `2`, transformation exception `3`, Spark error `4`, and internal error `5`.
- File and module target loading with signature validation for configured keyword input names.

### Configuration and generation

- Strict YAML version 1 parsing with ordered input schemas, nullability, row bounds, composite primary keys, named many-to-one relationships, enabled scenarios, and explicit invariants.
- Spark types: `string`, `integer`, `long`, `float`, `double`, `decimal(p,s)`, `boolean`, and `timestamp`.
- Hypothesis strategies for `nulls`, `duplicates`, `join_amplification`, `numeric_edges`, and `determinism`.
- Relationship-aware key generation and adversarial duplicated dimension keys without hardcoded example values.
- Precision-safe decimals, bounded numeric edges, non-nullable field enforcement, and UTC-normalized timestamps.
- A default of ten generated examples per enabled scenario, overridable from the CLI.

### Spark execution and invariants

- One `local[2]` Spark session per CLI run, using UTC, disabled UI, two shuffle partitions, controlled logging, forced actions, and `finally`-based shutdown.
- Real DataFrame creation from generated Python records and real execution of the user transformation.
- Structured `RunResult` and `InvariantResult` models.
- `unique_key`, including repeated all-NULL key tuples.
- `no_unexpected_nulls`, with per-column null counts.
- `no_join_amplification`, comparing absolute input and output measure totals with relative and absolute tolerance.
- `deterministic_output`, executing the transformation twice against equivalent inputs.
- Schema-aware, order-independent multiset comparison that preserves duplicate counts, handles NULL and Decimal exactly, normalizes timestamps to UTC, recursively compares compound values, and applies configured float tolerances.
- Failure reports include classification, scenario, invariant, target, minimized records, observed and expected context, Hypothesis version, seed, and an exact reproduction command.
- Only `INVARIANT_VIOLATION` is described as a discovered pipeline bug.

### Project material

- Broken and safe join examples sharing the same relationship and amplification invariant.
- README quick start, YAML reference, semantics, architecture, local-only privacy statement, and limitations.
- Contributing, code of conduct, security policy, full Apache License 2.0 text, and ignored local/build/Spark/Hypothesis artifacts.
- GitHub Actions definition for Temurin Java 17 and Python 3.10/3.13 using `actions/checkout@v7`, `actions/setup-python@v7`, and `actions/setup-java@v5`.

## Verification evidence

Commands below were run from the repository root with `.tools/runtime` providing Python and Java. Durations are recorded when pytest reported them.

| Verification | Result |
| --- | --- |
| Editable install: `.tools/runtime/python.exe -m pip install -e ".[dev]"` | Passed |
| Build: `.tools/runtime/python.exe -m build` | Passed; wheel and source archive created |
| Wheel install: `.tools/runtime/python.exe -m pip install --force-reinstall --no-deps dist/pipefuzz-0.1.0-py3-none-any.whl` | Passed |
| Dependency check: `.tools/runtime/python.exe -m pip check` | Passed; no broken requirements |
| CLI: `.tools/runtime/Scripts/pipefuzz.exe --help` | Passed; exit 0 |
| Unit: `.tools/runtime/python.exe -m pytest tests/unit` | `27 passed in 5.00s` |
| Integration: `.tools/runtime/python.exe -m pytest tests/integration` | `7 passed in 154.96s (0:02:34)` |
| Full wheel-installed suite: `.tools/runtime/python.exe -m pytest` | `34 passed in 181.31s (0:03:01)` |
| Broken join CLI, seed 20260820 | Expected invariant violation; exit 1 |
| Safe join CLI, seed 20260820 | Passed; exit 0 |
| `git diff --check` | Passed |

The real-Spark integration suite proves broken join detection and shrinking, safe join behavior under adversarial duplicates, null violations, nondeterministic output detection, transformation and Spark error classification, config discovery, explicit config handling, seed reproduction, rendering, and exit codes.

### Distribution artifacts

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `dist/pipefuzz-0.1.0-py3-none-any.whl` | 26,809 | `86E726D24D0584ACC5BD17A6035EECA5C104DB33972457FED0680731746158EF` |
| `dist/pipefuzz-0.1.0.tar.gz` | 29,811 | `6EB479A8EC3DB2556C8DF2ED987A05E27C5572E170EFCDBEE9C2244DF870E3C4` |

The wheel was inspected and contains the PipeFuzz modules, console entry point, package metadata, and `licenses/LICENSE`.

## Broken join demonstration

Command:

```powershell
.tools\runtime\Scripts\pipefuzz.exe test examples/broken_join/pipeline.py::transform --config examples/broken_join/pipefuzz.yaml --max-examples 1 --seed 20260820
```

Exit code: `1`.

Application output, excluding Spark's progress and platform-warning prelude:

```text
PipeFuzz

Transformation
  examples/broken_join/pipeline.py::transform

Scenarios
  join_amplification

Generated examples: 2
Hypothesis: 6.165.10
Seed: 20260820

FAILED

Classification: INVARIANT_VIOLATION

Invariant
  no_join_amplification

Minimal failing case

orders
  +-------------+--------+
  | customer_id | amount |
  +=============+========+
  | 0           | 1.0    |
  +-------------+--------+

customers
  +-------------+---------+
  | customer_id | country |
  +=============+=========+
  | 0           |         |
  | 0           |         |
  +-------------+---------+

Reason
  Output measure exceeds the input measure; a join may have amplified fact values

Context
  relationship: orders_customer
  input: orders
  input_column: amount
  output_column: total_amount
  input_absolute_total: 1.0
  output_absolute_total: 2.0
  tolerance: 1.001E-9

Reproduce
  pipefuzz test examples/broken_join/pipeline.py::transform --config "C:\Users\SST\Documents\ChatGPT\Open source\examples\broken_join\pipefuzz.yaml" --max-examples 1 --seed 20260820
```

This is the only demonstrated result classified as a discovered pipeline bug. Hypothesis reduced the failure to one fact record and two dimension records sharing the generated key.

## Safe join demonstration

Command:

```powershell
.tools\runtime\Scripts\pipefuzz.exe test examples/safe_join/pipeline.py::transform --config examples/safe_join/pipefuzz.yaml --max-examples 1 --seed 20260820
```

Exit code: `0`.

```text
PipeFuzz

Transformation
  examples/safe_join/pipeline.py::transform

Scenarios
  join_amplification

Generated examples: 1
Hypothesis: 6.165.10
Seed: 20260820

PASSED

No configured invariant was violated.
```

The safe transformation deduplicates the dimension relationship key before joining, so the same adversarial scenario does not amplify the fact measure.

## Architecture decisions

- Generation happens in Python first so Hypothesis can shrink plain, serializable record collections. Spark DataFrames are created only at the execution boundary.
- Scenario strategies stay independent and focused. The join-amplification strategy uses coordinated relationship keys, a minimal fact measure, and a duplicated dimension key so failure shrinking remains practical while still exercising a real Spark join. Numeric variability belongs to the numeric-edge scenario.
- The transformation is invoked twice with the same generated input DataFrames. This tests repeat execution against equivalent inputs, but does not test fresh input DataFrame objects or persisted-state idempotency.
- Input-side invariant snapshots use the declared Spark schema and generated records. Transformation outputs are actioned and collected, guaranteeing real Spark execution while avoiding redundant input jobs.
- Equality compares rows as a semantic multiset rather than sorting raw Spark rows, preserving duplicate counts and supporting nested values consistently.
- Spark lifecycle and error boundaries live in the runner. Configuration, target loading, transformation exceptions, Spark failures, and internal defects remain distinct from invariant violations.

## Limitations and known issues

- SQL transformations, Pandas, streaming, remote Spark clusters, cloud platforms, APIs, UI, stateful sinks, and persisted-state idempotency are out of scope for v0.1.
- Determinism covers repeated transformation execution on equivalent generated inputs only.
- Generated datasets are intentionally small and are a bug-finding aid, not a performance or load test.
- The equality layer supports recursively collected Python representations, but v1 YAML exposes only the documented scalar schema types.
- The current GitHub Actions workflow was authored but not executed by a hosted runner in this build session.
- Real local execution was verified on Windows. PySpark emitted expected Windows-local warnings for missing `winutils.exe` and the native Hadoop library; Spark used its built-in Java implementations and all jobs completed.
- The workspace path contains a space. PySpark prints a harmless worker-path warning during startup even though PipeFuzz configures the driver and worker with the exact runtime executable and the jobs pass.
- After some successful Spark-backed pytest and CLI processes, Windows printed `ERROR: Access denied` during PySpark's final subprocess cleanup. The application or pytest process had already returned its correct exit status; the full suite still returned `0`, the broken demonstration returned `1`, and the safe demonstration returned `0`.

## Recommended v0.2 milestone

Add SQL transformation support while retaining the v0.1 execution contract and classifications. A practical design is to allow a configured SQL file or query target, register generated inputs as temporary views with collision-safe names, execute through the same session, and feed the resulting DataFrame through the existing invariant, comparison, shrinking, seed, and reporting layers. The milestone should add SQL parsing/config validation, temporary-view lifecycle isolation, multi-statement policy, catalog access boundaries, and real-Spark tests for SQL joins, NULL semantics, deterministic output, and Spark SQL error classification.
