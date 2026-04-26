# MBG : Multimodal Bridge Generator for Unstructured Document Extraction
Enterprises talk about AI integration, but most of their data is still locked in unstructured formats like PDFs, images, and slides. Feeding raw documents directly into LLMs leads to high token costs, inconsistent outputs, and poor scalability. MBG (Multimodal Bridge Generator) is an open-source VLM-powered pipeline that bridges unstructured data into structured, schema-aware formats, making them easier, cheaper, and more reliable to use with LLM systems. It includes multi-provider routing (Claude, GPT-4V, Gemini), batch processing, and confidence scoring for production-oriented workflows.

# VISIONARY API

**Multimodal unstructured data → structured formats, at API scale.**

Transform images, PDFs, and web pages into production-ready structured JSON using SOTA vision models (Claude, GPT-4V, Gemini) — with automatic provider routing, batch processing, and schema validation.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         VISIONARY API                                │
│                                                                     │
│  POST /v1/extract          →  Sync extraction (returns immediately) │
│  POST /v1/batch            →  Async batch (returns job_id)          │
│  GET  /v1/jobs/{id}        →  Poll results                          │
│  GET  /v1/templates        →  11 built-in templates                 │
│  GET  /v1/providers        →  Provider status                       │
│  GET  /health              →  Health check                          │
└─────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   Anthropic Claude      OpenAI GPT-4o      Google Gemini
   (primary default)     (fallback)         (fallback)
```

---

## Quickstart

### 1. Configure
```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY (or OPENAI_API_KEY or GOOGLE_API_KEY)
# Set API_KEYS to your service keys
```

### 2. Run
```bash
# Local
pip install -r requirements.txt
uvicorn app.main:app --reload

# Docker
docker compose up
```

### 3. Extract
```bash
curl -X POST http://localhost:8000/v1/extract \
  -H "X-API-Key: vk_dev_testkey_1234" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": [{"type": "image_url", "data": "https://example.com/invoice.jpg"}],
    "extraction": {"mode": "template", "template": "invoice"},
    "model": {"provider": "auto"}
  }'
```

---

## Extraction Modes

| Mode | Description | When to use |
|---|---|---|
| `auto` | Model infers optimal structure | Unknown documents |
| `schema` | Validate against your JSON Schema | Known, typed output |
| `template` | 11 built-in templates | Standard doc types |
| `table` | Forced tabular extraction | Spreadsheets, grids |
| `key_value` | Flat KV extraction | Simple forms |
| `raw` | Markdown transcription | OCR-style extraction |

---

## Built-in Templates

`invoice` · `receipt` · `resume` · `business_card` · `id_document` · `contract` · `medical_report` · `form` · `table_data` · `chart_data` · `product_label`

---

## Supported Inputs

| Type | Description |
|---|---|
| `image_url` | Public image URL (JPEG, PNG, WebP, GIF) |
| `image_base64` | Base64-encoded image |
| `pdf_url` | Public PDF URL |
| `pdf_base64` | Base64-encoded PDF |
| `web_url` | Web page URL (fetched + extracted) |

Up to **10 inputs per request** (multi-page support).

---

## Python SDK

```python
from sdk.visionary import VisionaryClient, ExtractionMode, TemplateType

async with VisionaryClient(api_key="vk_...") as client:

    # Extract invoice from URL
    result = await client.extract_url(
        "https://example.com/invoice.pdf",
        mode=ExtractionMode.TEMPLATE,
        template=TemplateType.INVOICE,
        confidence_threshold=0.7,
    )
    print(result.data)
    print(result.low_confidence_fields)

    # Batch processing
    job = await client.batch_extract(
        [{"id": "r1", "url": "https://..."}, {"id": "r2", "url": "https://..."}],
        mode=ExtractionMode.TEMPLATE,
        template=TemplateType.RECEIPT,
        concurrency=10,
    )
    await job.wait(poll_interval=2.0, on_progress=lambda j: print(j.progress_pct))
    results = await job.results()
```

---

## Response Structure

```json
{
  "id": "uuid",
  "status": "completed",
  "result": {
    "data": { /* extracted structured data */ },
    "confidence": {
      "field_name": { "score": 0.97, "is_low_confidence": false }
    },
    "schema_valid": true,
    "low_confidence_fields": [],
    "extraction_mode": "template",
    "pages_processed": 1
  },
  "usage": {
    "input_tokens": 1500,
    "output_tokens": 300,
    "total_tokens": 1800,
    "provider": "anthropic",
    "model": "claude-opus-4-5",
    "latency_ms": 1842.3
  }
}
```

---

## Configuration

| Env var | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Claude Vision API key |
| `OPENAI_API_KEY` | — | GPT-4V API key |
| `GOOGLE_API_KEY` | — | Gemini API key |
| `API_KEYS` | `["vk_dev_..."]` | Service API keys (JSON array) |
| `DEFAULT_PROVIDER` | `auto` | anthropic / openai / google / auto |
| `RATE_LIMIT_RPM` | `60` | Requests per minute per key |
| `RATE_LIMIT_BURST` | `10` | Burst allowance |
| `REDIS_URL` | — | Redis for job persistence (optional) |
| `MAX_BATCH_SIZE` | `50` | Max items per batch |
| `MAX_RETRIES` | `3` | Per-item retry count |
| `JOB_TTL_SECONDS` | `3600` | Job retention (1 hour) |

---

## Architecture Notes

- **Zero-dependency fallback**: In-memory job store if Redis isn't configured. Swap to Redis via `REDIS_URL` for multi-instance deployments.
- **Provider abstraction**: Adding a new vision model = implement `VisionProvider` (3 methods). Zero changes to routing logic.
- **Token-bucket rate limiter**: Per-API-key, configurable RPM and burst. Middleware-level, before any business logic.
- **Exponential backoff**: Per batch item, up to `MAX_RETRIES` attempts with 2^n second wait.
- **HMAC webhooks**: SHA-256 signed payloads. Verified with `X-VISIONARY-Signature` header.

---

## Dashboard

Open `dashboard.html` in a browser for an interactive API explorer. Configure your base URL and API key in the header bar.

---

## Tests

```bash
pytest tests/ -v --no-cov        # All 67 tests
pytest tests/test_extraction_engine.py  # Unit tests only
pytest tests/test_api.py         # Integration tests only
```

---

## Production Deployment

```bash
# Build image
docker build -t visionary-api .

# Run with Redis
ANTHROPIC_API_KEY=sk-ant-... \
API_KEYS='["vk_prod_your_key"]' \
REDIS_URL=redis://redis:6379/0 \
docker compose up -d
```

For TLS termination, enable the nginx profile: `docker compose --profile production up -d`
