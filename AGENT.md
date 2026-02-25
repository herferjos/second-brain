# Claude Development Guidelines

Please note that all code in this project should be written in English.

Even if you communicate with me in Spanish, I will write the code, comments, and documentation in English to maintain consistency in the codebase.

---

## Imports

**All imports must be at the top of the file.** Do not import inside functions, methods, or `if __name__ == "__main__"` blocks. This keeps dependencies explicit and avoids hidden coupling.

---

## Structure documentation (proactive)

**Whenever the user asks for structural changes** (refactors, new layout, renaming modules, moving code, etc.), you must:

1. **Update this file (AGENT.md)** and record the decisions taken: what the structure is, why, and where things live.
2. Do this **proactively**—do not wait to be asked. After implementing the changes, add or update the relevant section under "Project structure decisions" below.

This keeps the codebase understandable for future work and for the user.

---

## Project structure decisions

### Processor — `processor/src/llm/`

The LLM layer is pluggable and split as follows:

- **`base.py`** — Generic abstract `LLMClient` only. It defines:
  - `generate(system, user, output_model)` (abstract, implemented per backend)
  - High-level methods that use prompts and models: `extract_concept()`, `generate_questions()`, `generate_task_plan_structured()`
  - No inline prompts or Pydantic models; those live in dedicated modules.

- **`models.py`** — All Pydantic models used for LLM structured output. This is the single place for LLM response shapes:
  - `Concept`, `GeneratedQuestions` (concept extraction and question generation).
  - `Task`, `Plan`, `TaskType`, `TaskStatus` (orchestrator task plan). Any new schema returned by the LLM should be added here.

- **`prompts.py`** — All prompt templates and small helpers that build user messages (e.g. `EXTRACT_CONCEPT_SYSTEM`, `GENERATE_QUESTIONS_SYSTEM`, `TASK_PLAN_SYSTEM`, `extract_concept_user()`, `generate_questions_user()`, `task_plan_user()`).

- **Backend clients** — One file per provider, **without** a `_client` suffix in the filename:
  - **`gemini.py`** — `GeminiClient(base.LLMClient)` with provider-specific `generate()`.
  - **`openai.py`** — `OpenAIClient(base.LLMClient)` with provider-specific `generate()`.
  - **`localllama.py`** — `LocalLlamaClient(base.LLMClient)` with provider-specific `generate()`.

- **`__init__.py`** — Exposes `get_client(provider)` which returns the appropriate client (`llama_cpp` | `openai` | `gemini`).

Callers use `get_client()` or `from .llm.base import LLMClient`; they do not import the concrete client modules directly. Pipeline and agent import `Task`, `Plan` from `llm.models`.
