import os
import subprocess
import tempfile
from faster_whisper import WhisperModel


class Transcriber:
    """Transcriber using faster-whisper (CTranslate2 backend)."""

    def __init__(self, model_name: str = "small"):
        print(f"🚀 Initializing transcriber with model: '{model_name}'")
        self.model = WhisperModel(model_name, device="cpu", compute_type="int8")

    def transcribe(self, file_path: str) -> str:
        print(f"🎤 Transcribing: {file_path}")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav_file:
            wav_path = tmp_wav_file.name

        try:
            command = [
                "ffmpeg", "-y", "-i", file_path,
                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
                wav_path
            ]
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            segments, _ = self.model.transcribe(wav_path, language=None)
            transcription = " ".join(segment.text for segment in segments)

            print(f"📝 Transcription: {transcription[:100]}...")
            return transcription.strip()

        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg conversion failed: {e}")
            return ""
        except Exception as e:
            print(f"❌ Error during transcription: {e}")
            return ""
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)


transcriber = Transcriber(model_name="small")
