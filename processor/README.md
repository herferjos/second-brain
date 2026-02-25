# Processor – LLM Obsidian Vault Generator

Reads `data/events/*.jsonl` and generates an Obsidian-style Markdown vault: concept notes from web/audio events and optional reflection questions. Supports local llama.cpp, OpenAI, and Gemini as LLM backends.

## Flow (high level)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  run.py (CLI)                                                                │
│  --day / --from --to / (all days from data/events/*.jsonl)                   │
└───────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  pipeline.run_pipeline()                                                     │
│  1. init_db(vault_dir) → vault/.src/state.sqlite                             │
│  2. ingest_jsonl(events_dir, days) → events in SQLite (unless --rebuild)     │
│  3. get_client(provider) → LLM (llama_cpp | openai | gemini)                │
│  4. get_events_by_day() for each day                                         │
└───────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  OrchestratorAgent.create_plan(all_events)                                   │
│  Builds timeline string → LLM → Plan (list of Task)                           │
│  Task types: CREATE_OR_UPDATE_NOTE | GENERATE_QUESTIONS                       │
│  Tasks have: task_id, dependencies, related_event_ids                        │
└───────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  _execute_plan(plan, llm, db_path, vault_dir, …)                             │
│  ThreadPoolExecutor: run tasks in parallel when dependencies are satisfied   │
└───────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
┌──────────────────────────────┐     ┌──────────────────────────────┐
│  CREATE_OR_UPDATE_NOTE       │     │  GENERATE_QUESTIONS           │
│  WorkerAgent                 │     │  WorkerAgent                  │
│  • get_events_by_id()        │     │  • Read concept note          │
│  • Load text from meta.      │     │  • LLM → questions markdown   │
│    text_path (data dir)      │     │  • write vault/Questions/     │
│  • LLM extract concept name  │     │  • set_artifact()             │
│  • render_page_note() (LLM)  │     └──────────────────────────────┘
│  • write vault/Concepts/     │
│  • upsert_concept(),         │
│    set_artifact()            │
└──────────────────────────────┘
```

**Data flow:**

- **Input:** `PROCESSOR_DATA_DIR/events/YYYY-MM-DD.jsonl` (events with `id`, `ts`, `type`, `meta`, etc.).
- **State:** `PROCESSOR_VAULT_DIR/.src/state.sqlite` — ingested files (last line), events, concepts, artifacts (content_sha for idempotency).
- **Output:** `PROCESSOR_VAULT_DIR/Concepts/<slug>.md`, `PROCESSOR_VAULT_DIR/Questions/<slug>.md`. Daily note rendering exists in code (`vault.render.render_daily_note`) but is not invoked by the current pipeline.

## Setup

1. Install dependencies (from repo root or from `processor/`):

   ```bash
   pip install -r processor/requirements.txt
   ```

2. Create env file:

   ```bash
   cp processor/.env.example processor/.env
   ```

3. Configure LLM provider in `.env` (see below).

## Running

```bash
# One day
python processor/run.py --day 2026-02-24

# Date range
python processor/run.py --from 2026-02-01 --to 2026-02-24

# Force provider
python processor/run.py --day 2026-02-24 --provider gemini

# Rebuild vault outputs without re-ingesting
python processor/run.py --day 2026-02-24 --rebuild

# Dry run (no writes)
python processor/run.py --day 2026-02-24 --dry-run
```

## LLM backends

### Local GGUF (default)

Uses [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) and a local `.gguf` file. No API key or server needed.

1. Install dependencies (includes `llama-cpp-python`):

   ```bash
   pip install -r processor/requirements.txt
   ```

2. In `processor/.env` set the path to your model:

   ```bash
   LLM_PROVIDER=llama_cpp
   LLM_MODEL_PATH=/path/to/your/model.gguf
   # Optional: LLM_CONTEXT_LENGTH=4096 LLM_N_GPU_LAYERS=-1 LLM_THREADS=4
   ```

### OpenAI

Set in `.env`:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

### Gemini

Set in `.env`:

```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash
```

## Quick smoke test

From the project root, run a dry run (no files written):

```bash
python processor/run.py --day 2026-02-24 --dry-run
```

Configure your LLM provider in `processor/.env` before a real run.

## Output layout

- `vault/Concepts/<slug>.md` – concept notes (from web/audio content)
- `vault/Questions/<slug>.md` – reflection questions per concept
- `vault/.src/state.sqlite` – incremental state (ingestion, artifacts, concepts)

`Daily/YYYY-MM-DD.md` and topic/source paths are defined in `storage/paths.py` / `vault/render.py` but only Concepts and Questions are written by the current pipeline.

## Module overview

| Package / module | Role |
|------------------|------|
| `run.py` | CLI; parses dates, calls `pipeline.run_pipeline()` |
| `src/pipeline.py` | Ingest → LLM client → orchestrator plan → execute tasks (thread pool) |
| `src/domain/` | **Data shapes:** `events.py` (normalize, get_events_by_id), `models.py` (Task, Plan, Concept, GeneratedQuestions) |
| `src/agents/` | **LLM actors:** `orchestrator.py` (timeline → Plan), `worker.py` (CREATE_OR_UPDATE_NOTE, GENERATE_QUESTIONS) |
| `src/storage/` | **Persistence:** `state_db.py` (SQLite), `writer.py` (idempotent writes), `paths.py` (Daily, Concepts, Questions) |
| `src/vault/` | **Markdown:** `render.py` (render_page_note, render_daily_note), `prompts.py` (all prompt templates) |
| `src/llm/` | `get_client()` → llama_cpp, openai, or gemini (with retry) |
| `src/settings.py` | Env-based config |
| `src/util.py` | slugify, sha256_text, etc. |
