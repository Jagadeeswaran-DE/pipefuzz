"""Hypothesis-driven execution of real PySpark transformations."""

from __future__ import annotations

import secrets
import traceback as traceback_module
from pathlib import Path

import hypothesis
from hypothesis import HealthCheck, given, seed as hypothesis_seed, settings

from pipefuzz.errors import ConfigurationError
from pipefuzz.invariants import evaluate_invariants
from pipefuzz.models import (
    DatasetSnapshot,
    FailureDetails,
    GeneratedCase,
    InvariantResult,
    PipeFuzzConfig,
    RunResult,
    Transformation,
)
from pipefuzz.spark import create_input_dataframe, create_spark_session, snapshot_dataframe
from pipefuzz.strategies import case_strategy


class _CaseFailure(Exception):
    def __init__(self, details: FailureDetails, original_traceback: str | None = None):
        super().__init__(details.reason)
        self.details = details
        self.original_traceback = original_traceback


class _InvariantCaseFailure(_CaseFailure):
    pass


class _TransformationCaseFailure(_CaseFailure):
    pass


class _SparkCaseFailure(_CaseFailure):
    pass


def _schemas(config: PipeFuzzConfig) -> dict[str, list[dict[str, object]]]:
    return {
        name: [
            {"name": column.name, "type": column.type_name, "nullable": column.nullable}
            for column in input_config.schema
        ]
        for name, input_config in config.inputs.items()
    }


def _details(
    config: PipeFuzzConfig,
    case: GeneratedCase,
    reason: str,
    *,
    invariant: InvariantResult | None = None,
) -> FailureDetails:
    return FailureDetails(
        scenario=case.scenario,
        records=case.records,
        reason=reason,
        invariant=invariant.name if invariant else None,
        context=invariant.context if invariant else {},
        schemas=_schemas(config),
    )


def _execute_case(spark, transformation: Transformation, config: PipeFuzzConfig, case: GeneratedCase) -> None:
    try:
        dataframes = {
            name: create_input_dataframe(spark, input_config, case.records[name])
            for name, input_config in config.inputs.items()
        }
        input_snapshots = {
            name: DatasetSnapshot(
                dataframe.schema.jsonValue(),
                [dict(record) for record in case.records[name]],
            )
            for name, dataframe in dataframes.items()
        }
    except Exception as exc:
        raise _SparkCaseFailure(
            _details(config, case, f"Spark could not materialize generated inputs: {exc}"),
            traceback_module.format_exc(),
        ) from exc

    try:
        output = transformation(**dataframes)
        from pyspark.sql import DataFrame

        if not isinstance(output, DataFrame):
            raise TypeError("Transformation must return a pyspark.sql.DataFrame")
        output_snapshot = snapshot_dataframe(output)
        repeated_snapshot = None
        if case.scenario == "determinism" and any(
            invariant.type == "deterministic_output" for invariant in config.invariants
        ):
            repeated = transformation(**dataframes)
            if not isinstance(repeated, DataFrame):
                raise TypeError("Transformation must return a pyspark.sql.DataFrame")
            repeated_snapshot = snapshot_dataframe(repeated)
    except Exception as exc:
        raise _TransformationCaseFailure(
            _details(config, case, f"Transformation raised {type(exc).__name__}: {exc}"),
            traceback_module.format_exc(),
        ) from exc

    results = evaluate_invariants(
        config,
        input_snapshots,
        output_snapshot,
        repeated_snapshot,
        case.scenario,
    )
    for result in results:
        if not result.passed:
            raise _InvariantCaseFailure(
                _details(config, case, result.reason, invariant=result)
            )


def _result(
    classification: str,
    target: str,
    config_path: Path,
    seed: int,
    max_examples: int,
    generated_examples: int,
    scenarios: tuple[str, ...],
    *,
    failure: FailureDetails | None = None,
    error: str | None = None,
    traceback: str | None = None,
) -> RunResult:
    return RunResult(
        classification=classification,
        target=target,
        config_path=config_path,
        seed=seed,
        max_examples=max_examples,
        generated_examples=generated_examples,
        hypothesis_version=hypothesis.__version__,
        scenarios=scenarios,
        failure=failure,
        error=error,
        traceback=traceback,
    )


def run_fuzz(
    target: str,
    config_path: Path,
    config: PipeFuzzConfig,
    transformation: Transformation,
    *,
    max_examples: int = 10,
    seed: int | None = None,
    verbose: bool = False,
    spark_session=None,
) -> RunResult:
    run_seed = seed if seed is not None else secrets.randbits(63)
    generated_examples = 0
    owns_spark = spark_session is None
    if owns_spark:
        try:
            spark = create_spark_session(verbose)
        except Exception as exc:
            return _result(
                "SPARK_ERROR",
                target,
                config_path,
                run_seed,
                max_examples,
                0,
                config.scenarios,
                error=f"Could not start local Spark: {exc}",
                traceback=traceback_module.format_exc(),
            )
    else:
        spark = spark_session

    try:
        for scenario_index, scenario in enumerate(config.scenarios):
            strategy = case_strategy(config, scenario)

            def property_test(case: GeneratedCase) -> None:
                nonlocal generated_examples
                generated_examples += 1
                _execute_case(spark, transformation, config, case)

            wrapped = given(case=strategy)(property_test)
            wrapped = settings(
                max_examples=max_examples,
                deadline=None,
                database=None,
                suppress_health_check=(HealthCheck.too_slow,),
                report_multiple_bugs=False,
            )(wrapped)
            wrapped = hypothesis_seed(run_seed + scenario_index)(wrapped)
            try:
                wrapped()
            except _InvariantCaseFailure as exc:
                return _result(
                    "INVARIANT_VIOLATION",
                    target,
                    config_path,
                    run_seed,
                    max_examples,
                    generated_examples,
                    config.scenarios,
                    failure=exc.details,
                )
            except _TransformationCaseFailure as exc:
                return _result(
                    "TRANSFORMATION_EXCEPTION",
                    target,
                    config_path,
                    run_seed,
                    max_examples,
                    generated_examples,
                    config.scenarios,
                    failure=exc.details,
                    traceback=exc.original_traceback,
                )
            except _SparkCaseFailure as exc:
                return _result(
                    "SPARK_ERROR",
                    target,
                    config_path,
                    run_seed,
                    max_examples,
                    generated_examples,
                    config.scenarios,
                    failure=exc.details,
                    traceback=exc.original_traceback,
                )
            except ConfigurationError as exc:
                return _result(
                    "PIPEFUZZ_CONFIGURATION_ERROR",
                    target,
                    config_path,
                    run_seed,
                    max_examples,
                    generated_examples,
                    config.scenarios,
                    error=str(exc),
                    traceback=traceback_module.format_exc(),
                )
            except Exception as exc:
                return _result(
                    "PIPEFUZZ_INTERNAL_ERROR",
                    target,
                    config_path,
                    run_seed,
                    max_examples,
                    generated_examples,
                    config.scenarios,
                    error=f"Unexpected PipeFuzz failure: {type(exc).__name__}: {exc}",
                    traceback=traceback_module.format_exc(),
                )
        return _result(
            "PASSED",
            target,
            config_path,
            run_seed,
            max_examples,
            generated_examples,
            config.scenarios,
        )
    finally:
        if owns_spark:
            spark.stop()
