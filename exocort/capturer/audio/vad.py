from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(slots=True)
class AudioVADConfig:
    enabled: bool = False
    energy_threshold: float = 400.0
    window_seconds: float = 0.1
    speech_ratio: float = 0.1


class SimpleVAD:
    def __init__(self, config: AudioVADConfig, sample_rate: int) -> None:
        self.config = config
        self.sample_rate = sample_rate
        self.window_samples = max(1, int(round(sample_rate * config.window_seconds)))
        self.last_ratio: float = 0.0
        self.last_rms: float = 0.0

    def is_speech(self, samples: np.ndarray) -> bool:
        mono = self._mix_down(samples)
        if mono.size == 0:
            self.last_ratio = 0.0
            self.last_rms = 0.0
            return False

        window = self.window_samples
        rms_values: list[float] = []

        for start in range(0, mono.size, window):
            chunk = mono[start : start + window]
            if chunk.size == 0:
                continue
            rms = float(np.sqrt(np.mean(np.square(chunk.astype(np.float32)))))
            rms_values.append(rms)

        if not rms_values:
            self.last_ratio = 0.0
            self.last_rms = 0.0
            return False

        speech_windows = sum(1 for rms in rms_values if rms >= self.config.energy_threshold)
        self.last_ratio = speech_windows / len(rms_values)
        self.last_rms = float(np.mean(rms_values))
        return self.last_ratio >= self.config.speech_ratio

    def _mix_down(self, samples: np.ndarray) -> np.ndarray:
        if samples.ndim <= 1:
            return samples
        return samples.mean(axis=1)
