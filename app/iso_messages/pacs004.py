from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from lxml import etree

# Minimal FIToFIPaymentReturn (pacs.004.001.x-like structure)
# Pragmatic artifact to represent a return/refund linked to an original receipt.
NS = "urn:iso:std:iso:20022:tech:xsd:pacs.004.001.11"
NSMAP = {None: NS}


def _iso_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_pacs004(original: Dict[str, Any], refund_id: str, reason_code: str | None = None) -> bytes:
    """
    Create a minimal FIToFIPaymentReturn message:
    - GrpHdr/MsgId: refund_id
    - OrgnlGrpInf: OrgnlMsgId = original.reference
    - TxInf: OrgnlEndToEndId = original.id
    - RtrId = refund_id
    - RtrRsnInf/Rsn/Cd = reason_code if provided
    """
    reference = str(original.get("reference"))
    orig_id = str(original.get("id"))
    created_at = original.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = datetime.utcnow().replace(tzinfo=timezone.utc)

    root = etree.Element("Document", nsmap=NSMAP)
    msg = etree.SubElement(root, "FIToFIPmtRtr")

    grp = etree.SubElement(msg, "GrpHdr")
    etree.SubElement(grp, "MsgId").text = refund_id
    etree.SubElement(grp, "CreDtTm").text = _iso_dt(created_at)

    ogi = etree.SubElement(msg, "OrgnlGrpInf")
    etree.SubElement(ogi, "OrgnlMsgId").text = reference

    tx = etree.SubElement(msg, "TxInf")
    etree.SubElement(tx, "OrgnlEndToEndId").text = orig_id
    etree.SubElement(tx, "RtrId").text = refund_id

    if reason_code:
        rr = etree.SubElement(tx, "RtrRsnInf")
        rsn = etree.SubElement(rr, "Rsn")
        etree.SubElement(rsn, "Cd").text = reason_code

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8", standalone="yes")
