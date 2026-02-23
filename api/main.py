from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
import logging
import time
import uvicorn
import shutil
import os
from uuid import uuid4

from api.config import settings
from api.logging_config import setup_logging
from api.services.llm import process_session_with_llm, warmup_model
from api.services.brain_manager import save_to_brain
from api.services.transcriber import get_transcriber
from api.services.life_log import append_entry
from api.services.notes import list_files as vault_list_files
from api.services.notes import read_file as vault_read_file
from api.services.notes import search_text as vault_search_text
from api.services.notes import write_file as vault_write_file
from api.services.agentic import archivist_ingest, researcher_answer

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger("second_brain.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API startup: warming up LLM | provider=%s | model=%s", settings.LLM_PROVIDER, settings.LLM_MODEL)
    warmup_ok = warmup_model()
    if warmup_ok:
        logger.info("API startup: LLM warmup completed | provider=%s", settings.LLM_PROVIDER)
    else:
        logger.warning("API startup: LLM warmup failed | provider=%s", settings.LLM_PROVIDER)
    yield
    logger.info("API shutdown completed")


app = FastAPI(
    title="Second Brain API",
    description="Knowledge capture and structuring system",
    lifespan=lifespan,
)


class ActivityData(BaseModel):
    url: str
    title: str
    content: Optional[str] = ""
    events: Optional[List[str]] = []
    timestamp: str


class SessionData(BaseModel):
    activities: List[ActivityData]
    session_end: str


class VaultWriteRequest(BaseModel):
    path: str
    content: str
    mode: str = "overwrite"


class AgentIngestRequest(BaseModel):
    raw_data: str


class AgentResearchRequest(BaseModel):
    question: str


@app.get("/")
def read_root():
    return {"status": "online", "system": "Second Brain Agent"}


@app.get("/vault/info")
def vault_info():
    return {
        "vault_path": settings.VAULT_PATH,
        "vault_logs_path": os.path.join(settings.VAULT_PATH, "_logs"),
        "notes_count": len(vault_list_files(limit=5000)),
    }


@app.get("/vault/list")
def vault_list(directory: str = ""):
    try:
        return {"files": vault_list_files(directory=directory, limit=5000)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/vault/read")
def vault_read(path: str):
    try:
        return vault_read_file(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except (IsADirectoryError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/vault/search")
def vault_search(q: str, directory: str = "", regex: bool = True, case_insensitive: bool = True):
    try:
        hits = vault_search_text(
            q,
            directory=directory,
            regex=regex,
            case_insensitive=case_insensitive,
            limit_hits=200,
        )
        return {
            "hits": [
                {"path": h.path, "line_number": h.line_number, "line": h.line} for h in hits
            ]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/vault/write")
def vault_write(req: VaultWriteRequest):
    try:
        return vault_write_file(req.path, req.content, mode=req.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/agent/archivist")
def agent_archivist(req: AgentIngestRequest):
    try:
        return archivist_ingest(req.raw_data)
    except Exception as e:
        logger.exception("Archivist ingestion failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agent/research")
def agent_research(req: AgentResearchRequest):
    try:
        return researcher_answer(req.question)
    except Exception as e:
        logger.exception("Researcher workflow failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/session")
async def receive_session(data: SessionData, background_tasks: BackgroundTasks):
    job_id = uuid4().hex[:8]
    activities_count = len(data.activities)
    logger.info(
        "Session request received | job_id=%s | activities=%d",
        job_id,
        activities_count,
    )

    if not data.activities:
        logger.info("Session request ignored (empty session) | job_id=%s", job_id)
        return {"status": "ignored", "message": "Empty session"}

    background_tasks.add_task(process_and_store_session, data, job_id)
    logger.info("Session request queued | job_id=%s", job_id)
    return {
        "status": "received",
        "message": f"Processing {activities_count} activities",
    }


@app.post("/audio")
async def upload_audio(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    job_id = uuid4().hex[:8]
    logger.info(
        "Audio upload received | job_id=%s | filename=%s",
        job_id,
        file.filename,
    )

    if not file.filename.endswith((".wav", ".mp3", ".m4a", ".flac", ".ogg")):
        logger.warning(
            "Audio upload rejected (unsupported format) | job_id=%s | filename=%s",
            job_id,
            file.filename,
        )
        raise HTTPException(status_code=400, detail="Unsupported file format")

    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, os.path.basename(file.filename))

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    logger.info("Audio file stored temporarily | job_id=%s | path=%s", job_id, file_path)

    background_tasks.add_task(process_audio_file, file_path, job_id)
    logger.info("Audio processing queued | job_id=%s", job_id)

    return {
        "status": "received",
        "message": "Audio received. Transcription and analysis in progress.",
    }


def process_and_store_session(data: SessionData, job_id: str = "unknown"):
    started_at = time.perf_counter()
    logger.info(
        "Session processing started | job_id=%s | activities=%d",
        job_id,
        len(data.activities),
    )
    try:
        payload = data.model_dump() if hasattr(data, "model_dump") else data.dict()
        result = process_session_with_llm(payload, job_id=job_id)

        if result and "content" in result:
            path = save_to_brain(result)
            logger.info(
                "Session archived | job_id=%s | path=%s | category=%s",
                job_id,
                path,
                result.get("category"),
            )

            titles = [a.title for a in data.activities if a.title]
            append_entry(
                entry_type="session",
                summary=result.get("filename", "untitled"),
                metadata={
                    "activities_count": len(data.activities),
                    "titles": titles[:10],
                    "category": result.get("category"),
                    "saved_to": path,
                },
            )
            logger.info("Life-log entry written | job_id=%s | type=session", job_id)
        else:
            logger.error("Session processing failed: invalid LLM output | job_id=%s", job_id)
    except Exception:
        logger.exception("Unhandled error processing session | job_id=%s", job_id)
    finally:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info("Session processing finished | job_id=%s | duration_ms=%d", job_id, duration_ms)


def process_audio_file(file_path: str, job_id: str = "unknown"):
    started_at = time.perf_counter()
    logger.info("Audio processing started | job_id=%s | file=%s", job_id, file_path)

    try:
        text = get_transcriber().transcribe(file_path, job_id=job_id)

        if not text:
            logger.error("Audio processing failed: empty transcription | job_id=%s", job_id)
            return

        logger.info(
            "Audio transcription completed | job_id=%s | chars=%d",
            job_id,
            len(text),
        )

        payload = {"transcription": text}
        result = process_session_with_llm(payload, job_id=job_id)

        if result and "content" in result:
            path = save_to_brain(result)
            logger.info(
                "Transcription archived | job_id=%s | path=%s | category=%s",
                job_id,
                path,
                result.get("category"),
            )

            preview = text[:200].replace("\n", " ")
            append_entry(
                entry_type="audio",
                summary=result.get("filename", "untitled"),
                metadata={
                    "transcription_preview": preview,
                    "transcription_length": len(text),
                    "source_file": os.path.basename(file_path),
                    "category": result.get("category"),
                    "saved_to": path,
                },
            )
            logger.info("Life-log entry written | job_id=%s | type=audio", job_id)
        else:
            logger.error("Audio processing failed: invalid LLM output | job_id=%s", job_id)

    except Exception:
        logger.exception("Critical error processing audio | job_id=%s", job_id)
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info("Temporary audio file removed | job_id=%s | file=%s", job_id, file_path)
            except OSError:
                logger.exception(
                    "Failed to remove temporary audio file | job_id=%s | file=%s",
                    job_id,
                    file_path,
                )
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info("Audio processing finished | job_id=%s | duration_ms=%d", job_id, duration_ms)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
