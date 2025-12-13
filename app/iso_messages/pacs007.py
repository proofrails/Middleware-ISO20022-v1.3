from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from lxml import etree

# Minimal pacs.007.001.x FIToFIPaymentReversal
NS = "urn:iso:std:iso:20022:tech:xsd:pacs.007.001.10"
NSMAP = {None: NS}


def _iso_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_pacs007(original: Dict[str, Any], reversal_id: str, reason_code: str | None = None) -> bytes:
    """
    Create a minimal FI-to-FI payment reversal referencing a prior instruction.
    Consumes best-effort fields:
      - id, reference, amount, currency, sender_wallet, receiver_wallet, created_at
    """
    rid = str(original.get("id", ""))
    reference = str(original.get("reference", ""))
    amount = str(original.get("amount", ""))
    currency = str(original.get("currency", ""))
    debtor = str(original.get("sender_wallet", ""))
    creditor = str(original.get("receiver_wallet", ""))
    created_at = original.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = datetime.utcnow().replace(tzinfo=timezone.utc)

    root = etree.Element("Document", nsmap=NSMAP)
    msg = etree.SubElement(root, "FIToFIPmtRvsl")

    # Group header
    grp = etree.SubElement(msg, "GrpHdr")
    etree.SubElement(grp, "MsgId").text = reversal_id
    etree.SubElement(grp, "CreDtTm").text = _iso_dt(created_at)

    # Original group info
    ogi = etree.SubElement(msg, "OrgnlGrpInf")
    etree.SubElement(ogi, "OrgnlMsgId").text = reference or rid

    # Reversal tx info (single)
    rvsl = etree.SubElement(msg, "TxInf")
    pmt_id = etree.SubElement(rvsl, "PmtId")
    etree.SubElement(pmt_id, "EndToEndId").text = reference or rid

    amt = etree.SubElement(rvsl, "IntrBkSttlmAmt")
    amt.attrib["Ccy"] = currency or "XXX"
    amt.text = amount or "0"

    # Debtor/Creditor placeholders
    dbtr = etree.SubElement(rvsl, "Dbtr")
    etree.SubElement(dbtr, "Nm").text = f"DEBTOR_{debtor[:12]}"
    cdtr = etree.SubElement(rvsl, "Cdtr")
    etree.SubElement(cdtr, "Nm").text = f"CREDITOR_{creditor[:12]}"

    # Reason
    if reason_code:
        rsn = etree.SubElement(rvsl, "Rsn")
        etree.SubElement(rsn, "Cd").text = reason_code

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8", standalone="yes")
