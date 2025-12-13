from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from lxml import etree

# Minimal camt.056.001.x FIToFIPaymentCancellationRequest
NS = "urn:iso:std:iso:20022:tech:xsd:camt.056.001.10"
NSMAP = {None: NS}


def _iso_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_camt056(original: Dict[str, Any], cancel_id: str, reason_code: Optional[str] = None) -> bytes:
    """
    Build a minimal FI-to-FI cancellation request (camt.056) referencing a prior instruction.
    Fields consumed from original dict:
      - id, reference, created_at
    """
    reference = str(original.get("reference"))
    orig_id = str(original.get("id"))
    created_at = original.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = datetime.utcnow().replace(tzinfo=timezone.utc)

    # Document root
    root = etree.Element("Document", nsmap=NSMAP)
    msg = etree.SubElement(root, "FIToFIPmtCxlReq")

    # Group Header
    grp = etree.SubElement(msg, "GrpHdr")
    etree.SubElement(grp, "MsgId").text = cancel_id
    etree.SubElement(grp, "CreDtTm").text = _iso_dt(created_at)

    # Underlying Cancellation Details
    undrlyg = etree.SubElement(msg, "Undrlyg")
    orgnl = etree.SubElement(undrlyg, "OrgnlGrpInf")
    etree.SubElement(orgnl, "OrgnlMsgId").text = reference or orig_id

    if reason_code:
        cxl = etree.SubElement(undrlyg, "CxlRsnInf")
        rsn = etree.SubElement(cxl, "Rsn")
        etree.SubElement(rsn, "Cd").text = reason_code

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8", standalone="yes")
