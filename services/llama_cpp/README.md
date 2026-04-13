# Llama.cpp service

Minimal HTTP service that exposes an OpenAI-compatible chat completion endpoint
backed by `llama-cpp-python`.

Endpoint

- `POST /v1/chat/completions`

Request JSON (subset):

- `messages`: list of `{ role, content }`
- `temperature`, `max_tokens`, `top_p`, `stop`
- `stream` is rejected (non-streaming only)

Response JSON:

Matches the OpenAI `chat.completions` schema with `choices[]` and `usage`.

Configuration

`config.yaml` keys:

- `model_id`: required Hugging Face repo id for auto-download (e.g. `TheBloke/Mistral-7B-Instruct-v0.2-GGUF`)
- `quantization`: required quantization level of the model to download (e.g. `Q4_K_M`)
- `model_dir`: download target directory (default `./models`)
- `n_ctx`: context size (default 4096)
- `n_gpu_layers`: GPU layers (default 0)
- `n_threads`: CPU threads (default 0 = llama.cpp default)
- `n_batch`: batch size (default 512)
- `seed`: seed for reproducibility (default 42)
- `temperature`: default temperature (default 0.2)
- `host`: bind host (default 127.0.0.1)
- `port`: bind port (default 9100)
- `reload`: enable `uvicorn` reload in local development (default `true`)

Running

From `services/llama_cpp`:

```bash
uv sync
uv run llama-cpp-service
```

Use `example.yaml` as the base for `config.yaml` before running. The example file includes the code defaults for optional runtime knobs and sample values for the required model settings.

If the model file is not present locally, the service will download the specified
quantization of the model from Hugging Face on startup.

Testing
-------

You can test the chat completions endpoint with `curl`:

```bash
curl -X POST http://127.0.0.1:9100/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{
  "messages": [
    {
      "role": "user",
      "content": "Hello! Can you tell me a joke?"
    }
  ],
  "temperature": 0.7,
  "max_tokens": 100
}'
```
