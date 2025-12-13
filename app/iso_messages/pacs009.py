from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from lxml import etree

# Minimal pacs.009.001.x FinancialInstitutionCreditTransfer
NS = "urn:iso:std:iso:20022:tech:xsd:pacs.009.001.10"
NSMAP = {None: NS}


def _iso_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_pacs009(payload: Dict[str, Any]) -> bytes:
    """
    Create a minimal FI-to-FI credit transfer (institution to institution).
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
    msg = etree.SubElement(root, "FICdtTrf")

    # Group Header
    grp = etree.SubElement(msg, "GrpHdr")
    etree.SubElement(grp, "MsgId").text = f"pacs009-{rid}"
    etree.SubElement(grp, "CreDtTm").text = _iso_dt(created_at)

    # Credit transfer transaction information (single)
    cdt = etree.SubElement(msg, "CdtTrfTxInf")

    # Payment ID
    pmt_id = etree.SubElement(cdt, "PmtId")
    etree.SubElement(pmt_id, "InstrId").text = reference or rid
    etree.SubElement(pmt_id, "EndToEndId").text = reference or rid

    # Amount
    amt = etree.SubElement(cdt, "IntrBkSttlmAmt")
    amt.attrib["Ccy"] = currency or "XXX"
    amt.text = amount or "0"

    # Debtor/Creditor agents/parties (placeholder mapping using wallet strings)
    dbtr_agt = etree.SubElement(cdt, "DbtrAgt")
    fin_instn = etree.SubElement(dbtr_agt, "FinInstnId")
    etree.SubElement(fin_instn, "Nm").text = f"DEBTOR_AGENT_{debtor[:12]}"

    cdtr_agt = etree.SubElement(cdt, "CdtrAgt")
    fin_instn2 = etree.SubElement(cdtr_agt, "FinInstnId")
    etree.SubElement(fin_instn2, "Nm").text = f"CREDITOR_AGENT_{creditor[:12]}"

    # Supplementary info
    sup = etree.SubElement(cdt, "SplmtryData")
    envlp = etree.SubElement(sup, "Envlp")
    add = etree.SubElement(envlp, "AddtlData")
    add.text = f"rid={rid}, ref={reference}"

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8", standalone="yes")
