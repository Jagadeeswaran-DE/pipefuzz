"""Semantic, order-independent comparison for small DataFrame snapshots."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pipefuzz.models import DatasetSnapshot


def _datetime_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def values_equal(left: Any, right: Any, rtol: float, atol: float) -> bool:
    if left is None or right is None:
        return left is right
    if isinstance(left, float) and isinstance(right, float):
        if math.isnan(left) or math.isnan(right):
            return math.isnan(left) and math.isnan(right)
        if math.isinf(left) or math.isinf(right):
            return left == right
        return math.isclose(left, right, rel_tol=rtol, abs_tol=atol)
    if isinstance(left, Decimal) or isinstance(right, Decimal):
        return isinstance(left, Decimal) and isinstance(right, Decimal) and left == right
    if isinstance(left, datetime) and isinstance(right, datetime):
        return _datetime_utc(left) == _datetime_utc(right)
    if hasattr(left, "asDict") and hasattr(right, "asDict"):
        return values_equal(left.asDict(recursive=True), right.asDict(recursive=True), rtol, atol)
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            values_equal(left[key], right[key], rtol, atol) for key in left
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            values_equal(a, b, rtol, atol) for a, b in zip(left, right, strict=True)
        )
    return type(left) is type(right) and left == right


def snapshots_equal(
    left: DatasetSnapshot,
    right: DatasetSnapshot,
    rtol: float = 1e-9,
    atol: float = 1e-12,
) -> bool:
    if left.schema != right.schema or len(left.rows) != len(right.rows):
        return False

    matched_left: list[int | None] = [None] * len(right.rows)

    def find_match(left_index: int, seen: set[int]) -> bool:
        for right_index, candidate in enumerate(right.rows):
            if right_index in seen or not values_equal(
                left.rows[left_index], candidate, rtol, atol
            ):
                continue
            seen.add(right_index)
            previous = matched_left[right_index]
            if previous is None or find_match(previous, seen):
                matched_left[right_index] = left_index
                return True
        return False

    for left_index in range(len(left.rows)):
        if not find_match(left_index, set()):
            return False
    return True
