import json
from datetime import datetime, timezone
from typing import Any


def json_default(value: Any):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def json_text(value: Any) -> str:
    return json.dumps(value, default=json_default)


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.10g}" for value in values) + "]"
