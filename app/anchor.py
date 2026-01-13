from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple, Any, Dict, List

from eth_account import Account  # type: ignore
from eth_utils import to_checksum_address  # type: ignore
from hexbytes import HexBytes  # type: ignore
from web3 import Web3  # type: ignore
from web3.contract import Contract  # type: ignore
from web3.exceptions import ContractLogicError  # type: ignore

from .schemas import ChainMatch

logger = logging.getLogger(__name__)


# Environment/config
FLARE_RPC = os.getenv("FLARE_RPC_URL", "https://coston2-api.flare.network/ext/C/rpc")
PRIVATE_KEY = os.getenv("ANCHOR_PRIVATE_KEY")  # hex string 0x...
CONTRACT_ADDR = os.getenv("ANCHOR_CONTRACT_ADDR")  # 0x...
ABI_PATH = os.getenv("ANCHOR_ABI_PATH", "contracts/EvidenceAnchor.abi.json")
LOOKBACK_BLOCKS = int(os.getenv("ANCHOR_LOOKBACK_BLOCKS", "50000"))

# Minimal ABI fallback if file not provided.
# Matches: function anchorEvidence(bytes32 bundleHash)
#          event EvidenceAnchored(bytes32 bundleHash, address sender, uint256 ts)
FALLBACK_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": False, "internalType": "bytes32", "name": "bundleHash", "type": "bytes32"},
            {"indexed": True, "internalType": "address", "name": "sender", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "ts", "type": "uint256"},
        ],
        "name": "EvidenceAnchored",
        "type": "event",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "bundleHash", "type": "bytes32"}],
        "name": "anchorEvidence",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


_w3: Optional[Web3] = None
_contract: Optional[Contract] = None
_acct = None


def _hex32_from_prefixed(hex_str: str) -> bytes:
    if not isinstance(hex_str, str) or not hex_str.startswith("0x"):
        raise ValueError("bundle_hash must be 0x-prefixed hex string")
    hex_body = hex_str[2:]
    if len(hex_body) != 64:
        raise ValueError("bundle_hash must be 32-byte (64 hex chars)")
    return int(hex_body, 16).to_bytes(32, "big")


def _load_web3() -> Web3:
    global _w3
    if _w3 is None:
        _w3 = Web3(Web3.HTTPProvider(FLARE_RPC))
    return _w3


def _load_contract() -> Tuple[Web3, Contract]:
    global _contract, _acct
    w3 = _load_web3()

    # Load ABI
    abi: List[Dict[str, Any]]
    if ABI_PATH and Path(ABI_PATH).exists():
        import json

        abi = json.loads(Path(ABI_PATH).read_text())
    else:
        abi = FALLBACK_ABI

    if not CONTRACT_ADDR:
        raise RuntimeError("ANCHOR_CONTRACT_ADDR is not set")

    address = to_checksum_address(CONTRACT_ADDR)
    contract = w3.eth.contract(address=address, abi=abi)

    # Private key may be missing for read-only operations
    if PRIVATE_KEY:
        _acct = w3.eth.account.from_key(PRIVATE_KEY)

    _contract = contract
    return w3, contract


def _estimate_fees_eip1559(w3: Web3) -> Optional[Tuple[int, int]]:
    try:
        # Use fee_history to derive a reasonable tip
        history = w3.eth.fee_history(5, "latest", [10, 50, 90])
        base_fees = history["baseFeePerGas"]
        base = int(base_fees[-1])
        # Pick a conservative tip (2 gwei) or max priority from history
        tip = int(2e9)
        try:
            prio = history.get("reward", [])
            if prio and prio[-1]:
                # Use median (50th percentile)
                tip = max(tip, int(prio[-1][1]))
        except Exception:
            pass
        max_priority = tip
        # Max fee = base * 2 + tip (simple rule)
        max_fee = base * 2 + max_priority
        return max_fee, max_priority
    except Exception:
        return None


def _build_tx_anchor(
    w3: Web3, contract: Contract, from_addr: str, bundle_hash32: bytes
) -> Dict[str, Any]:
    func = contract.functions.anchorEvidence(bundle_hash32)
    # Start with a basic tx skeleton
    tx: Dict[str, Any] = {
        "from": from_addr,
        "nonce": w3.eth.get_transaction_count(from_addr, "pending"),
        "chainId": w3.eth.chain_id,
    }

    # Try EIP-1559
    fees = _estimate_fees_eip1559(w3)
    if fees:
        max_fee, max_priority = fees
        tx.update({"type": 2, "maxFeePerGas": max_fee, "maxPriorityFeePerGas": max_priority})
    else:
        # Fallback to legacy
        tx.update({"gasPrice": w3.eth.gas_price})

    # Gas estimate
    try:
        gas_est = func.estimate_gas({"from": from_addr})
        # Add a safety margin
        gas_est = int(gas_est * 1.2)
    except Exception:
        # Fallback fixed gas
        gas_est = 200_000

    tx.update({"gas": gas_est})

    built = func.build_transaction(tx)
    return built


def anchor_bundle(bundle_hash_hex: str) -> Tuple[str, int]:
    """
    Anchors the 32-byte bundle hash on-chain by calling anchorEvidence.
    Returns (txid_hex, blockNumber) after waiting for 1 confirmation.
    """
    if not PRIVATE_KEY:
        raise RuntimeError("ANCHOR_PRIVATE_KEY is not set")

    w3, contract = _load_contract()
    acct = w3.eth.account.from_key(PRIVATE_KEY)
    from_addr = acct.address

    bundle_hash32 = _hex32_from_prefixed(bundle_hash_hex)
    logger.info(f"Anchoring bundle hash: {bundle_hash_hex} from {from_addr}")

    # Retry loop for nonce/gas issues
    last_err = None
    for attempt in range(3):
        try:
            tx = _build_tx_anchor(w3, contract, from_addr, bundle_hash32)
            signed = acct.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
            logger.debug(f"Transaction sent: {tx_hash.hex()}, waiting for confirmation...")
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            if receipt and receipt.get("status", 1) == 1:
                logger.info(f"Bundle anchored: hash={bundle_hash_hex}, tx={tx_hash.hex()}, block={receipt['blockNumber']}")
                return tx_hash.hex(), receipt["blockNumber"]
            last_err = RuntimeError("Transaction failed with status != 1")
            logger.warning(f"Transaction failed with status != 1: {tx_hash.hex()}")
        except Exception as e:
            last_err = e
            logger.warning(f"Anchoring attempt {attempt + 1}/3 failed: {e}")
            # Small backoff and nonce bump
            time.sleep(1 + attempt)
    if last_err:
        logger.error(f"Failed to anchor bundle after 3 attempts: {last_err}")
        raise last_err  # propagate last error
    raise RuntimeError("Unknown error anchoring bundle")


def find_anchor(bundle_hash_hex: str) -> ChainMatch:
    """
    Attempts to find the EvidenceAnchored event for the given bundle hash.
    Returns ChainMatch(matches, txid?, anchored_at?).

    Improvements vs previous logic:
      - Uses explicit topic0 = keccak256("EvidenceAnchored(bytes32,address,uint256)")
      - Scans in chunks to avoid provider limits
      - Decodes bundleHash from log.data (not topics) and compares as bytes
    """
    try:
        w3, contract = _load_contract()
    except Exception as e:
        logger.debug(f"Failed to load contract for anchor lookup: {e}")
        return ChainMatch(matches=False)

    try:
        bundle_hash32 = _hex32_from_prefixed(bundle_hash_hex)
    except Exception as e:
        logger.debug(f"Invalid bundle hash format: {bundle_hash_hex}, error: {e}")
        return ChainMatch(matches=False)
    
    logger.debug(f"Looking up anchor for bundle hash: {bundle_hash_hex}")

    latest = w3.eth.block_number
    from_block = max(0, latest - LOOKBACK_BLOCKS)
    address = to_checksum_address(CONTRACT_ADDR)  # type: ignore

    # Explicit topic0 for EvidenceAnchored(bytes32,address,uint256)
    topic0 = Web3.keccak(text="EvidenceAnchored(bytes32,address,uint256)").hex()

    # Chunked scan to respect RPC limits
    chunk = int(os.getenv("ANCHOR_CHUNK_SIZE", "500"))
    end = latest
    while end >= from_block:
        start = max(from_block, end - chunk + 1)
        try:
            logs = w3.eth.get_logs({
                "fromBlock": start,
                "toBlock": end,
                "address": address,
                "topics": [topic0],
            })
        except Exception:
            # Provider may throttle; reduce chunk and continue
            chunk = max(50, chunk // 2)
            end = start - 1
            continue

        # Iterate newest-first within chunk
        for log in reversed(logs):
            try:
                decoded = contract.events.EvidenceAnchored().process_log(log)  # type: ignore
                ev_hash = decoded["args"].get("bundleHash")
                if isinstance(ev_hash, HexBytes):
                    ev_hash = bytes(ev_hash)
                if isinstance(ev_hash, bytes) and ev_hash == bundle_hash32:
                    tx_hash = log["transactionHash"].hex()
                    blk = w3.eth.get_block(log["blockNumber"])
                    ts = blk.get("timestamp")
                    anchored_at = datetime.fromtimestamp(ts, tz=timezone.utc) if isinstance(ts, int) else None
                    logger.info(f"Found anchor: hash={bundle_hash_hex}, tx={tx_hash}, block={log['blockNumber']}")
                    return ChainMatch(matches=True, txid=tx_hash, anchored_at=anchored_at)
            except Exception:
                continue

        end = start - 1

    logger.debug(f"No anchor found for bundle hash: {bundle_hash_hex}")
    return ChainMatch(matches=False)
