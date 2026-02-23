import os
import logging
import subprocess
import tempfile
import time
from threading import Lock

from faster_whisper import WhisperModel

logger = logging.getLogger("second_brain.transcriber")


class Transcriber:
    def __init__(self, model_name: str = "small"):
        logger.info("Initializing transcriber | model=%s", model_name)
        self.model = WhisperModel(model_name, device="cpu", compute_type="int8")

    def transcribe(self, file_path: str, job_id: str = "unknown") -> str:
        started_at = time.perf_counter()
        logger.info("Transcription started | job_id=%s | file=%s", job_id, file_path)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav_file:
            wav_path = tmp_wav_file.name

        try:
            conversion_started = time.perf_counter()
            command = [
                "ffmpeg", "-y", "-i", file_path,
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                wav_path
            ]
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(
                "Audio conversion completed | job_id=%s | wav=%s | duration_ms=%d",
                job_id,
                wav_path,
                int((time.perf_counter() - conversion_started) * 1000),
            )

            segments, _ = self.model.transcribe(wav_path, language=None)
            transcription = " ".join(segment.text for segment in segments)
            clean_transcription = transcription.strip()

            logger.info(
                "Transcription completed | job_id=%s | chars=%d",
                job_id,
                len(clean_transcription),
            )
            logger.debug(
                "Transcription preview | job_id=%s | preview=%s",
                job_id,
                clean_transcription[:100],
            )
            return clean_transcription

        except subprocess.CalledProcessError:
            logger.exception("FFmpeg conversion failed | job_id=%s | file=%s", job_id, file_path)
            return ""
        except Exception:
            logger.exception("Error during transcription | job_id=%s | file=%s", job_id, file_path)
            return ""
        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except OSError:
                    logger.exception(
                        "Failed to remove temporary WAV file | job_id=%s | wav=%s",
                        job_id,
                        wav_path,
                    )
            logger.info(
                "Transcription finished | job_id=%s | duration_ms=%d",
                job_id,
                int((time.perf_counter() - started_at) * 1000),
            )


class OpenAITranscriber:
    def __init__(self, *, api_key: str, base_url: str = "", model: str = "whisper-1"):
        api_key = (api_key or "").strip()
        if not api_key:
            raise ValueError("Missing WHISPER_API_KEY for WHISPER_PROVIDER=openai")

        try:
            from openai import OpenAI
        except Exception as e:
            raise RuntimeError("OpenAI client not installed. Add 'openai' to requirements.") from e

        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url

        self._client = OpenAI(**kwargs)
        self._model = model

    def transcribe(self, file_path: str, job_id: str = "unknown") -> str:
        started_at = time.perf_counter()
        logger.info("Cloud transcription started | job_id=%s | file=%s", job_id, file_path)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav_file:
            wav_path = tmp_wav_file.name

        try:
            command = [
                "ffmpeg",
                "-y",
                "-i",
                file_path,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                wav_path,
            ]
            subprocess.run(
                command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

            with open(wav_path, "rb") as f:
                resp = self._client.audio.transcriptions.create(
                    model=self._model,
                    file=f,
                )

            text = getattr(resp, "text", None) or str(resp)
            text = (text or "").strip()
            logger.info(
                "Cloud transcription completed | job_id=%s | chars=%d",
                job_id,
                len(text),
            )
            return text
        except subprocess.CalledProcessError:
            logger.exception(
                "FFmpeg conversion failed (cloud) | job_id=%s | file=%s", job_id, file_path
            )
            return ""
        except Exception:
            logger.exception("Cloud transcription failed | job_id=%s | file=%s", job_id, file_path)
            return ""
        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except OSError:
                    logger.exception(
                        "Failed to remove temporary WAV file | job_id=%s | wav=%s",
                        job_id,
                        wav_path,
                    )
            logger.info(
                "Cloud transcription finished | job_id=%s | duration_ms=%d",
                job_id,
                int((time.perf_counter() - started_at) * 1000),
            )


_transcriber: Transcriber | None = None
_transcriber_lock = Lock()


def get_transcriber() -> Transcriber:
    global _transcriber
    if _transcriber is not None:
        return _transcriber

    with _transcriber_lock:
        if _transcriber is None:
            provider = os.getenv("WHISPER_PROVIDER", "local").strip().lower()
            if provider in {"openai", "cloud", "api"}:
                api_key = os.getenv("WHISPER_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
                base_url = os.getenv("WHISPER_BASE_URL", "").strip() or os.getenv("OPENAI_BASE_URL", "").strip()
                model = os.getenv("WHISPER_MODEL", "whisper-1").strip() or "whisper-1"
                _transcriber = OpenAITranscriber(api_key=api_key, base_url=base_url, model=model)
            else:
                _transcriber = Transcriber(model_name=os.getenv("WHISPER_MODEL", "small"))
        return _transcriber
