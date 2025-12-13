from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from lxml import etree

# Minimal pain.007.001.x Customer Payment Cancellation Request
# Pragmatic artifact to request cancellation of a previously submitted instruction (pain.001)
NS = "urn:iso:std:iso:20022:tech:xsd:pain.007.001.09"
NSMAP = {None: NS}


def _iso_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_pain007(original: Dict[str, Any], cancel_id: str, reason_code: str | None = None) -> bytes:
    """
    Create a minimal Customer Payment Cancellation Request:
    - GrpHdr/MsgId = cancel_id
    - OrgnlGrpInf/OrgnlMsgId = original.reference
    - OrgnlPmtInf/OrgnlEndToEndId = original.id
    - CxlRsnInf/Rsn/Cd = reason_code (optional)
    """
    reference = str(original.get("reference"))
    orig_id = str(original.get("id"))
    created_at = original.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = datetime.utcnow().replace(tzinfo=timezone.utc)

    root = etree.Element("Document", nsmap=NSMAP)
    msg = etree.SubElement(root, "CstmrPmtCxlReq")

    hdr = etree.SubElement(msg, "GrpHdr")
    etree.SubElement(hdr, "MsgId").text = cancel_id
    etree.SubElement(hdr, "CreDtTm").text = _iso_dt(created_at)

    ogi = etree.SubElement(msg, "OrgnlGrpInf")
    etree.SubElement(ogi, "OrgnlMsgId").text = reference

    opi = etree.SubElement(msg, "OrgnlPmtInf")
    etree.SubElement(opi, "OrgnlEndToEndId").text = orig_id

    if reason_code:
        cr = etree.SubElement(msg, "CxlRsnInf")
        rsn = etree.SubElement(cr, "Rsn")
        etree.SubElement(rsn, "Cd").text = reason_code

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8", standalone="yes")
