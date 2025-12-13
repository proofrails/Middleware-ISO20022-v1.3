from __future__ import annotations

from datetime import datetime, date, timezone
from typing import List, Dict, Any
from lxml import etree

NS = "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"
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


def generate_camt053(stmt_date: date, entries: List[Dict[str, Any]]) -> bytes:
    """
    Minimal camt.053 statement for a given date. Each entry expects:
    { id, reference, amount (str/Decimal), currency, created_at (datetime), sender_wallet, receiver_wallet }
    """
    root = etree.Element("Document", nsmap=NSMAP)
    stmt = _elm(root, "BkToCstmrStmt")

    grp = _elm(stmt, "GrpHdr")
    _elm(grp, "MsgId", f"c053-{stmt_date.isoformat()}")
    _elm(grp, "CreDtTm", _iso_dt(datetime.utcnow()))

    st = _elm(stmt, "Stmt")
    _elm(st, "Id", f"stmt-{stmt_date.isoformat()}")
    _elm(st, "FrToDt")
    _elm(st, "CreDtTm", _iso_dt(datetime.utcnow()))

    for e in entries:
        ntry = _elm(st, "Ntry")
        amt = str(e.get("amount"))
        ccy = str(e.get("currency") or "FLR")
        _elm(ntry, "Amt", amt, {"Ccy": ccy})
        _elm(ntry, "CdtDbtInd", "CRDT")
        _elm(ntry, "BookgDt")
        _elm(ntry, "ValDt")
        ntry_dtls = _elm(ntry, "NtryDtls")
        txdtls = _elm(ntry_dtls, "TxDtls")
        refs = _elm(txdtls, "Refs")
        _elm(refs, "EndToEndId", str(e.get("id")))
        _elm(refs, "TxId", str(e.get("reference")))

    xml = etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8", standalone="yes")
    return xml
