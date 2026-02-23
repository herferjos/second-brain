import json
import os
import logging
import time
from threading import BoundedSemaphore, Lock
from typing import Optional

from api.config import settings

logger = logging.getLogger("second_brain.llm")
LOCATION_RULE = (
    "LOCATION RULE:\n"
    "- The 'category' value may be empty (save in vault root) OR a relative subfolder.\n"
    "- If you want to append to an existing note, you may set 'category' to a relative file path ending in .md.\n"
    "- Never use absolute paths. Never use '..'.\n"
    "- Prefer shallow structure and rely on links/tags inside Markdown instead of deep folders.\n"
)

_inference_slots = BoundedSemaphore(
    value=max(1, settings.LLM_MAX_CONCURRENT_PREDICTIONS)
)
_model = None
_model_lock = Lock()
_openai_client = None
_openai_lock = Lock()


def _normalize_provider(value: str) -> str:
    p = (value or "").strip().lower()
    if p in {"local", "llama", "llama_cpp", "llamacpp"}:
        return "local"
    if p in {"openai", "cloud", "api"}:
        return "openai"
    return "local"


def _get_openai_client():
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    with _openai_lock:
        if _openai_client is not None:
            return _openai_client

        api_key = (settings.LLM_API_KEY or os.getenv("OPENAI_API_KEY", "")).strip()
        if not api_key:
            raise ValueError("Missing LLM_API_KEY for LLM_PROVIDER=openai")

        try:
            from openai import OpenAI
        except Exception as e:
            raise RuntimeError("OpenAI client not installed. Add 'openai' to requirements.") from e

        kwargs = {"api_key": api_key}
        base_url = (settings.LLM_BASE_URL or os.getenv("OPENAI_BASE_URL", "")).strip()
        if base_url:
            kwargs["base_url"] = base_url

        _openai_client = OpenAI(**kwargs)
        return _openai_client


def get_model():
    global _model

    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        try:
            from llama_cpp import Llama
        except Exception as e:
            raise RuntimeError(
                "Local LLM provider requires llama-cpp-python. Install it or switch LLM_PROVIDER=openai."
            ) from e

        if not os.path.exists(settings.LLM_MODEL_PATH):
            raise FileNotFoundError(
                f"LLM model file not found: {settings.LLM_MODEL_PATH}"
            )

        logger.info(
            "Loading local GGUF model | path=%s | ctx=%d | gpu_layers=%d | threads=%d | batch=%d",
            settings.LLM_MODEL_PATH,
            settings.LLM_CONTEXT_LENGTH,
            settings.LLM_N_GPU_LAYERS,
            settings.LLM_THREADS,
            settings.LLM_BATCH_SIZE,
        )

        llama_kwargs = {
            "model_path": settings.LLM_MODEL_PATH,
            "n_ctx": settings.LLM_CONTEXT_LENGTH,
            "n_threads": settings.LLM_THREADS,
            "n_gpu_layers": settings.LLM_N_GPU_LAYERS,
            "n_batch": settings.LLM_BATCH_SIZE,
            "flash_attn": settings.LLM_FLASH_ATTENTION,
            "use_mmap": settings.LLM_USE_MMAP,
            "offload_kqv": settings.LLM_OFFLOAD_KQV,
            "verbose": False,
        }
        if settings.LLM_SEED is not None:
            llama_kwargs["seed"] = settings.LLM_SEED

        try:
            _model = Llama(**llama_kwargs)
        except TypeError as e:
            logger.warning("Some advanced llama.cpp args are unsupported: %s", e)
            for arg in ("flash_attn", "offload_kqv"):
                llama_kwargs.pop(arg, None)
            _model = Llama(**llama_kwargs)

        logger.info("Local GGUF model loaded")
        return _model


def warmup_model() -> bool:
    try:
        provider = _normalize_provider(settings.LLM_PROVIDER)
        if provider == "openai":
            _get_openai_client()
        else:
            get_model()
        return True
    except Exception:
        logger.exception("LLM warmup failed")
        return False


def load_skill():
    vault_skill = os.path.join(settings.VAULT_PROMPTS_PATH, "_sb_skill.md")
    if os.path.exists(vault_skill):
        with open(vault_skill, "r", encoding="utf-8") as f:
            return f.read()

    return "You are a Second Brain Expert. Organize content efficiently."


def format_session_context(activities: list) -> str:
    context = "Captured Session Activity:\n"
    for i, act in enumerate(activities, 1):
        context += f"\n--- Activity {i} ---\n"
        context += f"URL: {act.get('url')}\n"
        context += f"Title: {act.get('title')}\n"
        context += f"Timestamp: {act.get('timestamp')}\n"
        content_snippet = act.get("content", "")[:1000].replace("\n", " ")
        context += f"Content Snippet: {content_snippet}...\n"

        if act.get("events"):
            context += f"Interaction Events: {json.dumps(act.get('events'))}\n"

    return context


def _extract_json_object(raw: str) -> Optional[dict]:
    raw = (raw or "").strip()
    if not raw:
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None


def run_json_completion(
    messages: list[dict],
    *,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> Optional[dict]:
    provider = _normalize_provider(settings.LLM_PROVIDER)
    max_tokens = max_tokens or settings.LLM_MAX_TOKENS

    if provider == "openai":
        client = _get_openai_client()

        try:
            with _inference_slots:
                resp = client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
            content = resp.choices[0].message.content
            return _extract_json_object(content)
        except Exception as e:
            logger.warning("OpenAI JSON mode failed, retrying without response_format: %s", e)
            fallback_messages = list(messages) + [
                {
                    "role": "user",
                    "content": "Return ONLY a JSON object. No prose, no markdown, no code fences.",
                }
            ]
            with _inference_slots:
                resp = client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=fallback_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            content = resp.choices[0].message.content
            return _extract_json_object(content)

    model = get_model()
    with _inference_slots:
        result = model.create_chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

    content = result["choices"][0]["message"]["content"]
    return _extract_json_object(content)


def process_session_with_llm(session_data: dict, job_id: str = "unknown") -> dict:
    skill_content = load_skill()

    started_at = time.perf_counter()
    request_type = "unknown"
    if "activities" in session_data:
        activities = session_data.get("activities", [])
        request_type = "session"
        if not activities:
            logger.warning("LLM request skipped: empty activities | job_id=%s", job_id)
            return None
        user_context = format_session_context(activities)
        prompt_instruction = """
TASK:
1. Analyze the session history above. Identify the user's INTENT.
2. FILTER out noise.
3. SYNTHESIZE the valuable information into a SINGLE atomic Markdown entry.
4. Return ONLY a valid JSON object with these exact keys:
   - category (string)
   - filename (string ending in .md)
   - content (string in Markdown)
5. Do not include any other keys or extra text.
"""

    elif "transcription" in session_data:
        transcription = session_data.get("transcription", "")
        request_type = "audio"
        if not transcription:
            logger.warning("LLM request skipped: empty transcription | job_id=%s", job_id)
            return None
        user_context = f"TRANSCRIPTION OF AUDIO RECORDING:\n\n{transcription}"
        prompt_instruction = """
TASK:
1. Analyze the audio transcription above.
2. IDENTIFY if it is a meeting, a voice note, a lecture, or a conversation.
3. EXTRACT key points, decisions, and action items.
4. FORMAT it as a structured note.
5. Return ONLY a valid JSON object with these exact keys:
   - category (string)
   - filename (string ending in .md)
   - content (string in Markdown)
6. Do not include any other keys or extra text.
"""
    else:
        logger.warning("LLM request skipped: unsupported payload | job_id=%s", job_id)
        return None

    messages = [
        {"role": "system", "content": skill_content},
        {
            "role": "user",
            "content": user_context + "\n" + LOCATION_RULE + "\n" + prompt_instruction,
        },
    ]

    try:
        logger.info("LLM inference started | job_id=%s | type=%s", job_id, request_type)
        parsed = run_json_completion(messages, temperature=0.2, max_tokens=settings.LLM_MAX_TOKENS)

        if not parsed:
            logger.error("LLM inference failed: invalid JSON output | job_id=%s", job_id)
            return None

        required = {"category", "filename", "content"}
        if not required.issubset(parsed.keys()):
            logger.error("LLM inference failed: missing required keys | job_id=%s", job_id)
            return None

        logger.info("LLM inference completed | job_id=%s | type=%s", job_id, request_type)
        return {
            "category": str(parsed["category"]),
            "filename": str(parsed["filename"]),
            "content": str(parsed["content"]),
        }

    except Exception:
        logger.exception("Error processing with LLM | job_id=%s | type=%s", job_id, request_type)
        return None
    finally:
        logger.info(
            "LLM inference finished | job_id=%s | type=%s | duration_ms=%d",
            job_id,
            request_type,
            int((time.perf_counter() - started_at) * 1000),
        )
