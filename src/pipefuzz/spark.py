"""Local SparkSession lifecycle and DataFrame materialization."""

from __future__ import annotations

import os
import sys
from typing import Any

from pipefuzz.models import DatasetSnapshot, InputConfig
from pipefuzz.schema import to_spark_schema


def create_spark_session(verbose: bool = False):
    # Spark defaults to ``python3`` on some Windows installations. Bind both
    # processes to the interpreter that is actually running PipeFuzz.
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

    import pyspark
    from pyspark.sql import SparkSession

    os.environ.setdefault("SPARK_HOME", os.path.dirname(pyspark.__file__))

    spark = (
        SparkSession.builder.master("local[2]")
        .appName("PipeFuzz")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.local.dir", os.path.abspath(".pipefuzz/spark-local"))
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .config("spark.pyspark.python", sys.executable)
        .config("spark.pyspark.driver.python", sys.executable)
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("INFO" if verbose else "WARN")
    return spark


def create_input_dataframe(spark, input_config: InputConfig, records: list[dict[str, Any]]):
    return spark.createDataFrame(records, schema=to_spark_schema(input_config))


def snapshot_dataframe(dataframe) -> DatasetSnapshot:
    rows = [row.asDict(recursive=True) for row in dataframe.collect()]
    return DatasetSnapshot(dataframe.schema.jsonValue(), rows)
