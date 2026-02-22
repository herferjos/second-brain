import json
import os
import logging
import time
from threading import BoundedSemaphore, Lock
from typing import Optional

from llama_cpp import Llama

from api.config import settings, BRAIN_STRUCTURE

logger = logging.getLogger("second_brain.llm")
ALLOWED_CATEGORY_ROOTS = ", ".join(BRAIN_STRUCTURE)
CATEGORY_RULE = (
    "CATEGORY RULE:\n"
    f"- The 'category' value MUST start with one of these roots: {ALLOWED_CATEGORY_ROOTS}\n"
    "- You may append subfolders after the root (e.g. 10_network/meetings).\n"
    "- Do NOT prepend labels like '03_LOGS & ANALYSIS'."
)

_inference_slots = BoundedSemaphore(
    value=max(1, settings.LLM_MAX_CONCURRENT_PREDICTIONS)
)
_model: Optional[Llama] = None
_model_lock = Lock()


def get_model() -> Llama:
    global _model

    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

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
        get_model()
        return True
    except Exception:
        logger.exception("LLM warmup failed")
        return False


def load_skill():
    skill_path = os.path.join(
        settings.BRAIN_PATH, "05_skills", "second_brain_expert.md"
    )
    # Fallback if the skill does not exist in 05_skills
    if not os.path.exists(skill_path):
        return "You are a Second Brain Expert. Organize content efficiently."

    with open(skill_path, "r", encoding="utf-8") as f:
        return f.read()


def format_session_context(activities: list) -> str:
    context = "Captured Session Activity:\n"
    for i, act in enumerate(activities, 1):
        context += f"\n--- Activity {i} ---\n"
        context += f"URL: {act.get('url')}\n"
        context += f"Title: {act.get('title')}\n"
        context += f"Timestamp: {act.get('timestamp')}\n"
        # Limit content to avoid saturating tokens
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


def process_session_with_llm(session_data: dict, job_id: str = "unknown") -> dict:
    """
    Analyze a complete activity session and generate a single synthesized note
    using the in-process GGUF model.
    """
    skill_content = load_skill()

    started_at = time.perf_counter()
    request_type = "unknown"
    # If it is a normal navigation session
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

    # If it is an audio transcription (conversation, voice note, etc.)
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
            "content": user_context + "\n" + CATEGORY_RULE + "\n" + prompt_instruction,
        },
    ]

    try:
        logger.info("LLM inference started | job_id=%s | type=%s", job_id, request_type)
        model = get_model()

        with _inference_slots:
            result = model.create_chat_completion(
                messages=messages,
                temperature=0.2,
                max_tokens=settings.LLM_MAX_TOKENS,
                response_format={"type": "json_object"},
            )

        content = result["choices"][0]["message"]["content"]
        parsed = _extract_json_object(content)

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
        logger.exception("Error processing with local LLM | job_id=%s | type=%s", job_id, request_type)
        return None
    finally:
        logger.info(
            "LLM inference finished | job_id=%s | type=%s | duration_ms=%d",
            job_id,
            request_type,
            int((time.perf_counter() - started_at) * 1000),
        )
