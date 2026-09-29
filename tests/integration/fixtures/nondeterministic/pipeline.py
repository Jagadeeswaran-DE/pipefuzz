import uuid

from pyspark.sql import functions as F


def transform(events):
    return events.withColumn("nonce", F.lit(str(uuid.uuid4())))

