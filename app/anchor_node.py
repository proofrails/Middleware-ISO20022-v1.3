from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Optional, Tuple

from dotenv import load_dotenv

from .schemas import ChainMatch

# Load .env so FLARE_RPC_URL and ANCHOR_CONTRACT_ADDR are available for Node scripts
load_dotenv()


def _parse_iso_utc(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    # Node uses toISOString() which appends 'Z' for UTC
    try:
        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _node_env() -> dict:
    env = os.environ.copy()
    # Normalize env var names for Node scripts
    rpc = os.getenv("FLARE_RPC_URL") or os.getenv("RPC_URL")
    addr = os.getenv("ANCHOR_CONTRACT_ADDR") or os.getenv("CONTRACT_ADDR")
    pk = os.getenv("ANCHOR_PRIVATE_KEY") or os.getenv("PRIVATE_KEY")

    if rpc:
        env["FLARE_RPC_URL"] = rpc
        env["RPC_URL"] = rpc
    if addr:
        env["ANCHOR_CONTRACT_ADDR"] = addr
        env["CONTRACT_ADDR"] = addr
    if pk:
        # Ensure 0x prefix and strip whitespace
        pk_norm = pk.strip()
        if not pk_norm.startswith("0x"):
            pk_norm = "0x" + pk_norm
        pk_norm = "".join(pk_norm.split())
        env["ANCHOR_PRIVATE_KEY"] = pk_norm
        env["PRIVATE_KEY"] = pk_norm
    return env


def _run_node(args: list[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        env=_node_env(),
        cwd=os.getcwd(),
        shell=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def anchor_bundle(bundle_hash_hex: str) -> Tuple[str, int]:
    """
    Anchors the bundle hash using Node script (scripts/anchor.js).
    Requires env: FLARE_RPC_URL, ANCHOR_CONTRACT_ADDR, ANCHOR_PRIVATE_KEY.
    Returns (txid_hex, blockNumber).
    """
    if not isinstance(bundle_hash_hex, str) or not bundle_hash_hex.startswith("0x") or len(bundle_hash_hex) != 66:
        raise ValueError("bundle_hash must be 0x-prefixed 32-byte hex")

    code, out, err = _run_node(["node", "scripts/anchor.js", bundle_hash_hex])
    if code != 0:
        raise RuntimeError(f"node anchor failed: {err or out}")

    try:
        data = json.loads(out)
        txid = data.get("txid")
        block_number = int(data.get("blockNumber")) if data.get("blockNumber") is not None else 0
        if not txid:
            raise ValueError("missing txid in node output")
        return txid, block_number
    except Exception as e:
        raise RuntimeError(f"invalid node anchor output: {e}; raw={out}") from e


def find_anchor(bundle_hash_hex: str) -> ChainMatch:
    """
    Looks up the EvidenceAnchored event using Node script (scripts/find.js).
    Requires env: FLARE_RPC_URL, ANCHOR_CONTRACT_ADDR.
    """
    if not isinstance(bundle_hash_hex, str) or not bundle_hash_hex.startswith("0x") or len(bundle_hash_hex) != 66:
        return ChainMatch(matches=False)

    code, out, err = _run_node(["node", "scripts/find.js", bundle_hash_hex])
    if code != 0:
        return ChainMatch(matches=False)

    try:
        data = json.loads(out)
        matches = bool(data.get("matches"))
        txid = data.get("txid") if matches else None
        anchored_at = _parse_iso_utc(data.get("anchored_at")) if matches else None
        return ChainMatch(matches=matches, txid=txid, anchored_at=anchored_at)
    except Exception:
        return ChainMatch(matches=False)
