# Mac OCR Service

One job: **OCR an image**. HTTP API that accepts the LiteLLM-normalized OCR input Exocort sends and returns a Mistral-style OCR payload using the native macOS Vision framework. The service follows the Mistral OCR response shape so Exocort can treat it as a Mistral-style OCR backend.

## Endpoint

- **POST /v1/ocr**
  Expected request format used by Exocort/LiteLLM: JSON with `document.type = "image_url"`
  and `document.image_url` as a base64 `data:image/...` URI.
  `model` is optional and ignored.
  Expected response format:

```json
{
  "pages": [
    {
      "index": 0,
      "markdown": "recognized text",
      "images": []
    }
  ],
  "model": "mac-ocr",
  "usage_info": {
    "pages_processed": 1,
    "doc_size_bytes": 12345
  },
  "document_annotation": null,
  "object": "ocr"
}
```
- **GET /health** — readiness.

This is the OCR format Exocort expects when it sends images through LiteLLM-compatible endpoints.

## Run

From `services/mac_ocr`:

```bash
uv sync
uv run mac-ocr-service
```

Config: copy `.env.example` to `.env` and adjust. Keys: `MAC_OCR_HOST`, `MAC_OCR_PORT`, `MAC_OCR_RELOAD`, `MAC_OCR_LOG_LEVEL`.
