from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from lxml import etree

# Minimal remt.001.001.x Remittance Information message
# Pragmatic structure to carry remittance data separate from the payment.
NS = "urn:iso:std:iso:20022:tech:xsd:remt.001.001.05"
NSMAP = {None: NS}


def _iso_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_remt001(payload: Dict[str, Any]) -> bytes:
    """
    Create a minimal Remittance Information message.
    Fields consumed from payload dict (best-effort if missing):
      - id, reference, amount, currency, sender_wallet, receiver_wallet, created_at
    """
    rid = str(payload.get("id", ""))
    reference = str(payload.get("reference", ""))
    amount = str(payload.get("amount", ""))
    currency = str(payload.get("currency", ""))
    debtor = str(payload.get("sender_wallet", ""))
    creditor = str(payload.get("receiver_wallet", ""))
    created_at = payload.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = datetime.utcnow().replace(tzinfo=timezone.utc)

    # XML
    root = etree.Element("Document", nsmap=NSMAP)
    remt = etree.SubElement(root, "RmtInf")

    # Identification and creation time
    id_el = etree.SubElement(remt, "Id")
    etree.SubElement(id_el, "InstrId").text = rid or reference or _iso_dt(created_at)

    # Structured remittance details
    strd = etree.SubElement(remt, "Strd")
    rfrd = etree.SubElement(strd, "RfrdDocInf")

    # Use reference in a generic doc identification
    doc_id = etree.SubElement(rfrd, "Tp")
    cd_or_prtry = etree.SubElement(doc_id, "CdOrPrtry")
    etree.SubElement(cd_or_prtry, "Prtry").text = "REFERENCE"

    rfrd_id = etree.SubElement(rfrd, "Nb")
    rfrd_id.text = reference

    # Additional remittance info (free text compatible with bank-safe policies)
    add_rem = etree.SubElement(strd, "AddtlRmtInf")
    add_rem.text = f"RID={rid} AMT={amount} {currency} FROM={debtor} TO={creditor}"

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8", standalone="yes")
