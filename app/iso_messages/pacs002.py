from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from lxml import etree

# Minimal pacs.002.001.x FIToFIPaymentStatusReport
NS = "urn:iso:std:iso:20022:tech:xsd:pacs.002.001.12"
NSMAP = {None: NS}


def _iso_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_pacs002(payload: Dict[str, Any]) -> bytes:
    """
    Create a minimal FIToFIPaymentStatusReport referencing a prior interbank instruction.
    Consumes best-effort fields from payload:
      - id, reference, status, created_at, anchored_at, flare_txid, bundle_hash
    """
    rid = str(payload.get("id", ""))
    reference = str(payload.get("reference", ""))
    status = str(payload.get("status", ""))
    created_at = payload.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = datetime.utcnow().replace(tzinfo=timezone.utc)

    root = etree.Element("Document", nsmap=NSMAP)
    msg = etree.SubElement(root, "FIToFIPmtStsRpt")

    # Group Header
    grp = etree.SubElement(msg, "GrpHdr")
    etree.SubElement(grp, "MsgId").text = f"pacs002-{rid}"
    etree.SubElement(grp, "CreDtTm").text = _iso_dt(created_at)

    # Original Group Info and Status
    ogi = etree.SubElement(msg, "OrgnlGrpInfAndSts")
    etree.SubElement(ogi, "OrgnlMsgId").text = reference or rid
    # Status code mapping (very simplified)
    st = etree.SubElement(ogi, "GrpSts")
    st.text = {
        "pending": "PDNG",
        "anchored": "ACSC",  # AcceptedSettlementCompleted (approximate)
        "failed": "RJCT",
    }.get(status, "PDNG")

    # Supplementary data (hashes/txids)
    sup = etree.SubElement(ogi, "SplmtryData")
    envlp = etree.SubElement(sup, "Envlp")
    add = etree.SubElement(envlp, "AddtlData")
    add.text = f"bundle_hash={payload.get('bundle_hash')}, flare_txid={payload.get('flare_txid')}"

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8", standalone="yes")
