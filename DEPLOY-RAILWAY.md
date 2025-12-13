# Deploying the ISO 20022 Middleware on Railway (API + Web UI + Anchoring)

This guide deploys:
- API (FastAPI) on port 8000
- Web UI served by API at /web
- On-chain anchoring on Flare/Coston2 via Python `web3.py`
- Persistent DB (Railway Postgres)
- Persistent artifacts (Railway Volume at /data)

No changes are required on Capella’s side beyond setting `ISO_MIDDLEWARE_URL` to the API URL.

Prereqs
- Repo connected to Railway (set “Root Directory” to `Middleware-ISO-20022-payments`)
- Funded Coston2 private key for anchoring
- Contract address on Coston2 (already provided in repo README)

Package note
- `requirements.txt` already includes the additional packages for anchoring and Postgres:
  - web3, eth-account, eth-utils, hexbytes, psycopg2-binary

Architecture overview
- API container runs from the Dockerfile default command:
  - `uvicorn app.main:app --host 0.0.0.0 --port 8000`

- Artifacts (XML, evidence.zip) stored under `ARTIFACTS_DIR` and served at `/files`.
- DB defaults to SQLite if `DATABASE_URL` is not set. For production, use Railway Postgres.

## Network selection (Coston2 testnet vs Mainnet)
You can deploy the API to either Coston2 or Flare mainnet. The UI talks to the API, so it will follow whichever network the API is configured for.

- Coston2 (testnet):
  - FLARE_RPC_URL=https://coston2-api.flare.network/ext/C/rpc
  - ANCHOR_CONTRACT_ADDR=<your Coston2 contract address>
- Mainnet:
  - FLARE_RPC_URL=https://flare-api.flare.network/ext/C/rpc
  - ANCHOR_CONTRACT_ADDR=0xb59f0d6077A15a3778C262264a83A54B9ABbdEff (from contracts/EvidenceAnchor.deployed.json)

Receipts and UI alignment
- The UI (both `/ui/receipt.html` and the `/web` pages) simply consumes the API. Once you point the API to mainnet (or testnet), the UI aligns automatically.
- Receipts displayed are whatever is stored in your connected database. New receipts created after switching to mainnet will anchor and verify on mainnet; older testnet receipts remain in the DB, but verifying them against mainnet typically yields `matches_onchain=false`.
- Ensure:
- WEB_ORIGIN is set to your web UI domain (for CORS) if hosting separately
- PUBLIC_BASE_URL is set to your API domain so callback URLs and UI links are absolute

Step 1 — Create the API Service
1) Create a new Railway “Web Service” from this repo.
   - Root Directory: `Middleware-ISO-20022-payments`
   - Build using Dockerfile (default)
2) Add a Postgres add-on in Railway and copy its connection string.
3) Add a small Volume (e.g., 1–5 GB) and mount at `/data`.
4) Set the following environment variables (API service):
   - FLARE_RPC_URL=https://coston2-api.flare.network/ext/C/rpc
   - ANCHOR_CONTRACT_ADDR=0x262b1C649CE016717c62b9403E719C4801974CeF
   - ANCHOR_PRIVATE_KEY=0x<your_funded_coston2_private_key>
   - ANCHOR_ABI_PATH=contracts/EvidenceAnchor.abi.json
   - DATABASE_URL=postgresql://<user>:<pass>@<host>:<port>/<db>   (from Railway Postgres)
   - ARTIFACTS_DIR=/data/artifacts
   - PUBLIC_BASE_URL=https://<your-api-service-domain>            (set after first deploy)
5) Deploy. The API should bind to port 8000 inside the container and be reachable at the public URL Railway provides.

Step 2 — Finalize CORS and Public URLs
- In the API service, set:
  - STREAMLIT_ORIGIN=https://<streamlit-service-domain>
  - PUBLIC_BASE_URL=https://<api-service-domain>
- Redeploy API if you had to update env vars.

Capella configuration (no code changes)
- In Capella’s `.env`:
  - ISO_MIDDLEWARE_URL=https://<api-service-domain>
  - ISO_MW_TIMEOUT_MS=30000
- If using the optional callback:
  - Ensure the Capella callback route exists (as per `capella_integration/README.md`)
  - With `PUBLIC_BASE_URL` set, xml_url and bundle_url in callbacks will be absolute.

Smoke test checklist
- Health:
  - GET https://<api>/v1/health → { "status": "ok", "ts": ... }
- Create receipt:
  - POST https://<api>/v1/iso/record-tip with JSON:
    {
      "tip_tx_hash": "0xabc123",
      "chain": "coston2",
      "amount": "0.001",
      "currency": "FLR",
      "sender_wallet": "0xSender",
      "receiver_wallet": "0xReceiver",
      "reference": "demo:tip:1"
    }
  - Response includes { "receipt_id": "...", "status": "pending" }
- Observe anchoring:
  - After background processing, status becomes "anchored" if `ANCHOR_PRIVATE_KEY` is funded/valid.
- Check receipt:
  - GET https://<api>/v1/iso/receipts/<receipt_id> → includes flare_txid, bundle_hash, xml_url, bundle_url
- Verify bundle:
  - POST https://<api>/v1/iso/verify { "bundle_url": "https://<api>/files/<id>/evidence.zip" } → matches_onchain true
- Web UI:
  - Open https://<api>/web/index.html to use the dashboard

Notes and troubleshooting
- Missing anchoring packages:
  - Ensure the deployed image includes web3 / eth-account / eth-utils / hexbytes; they are in `requirements.txt`.
- Funded key:
  - `ANCHOR_PRIVATE_KEY` must have gas on Coston2. If not, anchoring will fail and receipt status may be "failed".
- ABI path:
  - `ANCHOR_ABI_PATH=contracts/EvidenceAnchor.abi.json` is bundled; fallback ABI is used if not found.
- Database:
  - Use Railway Postgres to persist receipts. SQLite on ephemeral FS will not persist across deploys.
- Artifacts:
  - Use a Railway Volume and `ARTIFACTS_DIR=/data/artifacts` to persist `evidence.zip` and `pain001.xml`.
- CORS/SSE:
  - WEB_ORIGIN should be set to the web UI domain for the API to allow that origin.
- Public URLs in callbacks:
  - Set PUBLIC_BASE_URL to the API domain so `xml_url` and `bundle_url` in callbacks are absolute.

Reference endpoints
- POST /v1/iso/record-tip
- GET /v1/iso/receipts/{id}
- POST /v1/iso/verify
- GET /v1/iso/events/{id}
- GET /receipt/{id}
- GET /embed/receipt?rid={id}

That’s it — after both services are live, point Capella to the API domain via `ISO_MIDDLEWARE_URL`. Capella’s integration files remain unchanged.
