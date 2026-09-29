def transform(events):
    return events.selectExpr("id", "value AS required_value")

