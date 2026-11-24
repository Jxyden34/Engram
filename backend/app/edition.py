"""The edition is baked into an image; customers cannot select it in Settings."""
from pathlib import Path


def get_edition() -> str:
    marker = Path(__file__).with_name("EDITION")
    value = marker.read_text().strip() if marker.exists() else "community"
    if value not in {"community", "commercial"}:
        raise RuntimeError("Invalid Engram build edition")
    return value
