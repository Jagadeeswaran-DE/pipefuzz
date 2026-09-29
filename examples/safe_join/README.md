# Safe join example

This transformation deduplicates the customer dimension by `customer_id` before joining. PipeFuzz supplies the same family of adversarial duplicate dimension keys as the broken example, but the output amount is not amplified.

```bash
pipefuzz test examples/safe_join/pipeline.py::transform \
  --config examples/safe_join/pipefuzz.yaml
```

