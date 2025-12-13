from __future__ import annotations

from typing import Any, Dict

# Thin wrapper to align with iso_messages API style.
# Delegates to existing app.iso.generate_pain001 implementation.
from .. import iso  # type: ignore


def generate_pain001(payload: Dict[str, Any]) -> bytes:
    """
    Delegate to app.iso.generate_pain001 using the provided payload.
    Expected keys (same as iso.generate_pain001):
      - id, reference, amount, currency, sender_wallet, receiver_wallet, created_at
    """
    return iso.generate_pain001(payload)
