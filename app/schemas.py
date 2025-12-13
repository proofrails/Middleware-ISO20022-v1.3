from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict


class Chain(str, Enum):
    coston2 = "coston2"
    flare = "flare"  # allow for future mainnet


class Status(str, Enum):
    pending = "pending"
    anchored = "anchored"
    failed = "failed"


class TipRecordRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    tip_tx_hash: str = Field(..., description="Blockchain transaction hash of the tip")
    chain: Chain = Field(..., description="Blockchain network")
    amount: Decimal = Field(..., description="Tip amount (use decimal string)")
    currency: str = Field(..., description='Currency code (PoC uses "FLR")')
    sender_wallet: str = Field(..., description="Sender wallet address (0x...)")
    receiver_wallet: str = Field(..., description="Receiver wallet address (0x...)")
    reference: str = Field(..., description="External reference, e.g., capella:tip:<id>")
    callback_url: Optional[str] = Field(None, description="Optional: Capella callback URL to notify when anchoring completes")


class RecordTipResponse(BaseModel):
    receipt_id: str
    status: Status


class ReceiptResponse(BaseModel):
    id: str
    status: Status
    bundle_hash: Optional[str] = None
    flare_txid: Optional[str] = None
    xml_url: Optional[str] = None
    bundle_url: Optional[str] = None
    created_at: datetime
    anchored_at: Optional[datetime] = None


from pydantic import BaseModel, Field, ConfigDict, model_validator
import re


class VerifyRequest(BaseModel):
    bundle_url: Optional[str] = Field(None, description="URL to evidence.zip")
    bundle_hash: Optional[str] = Field(
        None,
        description="0x-prefixed 32-byte hash (hex)",
    )

    @model_validator(mode="after")
    def _xor_inputs(self):
        has_url = bool(self.bundle_url)
        has_hash = bool(self.bundle_hash)
        if has_url == has_hash:
            raise ValueError("Provide exactly one of bundle_url or bundle_hash")
        if self.bundle_hash:
            s = self.bundle_hash.strip()
            if not re.match(r"^0x[0-9a-fA-F]{64}$", s):
                raise ValueError("Invalid bundle_hash format - must be 0x followed by 64 hex chars")
            # normalize to lowercase
            self.bundle_hash = "0x" + s[2:].lower()
        return self


class VerifyResponse(BaseModel):
    matches_onchain: bool
    bundle_hash: Optional[str] = None
    flare_txid: Optional[str] = None
    anchored_at: Optional[datetime] = None
    errors: List[str] = Field(default_factory=list)


# Helper internal results for modules
@dataclass
class VerificationResult:
    bundle_hash: str
    errors: list[str]


@dataclass
class ChainMatch:
    matches: bool
    txid: Optional[str] = None
    anchored_at: Optional[datetime] = None
