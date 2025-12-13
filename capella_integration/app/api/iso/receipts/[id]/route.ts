import { NextResponse } from 'next/server';
import { mwGetReceipt } from '@/lib/isoClient';

// GET /api/iso/receipts/:id
// Proxies to middleware: /v1/iso/receipts/:id
export async function GET(_: Request, { params }: { params: { id: string } }) {
  try {
    const data = await mwGetReceipt(params.id);
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json(
      { error: 'mw_error', detail: String(e?.message || e) },
      { status: 502 },
    );
  }
}
