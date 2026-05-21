"""
Browser-safe JSON for SSE: Python's json.dumps emits NaN/Infinity tokens that
JavaScript JSON.parse rejects (RFC 8259).
"""
from __future__ import annotations

import json
import math
import numbers
from typing import Any


def sanitize_for_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, numbers.Integral):
        return int(obj)
    if isinstance(obj, numbers.Real):
        v = float(obj)
        return None if not math.isfinite(v) else v
    return obj


def sse_json_dumps(obj: Any) -> str:
    return json.dumps(sanitize_for_json(obj), ensure_ascii=False, allow_nan=False)
