from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any
from lxml import etree

NS = "urn:iso:std:iso:20022:tech:xsd:camt.054.001.09"
NSMAP = {None: NS}


def _iso_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _elm(parent, tag: str, text: str | None = None, attrib: dict | None = None):
    elem = etree.SubElement(parent, tag, attrib=attrib or {})
    if text is not None:
        elem.text = text
    return elem


def generate_camt054(payload: Dict[str, Any]) -> bytes:
    """
    Minimalistic camt.054 Debit/Credit Notification for a credited receipt.
    Expects keys: id, reference, amount (str), currency (str), sender_wallet, receiver_wallet, created_at (datetime)
    """
    rid = str(payload.get("id"))
    reference = str(payload.get("reference") or rid)
    amount = str(payload.get("amount"))
    currency = str(payload.get("currency") or "FLR")
    created_at = payload.get("created_at") or datetime.utcnow()

    root = etree.Element("Document", nsmap=NSMAP)
    dcn = _elm(root, "BkToCstmrDbtCdtNtfctn")

    grp = _elm(dcn, "GrpHdr")
    _elm(grp, "MsgId", f"c054-{rid}")
    _elm(grp, "CreDtTm", _iso_dt(created_at))

    ntf = _elm(dcn, "Ntfctn")
    _elm(ntf, "Id", f"ntf-{rid}")

    # One entry representing the credit
    ntry = _elm(ntf, "Ntry")
    _elm(ntry, "Amt", amount, {"Ccy": currency})
    _elm(ntry, "CdtDbtInd", "CRDT")
    _elm(ntry, "RvslInd", "false")

    ntry_dtls = _elm(ntry, "NtryDtls")
    txdtls = _elm(ntry_dtls, "TxDtls")
    refs = _elm(txdtls, "Refs")
    _elm(refs, "EndToEndId", rid)
    _elm(refs, "TxId", reference)

    rltdptys = _elm(txdtls, "RltdPties")
    dbtr = _elm(rltdptys, "Dbtr")
    _elm(dbtr, "Nm", payload.get("sender_wallet", "SENDER"))
    cdtr = _elm(rltdptys, "Cdtr")
    _elm(cdtr, "Nm", payload.get("receiver_wallet", "RECEIVER"))

    xml = etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8", standalone="yes")
    return xml
