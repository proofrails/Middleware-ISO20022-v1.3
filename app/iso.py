from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional, Dict, Any

from lxml import etree

try:
    import xmlschema  # type: ignore
except Exception:  # pragma: no cover
    xmlschema = None  # type: ignore


# Namespace for pain.001.001.09
NS_PAIN001 = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"
NSMAP = {None: NS_PAIN001}

# XSD path (must be vendored into the repo under schemas/)
SCHEMA_PATH = Path("schemas/pain.001.001.09.xsd")

_schema: Optional["xmlschema.XMLSchema"] = None  # type: ignore


def _get_schema() -> Optional["xmlschema.XMLSchema"]:  # type: ignore
    global _schema
    if _schema is not None:
        return _schema
    if xmlschema is None:
        return None
    if SCHEMA_PATH.exists():
        try:
            _schema = xmlschema.XMLSchema(str(SCHEMA_PATH))
            return _schema
        except Exception:
            return None
    return None


def _iso_dt(dt: datetime) -> str:
    # Ensure UTC Z-format
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    # Use ISO 8601 with Z
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
    """Constructs PartyIdentification: Nm (optional) + Id/PrvtId/Othr/{Id,SchmeNm/Prtry}"""
    if role_nm:
        _elm(parent, "Nm", role_nm)
    id_ = _elm(parent, "Id")
    prvt = _elm(id_, "PrvtId")
    othr = _elm(prvt, "Othr")
    _elm(othr, "Id", wallet_addr)
    schme = _elm(othr, "SchmeNm")
    _elm(schme, "Prtry", scheme)


def _wallet_acct(parent, wallet_addr: str, scheme: str = "WALLET_ACCOUNT"):
    """Constructs CashAccount: Id/Othr/{Id,SchmeNm/Prtry}"""
    id_ = _elm(parent, "Id")
    othr = _elm(id_, "Othr")
    _elm(othr, "Id", wallet_addr)
    schme = _elm(othr, "SchmeNm")
    _elm(schme, "Prtry", scheme)


def _agent_not_provided(parent):
    """Constructs FinancialInstitutionIdentification with Othr/Id=NOTPROVIDED"""
    agt = _elm(parent, "FinInstnId")
    othr = _elm(agt, "Othr")
    _elm(othr, "Id", "NOTPROVIDED")


def generate_pain001(receipt: Dict[str, Any]) -> bytes:
    """
    Build a minimal schema-valid pain.001.001.09 for a single credit transfer.
    Mapping decisions per spec:
    - GrpHdr.MsgId = receipt['reference']
    - GrpHdr.CreDtTm = receipt['created_at']
    - GrpHdr.NbOfTxs = '1'
    - GrpHdr.InitgPty.Nm = 'Capella' (or generic)
    - PmtInf:
      - PmtInfId = receipt['id']
      - PmtMtd = TRF
      - ReqdExctnDt = date(created_at)
      - Dbtr (+ WALLET id mapping)
      - DbtrAcct (Othr/Id = sender wallet)
      - DbtrAgt = NOTPROVIDED
      - ChrgBr = SLEV
    - CdtTrfTxInf:
      - PmtId.EndToEndId = receipt['id']
      - Amt.InstdAmt @Ccy = receipt['currency'] (FLR for PoC)
      - CdtrAgt = NOTPROVIDED
      - Cdtr (+ WALLET id mapping)
      - CdtrAcct (Othr/Id = receiver wallet)
      - RmtInf.Ustrd = receipt['reference']
    """
    created_at: datetime = receipt["created_at"]
    reference: str = receipt["reference"]
    rid: str = receipt["id"]
    sender_wallet: str = receipt["sender_wallet"]
    receiver_wallet: str = receipt["receiver_wallet"]
    currency: str = str(receipt["currency"])
    amount = receipt["amount"]
    if isinstance(amount, Decimal):
        amt_str = format(amount, "f")
    else:
        amt_str = str(amount)

    root = etree.Element("Document", nsmap=NSMAP)
    cst = _elm(root, "CstmrCdtTrfInitn")

    # Group Header
    grp = _elm(cst, "GrpHdr")
    _elm(grp, "MsgId", reference)
    _elm(grp, "CreDtTm", _iso_dt(created_at))
    _elm(grp, "NbOfTxs", "1")
    initg = _elm(grp, "InitgPty")
    _elm(initg, "Nm", "Capella")

    # Payment Information
    pmt = _elm(cst, "PmtInf")
    _elm(pmt, "PmtInfId", rid)
    _elm(pmt, "PmtMtd", "TRF")
    _elm(pmt, "NbOfTxs", "1")
    _elm(pmt, "CtrlSum", amt_str)
    _elm(pmt, "ReqdExctnDt", _iso_date(created_at))

    # Debtor
    dbtr = _elm(pmt, "Dbtr")
    _wallet_party(dbtr, role_nm=None, wallet_addr=sender_wallet, scheme="WALLET")

    dbtr_acct = _elm(pmt, "DbtrAcct")
    _wallet_acct(dbtr_acct, wallet_addr=sender_wallet, scheme="WALLET_ACCOUNT")

    dbtr_agt = _elm(pmt, "DbtrAgt")
    _agent_not_provided(dbtr_agt)

    _elm(pmt, "ChrgBr", "SLEV")

    # Credit Transfer Transaction
    cdt = _elm(pmt, "CdtTrfTxInf")
    pmt_id = _elm(cdt, "PmtId")
    _elm(pmt_id, "EndToEndId", rid)

    amt = _elm(cdt, "Amt")
    _elm(amt, "InstdAmt", amt_str, attrib={"Ccy": currency})

    cdtr_agt = _elm(cdt, "CdtrAgt")
    _agent_not_provided(cdtr_agt)

    cdtr = _elm(cdt, "Cdtr")
    _wallet_party(cdtr, role_nm=None, wallet_addr=receiver_wallet, scheme="WALLET")

    cdtr_acct = _elm(cdt, "CdtrAcct")
    _wallet_acct(cdtr_acct, wallet_addr=receiver_wallet, scheme="WALLET_ACCOUNT")

    rmt = _elm(cdt, "RmtInf")
    _elm(rmt, "Ustrd", reference)

    xml_bytes = etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
        standalone="yes",
    )

    # Validate if schema available
    schema = _get_schema()
    if schema is not None:
        try:
            # xmlschema can validate bytes directly
            schema.validate(xml_bytes)
        except Exception as e:
            # Re-raise with readable error list if possible
            if hasattr(schema, "iter_errors"):
                msgs = []
                for err in schema.iter_errors(xml_bytes):
                    msgs.append(str(err))
                raise ValueError("ISO20022 schema validation failed:\n" + "\n".join(msgs)) from e
            raise

    return xml_bytes
