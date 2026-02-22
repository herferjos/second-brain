import requests
import json
import os
from api.config import settings


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


def process_session_with_llm(session_data: dict) -> dict:
    """
    Analyze a complete activity session and generate a single synthesized note.
    Use the OpenAI compatible LM Studio endpoint with JSON Schema enforcement.
    """
    # Use the OpenAI compatible LM Studio endpoint
    if settings.LM_STUDIO_URL.endswith("/v1"):
        url = f"{settings.LM_STUDIO_URL}/chat/completions"
    else:
        url = f"{settings.LM_STUDIO_URL}/v1/chat/completions"

    skill_content = load_skill()

    # If it is a normal navigation session
    if "activities" in session_data:
        activities = session_data.get("activities", [])
        if not activities:
            return None
        user_context = format_session_context(activities)
        prompt_instruction = """
TASK:
1. Analyze the session history above. Identify the user's INTENT.
2. FILTER out noise.
3. SYNTHESIZE the valuable information into a SINGLE atomic Markdown entry.
4. Return ONLY a JSON object compatible with the schema provided.
"""

    # If it is an audio transcription (conversation, voice note, etc.)
    elif "transcription" in session_data:
        transcription = session_data.get("transcription", "")
        if not transcription:
            return None
        user_context = f"TRANSCRIPTION OF AUDIO RECORDING:\n\n{transcription}"
        prompt_instruction = """
TASK:
1. Analyze the audio transcription above.
2. IDENTIFY if it is a meeting, a voice note, a lecture, or a conversation.
3. EXTRACT key points, decisions, and action items.
4. FORMAT it as a structured note.
5. Return ONLY a JSON object compatible with the schema provided.
"""
    else:
        return None

    # Define strict schema for the response
    json_schema = {
        "type": "json_schema",
        "json_schema": {
            "name": "second_brain_entry",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Folder or file category from Second Brain Spec (e.g. '00_inbox', '04_knowledge', '10_network', '06_decisions').",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Suggested filename ending in .md (e.g. 'meeting_notes_project_x.md').",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content of the note in Markdown format.",
                    },
                },
                "required": ["category", "filename", "content"],
                "additionalProperties": False,
            },
        },
    }

    # Payload LM Studio compatible
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": skill_content},
            {"role": "user", "content": user_context + "\n" + prompt_instruction},
        ],
        "temperature": 0.2,
        "response_format": json_schema,
        "stream": False,
    }

    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        return json.loads(content)

    except Exception as e:
        print(f"Error processing session with Second Brain Skill: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Error details: {e.response.text}")
        return None
