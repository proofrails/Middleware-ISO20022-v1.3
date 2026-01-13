from __future__ import annotations

import os
import logging
from uuid import uuid4
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
import requests
from starlette.responses import StreamingResponse, RedirectResponse
import anyio
from .sse import stream_events, hub

import secrets
import hashlib
import base64
from fastapi import Request
from typing import Optional as _Opt

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- API key helpers ---
API_KEY_HASH_SECRET = os.getenv("API_KEY_HASH_SECRET", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")


def _hash_key(plaintext: str) -> str:
    return hashlib.sha256((API_KEY_HASH_SECRET + plaintext).encode("utf-8")).hexdigest()


def _require_admin(req: Request):
    tok = req.headers.get("x-admin-token")
    if not tok or not ADMIN_TOKEN or tok != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="admin_unauthorized")


def _get_project_from_key(req: Request, session):
    key = req.headers.get("x-api-key")
    if not key:
        return None
    h = _hash_key(key)
    from .models import ApiKey  # local import to avoid circular at import time
    ak = (
        session.query(ApiKey)
        .filter(ApiKey.key_hash == h, ApiKey.revoked_at.is_(None))
        .one_or_none()
    )
    if ak is None:
        raise HTTPException(status_code=401, detail="invalid_api_key")
    return ak.project_id

# These local modules will be added in subsequent steps
# - app/schemas.py: Pydantic models for requests/responses
# - app/db.py: SQLAlchemy engine/session helpers
# - app/models.py: SQLAlchemy models (Receipt)
# - app/iso.py: ISO 20022 pain.001 generator + XSD validation
# - app/bundle.py: Deterministic ZIP bundle + signing
# - app/anchor.py: Flare (Coston2) anchoring + log queries
from . import schemas, db, models, iso, bundle  # type: ignore
from .iso_messages import camt054 as iso_camt054  # type: ignore
from .iso_messages import pain002 as iso_pain002  # type: ignore
from .iso_messages import camt053 as iso_camt053  # type: ignore
from .iso_messages import camt052 as iso_camt052  # type: ignore
from .iso_messages import pain007 as iso_pain007  # type: ignore
from .iso_messages import pain008 as iso_pain008  # type: ignore


ARTIFACTS_DIR = os.getenv("ARTIFACTS_DIR", "artifacts")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

app = FastAPI(title="ISO 20022 Payments Middleware", version="0.1.0")

# Basic sanity guard: if configured for Flare mainnet, ensure contract address matches deployed mainnet EvidenceAnchor
MAINNET_RPC_SUBSTR = "flare-api.flare.network"
MAINNET_EXPECTED_CONTRACT = "0xb59f0d6077A15a3778C262264a83A54B9ABbdEff"
_cfg_rpc = os.getenv("FLARE_RPC_URL", "")
_cfg_addr = os.getenv("ANCHOR_CONTRACT_ADDR", "")
if MAINNET_RPC_SUBSTR in _cfg_rpc:
    # Enforce exact match (case-insensitive)
    if _cfg_addr.lower() != MAINNET_EXPECTED_CONTRACT.lower():
        raise RuntimeError(
            "FLARE_RPC_URL points to Flare mainnet but ANCHOR_CONTRACT_ADDR does not match "
            f"expected mainnet EvidenceAnchor address ({MAINNET_EXPECTED_CONTRACT})."
        )

# CORS: Allow configured web UI origin (supports both WEB_ORIGIN and legacy STREAMLIT_ORIGIN)
web_origin = os.getenv("WEB_ORIGIN") or os.getenv("STREAMLIT_ORIGIN", "http://localhost:8501")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[web_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static serving of artifacts
# Files will live under artifacts/{receipt_id}/...
app.mount("/files", StaticFiles(directory=ARTIFACTS_DIR), name="files")
# Static UI (HTML/JS) for optional receipt pages/widgets
app.mount("/ui", StaticFiles(directory="ui"), name="ui")
app.mount("/embed", StaticFiles(directory="embed"), name="embed")
# New web UI (replaces Streamlit)
app.mount("/web", StaticFiles(directory="web"), name="web")


# Database setup
models.Base.metadata.create_all(bind=db.engine)


def get_session():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@app.get("/v1/health")
def health() -> dict:
    # Include network-related info from env to help the Web UI display current network
    return {
        "status": "ok",
        "ts": datetime.utcnow().isoformat(),
        "rpc_url": os.getenv("FLARE_RPC_URL"),
        "contract": os.getenv("ANCHOR_CONTRACT_ADDR"),
    }

@app.get("/v1/iso/events/{rid}")
async def sse_events(rid: str):
    # Server-Sent Events stream for live receipt updates (zero polling)
    return StreamingResponse(stream_events(rid), media_type="text/event-stream")

@app.get("/receipt/{rid}")
def receipt_redirect(rid: str):
    # Convenience route to the UI receipt page
    return RedirectResponse(url=f"/ui/receipt.html?rid={rid}", status_code=307)

@app.get("/embed/receipt")
def embed_receipt_redirect(rid: Optional[str] = None, theme: Optional[str] = None):
    # Convenience route to the embed widget without .html
    if not rid:
        return RedirectResponse(url="/", status_code=307)
    q = f"?rid={rid}"
    if theme:
        q += f"&theme={theme}"
    return RedirectResponse(url=f"/embed/receipt.html{q}", status_code=307)


@app.post("/v1/iso/record-tip", response_model=schemas.RecordTipResponse)
def record_tip(
    payload: schemas.TipRecordRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    session=Depends(get_session),
):
    # Require project API key and bind receipt to project
    project_id = _get_project_from_key(request, session)
    if not project_id:
        raise HTTPException(status_code=401, detail="api_key_required")
    # Idempotency: dedupe by (chain, tip_tx_hash)
    existing = (
        session.query(models.Receipt)
        .filter(
            models.Receipt.chain == payload.chain,
            models.Receipt.tip_tx_hash == payload.tip_tx_hash,
        )
        .one_or_none()
    )
    if existing:
        return schemas.RecordTipResponse(receipt_id=str(existing.id), status=existing.status)

    rid = uuid4()
    created_at = datetime.utcnow()

    receipt = models.Receipt(
        id=rid,
        reference=payload.reference,
        tip_tx_hash=payload.tip_tx_hash,
        chain=payload.chain,
        amount=payload.amount,
        currency=payload.currency,
        sender_wallet=payload.sender_wallet,
        receiver_wallet=payload.receiver_wallet,
        project_id=project_id,
        status="pending",
        created_at=created_at,
        anchored_at=None,
    )
    session.add(receipt)
    session.commit()

    # Background processing: XML -> bundle -> sign -> anchor -> update DB
    background_tasks.add_task(_process_receipt, str(rid), payload.callback_url)
    
    logger.info(f"Receipt created: id={rid}, reference={payload.reference}, project={project_id}")

    return schemas.RecordTipResponse(receipt_id=str(rid), status="pending")


def _process_receipt(receipt_id: str, callback_url: Optional[str] = None):
    # New session in background task
    session = db.SessionLocal()
    try:
        rec: Optional[models.Receipt] = session.get(models.Receipt, receipt_id)
        if not rec:
            logger.warning(f"Receipt not found for processing: {receipt_id}")
            return
        
        logger.info(f"Processing receipt: id={receipt_id}, reference={rec.reference}")

        # Build a dict view for ISO and bundle metadata
        receipt_dict = {
            "id": str(rec.id),
            "reference": rec.reference,
            "tip_tx_hash": rec.tip_tx_hash,
            "chain": rec.chain,
            "amount": rec.amount,
            "currency": rec.currency,
            "sender_wallet": rec.sender_wallet,
            "receiver_wallet": rec.receiver_wallet,
            "status": rec.status,
            "created_at": rec.created_at,
        }

        # 1) Generate ISO XML (validate when XSD is present)
        logger.debug(f"Generating ISO XML for receipt: {receipt_id}")
        xml_bytes = iso.generate_pain001(receipt_dict)

        # 2) Create deterministic bundle and sign
        logger.debug(f"Creating bundle for receipt: {receipt_id}")
        zip_path, bundle_hash = bundle.create_bundle(receipt_dict, xml_bytes)
        logger.info(f"Bundle created: id={receipt_id}, hash={bundle_hash}")

        # 3) Anchor on Flare (Coston2) if available
        rec.bundle_hash = bundle_hash
        anchored = False
        # Try Python web3 first, then Node fallback
        try:
            from . import anchor  # type: ignore
            logger.info(f"Anchoring bundle on-chain: hash={bundle_hash}")
            txid, block_number = anchor.anchor_bundle(bundle_hash)
            rec.flare_txid = txid
            rec.status = "anchored"
            rec.anchored_at = datetime.utcnow()
            anchored = True
            logger.info(f"Bundle anchored successfully: id={receipt_id}, tx={txid}, block={block_number}")
        except Exception as e:
            logger.warning(f"Python anchor failed, trying Node fallback: {e}")
            try:
                from . import anchor_node  # type: ignore
                txid, block_number = anchor_node.anchor_bundle(bundle_hash)
                rec.flare_txid = txid
                rec.status = "anchored"
                rec.anchored_at = datetime.utcnow()
                anchored = True
                logger.info(f"Bundle anchored via Node: id={receipt_id}, tx={txid}, block={block_number}")
            except Exception as e2:
                # Anchoring unavailable/failed; keep artifacts and mark failed
                logger.error(f"Anchoring failed for receipt {receipt_id}: {e2}")
                rec.status = "failed"

        # 4) Persist artifact paths
        rec.xml_path = f"{ARTIFACTS_DIR}/{rec.id}/pain001.xml"
        rec.bundle_path = f"{ARTIFACTS_DIR}/{rec.id}/evidence.zip"
        session.commit()

        # Additional ISO artifacts (best-effort)
        try:
            payload2 = {
                "id": str(rec.id),
                "reference": rec.reference,
                "status": rec.status,
                "bundle_hash": rec.bundle_hash,
                "flare_txid": rec.flare_txid,
                "created_at": rec.created_at,
                "anchored_at": rec.anchored_at,
                "amount": rec.amount,
                "currency": rec.currency,
                "sender_wallet": rec.sender_wallet,
                "receiver_wallet": rec.receiver_wallet,
            }
            # pain.002 status report
            p002 = iso_pain002.generate_pain002(payload2)
            (Path(ARTIFACTS_DIR) / str(rec.id) / "pain002.xml").write_bytes(p002)

            # pain.007 (e.g. rejection / reversal demo)
            try:
                p007 = iso_pain007.generate_pain007(payload2)
                (Path(ARTIFACTS_DIR) / str(rec.id) / "pain007.xml").write_bytes(p007)
            except Exception:
                pass

            # pain.008 (direct debit demo)
            try:
                p008 = iso_pain008.generate_pain008(payload2)
                (Path(ARTIFACTS_DIR) / str(rec.id) / "pain008.xml").write_bytes(p008)
            except Exception:
                pass

            # camt.054 DCN if anchored
            if rec.status == "anchored":
                c054 = iso_camt054.generate_camt054(payload2)
                (Path(ARTIFACTS_DIR) / str(rec.id) / "camt054.xml").write_bytes(c054)
        except Exception:
            pass

        # 4b) Publish SSE event (best-effort)
        try:
            evt_payload = {
                "receipt_id": str(rec.id),
                "status": rec.status,
                "bundle_hash": rec.bundle_hash,
                "flare_txid": rec.flare_txid,
                "xml_url": f"/files/{rec.id}/pain001.xml",
                "bundle_url": f"/files/{rec.id}/evidence.zip",
                "created_at": rec.created_at.isoformat() if rec.created_at else None,
                "anchored_at": rec.anchored_at.isoformat() if rec.anchored_at else None,
            }
            anyio.from_thread.run(hub.publish, str(rec.id), evt_payload)  # type: ignore
        except Exception:
            pass

        # 5) Optional callback to Capella
        if callback_url:
            try:
                cb_payload = {
                    "receipt_id": str(rec.id),
                    "status": rec.status,
                    "bundle_hash": rec.bundle_hash,
                    "flare_txid": rec.flare_txid,
                    "xml_url": f"/files/{rec.id}/pain001.xml",
                    "bundle_url": f"/files/{rec.id}/evidence.zip",
                    "created_at": rec.created_at.isoformat() if rec.created_at else None,
                    "anchored_at": rec.anchored_at.isoformat() if rec.anchored_at else None,
                }
                # If PUBLIC_BASE_URL is set, prefix artifact URLs for external consumers
                base_url = os.getenv("PUBLIC_BASE_URL")
                if base_url:
                    cb_payload["xml_url"] = f"{base_url}{cb_payload['xml_url']}"
                    cb_payload["bundle_url"] = f"{base_url}{cb_payload['bundle_url']}"
                # Fire-and-forget callback
                logger.debug(f"Sending callback to {callback_url} for receipt {rec.id}")
                requests.post(callback_url, json=cb_payload, timeout=15)
                logger.debug(f"Callback sent successfully for receipt {rec.id}")
            except Exception as e:
                # Do not fail background task on callback errors
                logger.warning(f"Callback failed for receipt {rec.id}: {e}")
    except Exception as e:
        logger.error(f"Error processing receipt {receipt_id}: {e}", exc_info=True)
        if rec:
            rec.status = "failed"
            session.commit()
        raise
    finally:
        session.close()


@app.get("/v1/iso/receipts")
def list_receipts(limit: int = 50, request: Request = None, session=Depends(get_session)):
    # If X-API-Key is present, only list receipts for that project; else list all (public dashboard)
    project_id = None
    try:
        project_id = _get_project_from_key(request, session) if request else None
    except HTTPException as e:
        raise e

    q = session.query(models.Receipt)
    if project_id:
        q = q.filter(models.Receipt.project_id == project_id)
    q = q.order_by(models.Receipt.created_at.desc()).limit(max(1, min(limit, 200))).all()
    out = []
    for r in q:
        out.append({
            "id": str(r.id),
            "status": r.status,
            "bundle_hash": r.bundle_hash,
            "flare_txid": r.flare_txid,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return {"items": out}


@app.get("/v1/iso/receipts/{rid}", response_model=schemas.ReceiptResponse)
def get_receipt(rid: str, request: Request, session=Depends(get_session)):
    rec: Optional[models.Receipt] = session.get(models.Receipt, rid)
    if not rec:
        raise HTTPException(status_code=404, detail="Receipt not found")
    # Enforce project scope if API key is supplied
    try:
        project_id = _get_project_from_key(request, session)
    except HTTPException:
        project_id = None
    if project_id and rec.project_id and rec.project_id != project_id:
        raise HTTPException(status_code=404, detail="Receipt not found")

    xml_url = f"/files/{rid}/pain001.xml"
    bundle_url = f"/files/{rid}/evidence.zip"

    return schemas.ReceiptResponse(
        id=str(rec.id),
        status=rec.status,
        bundle_hash=rec.bundle_hash,
        flare_txid=rec.flare_txid,
        xml_url=xml_url,
        bundle_url=bundle_url,
        created_at=rec.created_at,
        anchored_at=rec.anchored_at,
    )


@app.post("/v1/iso/verify", response_model=schemas.VerifyResponse)
def verify(req: schemas.VerifyRequest, session=Depends(get_session)):
    """
    Verify a bundle by URL (compute SHA-256 on the fly) or directly by bundle_hash.
    If enabled via VERIFY_AUTO_ANCHOR=1 and ANCHOR_PRIVATE_KEY is present, will auto-anchor
    when no on-chain match is found.
    """
    errors: list[str] = []

    # 1) Determine bundle_hash
    bundle_hash: Optional[str] = None
    if req.bundle_hash:
        bundle_hash = req.bundle_hash
    else:
        verification = bundle.verify_bundle(req.bundle_url or "")
        bundle_hash = verification.bundle_hash
        errors.extend(list(verification.errors))

    # Guard
    if not bundle_hash or not bundle_hash.startswith("0x") or len(bundle_hash) != 66:
        errors.append("invalid_or_missing_bundle_hash")
        return schemas.VerifyResponse(matches_onchain=False, bundle_hash=bundle_hash, errors=errors)

    # 2) On-chain lookup
    matches = False
    txid: Optional[str] = None
    anchored_at: Optional[datetime] = None
    try:
        from . import anchor  # type: ignore
        chain_info = anchor.find_anchor(bundle_hash)
        matches = chain_info.matches
        txid = chain_info.txid
        anchored_at = chain_info.anchored_at
    except Exception:
        try:
            from . import anchor_node  # type: ignore
            chain_info = anchor_node.find_anchor(bundle_hash)
            matches = chain_info.matches
            txid = chain_info.txid
            anchored_at = chain_info.anchored_at
        except Exception:
            errors.append("anchor_lookup_unavailable")

    # 3) Optional auto-anchoring
    if not matches and os.getenv("VERIFY_AUTO_ANCHOR", "0") == "1" and os.getenv("ANCHOR_PRIVATE_KEY"):
        try:
            from . import anchor  # type: ignore
            txid2, _block = anchor.anchor_bundle(bundle_hash)
            matches = True
            txid = txid2
            anchored_at = datetime.utcnow()
        except Exception as e:
            errors.append("anchoring_failed")

    # 4) Best-effort DB update for any matching receipt
    if matches:
        try:
            rec = (
                session.query(models.Receipt)
                .filter(models.Receipt.bundle_hash == bundle_hash)
                .order_by(models.Receipt.created_at.desc())
                .first()
            )
            if rec:
                rec.flare_txid = txid
                rec.status = "anchored"
                rec.anchored_at = anchored_at or datetime.utcnow()
                session.commit()
        except Exception:
            pass

    return schemas.VerifyResponse(
        matches_onchain=matches,
        bundle_hash=bundle_hash,
        flare_txid=txid,
        anchored_at=anchored_at,
        errors=errors,
    )


@app.get("/v1/iso/messages/{rid}")
def list_messages(rid: str):
    base_dir = Path(ARTIFACTS_DIR) / rid
    msgs: dict[str, str] = {}
    mapping = {
        "pain.001": "pain001.xml",
        "pain.002": "pain002.xml",
        "pain.007": "pain007.xml",
        "pain.008": "pain008.xml",
        "camt.054": "camt054.xml",
        "camt.029": "camt029.xml",
        "camt.056": "camt056.xml",
        "pacs.002": "pacs002.xml",
        "pacs.004": "pacs004.xml",
        "pacs.007": "pacs007.xml",
        "pacs.008": "pacs008.xml",
        "pacs.009": "pacs009.xml",
        "remt.001": "remt001.xml",
    }
    for k, fname in mapping.items():
        if (base_dir / fname).exists():
            msgs[k] = f"/files/{rid}/{fname}"
    return {"receipt_id": rid, "messages": msgs}


@app.post("/v1/iso/statement/camt053")
def generate_camt053(payload: dict, request: Request, session=Depends(get_session)):
    """
    Body: { "date": "YYYY-MM-DD" }
    """
    try:
        date_str = str(payload.get("date"))
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or missing date (YYYY-MM-DD)")

    start = datetime.combine(d, datetime.min.time())
    end = start + timedelta(days=1)

    # If project API key present, only that project's receipts
    try:
        project_id = _get_project_from_key(request, session)
    except HTTPException:
        project_id = None

    q = session.query(models.Receipt).filter(
        models.Receipt.created_at >= start,
        models.Receipt.created_at < end,
    )
    if project_id:
        q = q.filter(models.Receipt.project_id == project_id)
    recs = q.order_by(models.Receipt.created_at.asc()).all()
    entries = [
        {
            "id": str(r.id),
            "reference": r.reference,
            "amount": r.amount,
            "currency": r.currency,
            "created_at": r.created_at,
            "sender_wallet": r.sender_wallet,
            "receiver_wallet": r.receiver_wallet,
        }
        for r in recs
    ]
    xml = iso_camt053.generate_camt053(d, entries)
    out_dir = Path(ARTIFACTS_DIR) / "statements"
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"camt053-{d.isoformat()}.xml"
    (out_dir / fname).write_bytes(xml)
    return {"status": "ok", "url": f"/files/statements/{fname}"}


@app.post("/v1/iso/statement/camt052")
def generate_camt052(payload: dict, request: Request, session=Depends(get_session)):
    """
    Body: { "date": "YYYY-MM-DD", "window": "HH:MM-HH:MM" (optional) }
    """
    try:
        date_str = str(payload.get("date"))
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or missing date (YYYY-MM-DD)")
    window = payload.get("window")

    start = datetime.combine(d, datetime.min.time())
    end = start + timedelta(days=1)

    try:
        project_id = _get_project_from_key(request, session)
    except HTTPException:
        project_id = None

    q = session.query(models.Receipt).filter(
        models.Receipt.created_at >= start,
        models.Receipt.created_at < end,
    )
    if project_id:
        q = q.filter(models.Receipt.project_id == project_id)
    recs = q.order_by(models.Receipt.created_at.asc()).all()
    entries = [
        {
            "id": str(r.id),
            "reference": r.reference,
            "amount": r.amount,
            "currency": r.currency,
            "created_at": r.created_at,
            "sender_wallet": r.sender_wallet,
            "receiver_wallet": r.receiver_wallet,
        }
        for r in recs
    ]
    xml = iso_camt052.generate_camt052(d, entries, window=window)
    out_dir = Path(ARTIFACTS_DIR) / "statements"
    out_dir.mkdir(parents=True, exist_ok=True)
    w_suffix = ("-" + str(window).replace(":", "").replace("/", "").replace("\\", "").replace(" ", "")) if window else ""
    fname = f"camt052-{d.isoformat()}{w_suffix}.xml"
    (out_dir / fname).write_bytes(xml)
    return {"status": "ok", "url": f"/files/statements/{fname}"}


@app.get("/v1/whoami")
def whoami(request: Request, session=Depends(get_session)):
    """Return project context from X-API-Key, or null for public."""
    try:
        pid = _get_project_from_key(request, session)
    except HTTPException:
        pid = None
    return {"project_id": pid}

# --- Public / project API key management ---

def _generate_api_key(session, project_id: str, label: str | None = None) -> tuple[str, str]:
    """Internal helper to create an API key row and return (row_id, plaintext_key)."""
    from .models import ApiKey  # local import

    # generate key
    raw = secrets.token_bytes(32)
    b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    api_key = "pk_" + b64
    key_hash = _hash_key(api_key)

    # ensure uniqueness on hash (extremely unlikely to collide, but check once)
    existing = session.query(ApiKey).filter(ApiKey.key_hash == key_hash).one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="key_collision")

    row = ApiKey(project_id=project_id, key_hash=key_hash, label=label)
    session.add(row)
    session.commit()
    return str(row.id), api_key


@app.post("/v1/public/api-keys")
def public_issue_api_key(payload: dict | None = None, session=Depends(get_session)):
    """Self-serve: create a new project + API key.

    Returns a freshly generated project_id and a single API key bound to it.
    No ADMIN_TOKEN required.
    """
    label = (payload or {}).get("label") if isinstance(payload, dict) else None
    project_id = f"proj-{uuid4().hex[:8]}"
    row_id, api_key = _generate_api_key(session, project_id=project_id, label=label)
    return {
        "id": row_id,
        "project_id": project_id,
        "label": label,
        "api_key": api_key,
    }


@app.post("/v1/api-keys/rotate")
def rotate_api_key(request: Request, session=Depends(get_session)):
    """Rotate the current project's API key.

    Requires X-API-Key; revokes existing keys for that project and returns a new one.
    """
    # Identify calling project
    project_id = _get_project_from_key(request, session)
    if not project_id:
        raise HTTPException(status_code=401, detail="api_key_required")

    from .models import ApiKey  # local import

    # Revoke existing active keys for this project
    now = datetime.utcnow()
    session.query(ApiKey).filter(ApiKey.project_id == project_id, ApiKey.revoked_at.is_(None)).update({ApiKey.revoked_at: now})
    session.commit()

    row_id, api_key = _generate_api_key(session, project_id=project_id, label="rotated")
    return {
        "id": row_id,
        "project_id": project_id,
        "label": "rotated",
        "api_key": api_key,
    }


# --- Admin API key management ---
@app.post("/v1/admin/api-keys")
def admin_issue_api_key(payload: dict, request: Request, session=Depends(get_session)):
    """
    Admin: issue a new API key for a project.
    Body: { "project_id": "proj-123", "label": "capella-prod" }
    Returns plaintext api_key once + metadata.
    """
    _require_admin(request)
    project_id = (payload or {}).get("project_id")
    label = (payload or {}).get("label")
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id_required")
    # generate key
    raw = secrets.token_bytes(32)
    b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    api_key = "pk_" + b64
    key_hash = _hash_key(api_key)

    from .models import ApiKey  # local import
    # ensure uniqueness on hash
    existing = session.query(ApiKey).filter(ApiKey.key_hash == key_hash).one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="key_collision")
    row = ApiKey(project_id=project_id, key_hash=key_hash, label=label)
    session.add(row)
    session.commit()
    return {
        "id": str(row.id),
        "project_id": project_id,
        "label": label,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "api_key": api_key,  # show once
    }


@app.get("/v1/admin/api-keys")
def admin_list_api_keys(project_id: str, request: Request, session=Depends(get_session)):
    """Admin: list keys for a project (no plaintext)."""
    _require_admin(request)
    from .models import ApiKey
    rows = (
        session.query(ApiKey)
        .filter(ApiKey.project_id == project_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": str(r.id),
                "project_id": r.project_id,
                "label": r.label,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "revoked": r.revoked_at is not None,
            }
            for r in rows
        ]
    }


@app.post("/v1/admin/api-keys/{id}/revoke")
def admin_revoke_api_key(id: str, request: Request, session=Depends(get_session)):
    """Admin: revoke a key by id."""
    _require_admin(request)
    from .models import ApiKey
    row = session.get(ApiKey, id)
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    if row.revoked_at is None:
        row.revoked_at = datetime.utcnow()
        session.commit()
    return {"status": "ok", "revoked": True}
