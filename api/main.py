from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import shutil
import os
import time
import requests

from api.config import settings
from api.services.llm import process_session_with_llm
from api.services.brain_manager import save_to_brain
from api.services.transcriber import transcriber
from api.services.life_log import append_entry


def is_model_loaded():
    """Check if the target model is already loaded in LM Studio."""
    try:
        models_url = f"{settings.LM_STUDIO_URL}/models"
        response = requests.get(models_url, timeout=10)
        response.raise_for_status()
        loaded = response.json().get("data", [])
        return any(m.get("id") == settings.LLM_MODEL for m in loaded)
    except Exception:
        return False


def load_llm_model():
    base_url = settings.LM_STUDIO_URL.rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    load_url = f"{base_url}/api/v1/models/load"

    print(
        f"🔄 Loading LLM: {settings.LLM_MODEL} ({settings.LLM_CONTEXT_LENGTH} tokens)"
    )

    max_retries = 30
    for attempt in range(max_retries):
        try:
            if is_model_loaded():
                print(f"✅ LLM already loaded: {settings.LLM_MODEL}")
                return

            payload = {
                "model": settings.LLM_MODEL,
                "context_length": settings.LLM_CONTEXT_LENGTH,
            }
            response = requests.post(load_url, json=payload, timeout=300)
            response.raise_for_status()
            result = response.json()
            print(
                f"✅ LLM loaded: {result.get('instance_id')} in {result.get('load_time_seconds', '?')}s"
            )
            return
        except requests.exceptions.ConnectionError:
            print(f"⏳ Waiting for LM Studio... ({attempt + 1}/{max_retries})")
            time.sleep(5)
        except Exception as e:
            print(f"⚠️  LLM load warning: {e}")
            return

    print("⚠️  Could not connect to LM Studio - LLM features may not work")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_llm_model()
    yield


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
    if not data.activities:
        return {"status": "ignored", "message": "Empty session"}

    background_tasks.add_task(process_and_store_session, data)
    return {
        "status": "received",
        "message": f"Processing {len(data.activities)} activities",
    }


@app.post("/audio")
async def upload_audio(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Endpoint to upload and transcribe audio.
    """
    if not file.filename.endswith((".wav", ".mp3", ".m4a", ".flac", ".ogg")):
        raise HTTPException(status_code=400, detail="Unsupported file format")

    # Temporarily save file
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, os.path.basename(file.filename))

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    background_tasks.add_task(process_audio_file, file_path)

    return {
        "status": "received",
        "message": "Audio received. Transcription and analysis in progress.",
    }


def process_and_store_session(data: SessionData):
    print(f"🧠 Analyzing Session ({len(data.activities)} items)...")

    result = process_session_with_llm(data.dict())

    if result and "content" in result:
        path = save_to_brain(result)
        print(f"✅ Knowledge archived in: {path}")

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
    else:
        print("❌ Error: Could not structure the session")


def process_audio_file(file_path: str):
    print(f"🎧 Starting audio processing: {file_path}")

    try:
        text = transcriber.transcribe(file_path)

        if not text:
            print("❌ Error: Empty transcription")
            return

        print(f"✅ Audio transcribed ({len(text)} characters)")

        payload = {"transcription": text}
        result = process_session_with_llm(payload)

        if result and "content" in result:
            path = save_to_brain(result)
            print(f"✅ Transcription archived in: {path}")

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
        else:
            print("❌ Error: Could not structure the transcription")

    except Exception as e:
        print(f"❌ Critical error processing audio: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
