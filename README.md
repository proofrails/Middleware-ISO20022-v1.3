# ISO 20022 Payments Middleware (PoC)

A prototype middleware that ingests on-chain tips (Capella on Flare/Coston2), produces ISO 20022 pain.001.001.09 XML, builds a deterministic evidence bundle, anchors the bundle hash on Flare (Coston2 / Flare mainnet), and exposes:

- A REST API (FastAPI)
- A static **web UI** served at `/web` (public + per‑project dashboards)
- Zero‑polling live receipt pages and embed widgets
- Optional Capella integration helpers (Next.js 14 backend routes + client)

Streamlit is no longer part of the active stack; all day‑to‑day usage goes through the `/web` UI and the HTTP API.

---

## What this prototype does

1. Client (e.g. Capella) calls `POST /v1/iso/record-tip` after a successful tip, passing:
   - `tip_tx_hash`, `chain` (`"coston2"` or `"flare"`), `amount` (string to preserve decimals), `currency` (`"FLR"`), `sender_wallet`, `receiver_wallet`, `reference` (e.g. `"capella:tip:<id>"`)
   - Optional: `callback_url` for server-to-server notification
2. API returns `{"receipt_id":"<uuid>","status":"pending"}` immediately.
3. Background task:
   - Builds ISO 20022 pain.001.001.09 XML (CstmrCdtTrfInitn)
   - Creates deterministic `evidence.zip` with manifest and signs it
   - Anchors the bundle hash on Flare via `EvidenceAnchor`
   - Updates the receipt to `status="anchored"` with `flare_txid`, `bundle_hash`
   - Emits an SSE update on `/v1/iso/events/{id}`; if `callback_url` is provided, POSTs a JSON payload to that URL
4. Clients retrieve:
   - `GET /v1/iso/receipts/{id}` for status and artifact links
   - Live page: `/receipt/{id}` (redirects to `/ui/receipt.html?rid=...`)
   - Embeddable widget: `/embed/receipt?rid={id}`
   - Verify bundle: `POST /v1/iso/verify` with either `bundle_url` or `bundle_hash`

---

## Repository structure

- `app/`
  - `main.py` (routes, background tasks, SSE endpoints, API key mgmt)
  - `iso.py` (ISO 20022 pain.001.001.09 generator)
  - `bundle.py` (deterministic zip + signature + verification)
  - `anchor.py` / `anchor_node.py` (anchoring and event lookup)
  - `sse.py` (in-memory SSE hub)
  - `models.py`, `db.py`, `schemas.py` (SQLAlchemy + Pydantic)
- `web/` – static web UI served at `/web`
  - `index.html` – **Public dashboard + self‑serve API key generator**
  - `project.html` – **Per‑project dashboard (requires API key)**
  - `verify.html` – Verify any bundle by URL or hash
  - `statements.html` – Generate camt.052/053 statements
  - `admin.html` – Admin API key management (requires `ADMIN_TOKEN`)
  - `styles.css`, `app.js` – shared styling + JS helpers
- `ui/receipt.html` – full receipt page (auto-updates via SSE)
- `embed/receipt.html` and `/embed/receipt` – compact widget, iframe‑friendly
- `contracts/` – Solidity contract, ABI, deployed.json
- `capella_integration/` – helpers to integrate with a Capella Next.js backend
- `scripts/` – deploy, anchor, find, smoke tests
- `schemas/` – README for XSD placement

---

## Key concepts: projects & API keys

Receipts are scoped to **projects**, and access is controlled via API keys.

- Table `api_keys` stores a hashed API key per project (`project_id`, `key_hash`, optional `label`).
- Header `X-API-Key` is used by the API and UI to determine the current project.
- `GET /v1/whoami` tells you which project, if any, your key belongs to.
- `GET /v1/iso/receipts` behaves as:
  - **With `X-API-Key`**: only that project’s receipts
  - **Without**: public view (all receipts)

New keys can be created in two ways:

1. **Self‑serve** (no admin token):
   - `POST /v1/public/api-keys`
   - Auto‑generates a `project_id` (e.g. `proj-abcdef12`) and a single API key
2. **Admin‑issued** (requires `ADMIN_TOKEN`):
   - `POST /v1/admin/api-keys` with body `{ "project_id": "proj-123", "label": "capella-prod" }`

Keys can be rotated by project owners via:
- `POST /v1/api-keys/rotate` (requires a valid `X-API-Key`)

The web UI wraps these endpoints so most users don’t need to call them directly.

---

## Quickstart (local)

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Start the API**

   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

   - Open docs: http://127.0.0.1:8000/docs

3. **Open the web UI**

   - Public dashboard: http://127.0.0.1:8000/web/index.html
   - Project dashboard: http://127.0.0.1:8000/web/project.html

4. **Generate a project & API key (public UI)**

   - Visit `/web/index.html`
   - In the **Get Your Project API Key** panel:
     - Optionally set a label (e.g. `capella-prod`)
     - Click **Generate API key**
   - The page will:
     - Call `POST /v1/public/api-keys`
     - Display `project_id` and `api_key` once
     - Store `api_key` in this browser’s `localStorage`

5. **View your project receipts**

   - Go to `/web/project.html`
   - The UI will call `GET /v1/whoami` and show:
     - `Scope: <project_id>` badge in the banner
     - A table of receipts returned by `GET /v1/iso/receipts` (scoped to your project)
   - You can rotate your key from this page; the new key is stored in the browser.

6. **Verify bundles**

   - Use `/web/verify.html` to verify any bundle URL or `bundle_hash` via `POST /v1/iso/verify`.
   - This works for both public receipts and your project’s receipts.

7. **Live viewing (zero polling)**

   - Full page: `http://127.0.0.1:8000/receipt/<receipt_id>`
   - Embeddable widget: `http://127.0.0.1:8000/embed/receipt?rid=<receipt_id>&theme=light`

---

## Web UI summary

- **Public page** (`/web/index.html`)
  - Generate project + API key (self‑serve)
  - See a public list of recent receipts (all projects)
- **Project page** (`/web/project.html`)
  - Requires API key in localStorage
  - Shows only your project’s receipts
  - Lets you rotate your API key via `POST /v1/api-keys/rotate`
- **Verify page** (`/web/verify.html`)
  - Verify by bundle URL or hash
- **Statements page** (`/web/statements.html`)
  - Generate `camt.053` (daily) and `camt.052` (intraday) statements

The banner at the top of all `/web` pages shows:

- Network: Coston2 Testnet / Flare Mainnet
- Contract: short form of the EvidenceAnchor address
- Scope badge:
  - `Scope: <project_id>` when an API key is present
  - `Scope: Public (all receipts)` otherwise

---

## Contract & environment

- Example Coston2 contract `EvidenceAnchor` (testnet):
  - `0x262b1C649CE016717c62b9403E719C4801974CeF`
- Example mainnet contract (from `contracts/EvidenceAnchor.deployed.json`):
  - `0xb59f0d6077A15a3778C262264a83A54B9ABbdEff`

Key environment variables (see `.env.example`):

- `FLARE_RPC_URL` – RPC endpoint (Coston2 or Flare mainnet)
- `ANCHOR_CONTRACT_ADDR` – deployed EvidenceAnchor address
- `ANCHOR_PRIVATE_KEY` – funded key used for anchoring
- `ANCHOR_ABI_PATH` – path to contract ABI JSON
- `DATABASE_URL` – SQLAlchemy connection string (Postgres recommended)
- `ARTIFACTS_DIR` – where XML and bundles are stored (served at `/files`)
- `WEB_ORIGIN` – CORS origin for your web UI / frontend (comma-separated if needed). The backend still accepts legacy `STREAMLIT_ORIGIN` for compatibility.
- `PUBLIC_BASE_URL` – base URL to prefix artifact links in callbacks
- `ADMIN_TOKEN` / `API_KEY_HASH_SECRET` – used for admin API key management

---

## Docker Compose (local dev)

```bash
cd Middleware-ISO-20022-payments
docker compose up --build
```

Services:
- **API**: http://localhost:8000
- **PostgreSQL**: localhost:5432

The web UI is served by the API container at `/web`.

---

## ISO messages produced per receipt

For each receipt with id `<receipt_id>`, the middleware writes ISO XML files under:

- `ARTIFACTS_DIR/<receipt_id>/`

Currently generated messages:

- `pain001.xml` – **Customer Credit Transfer Initiation** (`pain.001.001.09`)
  - Always generated.
- `pain002.xml` – **Payment Status Report** (`pain.002.*`)
  - Generated for each receipt (best-effort; failures are ignored, but the core flow still works).
- `pain007.xml` – **Cancellation / reversal demo** (`pain.007.*`)
  - Best-effort demo artifact; some downstreams may ignore it.
- `pain008.xml` – **Direct debit demo** (`pain.008.*`)
  - Best-effort demo artifact.
- `camt054.xml` – **Credit notification** (`camt.054.*`)
  - Only generated when the receipt is successfully **anchored on-chain**.

You can:
- List all available message URLs for a receipt via `GET /v1/iso/messages/{receipt_id}`.
- Download files directly from `/files/<receipt_id>/*`.

Statements are generated separately via:
- `POST /v1/iso/statement/camt052` – intraday statement (also wired to `/web/statements.html`).
- `POST /v1/iso/statement/camt053` – end-of-day statement.

---

## ISO 20022 mapping (high level)

- Message: `pain.001.001.09` (`Document/CstmrCdtTrfInitn`)
- Namespace: `urn:iso:std:iso:20022:tech:xsd:pain.001.001.09`
- Key elements:
  - `GrpHdr` – message header (id, creation time, number of txs)
  - `PmtInf` – payment information (debtor, creditor, requested execution date)
  - `CdtTrfTxInf` – credit transfer details (end-to-end id, instructed amount, wallets)
- Wallets are represented via `Othr/Id` with proprietary scheme names.
- Optional XSD validation: place official XSDs under `./schemas` (see `schemas/README.md`).

Note: this PoC uses `"FLR"` as the currency code; coordinate with downstream systems for strict ISO 4217 compliance.

---

## Capella integration (Next.js backend)

Use the files in `capella_integration/`:

- `lib/isoClient.ts` – small TypeScript client for the middleware
- `app/api/iso/...` route handlers to proxy:
  - `POST /v1/iso/record-tip`
  - `GET /v1/iso/receipts/{id}`
  - `POST /v1/iso/verify`

Capella `.env` example:

```bash
ISO_MIDDLEWARE_URL=https://your-middleware.example.com
ISO_MW_TIMEOUT_MS=30000
```

Once wired, Capella can forward tips to the middleware and embed links to `/receipt/{id}` or `/embed/receipt?...` for auditors.

---

## Security notes

- Never commit secrets (`.env`, private keys, API keys).
- For production deployments:
  - Serve behind HTTPS
  - Lock down `ADMIN_TOKEN` and admin endpoints
  - Rate‑limit public endpoints
  - Monitor anchoring success and RPC health

---

## Additional documentation

See also:
- `API_Documentation.md` – detailed HTTP API reference
- `Specifications.md` – deeper dive into design and data model
- `DEPLOY-RAILWAY.md` – deploying API + web UI on Railway

External reference:
- [Deepwiki](https://deepwiki.com/proofrails/Middleware-ISO20022-v1.3)

---

## License

MIT for this codebase; ISO schemas follow their own licensing per provider.
