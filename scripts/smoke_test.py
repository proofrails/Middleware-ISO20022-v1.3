import os
import time
import json
import requests

BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

def main():
    payload = {
        "tip_tx_hash": "0xdeadbeefc0de01",
        "chain": "coston2",
        "amount": "0.000000000000000001",  # very small FLR as requested
        "currency": "FLR",
        "sender_wallet": "0x1111111111111111111111111111111111111111",
        "receiver_wallet": "0x2222222222222222222222222222222222222222",
        "reference": "demo:tip:tiny-coston2-1",
    }

    print("POST /v1/iso/record-tip ...")
    r = requests.post(f"{BASE}/v1/iso/record-tip", json=payload, timeout=30)
    print("Status:", r.status_code)
    print("Body:", r.text)
    r.raise_for_status()
    rid = r.json()["receipt_id"]
    print("receipt_id:", rid)

    # Wait background task
    time.sleep(12)

    print(f"GET /v1/iso/receipts/{rid} ...")
    rec = requests.get(f"{BASE}/v1/iso/receipts/{rid}", timeout=30)
    print("Status:", rec.status_code)
    print("Body:", rec.text)
    rec.raise_for_status()
    rec_json = rec.json()

    bundle_url = rec_json.get("bundle_url")
    xml_url = rec_json.get("xml_url")
    print("bundle_url:", bundle_url)
    print("xml_url:", xml_url)

    if bundle_url:
        full_bundle_url = f"{BASE}{bundle_url}"
        print("POST /v1/iso/verify ...")
        v = requests.post(f"{BASE}/v1/iso/verify", json={"bundle_url": full_bundle_url}, timeout=60)
        print("Status:", v.status_code)
        print("Body:", v.text)
    else:
        print("No bundle_url available to verify.")

if __name__ == "__main__":
    main()
