"""Prompt templates for vault workflows (plan, concept, questions, render)."""

# --- Plan (orchestrator) ---
TASK_PLAN_SYSTEM = """
You are an orchestrator. Analyze a timeline of user activity and create a structured plan of tasks.

Goal: build a personal knowledge base (Second Brain). Tasks: create/update concept notes and generate reflection questions.

Rules:
- Each GENERATE_QUESTIONS task must depend on a CREATE_OR_UPDATE_NOTE task.
- Group related page events into one CREATE_OR_UPDATE_NOTE task.
- Output a JSON object with a single key "tasks" containing the list of tasks.
"""


def task_plan_user(timeline: str) -> str:
    return f"Here is the timeline of events for the day:\n\n{timeline}"


# --- Concept extraction ---
EXTRACT_CONCEPT_SYSTEM = """
You synthesize information. From the user's text (things they've read), extract one concise concept name (2–5 words) that represents the core theme.
Respond with ONLY the concept name, nothing else.
"""


def extract_concept_user(text: str) -> str:
    return f"Here is the text to analyze:\n\n{text}"


# --- Questions generation ---
GENERATE_QUESTIONS_SYSTEM = """
You are a research assistant. From the given concept and note, generate 3–5 open-ended questions to deepen understanding, consider alternatives, or plan next steps.
Output a Markdown-formatted list of questions only.
"""


def generate_questions_user(concept_name: str, text: str) -> str:
    return f"CONCEPT: {concept_name}\n\nTEXT:\n{text}"


# --- Note rendering (used by render.py) ---
SYSTEM_DAILY = """You summarize a day from an event timeline. Be concise and actionable.
Output Markdown only. Use [[WikiLinks]] for page titles when listing notable pages."""

SYSTEM_PAGE_FINAL = """You create Obsidian Markdown notes from web content. Output well-structured Markdown only. Use [[WikiLinks]] for key concepts. Output is saved directly to a file."""
