import os
from api.config import settings


def save_to_brain(llm_response: dict):
    """
    Save the content in the Second Brain following the MASTER SPEC.
    Distinguish between folders (05, 06, 12, 14, 16, 17) and root files (00-04, 07-11, 13, 15, 18).
    """
    category = llm_response.get("category", "06_knowledge")
    filename = llm_response.get("filename", "untitled.md")
    content = llm_response.get("content", "")

    # Case 1: The category is a root file (e.g. 07_decision_log.md)
    if category.endswith(".md"):
        target_path = os.path.join(settings.BRAIN_PATH, category)
        # If it is a log, append the new entry at the end
        with open(target_path, "a", encoding="utf-8") as f:
            f.write("\n\n" + content)
        return target_path

    # Case 2: The category is a folder (e.g. 06_knowledge)
    else:
        # Ensure the filename is clean
        clean_filename = os.path.basename(filename)
        if not clean_filename.endswith(".md"):
            clean_filename += ".md"

        target_path = os.path.join(settings.BRAIN_PATH, category, clean_filename)

        # Create subdirectories if the LLM specifies a path (e.g. 06_knowledge/ai/file.md)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        return target_path
