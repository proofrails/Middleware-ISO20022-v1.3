from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from lxml import etree

# Minimal pacs.008.001.x FIToFICustomerCreditTransfer
NS = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.10"
NSMAP = {None: NS}


def _iso_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_pacs008(payload: Dict[str, Any]) -> bytes:
    """
    Create a minimal FI-to-FI Customer Credit Transfer initiation message.
    Consumes best-effort fields from payload:
      - id, reference, amount, currency, sender_wallet, receiver_wallet, created_at
    """
    rid = str(payload.get("id", ""))
    reference = str(payload.get("reference", ""))
    amount = str(payload.get("amount", ""))
    currency = str(payload.get("currency", ""))
    debtor = str(payload.get("sender_wallet", ""))
    creditor = str(payload.get("receiver_wallet", ""))
    created_at = payload.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = datetime.utcnow().replace(tzinfo=timezone.utc)

    # XML skeleton
    root = etree.Element("Document", nsmap=NSMAP)
    msg = etree.SubElement(root, "FIToFICstmrCdtTrf")

    # Group Header
    grp = etree.SubElement(msg, "GrpHdr")
    etree.SubElement(grp, "MsgId").text = f"pacs008-{rid}"
    etree.SubElement(grp, "CreDtTm").text = _iso_dt(created_at)

    # Credit transfer transaction information (single)
    cdt = etree.SubElement(msg, "CdtTrfTxInf")

    # Payment ID
    pmt_id = etree.SubElement(cdt, "PmtId")
    etree.SubElement(pmt_id, "EndToEndId").text = reference or rid

    # Amount
    amt = etree.SubElement(cdt, "IntrBkSttlmAmt")
    amt.attrib["Ccy"] = currency or "XXX"
    amt.text = amount or "0"

    # Debtor/Creditor agents/parties (placeholder mapping using wallet strings)
    dbtr = etree.SubElement(cdt, "Dbtr")
    etree.SubElement(dbtr, "Nm").text = f"DEBTOR_{debtor[:12]}"
    dbtr_acct = etree.SubElement(cdt, "DbtrAcct")
    id_el = etree.SubElement(dbtr_acct, "Id")
    etree.SubElement(id_el, "Othr").append(etree.Element("Id"))
    id_el_O = id_el.find("Othr")
    if id_el_O is not None:
        etree.SubElement(id_el_O, "Id").text = debtor

    cdtr = etree.SubElement(cdt, "Cdtr")
    etree.SubElement(cdtr, "Nm").text = f"CREDITOR_{creditor[:12]}"
    cdtr_acct = etree.SubElement(cdt, "CdtrAcct")
    id2 = etree.SubElement(cdtr_acct, "Id")
    etree.SubElement(id2, "Othr").append(etree.Element("Id"))
    id2_O = id2.find("Othr")
    if id2_O is not None:
        etree.SubElement(id2_O, "Id").text = creditor

    # Supplementary data for traceability
    sup = etree.SubElement(cdt, "SplmtryData")
    envlp = etree.SubElement(sup, "Envlp")
    add = etree.SubElement(envlp, "AddtlData")
    add.text = f"rid={rid}, ref={reference}"

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8", standalone="yes")
