import os
import logging

from api.config import settings, BRAIN_STRUCTURE

logger = logging.getLogger("second_brain.brain_manager")

_ALLOWED_ROOTS = set(BRAIN_STRUCTURE)
_DEFAULT_CATEGORY = "00_inbox"


def _normalize_category(raw_category: str) -> str:
    """
    Keep only valid categories rooted in configured Brain folders.
    """
    category = (raw_category or "").replace("\\", "/").strip().strip("/")
    if not category:
        logger.warning("Empty category from LLM. Falling back to %s", _DEFAULT_CATEGORY)
        return _DEFAULT_CATEGORY

    parts = [part.strip() for part in category.split("/") if part.strip()]
    if not parts or any(part == ".." for part in parts):
        logger.warning(
            "Unsafe category from LLM: %s. Falling back to %s",
            raw_category,
            _DEFAULT_CATEGORY,
        )
        return _DEFAULT_CATEGORY

    root_index = next((i for i, part in enumerate(parts) if part in _ALLOWED_ROOTS), None)
    if root_index is None:
        logger.warning(
            "Unknown category from LLM: %s. Falling back to %s",
            raw_category,
            _DEFAULT_CATEGORY,
        )
        return _DEFAULT_CATEGORY

    normalized = "/".join(parts[root_index:])
    if normalized != category:
        logger.warning(
            "Category normalized from '%s' to '%s'",
            raw_category,
            normalized,
        )
    return normalized


def _safe_target(relative_path: str) -> str:
    brain_root = os.path.abspath(settings.BRAIN_PATH)
    target_path = os.path.abspath(os.path.join(brain_root, relative_path))
    if os.path.commonpath([brain_root, target_path]) != brain_root:
        logger.warning(
            "Blocked unsafe target path '%s'. Falling back to %s/untitled.md",
            relative_path,
            _DEFAULT_CATEGORY,
        )
        return os.path.join(brain_root, _DEFAULT_CATEGORY, "untitled.md")
    return target_path


def save_to_brain(llm_response: dict):
    """
    Save content in a valid Second Brain location.
    Invalid or unknown categories are redirected to 00_inbox.
    """
    category = _normalize_category(str(llm_response.get("category", "")))
    filename = llm_response.get("filename", "untitled.md")
    content = llm_response.get("content", "")

    # Case 1: The category points directly to a markdown file path.
    if category.endswith(".md"):
        target_path = _safe_target(category)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "a", encoding="utf-8") as f:
            f.write("\n\n" + content)
        logger.info("Saved LLM output in markdown file | path=%s", target_path)
        return target_path

    # Case 2: The category is a folder (e.g. 10_network/meetings).
    else:
        clean_filename = os.path.basename(str(filename).replace("\\", "/"))
        if not clean_filename:
            clean_filename = "untitled.md"
        if not clean_filename.endswith(".md"):
            clean_filename += ".md"

        target_path = _safe_target(os.path.join(category, clean_filename))

        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("Saved LLM output in folder | category=%s | path=%s", category, target_path)
        return target_path
