from __future__ import annotations

from datetime import datetime, date, timezone
from typing import List, Dict, Any
from lxml import etree

NS = "urn:iso:std:iso:20022:tech:xsd:camt.052.001.08"
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


def generate_camt052(stmt_date: date, entries: List[Dict[str, Any]], window: str | None = None) -> bytes:
    """
    Minimal camt.052 intraday report for a date and optional time window (HH:MM-HH:MM UTC).
    Each entry expects: { id, reference, amount, currency, created_at }
    """
    root = etree.Element("Document", nsmap=NSMAP)
    rpt = _elm(root, "BkToCstmrAcctRpt")

    grp = _elm(rpt, "GrpHdr")
    _elm(grp, "MsgId", f"c052-{stmt_date.isoformat()}")
    _elm(grp, "CreDtTm", _iso_dt(datetime.utcnow()))

    r = _elm(rpt, "Rpt")
    _elm(r, "Id", f"rpt-{stmt_date.isoformat()}")
    if window:
        _elm(r, "FrToDt")
        _elm(r, "AddtlRptInf", f"window={window}")

    for e in entries:
        ntry = _elm(r, "Ntry")
        amt = str(e.get("amount"))
        ccy = str(e.get("currency") or "FLR")
        _elm(ntry, "Amt", amt, {"Ccy": ccy})
        _elm(ntry, "CdtDbtInd", "CRDT")
        ntry_dtls = _elm(ntry, "NtryDtls")
        txdtls = _elm(ntry_dtls, "TxDtls")
        refs = _elm(txdtls, "Refs")
        _elm(refs, "EndToEndId", str(e.get("id")))
        _elm(refs, "TxId", str(e.get("reference")))

    xml = etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8", standalone="yes")
    return xml
