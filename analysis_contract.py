"""Shared execution contract for historical and live validation."""
from __future__ import annotations

HORIZONS = (5, 20, 60)


def holding_exit_index(entry_index: int, horizon: int) -> int:
    """Return the close index after exactly horizon trading sessions.

    Entry occurs at the open of entry_index and counts as session one,
    so a 5D holding period exits at the close of entry_index + 4.
    """
    if horizon not in HORIZONS:
        raise ValueError(f"Unsupported horizon: {horizon}")
    if entry_index < 0:
        raise ValueError("entry_index must be non-negative")
    return entry_index + horizon - 1
