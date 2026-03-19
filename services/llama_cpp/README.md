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

Environment variables:

- `LLAMA_CPP_MODEL_PATH`: path to a `.gguf` file (preferred)
- `LLAMA_CPP_MODEL_ID`: Hugging Face repo id for auto-download
- `LLAMA_CPP_MODEL_FILE`: if the repo has multiple `.gguf` files, choose one
- `LLAMA_CPP_MODEL_DIR`: download target directory (default `./models`)
- `LLAMA_CPP_REVISION`: optional HF revision
- `LLAMA_CPP_CTX`: context size (default 4096)
- `LLAMA_CPP_N_GPU_LAYERS`: GPU layers (default 0)
- `LLAMA_CPP_THREADS`: CPU threads (default 0 = llama.cpp default)
- `LLAMA_CPP_TEMPERATURE`: default temperature (default 0.2)
- `LLAMA_CPP_HOST`: bind host (default 127.0.0.1)
- `LLAMA_CPP_PORT`: bind port (default 9100)

Running

From `services/llama_cpp`:

```bash
uv sync
uv run llama-cpp-service
```

If the model file is not present locally and `LLAMA_CPP_MODEL_ID` is set, the
service will download the `.gguf` files from Hugging Face on startup.
