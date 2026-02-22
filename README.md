# Mind-Log: Setup Guide

This system monitors your activity and generates automatic notes in Obsidian using a local LLM.

## 1. Requirements
- **Python 3.9+**
- **Chrome Browser**
- **Docker / Docker Compose**
- **Obsidian** (to view the generated notes)

## 2. API Setup

### Option A: Local (development)
1. Go to the `api/` folder:
   ```bash
   cd api
   ```
2. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the server:
   ```bash
   python main.py
   ```
   *The API will run at `http://localhost:8000`. Notes will be saved in a folder named `second_brain` within this project (you can change the path in `api/config.py`).*

### Option B: Deploy with Docker
1. Create or edit `.env` and set:
   ```bash
   LLM_MODEL_HOST_PATH=/absolute/path/to/your-model.gguf
   LLM_MODEL_PATH=/models/model.gguf
   LLM_MODEL=your-model-id
   ```
2. Ensure that file exists in your host machine.
3. From the project root:
   ```bash
   docker compose up --build
   ```
4. The API runs at `http://localhost:8000`.
5. The model is loaded inside the same FastAPI process from the GGUF path defined in `.env` (no separate LLM API service).
6. **Optional env vars** (in `docker-compose.yml` or `.env`):
   - `LLM_MODEL_HOST_PATH` — Host path of the GGUF mounted by Docker (required)
   - `LLM_MODEL` — Model key/alias used by the app (default: `local-gguf-model`)
   - `LLM_MODEL_PATH` — Path to GGUF inside the container (default: `/models/model.gguf`)
   - `LLM_CONTEXT_LENGTH` — Context length in tokens (default: `32768`)
   - `LLM_N_GPU_LAYERS` — Number of layers offloaded to GPU (default: `30`)
   - `LLM_THREADS` — CPU thread pool size (default: `6`)
   - `LLM_BATCH_SIZE` — Evaluation batch size (default: `512`)
   - `LLM_MAX_CONCURRENT_PREDICTIONS` — Max concurrent inferences (default: `4`)
   - `LLM_FLASH_ATTENTION` — Enable flash attention (default: `true`)
   - `LLM_USE_MMAP` — Enable memory-mapped model loading (default: `true`)
   - `LLM_OFFLOAD_KQV` — Offload KV-related ops to GPU when available (default: `true`)
   - `LLM_SEED` — Optional deterministic seed. If omitted, random seed is used.
7. Notes about parity with LM Studio:
   - `Unified KV Cache` and `K/V Cache Quantization Type` are experimental in LM Studio and do not have a stable 1:1 flag here.
   - `RoPE Frequency Base/Scale` remain in automatic mode unless you set custom rope parameters in code.

The `second_brain/` folder is mounted as a volume so notes persist across container restarts.

## 3. Extension Installation
1. Open Chrome and go to `chrome://extensions/`.
2. Enable **Developer mode** (top right corner).
3. Click on **Load unpacked**.
4. Select the `extension/` folder from this project.

## 4. Usage
- Start the stack with `docker compose up --build`.
- The extension will automatically send a summary of your activity every 5 minutes.
- The notes will appear in your Obsidian folder in organized Markdown format.

## Generated Note Structure
The system is configured for the LLM to organize the information into:
- `# Activity Summary`
- `# Knowledge Extracted`
- `# Actions and Context`
- YAML Metadata (date, url, tags).
