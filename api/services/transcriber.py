import os
import logging
import subprocess
import tempfile
import time
from faster_whisper import WhisperModel

logger = logging.getLogger("second_brain.transcriber")


class Transcriber:
    """Transcriber using faster-whisper (CTranslate2 backend)."""

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


transcriber = Transcriber(model_name="small")
