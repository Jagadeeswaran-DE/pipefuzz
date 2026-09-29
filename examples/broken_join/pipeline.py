"""A deliberately unsafe dimension join used by PipeFuzz's real demo."""

from pyspark.sql import functions as F


def transform(orders, customers):
    return (
        orders.join(customers, "customer_id")
        .groupBy("country")
        .agg(F.sum("amount").alias("total_amount"))
    )

