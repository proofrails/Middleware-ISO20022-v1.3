# ISO 20022 Payments Middleware API Documentation

## Overview

The ISO 20022 Payments Middleware is a production-ready system that bridges blockchain transactions with traditional banking standards. It automatically converts blockchain tips into ISO 20022 XML documents, creates cryptographic evidence bundles, and anchors them on the Flare blockchain for immutable audit trails.

## Quick Start

### 1. Start the Server
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Access Interactive Documentation
- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

### 3. Test the API
```bash
# Health check
curl http://127.0.0.1:8000/v1/health

# Record a tip
curl -X POST http://127.0.0.1:8000/v1/iso/record-tip \
  -H "Content-Type: application/json" \
  -d '{
    "tip_tx_hash": "0xabc123",
    "chain": "coston2",
    "amount": "0.001",
    "currency": "FLR",
    "sender_wallet": "0xSender",
    "receiver_wallet": "0xReceiver",
    "reference": "demo:tip:1"
  }'
```

## Core Endpoints

### POST /v1/iso/record-tip
Records a blockchain tip and automatically processes it into ISO 20022 format.

**Request Body:**
```json
{
  "tip_tx_hash": "0xabc123",
  "chain": "coston2",
  "amount": "0.001",
  "currency": "FLR",
  "sender_wallet": "0xSender",
  "receiver_wallet": "0xReceiver",
  "reference": "demo:tip:1",
  "callback_url": "https://your-app.com/callback" // optional
}
```

**Response:**
```json
{
  "receipt_id": "1150292a-4699-46b6-8a0e-60ece78ce8e2",
  "status": "pending"
}
```

### GET /v1/iso/receipts/{id}
Retrieves detailed information about a processed tip receipt.

**Response:**
```json
{
  "id": "1150292a-4699-46b6-8a0e-60ece78ce8e2",
  "status": "anchored",
  "bundle_hash": "0xcc4cdd738ada83b7d7c04fd8d96415dfd78dfe1f0011b3250fcb508f77632f4f",
  "flare_txid": "0x58f6e1b8b8175adb7d1ae164a289d3ff2b6370ea5977cbd65cad05a885a5857b",
  "xml_url": "/files/1150292a-4699-46b6-8a0e-60ece78ce8e2/pain001.xml",
  "bundle_url": "/files/1150292a-4699-46b6-8a0e-60ece78ce8e2/evidence.zip",
  "created_at": "2025-10-05T17:34:24.316407",
  "anchored_at": "2025-10-05T17:34:25.351755"
}
```

### POST /v1/iso/verify
Verifies the integrity of an evidence bundle by checking on-chain anchoring.

**Request Body (Option 1 - Bundle URL):**
```json
{
  "bundle_url": "http://127.0.0.1:8000/files/1150292a-4699-46b6-8a0e-60ece78ce8e2/evidence.zip"
}
```

**Request Body (Option 2 - Bundle Hash):**
```json
{
  "bundle_hash": "0xcc4cdd738ada83b7d7c04fd8d96415dfd78dfe1f0011b3250fcb508f77632f4f"
}
```

**Response:**
```json
{
  "matches_onchain": true,
  "bundle_hash": "0xcc4cdd738ada83b7d7c04fd8d96415dfd78dfe1f0011b3250fcb508f77632f4f",
  "flare_txid": "0x58f6e1b8b8175adb7d1ae164a289d3ff2b6370ea5977cbd65cad05a885a5857b",
  "anchored_at": "2025-10-05T17:34:25.351755",
  "errors": []
}
```

## Additional Endpoints

### GET /v1/health
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "ts": "2025-10-05T18:30:00.000000"
}
```

### GET /v1/iso/events/{id}
Server-Sent Events stream for real-time receipt updates.

**Usage:**
```javascript
const eventSource = new EventSource('/v1/iso/events/1150292a-4699-46b6-8a0e-60ece78ce8e2');
eventSource.onmessage = function(event) {
  const data = JSON.parse(event.data);
  console.log('Receipt update:', data);
};
```

### POST /v1/debug/anchor
Debug endpoint to directly anchor a bundle hash.

**Request Body:**
```json
{
  "bundle_hash": "0xcc4cdd738ada83b7d7c04fd8d96415dfd78dfe1f0011b3250fcb508f77632f4f"
}
```

## UI Endpoints

### GET /receipt/{id}
Live receipt page with real-time updates.

### GET /embed/receipt?rid={id}
Embeddable widget for integration into other applications.

### Static web UI under /web

- `/web/index.html` – public dashboard and self-serve project/API key creation
- `/web/project.html` – per-project dashboard (requires API key)
- `/web/verify.html` – verify bundle URL or hash
- `/web/statements.html` – generate camt.052/053 statements

## Data Models

### TipRecordRequest
```json
{
  "tip_tx_hash": "string",
  "chain": "coston2" | "flare",
  "amount": "number",
  "currency": "string",
  "sender_wallet": "string",
  "receiver_wallet": "string",
  "reference": "string",
  "callback_url": "string" // optional
}
```

### ReceiptResponse
```json
{
  "id": "string (UUID)",
  "status": "pending" | "anchored" | "failed",
  "bundle_hash": "string (0x-prefixed hex)",
  "flare_txid": "string (0x-prefixed hex)",
  "xml_url": "string (relative path)",
  "bundle_url": "string (relative path)",
  "created_at": "string (ISO datetime)",
  "anchored_at": "string (ISO datetime)" // nullable
}
```

### VerifyRequest
```json
{
  "bundle_url": "string (URL)" // OR
  "bundle_hash": "string (0x-prefixed hex)"
}
```

### VerifyResponse
```json
{
  "matches_onchain": "boolean",
  "bundle_hash": "string (0x-prefixed hex)",
  "flare_txid": "string (0x-prefixed hex)", // nullable
  "anchored_at": "string (ISO datetime)", // nullable
  "errors": "array of strings"
}
```

## Error Handling

### HTTP Status Codes
- **200**: Success
- **400**: Bad Request (invalid input)
- **404**: Not Found (receipt not found)
- **422**: Validation Error (invalid data format)
- **500**: Internal Server Error

### Error Response Format
```json
{
  "detail": "Error message",
  "errors": ["specific", "validation", "errors"]
}
```

## Authentication

Currently, the API is open for development. For production deployment, some suggested considerations are:
- API key authentication
- JWT tokens
- OAuth 2.0
- Rate limiting

## Rate Limits

No rate limits are currently implemented. For production, some suggested things to consider:
- 100 requests per minute per IP 
- 1000 requests per hour per API key
- Burst protection for high-volume usage

## Webhooks

The system supports optional webhooks for asynchronous notifications:

### Callback URL
When recording a tip, you can provide a `callback_url` that will receive POST requests when processing completes.

### Callback Payload
```json
{
  "receipt_id": "1150292a-4699-46b6-8a0e-60ece78ce8e2",
  "status": "anchored",
  "bundle_hash": "0xcc4cdd738ada83b7d7c04fd8d96415dfd78dfe1f0011b3250fcb508f77632f4f",
  "flare_txid": "0x58f6e1b8b8175adb7d1ae164a289d3ff2b6370ea5977cbd65cad05a885a5857b",
  "xml_url": "http://127.0.0.1:8000/files/1150292a-4699-46b6-8a0e-60ece78ce8e2/pain001.xml",
  "bundle_url": "http://127.0.0.1:8000/files/1150292a-4699-46b6-8a0e-60ece78ce8e2/evidence.zip",
  "created_at": "2025-10-05T17:34:24.316407",
  "anchored_at": "2025-10-05T17:34:25.351755"
}
```

## Integration Examples

### JavaScript/Node.js
```javascript
const response = await fetch('http://127.0.0.1:8000/v1/iso/record-tip', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    tip_tx_hash: '0xabc123',
    chain: 'coston2',
    amount: '0.001',
    currency: 'FLR',
    sender_wallet: '0xSender',
    receiver_wallet: '0xReceiver',
    reference: 'demo:tip:1'
  })
});

const result = await response.json();
console.log('Receipt ID:', result.receipt_id);
```

### Python
```python
import requests

response = requests.post('http://127.0.0.1:8000/v1/iso/record-tip', json={
    'tip_tx_hash': '0xabc123',
    'chain': 'coston2',
    'amount': '0.001',
    'currency': 'FLR',
    'sender_wallet': '0xSender',
    'receiver_wallet': '0xReceiver',
    'reference': 'demo:tip:1'
})

result = response.json()
print(f"Receipt ID: {result['receipt_id']}")
```

### cURL
```bash
curl -X POST http://127.0.0.1:8000/v1/iso/record-tip \
  -H "Content-Type: application/json" \
  -d '{
    "tip_tx_hash": "0xabc123",
    "chain": "coston2",
    "amount": "0.001",
    "currency": "FLR",
    "sender_wallet": "0xSender",
    "receiver_wallet": "0xReceiver",
    "reference": "demo:tip:1"
  }'
```

## Monitoring and Admin

### Web UI

For day-to-day monitoring and verification, use the web UI served by the API:

- Public dashboard: `/web/index.html`
- Project dashboard: `/web/project.html` (requires API key)
- Verify page: `/web/verify.html`

These UIs consume the same HTTP endpoints documented above.

### Health Monitoring
```bash
# Check server health
curl http://127.0.0.1:8000/v1/health

# Check database connectivity
# Look for "Application startup complete" in server logs
```

## Production Deployment

### Environment Variables
```bash
# Required for anchoring
FLARE_RPC_URL=https://coston2-api.flare.network/ext/C/rpc
ANCHOR_CONTRACT_ADDR=0x262b1C649CE016717c62b9403E719C4801974CeF
ANCHOR_PRIVATE_KEY=0x<your_private_key_here>

# Optional
ANCHOR_LOOKBACK_BLOCKS=1000
WEB_ORIGIN=http://localhost:8501
DATABASE_URL=postgresql://user:pass@localhost/iso_mw
```

### Docker Deployment
```bash
docker compose up --build
```

Services:
- **API**: http://localhost:8000
- **PostgreSQL**: localhost:5432

## Security Considerations

### Data Privacy
- Only cryptographic hashes are stored on-chain
- Sensitive data remains in the database
- Evidence bundles are signed for integrity

### Best Practices
- Use HTTPS in production
- Implement proper authentication
- Monitor for unusual activity
- Regular security audits
- Keep dependencies updated

## Support

For technical support:
- Check the troubleshooting guide
- Review server logs for errors
- Test with debug endpoints
- Verify environment configuration

## License

MIT License - see LICENSE file for details.
