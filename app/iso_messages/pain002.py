from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any
from lxml import etree

# Pragmatic pain.002.001.10-like structure (not strict XSD enforcement here)
NS = "urn:iso:std:iso:20022:tech:xsd:pain.002.001.10"
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


def generate_pain002(payload: Dict[str, Any]) -> bytes:
    """
    Minimal payment status report reflecting receipt processing outcome.
    Expects: id, reference, status (pending/anchored/failed), created_at, anchored_at?, flare_txid?
    """
    rid = str(payload.get("id"))
    reference = str(payload.get("reference") or rid)
    status = str(payload.get("status") or "pending").lower()
    created_at = payload.get("created_at") or datetime.utcnow()
    anchored_at = payload.get("anchored_at")
    txid = payload.get("flare_txid")

    root = etree.Element("Document", nsmap=NSMAP)
    rpt = _elm(root, "CstmrPmtStsRpt")

    grp = _elm(rpt, "GrpHdr")
    _elm(grp, "MsgId", f"p002-{rid}")
    _elm(grp, "CreDtTm", _iso_dt(datetime.utcnow()))
    _elm(grp, "InitgPty")

    org = _elm(rpt, "OrgnlGrpInfAndSts")
    _elm(org, "OrgnlMsgId", reference)
    _elm(org, "OrgnlMsgNmId", "pain.001.001.09")

    # Report status
    sts = _elm(org, "GrpSts", "ACCP" if status == "anchored" else ("RJCT" if status == "failed" else "ACTC"))

    # Optional reason/tx info
    if txid:
        inf = _elm(org, "StsRsnInf")
        rsn = _elm(inf, "Rsn")
        _elm(rsn, "Prtry", "ONCHAIN")
        _elm(inf, "AddtlInf", f"tx={txid}")

    xml = etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8", standalone="yes")
    return xml
