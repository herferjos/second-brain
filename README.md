# Mind-Log: Setup Guide

This system monitors your activity and generates automatic notes in Obsidian using a local LLM.

## 1. Requirements
- **Python 3.9+**
- **Chrome Browser**
- **LM Studio** (running with the local server on port 1234)
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
1. **LM Studio**: Start LM Studio on your machine and ensure the model **gemma-3n-e2b-it** is downloaded. Start the local server (port 1234). The API will auto-load this model on startup (32768 context).
2. From the project root:
   ```bash
   docker compose up --build
   ```
3. The API runs at `http://localhost:8000`. Whisper (transcription) and the LLM model are loaded automatically when the container starts.
4. **Optional env vars** (in `docker-compose.yml` or `.env`):
   - `LM_STUDIO_URL` — LM Studio base URL (default: `http://host.docker.internal:1234/v1`)
   - `LLM_MODEL` — Model key to load (default: `gemma-3n-e2b-it`)
   - `LLM_CONTEXT_LENGTH` — Context length in tokens (default: `32768`)

The `second_brain/` folder is mounted as a volume so notes persist across container restarts.

## 3. Extension Installation
1. Open Chrome and go to `chrome://extensions/`.
2. Enable **Developer mode** (top right corner).
3. Click on **Load unpacked**.
4. Select the `extension/` folder from this project.

## 4. Usage
- Make sure you have a model loaded in **LM Studio** and the "Local Server" is active.
- The extension will automatically send a summary of your activity every 5 minutes.
- The notes will appear in your Obsidian folder in organized Markdown format.

## Generated Note Structure
The system is configured for the LLM to organize the information into:
- `# Activity Summary`
- `# Knowledge Extracted`
- `# Actions and Context`
- YAML Metadata (date, url, tags).
