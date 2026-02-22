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
from api.services.transcriber import transcriber
from api.services.life_log import append_entry

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger("second_brain.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API startup: warming up LLM model")
    warmup_ok = warmup_model()
    if warmup_ok:
        logger.info("API startup: LLM warmup completed")
    else:
        logger.warning("API startup: LLM warmup failed")
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


@app.get("/")
def read_root():
    return {"status": "online", "system": "Second Brain Agent"}


@app.post("/session")
async def receive_session(data: SessionData, background_tasks: BackgroundTasks):
    """
    Endpoint to receive a complete activity session (idle flush).
    """
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
    """
    Endpoint to upload and transcribe audio.
    """
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

    # Temporarily save file
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
        text = transcriber.transcribe(file_path, job_id=job_id)

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
