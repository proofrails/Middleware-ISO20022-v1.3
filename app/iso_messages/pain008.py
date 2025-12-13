from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional

from lxml import etree

# Minimalistic CustomerDirectDebitInitiation (pain.008) generator for demo/testing.
# This does NOT validate against an XSD here (no schema bundled).
# It mirrors wallet-based mapping used elsewhere and flips roles (debtor pays, creditor collects).

NS_PAIN008 = "urn:iso:std:iso:20022:tech:xsd:pain.008.001.08"
NSMAP = {None: NS_PAIN008}


def _iso_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z").replace("+0000", "Z")


def _iso_date(dt: datetime) -> str:
    return dt.date().isoformat()


def _elm(parent, tag: str, text: Optional[str] = None, attrib: Optional[Dict[str, str]] = None):
    if attrib is None:
        elem = etree.SubElement(parent, tag)
    else:
        elem = etree.SubElement(parent, tag, attrib=attrib)
    if text is not None:
        elem.text = text
    return elem


def _wallet_party(parent, role_nm: Optional[str], wallet_addr: str, scheme: str = "WALLET"):
    if role_nm:
        _elm(parent, "Nm", role_nm)
    id_ = _elm(parent, "Id")
    prvt = _elm(id_, "PrvtId")
    othr = _elm(prvt, "Othr")
    _elm(othr, "Id", wallet_addr)
    schme = _elm(othr, "SchmeNm")
    _elm(schme, "Prtry", scheme)


def _wallet_acct(parent, wallet_addr: str, scheme: str = "WALLET_ACCOUNT"):
    id_ = _elm(parent, "Id")
    othr = _elm(id_, "Othr")
    _elm(othr, "Id", wallet_addr)
    schme = _elm(othr, "SchmeNm")
    _elm(schme, "Prtry", scheme)


def _agent_not_provided(parent):
    agt = _elm(parent, "FinInstnId")
    othr = _elm(agt, "Othr")
    _elm(othr, "Id", "NOTPROVIDED")


def generate_pain008(payload: Dict[str, Any]) -> bytes:
    """
    Minimal pain.008.001.08:
      - GrpHdr.MsgId = reference
      - GrpHdr.CreDtTm
      - PmtInfId = id
      - PmtMtd = DD
      - ReqdColltnDt = date(created_at)
      - Cdtr = receiver_wallet
      - Dbtr = sender_wallet
      - DrctDbtTxInf with InstdAmt and RmtInf.Ustrd
    """
    created_at: datetime = payload["created_at"]
    reference: str = str(payload["reference"])
    rid: str = str(payload["id"])
    sender_wallet: str = str(payload["sender_wallet"])      # debtor
    receiver_wallet: str = str(payload["receiver_wallet"])  # creditor
    currency: str = str(payload["currency"])
    amount = payload["amount"]
    if isinstance(amount, Decimal):
        amt_str = format(amount, "f")
    else:
        amt_str = str(amount)

    root = etree.Element("Document", nsmap=NSMAP)
    cst = _elm(root, "CstmrDrctDbtInitn")

    grp = _elm(cst, "GrpHdr")
    _elm(grp, "MsgId", reference)
    _elm(grp, "CreDtTm", _iso_dt(created_at))
    _elm(grp, "NbOfTxs", "1")
    initg = _elm(grp, "InitgPty")
    _elm(initg, "Nm", "Capella")

    pmt = _elm(cst, "PmtInf")
    _elm(pmt, "PmtInfId", rid)
    _elm(pmt, "PmtMtd", "DD")
    _elm(pmt, "NbOfTxs", "1")
    _elm(pmt, "CtrlSum", amt_str)
    _elm(pmt, "ReqdColltnDt", _iso_date(created_at))

    # Creditor (collector)
    cdtr = _elm(pmt, "Cdtr")
    _wallet_party(cdtr, role_nm=None, wallet_addr=receiver_wallet, scheme="WALLET")

    cdtr_acct = _elm(pmt, "CdtrAcct")
    _wallet_acct(cdtr_acct, wallet_addr=receiver_wallet, scheme="WALLET_ACCOUNT")

    cdtr_agt = _elm(pmt, "CdtrAgt")
    _agent_not_provided(cdtr_agt)

    # Direct Debit Transaction
    dd = _elm(pmt, "DrctDbtTxInf")

    pmt_id = _elm(dd, "PmtId")
    _elm(pmt_id, "EndToEndId", rid)

    # Mandate info (minimal placeholder for demo)
    ddt = _elm(dd, "DrctDbtTx")
    mndt = _elm(ddt, "MndtRltdInf")
    _elm(mndt, "MndtId", f"mndt-{rid}")
    _elm(mndt, "DtOfSgntr", _iso_date(created_at))

    # Debtor
    dbtr_agt = _elm(dd, "DbtrAgt")
    _agent_not_provided(dbtr_agt)

    dbtr = _elm(dd, "Dbtr")
    _wallet_party(dbtr, role_nm=None, wallet_addr=sender_wallet, scheme="WALLET")

    dbtr_acct = _elm(dd, "DbtrAcct")
    _wallet_acct(dbtr_acct, wallet_addr=sender_wallet, scheme="WALLET_ACCOUNT")

    amt = _elm(dd, "InstdAmt", amt_str, attrib={"Ccy": currency})

    rmt = _elm(dd, "RmtInf")
    _elm(rmt, "Ustrd", reference)

    xml_bytes = etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
        standalone="yes",
    )
    return xml_bytes
