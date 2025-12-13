
# ISO 20022 Payments Middleware (PoC)

## 📌 Context

This middleware takes on-chain tips (from Capella on Flare/Coston), generates ISO 20022 XML, bundles evidence, and anchors a hash on Flare.  
It exposes an HTTP API for Capella and a web UI (served under `/web`) for browsing/verifying receipts.

---

## 🎯 Goals

- Generate ISO 20022 `pain.001.001.09` XML.
- Validate XML against official XSD schema.
- Create an evidence bundle (zip + checksum).
- Compute SHA-256 hash of bundle.
- Anchor hash on Flare (Coston testnet).
- Store receipt metadata in Postgres.
- Provide REST API for record/fetch/verify.
- Provide a web-based admin/dashboard UI for browsing and verifying receipts.

---

## 🛠️ Tech Stack

- **Python 3.11**
- **FastAPI + Uvicorn**
- **SQLAlchemy + PostgreSQL**
- **web3.py** (Flare anchoring)
- **lxml + xmlschema** (ISO XML generation + validation)
- **hashlib, pynacl** (hashing, signatures)
- **Docker Compose** (for DB + API + UI stack)

---

## 📂 Repo Layout

```

middleware/
├─ app/
│  ├─ main.py
│  ├─ models.py
│  ├─ schemas.py
│  ├─ db.py
│  ├─ iso.py
│  ├─ bundle.py
│  ├─ anchor.py
│  ├─ sse.py
│  └─ utils.py (internal helpers)
├─ web/
│  ├─ index.html (public dashboard + API key creation)
│  ├─ project.html (per-project dashboard)
│  ├─ verify.html (bundle verification)
│  ├─ statements.html (camt.052/053 generation)
│  └─ assets (styles.css, app.js)
├─ ui/ (full receipt page)
├─ embed/ (embed receipt widget)
├─ requirements.txt
├─ docker-compose.yml
└─ README.md

````

---

## 📊 Database Schema

**Table: receipts**

| Column          | Type        | Notes                       |
|-----------------|-------------|-----------------------------|
| id              | UUID (PK)   | Receipt ID                  |
| reference       | text        | capella:tip:<id>            |
| tip_tx_hash     | text        | Flare transaction hash      |
| chain           | text        | "flare" / "coston"          |
| amount          | numeric     | tip amount                  |
| currency        | text        | "FLR"                       |
| sender_wallet   | text        | tip sender address          |
| receiver_wallet | text        | tip receiver address        |
| status          | text        | pending/anchored/failed     |
| bundle_hash     | text        | SHA-256 of evidence.zip     |
| flare_txid      | text        | Anchor transaction hash     |
| created_at      | timestamptz | Default now()               |
| anchored_at     | timestamptz | Nullable                    |

---

## 🔌 API

### POST `/v1/iso/record-tip`

Request:
```json
{
  "tip_tx_hash": "0xabc...",
  "chain": "coston",
  "amount": "10.5",
  "currency": "FLR",
  "sender_wallet": "0xSENDER",
  "receiver_wallet": "0xRECEIVER",
  "reference": "capella:tip:1234"
}
````

Response:

```json
{
  "receipt_id": "uuid",
  "status": "pending"
}
```

---

### GET `/v1/iso/receipts/{id}`

Response:

```json
{
  "id": "uuid",
  "status": "anchored",
  "bundle_hash": "0xabc...",
  "flare_txid": "0xdef...",
  "xml_url": "/files/<id>/pain001.xml",
  "bundle_url": "/files/<id>/evidence.zip",
  "created_at": "2025-10-01T12:00:00Z"
}
```

---

### POST `/v1/iso/verify`

Request:

```json
{ "bundle_url": "http://.../evidence.zip" }
```

Response:

```json
{
  "matches_onchain": true,
  "bundle_hash": "0xabc...",
  "flare_txid": "0xdef...",
  "anchored_at": "2025-10-01T12:34:56Z"
}
```

---

## 🧩 Core Modules

### `app/iso.py` (ISO XML with schema validation)

```python
from lxml import etree
import xmlschema
from pathlib import Path

SCHEMA_PATH = Path("schemas/pain.001.001.09.xsd")
schema = xmlschema.XMLSchema(SCHEMA_PATH)

def generate_pain001(receipt):
    root = etree.Element("Document", nsmap={None: "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"})
    pmt = etree.SubElement(root, "CstmrCdtTrfInitn")
    hdr = etree.SubElement(pmt, "GrpHdr")
    etree.SubElement(hdr, "MsgId").text = receipt["reference"]
    etree.SubElement(hdr, "CreDtTm").text = receipt["created_at"].isoformat()

    tx = etree.SubElement(pmt, "PmtInf")
    etree.SubElement(tx, "Dbtr").text = receipt["sender_wallet"]
    etree.SubElement(tx, "Cdtr").text = receipt["receiver_wallet"]
    amt = etree.SubElement(tx, "InstdAmt", Ccy=receipt["currency"])
    amt.text = str(receipt["amount"])

    xml_bytes = etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8")

    # validate
    schema.validate(xml_bytes)

    return xml_bytes
```

---

### `app/anchor.py` (real Flare anchoring)

#### Smart Contract (Solidity)

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract EvidenceAnchor {
    event EvidenceAnchored(bytes32 bundleHash, address indexed sender, uint256 ts);

    function anchorEvidence(bytes32 bundleHash) external {
        emit EvidenceAnchored(bundleHash, msg.sender, block.timestamp);
    }
}
```

Deploy this contract to Coston2 testnet.

#### Python anchoring (`web3.py`)

```python
from web3 import Web3
import json, os

FLARE_RPC = os.getenv("FLARE_RPC_URL", "https://coston-api.flare.network/ext/bc/C/rpc")
PRIVATE_KEY = os.getenv("ANCHOR_PRIVATE_KEY")
CONTRACT_ADDR = os.getenv("ANCHOR_CONTRACT_ADDR")
ABI_PATH = "contracts/EvidenceAnchor.abi.json"

w3 = Web3(Web3.HTTPProvider(FLARE_RPC))
acct = w3.eth.account.from_key(PRIVATE_KEY)
with open(ABI_PATH) as f: ABI = json.load(f)

contract = w3.eth.contract(address=CONTRACT_ADDR, abi=ABI)

def anchor_bundle(bundle_hash_hex: str):
    bundle_bytes32 = Web3.to_bytes(hexstr=bundle_hash_hex)
    tx = contract.functions.anchorEvidence(bundle_bytes32).build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 200000,
        "gasPrice": w3.eth.gas_price
    })
    signed = acct.sign_transaction(tx)
    txid = w3.eth.send_raw_transaction(signed.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(txid)
    return txid.hex(), receipt["blockNumber"]
```

---

### `app/main.py` (using validation + real anchoring)

```python
from fastapi import FastAPI
from uuid import uuid4
from datetime import datetime
from . import iso, bundle, anchor

app = FastAPI()
db = {}

@app.post("/v1/iso/record-tip")
def record_tip(payload: dict):
    rid = str(uuid4())
    receipt = {**payload, "id": rid, "status": "pending", "created_at": datetime.utcnow()}

    xml = iso.generate_pain001(receipt)
    zip_path, bundle_hash = bundle.create_bundle(receipt, xml)
    receipt["bundle_hash"] = bundle_hash

    txid, block = anchor.anchor_bundle(bundle_hash)
    receipt["flare_txid"] = txid
    receipt["status"] = "anchored"
    receipt["anchored_at"] = datetime.utcnow()

    db[rid] = receipt
    return {"receipt_id": rid, "status": receipt["status"]}

@app.get("/v1/iso/receipts/{rid}")
def get_receipt(rid: str):
    return db[rid]
```

---

## � Testing Locally

1. Run API:

   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
2. Submit tip:

   ```bash
   curl -X POST http://localhost:8000/v1/iso/record-tip \
   -H "Content-Type: application/json" \
   -d '{"tip_tx_hash":"0xabc","chain":"coston","amount":"10","currency":"FLR","sender_wallet":"0xS","receiver_wallet":"0xR","reference":"demo:tip:1"}'
   ```

Check:

* XML is valid against `pain.001.001.09.xsd`.
* Bundle hash appears on Coston testnet via Flare explorer.
* Web UI (under `/web`) fetches and verifies.

---

## 🔗 Integration with Capella

* Capella adds proxy route `/api/iso/record-tip`.
* Calls middleware after tip success.
* Displays receipt download/verify links.

---
