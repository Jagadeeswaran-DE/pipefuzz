"""A join that protects its many-to-one dimension contract."""

from pyspark.sql import functions as F


def transform(orders, customers):
    unique_customers = customers.dropDuplicates(["customer_id"])
    return (
        orders.join(unique_customers, "customer_id")
        .groupBy("country")
        .agg(F.sum("amount").alias("total_amount"))
    )

