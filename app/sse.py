from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Tuple, Optional


class _SSEHub:
    """
    Very simple in-memory pub/sub hub for SSE per receipt_id.
    Not intended for multi-process scaling (PoC).
    """
    def __init__(self) -> None:
        # Map receipt_id -> list of subscriber queues
        self._subs: Dict[str, List[asyncio.Queue[str]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, rid: str) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subs.setdefault(rid, []).append(q)
        return q

    async def unsubscribe(self, rid: str, q: asyncio.Queue[str]) -> None:
        async with self._lock:
            lst = self._subs.get(rid, [])
            if q in lst:
                lst.remove(q)
            if not lst and rid in self._subs:
                del self._subs[rid]

    async def publish(self, rid: str, payload: dict) -> None:
        data = json.dumps(payload, separators=(",", ":"))
        async with self._lock:
            lst = list(self._subs.get(rid, []))
        # Put without blocking; drop if queue is full
        for q in lst:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                # best-effort: drop message for this slow consumer
                pass


hub = _SSEHub()


def format_sse_event(event: str, data: str) -> str:
    """
    Format an SSE event string.
    """
    # Ensure no bare CRLF in data (split lines)
    lines = data.splitlines() or [data]
    out = []
    if event:
        out.append(f"event: {event}")
    for ln in lines:
        out.append(f"data: {ln}")
    out.append("")  # end of event
    return "\n".join(out) + "\n"


async def stream_events(rid: str):
    """
    Async generator yielding SSE events for a given receipt id.
    Sends periodic comments as keepalive.
    """
    q = await hub.subscribe(rid)
    try:
        # initial keepalive to establish stream
        yield b": ok\n\n"
        while True:
            try:
                # wait for either new message or timeout for keepalive
                msg = await asyncio.wait_for(q.get(), timeout=25.0)
                evt = format_sse_event("update", msg)
                yield evt.encode("utf-8")
            except asyncio.TimeoutError:
                # keepalive
                yield b": ping\n\n"
    finally:
        await hub.unsubscribe(rid, q)
