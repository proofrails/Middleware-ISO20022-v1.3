# Capella Integration Guide (Next.js 14 + API Routes)

This folder contains example client and API routes you can copy into your Capella project to integrate with the ISO 20022 Middleware.

Environment (Capella)
Add these to your Capella .env:
- ISO_MIDDLEWARE_URL=https://your-mw-host:8000   (e.g., http://localhost:8000 for local)
- ISO_MW_TIMEOUT_MS=30000

Optional, if you plan to use the middleware callback:
- PUBLIC_BASE_URL=https://your-mw-host:8000   (set on the middleware side to prefix artifact URLs)
- (You do not need secrets in Capella to read receipts; anchoring keys stay in the middleware.)

Files to copy
- lib/isoClient.ts
- app/api/iso/record-tip/route.ts
- app/api/iso/receipts/[id]/route.ts
- app/api/iso/verify/route.ts

These expose a thin proxy — Capella backend calls the middleware server-to-server, avoiding CORS and exposing a stable interface to your frontend.

Usage from Capella flows
1) On successful tip (you already have tx hash and amounts in wagmi/viem):
- Build payload with strings for amounts to preserve precision (FLR has very low decimal).
- POST /api/iso/record-tip

Example (in a server action or API route):
import { mwRecordTip } from '@/lib/isoClient';
const resp = await mwRecordTip({
  tip_tx_hash: txHash,
  chain: 'coston2',
  amount: amountDecimalString, // keep as string
  currency: 'FLR',
  sender_wallet: tipper,
  receiver_wallet: author,
  reference: `capella:tip:${tipId}`,
  // Optional: callback_url if you want async notification:
  // callback_url: 'https://your-capella-host/api/iso/callback'
});
// Persist resp.receipt_id alongside the tip in Prisma.

2) Show receipt
- GET /api/iso/receipts/{receipt_id} returns:
  - status: pending/anchored/failed
  - flare_txid
  - bundle_hash
  - xml_url and bundle_url (relative to the middleware)

3) Verify bundle
- POST /api/iso/verify with the bundle_url (prefixed with ISO_MIDDLEWARE_URL if needed).
- Returns matches_onchain plus tx details (if the middleware can query logs).

Optional callback (no polling)
The middleware supports an optional callback_url in record-tip. When anchoring completes (or fails), it POSTs back a JSON payload:
{
  "receipt_id": "uuid",
  "status": "anchored" | "failed",
  "bundle_hash": "0x...",
  "flare_txid": "0x...",
  "xml_url": "/files/<id>/pain001.xml",
  "bundle_url": "/files/<id>/evidence.zip",
  "created_at": "2025-10-04T10:57:24.691999Z",
  "anchored_at": "2025-10-04T10:57:31.3664883Z"
}
- If PUBLIC_BASE_URL is set on the middleware, xml_url and bundle_url are absolute.

Add a route in Capella (e.g., app/api/iso/callback/route.ts) to accept this payload and update your Prisma row (match by receipt_id).

Security notes
- Keep Capella → Middleware server-to-server. Don’t call middleware directly from the browser.
- If you want a shared secret until proper auth, we can add an API key header on both ends.
- Do not share anchoring private keys; these remain in the middleware only.

End-to-end checklist
- Capella tip succeeds → POST /api/iso/record-tip (idempotent)
- Capella stores receipt_id
- Capella UI shows receipt status and artifacts (poll or use callback)
- Verify button calls /api/iso/verify
