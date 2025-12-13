import { NextResponse } from 'next/server';
import { mwRecordTip, type RecordTipRequest } from '@/lib/isoClient';

// POST /api/iso/record-tip
// Proxies to middleware: /v1/iso/record-tip
export async function POST(req: Request) {
  try {
    const body = (await req.json()) as Partial<RecordTipRequest>;

    // Basic validation (you may replace with zod)
    const required = [
      'tip_tx_hash',
      'chain',
      'amount',
      'currency',
      'sender_wallet',
      'receiver_wallet',
      'reference',
    ] as const;
    for (const k of required) {
      if (!body?.[k]) {
        return NextResponse.json({ error: 'invalid_payload', missing: k }, { status: 400 });
      }
    }

    // Ensure amount is passed as string to preserve FLR precision
    const payload: RecordTipRequest = {
      tip_tx_hash: String(body.tip_tx_hash),
      chain: body.chain === 'flare' ? 'flare' : 'coston2',
      amount: String(body.amount),
      currency: String(body.currency),
      sender_wallet: body.sender_wallet as `0x${string}`,
      receiver_wallet: body.receiver_wallet as `0x${string}`,
      reference: String(body.reference),
      // Optional callback URL if you implement /api/iso/callback:
      callback_url: body.callback_url ? String(body.callback_url) : undefined,
    };

    const data = await mwRecordTip(payload);
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json(
      { error: 'mw_error', detail: String(e?.message || e) },
      { status: 502 },
    );
  }
}
