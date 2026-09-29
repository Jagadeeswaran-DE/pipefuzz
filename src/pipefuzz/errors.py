"""PipeFuzz exception hierarchy and process exit codes."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    OK = 0
    INVARIANT_VIOLATION = 1
    CONFIGURATION_ERROR = 2
    TRANSFORMATION_EXCEPTION = 3
    SPARK_ERROR = 4
    INTERNAL_ERROR = 5


class PipeFuzzError(Exception):
    """Base class for errors PipeFuzz can classify."""


class ConfigurationError(PipeFuzzError):
    """The target or configuration does not satisfy PipeFuzz's contract."""


class SparkExecutionError(PipeFuzzError):
    """Spark could not create or materialize PipeFuzz-managed data."""

