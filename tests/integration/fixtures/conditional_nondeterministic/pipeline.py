"""A nondeterministic result that is exposed only for generated non-zero IDs."""

from pyspark.sql import functions as F


def transform(events):
    return events.withColumn(
        "nonce",
        F.when(F.col("id") != 0, F.expr("uuid()")).otherwise(F.lit("stable")),
    )
