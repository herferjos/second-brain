import os
import logging

from api.config import settings

logger = logging.getLogger("second_brain.brain_manager")

_DEFAULT_RELATIVE_PATH = "untitled.md"


def _normalize_relative_path(raw_path: str) -> str:
    raw_path = (raw_path or "").replace("\\", "/").strip()
    if not raw_path:
        return ""

    raw_path = raw_path.lstrip("/")

    parts = [p.strip() for p in raw_path.split("/") if p.strip() and p.strip() != "."]
    if not parts or any(p == ".." for p in parts):
        logger.warning("Unsafe path from LLM blocked: %s", raw_path)
        return ""

    return "/".join(parts)


def _safe_target(relative_path: str) -> str:
    vault_root = os.path.abspath(settings.VAULT_PATH)
    target_path = os.path.abspath(os.path.join(vault_root, relative_path))
    if os.path.commonpath([vault_root, target_path]) != vault_root:
        logger.warning(
            "Blocked unsafe target path '%s'. Falling back to %s",
            relative_path,
            _DEFAULT_RELATIVE_PATH,
        )
        return os.path.join(vault_root, _DEFAULT_RELATIVE_PATH)
    return target_path


def save_to_brain(llm_response: dict):
    explicit_path = _normalize_relative_path(str(llm_response.get("path", "")))
    category = _normalize_relative_path(str(llm_response.get("category", "")))
    filename = llm_response.get("filename", "untitled.md")
    content = llm_response.get("content", "")
    write_mode = str(llm_response.get("write_mode", "")).strip().lower()

    if explicit_path:
        rel_path = explicit_path
        if not rel_path.endswith(".md"):
            rel_path += ".md"
        target_path = _safe_target(rel_path)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        mode = "a" if write_mode == "append" else "w"
        with open(target_path, mode, encoding="utf-8") as f:
            if mode == "a" and content:
                f.write("\n\n" + content)
            else:
                f.write(content)
        logger.info("Saved LLM output | path=%s | mode=%s", target_path, mode)
        return target_path

    if category.endswith(".md"):
        target_path = _safe_target(category)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "a", encoding="utf-8") as f:
            if content:
                f.write("\n\n" + content)
        logger.info("Appended LLM output in markdown file | path=%s", target_path)
        return target_path

    clean_filename = os.path.basename(str(filename).replace("\\", "/").strip())
    if not clean_filename:
        clean_filename = _DEFAULT_RELATIVE_PATH
    if not clean_filename.endswith(".md"):
        clean_filename += ".md"

    rel_path = clean_filename if not category else os.path.join(category, clean_filename)
    target_path = _safe_target(rel_path)

    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    with open(target_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info("Saved LLM output | path=%s", target_path)
    return target_path
