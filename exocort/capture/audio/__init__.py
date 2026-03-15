"""Audio capture: VAD segmentation, spool upload, capture agent."""

from .agent import AudioCaptureAgent, capture_once, listen_microphone
from .device import detect_loopback_input_device_name
from .models import AudioConfig, AudioSegment, Settings
from .run import main
from .uploader import SpoolUploader
from .vad import VadSegmenter

__all__ = [
    "AudioCaptureAgent",
    "AudioConfig",
    "AudioSegment",
    "Settings",
    "SpoolUploader",
    "VadSegmenter",
    "capture_once",
    "detect_loopback_input_device_name",
    "listen_microphone",
    "main",
]
