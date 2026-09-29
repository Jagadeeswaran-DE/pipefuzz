# PipeFuzz v0.1 adversarial release audit

Audit date: 2026-09-29. Scope: the local `0.1.0` checkout and its declared PySpark DataFrame/YAML v1 behavior. The instructions in the two supplied audit documents were used as test criteria; findings below come from executing or inspecting this repository.

## Release recommendation

**NOT READY for public release.** The audit reproduced defects that the original 34-test suite missed, added focused repairs and regressions, then observed 49 passing tests, successful final wheel/source builds and wheel installation, and the expected exit status from both public examples. The documented v0.1 behavior is verified locally on Windows/Python 3.13/Java 17, and no reproduced core defect remains open. The declared Python 3.10–3.12 compatibility and non-Windows behavior remain unexecuted; hosted CI has not run, and all project files remain untracked. The remaining release gate is to commit the reviewed tree and run the cross-version CI matrix before making public compatibility claims.

## Environment and baseline

- Windows 11 (`Windows-11-10.0.26200-SP0`), Python 3.13.15, OpenJDK 17.0.14, PySpark 4.2.0, Hypothesis 6.165.10, PyYAML 6.0.3, PipeFuzz 0.1.0. Versions were read from the isolated audit wheel environment and workspace Java executable.
- The checkout has no committed project files yet; all project files currently appear as untracked to Git. No release upload or hosted CI run was performed.
- Local Spark runs require the workspace Java on `JAVA_HOME` and `PATH`. The following PowerShell prelude was used for the Spark test commands:

  ```powershell
  $runtime='C:\Users\SST\Documents\ChatGPT\Open source\.tools\runtime'
  $env:JAVA_HOME=Join-Path $runtime 'Library'
  $env:PATH=(Join-Path $runtime 'Library\bin')+';'+$runtime+';'+$env:PATH
  $env:PYTHONNOUSERSITE='1'
  ```

| Executed command from repository root | Actual result |
| --- | --- |
| `& (Join-Path $runtime 'python.exe') -m pytest` | Baseline: **34 passed in 171.71s**. Passing existing tests did not exclude the defects below. |
| `.tools/runtime/python.exe -m build --outdir .tools/audit-baseline-dist` | Built wheel and source distribution. |
| `.tools/runtime/python.exe -m venv .tools/audit-baseline-venv` | Created fresh isolated Python environment. |
| `.tools/audit-baseline-venv/Scripts/python.exe -m pip install .tools/audit-baseline-dist/pipefuzz-0.1.0-py3-none-any.whl` | Installed built baseline wheel and its dependencies. |
| `.tools/audit-baseline-venv/Scripts/pipefuzz.exe --help` | CLI entry point worked, exit 0. |
| `.tools/audit-baseline-venv/Scripts/python.exe -m pip check` | No broken requirements. |

The baseline wheel was `pipefuzz-0.1.0-py3-none-any.whl`; the baseline source archive was `pipefuzz-0.1.0.tar.gz`. These baseline artifacts predate the audit fixes and are not release evidence for the final tree.

## Reproduced defects and fixes

Each entry describes an observed pre-fix behavior or a direct code-level failure, followed by the narrow repair and regression evidence added to this repository. Test pass results are recorded separately below.

| ID | Reproduction and impact | Root-cause fix | Regression |
| --- | --- | --- | --- |
| A1 | YAML `.inf` tolerance made a million-fold measure increase pass `no_join_amplification`; `.nan` reached an internal-error path. | Require finite, non-negative `rtol` and `atol` during configuration parsing. | `test_rejects_non_finite_invariant_tolerances` in `tests/unit/test_config.py`. |
| A2 | A valid unordered float matching was reported unequal: left `[0.0, 0.1]`, right `[0.05, -0.05]`, `atol=0.06`. A greedy first match consumed the only partner for `0.1`. | Use a complete bipartite row matching so every duplicate-aware match can be considered. | `test_snapshot_comparison_finds_a_valid_non_greedy_float_matching`. |
| A3 | Join and determinism scenarios repeatedly used zero/default values. A join bug guarded by `customer_id != 0`, and a nondeterministic branch guarded by `id != 0`, could be missed despite being in the configured scope. | Draw compact schema-valid values for the relevant generated rows and coordinate relationship keys; retain guaranteed duplicate dimension keys and positive fact measure. | `test_join_scenario_explores_relationship_values`, `test_determinism_scenario_explores_values`, plus real-Spark `test_value_dependent_join_bug_is_not_hidden_by_fixed_demo_data` and `test_value_dependent_nondeterminism_is_discovered`. |
| A4 | `unique_key` on a collected array/list key raised `TypeError: unhashable type: 'list'` instead of reporting repeated keys. | Canonicalize nested key values for counting while preserving the original values in diagnostics. | `test_unique_key_handles_compound_output_values`. |
| A5 | A file target importing a sibling module failed loading when that directory was absent from `sys.path`; similarly named sibling modules from different targets could collide in `sys.modules`. | Isolate the target directory during file import and avoid reusing the wrong sibling module. | `test_file_transformation_can_import_a_sibling_module` and `test_file_targets_isolate_same_named_sibling_imports`. |
| A6 | The failure text omitted an explicit failing-scenario section and displayed records without their schema; this made a minimized case ambiguous. | Render the failing scenario, configured column types/nullability, and records together. | `test_reports_minimal_case_and_reproduction_command`. |
| A7 | The printed reproduction command used Windows quoting even on non-Windows systems. | Format arguments with the platform's appropriate shell quoting. | `tests/unit/test_reporting_platform.py` checks POSIX quoting; a non-Windows runner remains unverified. |
| A8 | Generated/default `timestamp` values were naive. On this Asia/Calcutta host, Spark interpreted them in local time, shifting the intended instant by 5 hours 30 minutes. | Generate UTC-aware datetimes and use UTC-aware defaults. | `test_timestamp_strategy_represents_utc_instant`, which checks the value against `TimestampType.toInternal`. |

Representative pre-fix probes and observed results (abridged expressions; snapshot/config object construction is omitted):

```python
# A1: _float_option({'rtol': float('inf')}, 'rtol', 1e-9, 'audit')
# accepted Infinity; no_join_amplification(input=1.0, output=1000000.0)
# returned passed=True. NaN tolerance reached decimal.InvalidOperation.

# A2: snapshots_equal(left=[0.0, 0.1], right=[0.05, -0.05],
#                     rtol=0, atol=0.06) returned False.
# Pairing 0.0 -> -0.05 and 0.1 -> 0.05 is within tolerance.

# A3: find(case_strategy(config, 'join_amplification'),
#          lambda case: case.records['orders'][0]['customer_id'] != 0,
#          settings=settings(max_examples=100, database=None, deadline=None))
# raised NoSuchExample. The real-Spark nonzero_broken_join and
# conditional_nondeterministic fixtures both returned PASSED pre-fix.

# A8 on the Asia/Calcutta host:
# TimestampType().toInternal(datetime(2020, 1, 1))
#   -> 1577817000000000
# TimestampType().toInternal(datetime(2020, 1, 1, tzinfo=timezone.utc))
#   -> 1577836800000000
```

The package distinguishes a discovered invariant violation from configuration, transformation, Spark boundary, and internal failures. An actual Spark `AnalysisException` raised by user transformation logic is a transformation exception; a Spark-managed input creation failure is `SPARK_ERROR`. The tests exercise both classifications.

## Core claim and adversarial coverage

The execution path under review is `case_strategy` -> Hypothesis `given`/`seed` -> Python records -> `spark.createDataFrame` -> the loaded user function -> `DataFrame.collect()` -> invariant evaluation. The broken-join integration test checks a minimized case with one fact measure and duplicate generated dimension keys, and compares observed output total with input total. The safe-join integration test uses the same configured relationship and checks that deduplication passes. The non-zero-key tests prevent the demo from being the only value the strategies can exercise.

Real-Spark tests also cover a NULL-sensitive transformation, nondeterministic output, user exceptions, Spark boundary classification, valid duplicate rows and cardinality growth, empty DataFrames, empty and Unicode strings, integer/long extremes, Decimal, timestamp, NaN/Infinity materialization where the Spark scalar type permits them, and repeated use of the shared test session. A separate real-Spark NULL join-key probe used one order `(NULL, 1.0)` and two customers with NULL keys; the equijoin produced zero rows, and `_execute_case` passed `no_join_amplification` (exit 0, `NULL_JOIN_KEY_PROBE_PASSED output_rows=0 invariant=no_join_amplification`). Unit tests cover repeated NULL key tuples, decimal strategy bounds, float/Decimal/UTC comparison, and configuration and target errors. `DateType` is outside the v1 input schema; its omission is not treated as a defect.

The declared invariant is deliberately specific: `no_join_amplification` compares absolute measure totals. It is appropriate only when that measure should not increase. Legitimate one-to-many joins or cardinality-changing aggregations can be tested without that invariant, as long as the configured properties fit the transformation. A primary key declaration alone does not prove uniqueness of output; `unique_key` must be configured for the dataset and columns under test.

## Packaging, lifecycle, privacy, and documentation check

- The built baseline wheel imports and exposes the CLI. The package metadata declares Python `>=3.10,<3.14`, PySpark `>=4.2,<4.3`, Hypothesis `>=6.158,<7`, and PyYAML `>=6.0.3,<7`. Only Python 3.13 on Windows was executed in this audit; Python 3.10–3.12 and macOS/Linux are unverified here. A hosted CI workflow exists but was not run in this audit.
- The CLI creates one `local[2]` SparkSession per run and calls `stop()` in `finally`; integration tests share one fixture session. Snapshotting collects small output DataFrames to the driver. Hypothesis shrinking may invoke additional Spark jobs beyond `--max-examples` after a failure; that is expected property-testing behavior, not a load-test guarantee.
- Source inspection found no PipeFuzz telemetry, network client, or API-key requirement. The user transformation is arbitrary Python and is not sandboxed. Failure reports intentionally print generated records, schema, and column names to the terminal; logs therefore need the same care as other potentially sensitive test output. The README now states this.
- The pre-audit `BUILD_REPORT.md` is historical. Its earlier statement that determinism recreated input DataFrames was corrected: the implementation executes the function twice using the same equivalent input DataFrames. This tests the transformation's observed output, not persisted-state idempotency.
- Spark/Windows may print `winutils.exe`, native Hadoop, or Python-path warnings in this workspace. The existence of warnings alone does not prove a job failure; command exit status and test assertions are used for the verdict.

## Final verification gate

The post-fix full suite used the environment prelude above:

```powershell
.tools/runtime/python.exe -m pytest -q --durations=12
```

Result: **49 passed in 247.42s (0:04:07), process exit 0**. After pytest completed, Windows/PySpark printed `ERROR: Access denied` during subprocess cleanup; it did not change the test result or exit status. Post-fix packaging checks also completed:

| Executed command from repository root | Actual result |
| --- | --- |
| `.tools/runtime/python.exe -m build --outdir .tools/audit-final-dist` | Successfully built `pipefuzz-0.1.0.tar.gz` and `pipefuzz-0.1.0-py3-none-any.whl` from the repaired tree. |
| `.tools/audit-baseline-venv/Scripts/python.exe -m pip install --force-reinstall --no-deps .tools/audit-final-dist/pipefuzz-0.1.0-py3-none-any.whl` | Reinstalled the final wheel into the isolated audit venv. |
| `.tools/audit-baseline-venv/Scripts/pipefuzz.exe --help` | Exit 0. |
| Import and metadata inspection using `.tools/audit-baseline-venv/Scripts/python.exe` | Imported version `0.1.0` from the venv's `site-packages`; expected dependency metadata present. |
| `.tools/audit-baseline-venv/Scripts/python.exe -m pip check` | No broken requirements. |

The rebuilt wheel's public examples were run through the installed CLI with the same seed and options:

| Executed command from repository root | Actual result |
| --- | --- |
| `.tools/audit-baseline-venv/Scripts/pipefuzz.exe test examples/broken_join/pipeline.py::transform --config examples/broken_join/pipefuzz.yaml --max-examples 1 --seed 20260820` | Exit **1**, `INVARIANT_VIOLATION` / `no_join_amplification`. Hypothesis 6.165.10 ran 4 examples including shrinking. Minimal records: one order `{customer_id: 1, amount: 1.0}` and two customer rows `{customer_id: 1, country: ''}`. Input absolute total `1.0`, output `2.0`, tolerance `1.001E-9`. Report included the failing scenario, schemas, and seed reproduction command. |
| `.tools/audit-baseline-venv/Scripts/pipefuzz.exe test examples/safe_join/pipeline.py::transform --config examples/safe_join/pipefuzz.yaml --max-examples 1 --seed 20260820` | Exit **0**, `PASSED`, 1 generated example. |

Both installed-CLI processes printed Windows/PySpark `ERROR: Access denied` during late subprocess cleanup after returning their correct application status. Two independent installed-CLI runs plus the shared-session Spark tests provided basic lifecycle evidence; no long-running leak/stress test was performed.

## Remaining limits

- No SQL, dbt, Pandas, Polars, cloud execution, UI, streaming, stateful sink/idempotency, or load-testing support is claimed for v0.1.
- A configured invariant is an assertion about the user's intended semantics; a passing run only means sampled generated inputs did not violate those assertions. It cannot establish that every possible input is safe.
- Output collection is bounded by the user's transformation, not by an enforced output-row limit; a transformation that expands a small input dramatically can exhaust local resources.
- The audit exercised one Windows/Python 3.13/Java 17 environment. Cross-platform and the remaining declared Python versions need hosted CI or equivalent execution before broad compatibility claims are confirmed.

