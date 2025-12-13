from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from lxml import etree

# Minimal camt.029.001.x Resolution of Investigation
NS = "urn:iso:std:iso:20022:tech:xsd:camt.029.001.09"
NSMAP = {None: NS}


def _iso_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_camt029(original: Dict[str, Any], resolution_id: str, resolution_code: Optional[str] = None) -> bytes:
    """
    Build a minimal Resolution of Investigation (camt.029) referencing a prior instruction.
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
    msg = etree.SubElement(root, "RsltnOfInvstgtn")

    # Group Header
    grp = etree.SubElement(msg, "GrpHdr")
    etree.SubElement(grp, "MsgId").text = resolution_id
    etree.SubElement(grp, "CreDtTm").text = _iso_dt(created_at)

    # Original Group/Case identification
    orgnl = etree.SubElement(msg, "OrgnlGrpInf")
    etree.SubElement(orgnl, "OrgnlMsgId").text = reference or orig_id

    # Resolution details (simplified)
    rslt = etree.SubElement(msg, "RsltnRltdInf")
    etree.SubElement(rslt, "CxlPrcgSts").text = "CANC"  # generic resolution status for cancel path

    if resolution_code:
        add = etree.SubElement(msg, "AddtlInf")
        add.text = resolution_code

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8", standalone="yes")
