import { NextResponse } from 'next/server';
import { mwVerify } from '@/lib/isoClient';

// POST /api/iso/verify
// Body: { bundle_url: string }
// Proxies to middleware: /v1/iso/verify
export async function POST(req: Request) {
  try {
    const { bundle_url } = (await req.json()) as { bundle_url?: string };
    if (!bundle_url) {
      return NextResponse.json({ error: 'bundle_url_required' }, { status: 400 });
    }
    const data = await mwVerify(bundle_url);
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json(
      { error: 'mw_error', detail: String(e?.message || e) },
      { status: 502 },
    );
  }
}
