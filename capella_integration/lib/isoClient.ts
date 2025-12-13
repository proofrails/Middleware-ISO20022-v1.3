import 'server-only';

const ISO_URL = process.env.ISO_MIDDLEWARE_URL!;
const TIMEOUT = Number(process.env.ISO_MW_TIMEOUT_MS || 30000);

function assertEnv() {
  if (!ISO_URL) {
    throw new Error('ISO_MIDDLEWARE_URL is not set in Capella .env');
  }
}

async function mwFetch<T>(path: string, init: RequestInit): Promise<T> {
  assertEnv();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT);

  try {
    const r = await fetch(`${ISO_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        'content-type': 'application/json',
        ...(init.headers || {}),
      },
      cache: 'no-store',
    });

    const text = await r.text();
    if (!r.ok) {
      throw new Error(`Middleware ${path} ${r.status}: ${text}`);
    }
    return text ? (JSON.parse(text) as T) : ({} as T);
  } finally {
    clearTimeout(timer);
  }
}

export type RecordTipRequest = {
  tip_tx_hash: string;
  chain: 'coston2' | 'flare';
  amount: string; // keep as string to preserve decimals for FLR
  currency: string; // 'FLR'
  sender_wallet: `0x${string}`;
  receiver_wallet: `0x${string}`;
  reference: string; // 'capella:tip:<id>'
  callback_url?: string; // optional, to avoid polling
};

export type RecordTipResponse = {
  receipt_id: string;
  status: 'pending' | 'anchored' | 'failed';
};

export type ReceiptResponse = {
  id: string;
  status: 'pending' | 'anchored' | 'failed';
  bundle_hash?: string | null;
  flare_txid?: string | null;
  xml_url?: string | null;
  bundle_url?: string | null;
  created_at: string;
  anchored_at?: string | null;
};

export type VerifyResponse = {
  matches_onchain: boolean;
  bundle_hash?: string | null;
  flare_txid?: string | null;
  anchored_at?: string | null;
  errors: string[];
};

export async function mwRecordTip(p: RecordTipRequest): Promise<RecordTipResponse> {
  return mwFetch<RecordTipResponse>('/v1/iso/record-tip', {
    method: 'POST',
    body: JSON.stringify(p),
  });
}

export async function mwGetReceipt(id: string): Promise<ReceiptResponse> {
  return mwFetch<ReceiptResponse>(`/v1/iso/receipts/${id}`, {
    method: 'GET',
  });
}

export async function mwVerify(bundleUrl: string): Promise<VerifyResponse> {
  return mwFetch<VerifyResponse>('/v1/iso/verify', {
    method: 'POST',
    body: JSON.stringify({ bundle_url: bundleUrl }),
  });
}
