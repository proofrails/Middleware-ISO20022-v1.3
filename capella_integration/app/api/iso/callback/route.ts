import { NextResponse } from 'next/server';

// Optional callback endpoint if you pass callback_url to the middleware.
// The middleware will POST here when anchoring completes or fails.
// Payload shape:
// {
//   "receipt_id": "uuid",
//   "status": "anchored" | "failed",
//   "bundle_hash": "0x...",
//   "flare_txid": "0x...",
//   "xml_url": "/files/<id>/pain001.xml" | "https://.../files/... (if PUBLIC_BASE_URL set)",
//   "bundle_url": "/files/<id>/evidence.zip" | "https://.../files/...",
//   "created_at": "ISO timestamp",
//   "anchored_at": "ISO timestamp | null"
// }
//
// In production, update your Prisma Tip (or Receipt) row here using receipt_id.

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const {
      receipt_id,
      status,
      bundle_hash,
      flare_txid,
      xml_url,
      bundle_url,
      created_at,
      anchored_at,
    } = body || {};

    if (!receipt_id || !status) {
      return NextResponse.json({ error: 'invalid_payload' }, { status: 400 });
    }

    // TODO: Persist this to your DB (Prisma example):
    // const db = getPrisma();
    // await db.tip.update({
    //   where: { isoReceiptId: receipt_id },
    //   data: {
    //     isoStatus: status,
    //     isoBundleHash: bundle_hash,
    //     isoFlareTxid: flare_txid,
    //     isoXmlUrl: xml_url,
    //     isoBundleUrl: bundle_url,
    //     isoAnchoredAt: anchored_at ? new Date(anchored_at) : null,
    //   },
    // });

    // For now, just acknowledge
    return NextResponse.json({ ok: true });
  } catch (e: any) {
    return NextResponse.json(
      { error: 'callback_error', detail: String(e?.message || e) },
      { status: 400 },
    );
  }
}
