import os
import time
import requests

BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

def post_tip():
    payload = {
        "tip_tx_hash": "0xdeadbeefsse01",
        "chain": "coston2",
        "amount": "0.000000000000000001",
        "currency": "FLR",
        "sender_wallet": "0x1111111111111111111111111111111111111111",
        "receiver_wallet": "0x2222222222222222222222222222222222222222",
        "reference": "demo:tip:sse-01",
        # omit callback_url here; testing SSE and pages
    }
    r = requests.post(f"{BASE}/v1/iso/record-tip", json=payload, timeout=30)
    print("record-tip:", r.status_code, r.text)
    r.raise_for_status()
    return r.json()["receipt_id"]

def get_receipt(rid: str):
    r = requests.get(f"{BASE}/v1/iso/receipts/{rid}", timeout=30)
    print("get-receipt:", r.status_code)
    print(r.text)
    r.raise_for_status()
    return r.json()

def verify_bundle(full_bundle_url: str):
    r = requests.post(f"{BASE}/v1/iso/verify", json={"bundle_url": full_bundle_url}, timeout=60)
    print("verify:", r.status_code)
    print(r.text)

def test_pages(rid: str):
    # Redirect route
    r = requests.get(f"{BASE}/receipt/{rid}", allow_redirects=False, timeout=15)
    print("receipt redirect:", r.status_code, r.headers.get("location"))

    # UI page
    r2 = requests.get(f"{BASE}/ui/receipt.html", params={"rid": rid}, timeout=15)
    print("ui receipt page:", r2.status_code, "len=", len(r2.text))
    print("ui receipt contains title:", "ISO Middleware Receipt" in r2.text)

    # Embed widget
    r3 = requests.get(f"{BASE}/embed/receipt", params={"rid": rid, "theme": "light"}, timeout=15)
    print("embed receipt:", r3.status_code, "len=", len(r3.text))
    print("embed contains marker:", "Receipt Widget" in r3.text)

def test_sse_head(rid: str):
    # Check SSE endpoint responds with stream content-type
    r = requests.get(f"{BASE}/v1/iso/events/{rid}", stream=True, timeout=10)
    print("sse status:", r.status_code)
    print("sse content-type:", r.headers.get("content-type"))
    # Read a small chunk then close
    try:
        for i, line in enumerate(r.iter_lines(chunk_size=1024, decode_unicode=True)):
            print("sse line:", line)
            if i >= 2:
                break
    except Exception as e:
        print("sse read error (ok for quick test):", e)
    finally:
        r.close()

def main():
    rid = post_tip()
    print("RID:", rid)

    # Wait for background processing to run
    time.sleep(12)

    rec = get_receipt(rid)
    # Exercise pages
    test_pages(rid)

    # Verify endpoint if bundle_url present
    bun = rec.get("bundle_url")
    if bun:
        full = f"{BASE}{bun}"
        verify_bundle(full)

    # Quick SSE header check
    test_sse_head(rid)

if __name__ == "__main__":
    main()
