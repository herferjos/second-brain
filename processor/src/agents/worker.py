"""Worker: executes a single task (create/update note or generate questions)."""
import logging
from pathlib import Path

from .. import settings
from ..domain.events import get_events_by_id
from ..domain.models import Concept, GeneratedQuestions, Task
from ..llm.base import LLMClient
from ..storage import state_db
from ..storage.paths import concept_note_path, question_note_path
from ..storage.writer import content_sha, write_idempotent
from ..vault.prompts import (
    EXTRACT_CONCEPT_SYSTEM,
    GENERATE_QUESTIONS_SYSTEM,
    extract_concept_user,
    generate_questions_user,
)
from ..vault.render import render_page_note

log = logging.getLogger("processor.worker")


def _extract_concept(llm: LLMClient, text: str) -> str:
    out = llm.generate(EXTRACT_CONCEPT_SYSTEM, extract_concept_user(text), Concept)
    return out.concept.replace('"', "").strip()


def _generate_questions(llm: LLMClient, note_content: str, concept_name: str) -> str:
    out = llm.generate(
        GENERATE_QUESTIONS_SYSTEM,
        generate_questions_user(concept_name, note_content),
        GeneratedQuestions,
    )
    return out.questions_markdown


class WorkerAgent:
    """Executes one task: CREATE_OR_UPDATE_NOTE or GENERATE_QUESTIONS."""

    def __init__(self, llm_client: LLMClient, db_path: Path, vault_dir: Path, all_events: list[dict]):
        self.llm = llm_client
        self.db_path = db_path
        self.vault_dir = vault_dir
        self.all_events = all_events
        self.data_dir = settings.data_dir()

    def execute_task(self, task: Task) -> None:
        if task.task_type == "CREATE_OR_UPDATE_NOTE":
            self._create_or_update_note(task)
        elif task.task_type == "GENERATE_QUESTIONS":
            self._generate_questions_task(task)
        else:
            raise ValueError(f"Unknown task type: {task.task_type}")
        log.info("Completed task: %s", task.task_id)

    def _create_or_update_note(self, task: Task) -> None:
        task_events = get_events_by_id(self.all_events, task.related_event_ids)
        if not task_events:
            log.warning("No events for task %s. Skipping.", task.task_id)
            return

        full_text = ""
        for ev in task_events:
            meta = ev.get("meta", {})
            if "text_path" not in meta:
                continue
            content_path = self.data_dir / meta["text_path"]
            if not content_path.exists():
                log.warning("Content file not found: %s", content_path)
                continue
            full_text += f"\n\n---\n\nURL: {meta.get('url')}\nTitle: {meta.get('title')}\n\n"
            full_text += content_path.read_text(encoding="utf-8")

        if not full_text.strip():
            log.warning("No text for task %s. Skipping.", task.task_id)
            return

        concept_name = _extract_concept(self.llm, full_text)
        log.info("Concept for task %s: %s", task.task_id, concept_name)

        path = concept_note_path(self.vault_dir, concept_name)
        existing_content = path.read_text(encoding="utf-8") if path.exists() else None
        existing_titles = state_db.get_all_concept_titles(self.db_path)

        note_content = render_page_note(
            text=full_text,
            llm_client=self.llm,
            existing_concept_titles=existing_titles,
            existing_note_content=existing_content,
        )

        sha = content_sha(note_content)
        write_idempotent(path, note_content)
        ts = task_events[-1].get("ts", "")[:19]
        state_db.set_artifact(self.db_path, f"concept:{concept_name}", "concept", str(path), sha)
        state_db.upsert_concept(self.db_path, concept_name, concept_name, sha, ts)
        log.info("Wrote concept note: %s", path)

    def _generate_questions_task(self, task: Task) -> None:
        # description is like "Generate questions for 'ConceptName'"
        concept_name = task.description.split("'")[1]
        path = concept_note_path(self.vault_dir, concept_name)
        if not path.exists():
            log.error("Concept note not found: %s", path)
            return

        note_content = path.read_text(encoding="utf-8")
        questions = _generate_questions(self.llm, note_content, concept_name)

        q_path = question_note_path(self.vault_dir, concept_name)
        sha = content_sha(questions)
        write_idempotent(q_path, questions)
        state_db.set_artifact(self.db_path, f"question:{concept_name}", "question", str(q_path), sha)
        log.info("Wrote question note: %s", q_path)
