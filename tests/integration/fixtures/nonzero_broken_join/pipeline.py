"""A join bug that is exposed only for generated non-zero relationship keys."""

from pyspark.sql import functions as F


def transform(orders, customers):
    return (
        orders.filter(F.col("customer_id") != 0)
        .join(customers, "customer_id")
        .groupBy("country")
        .agg(F.sum("amount").alias("total_amount"))
    )
