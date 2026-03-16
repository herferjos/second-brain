from __future__ import annotations

import pytest

from exocort.capture.audio import device


pytestmark = [pytest.mark.unit, pytest.mark.stt]


def test_resolve_system_device_uses_monitor_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(device.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        device.sd,
        "query_devices",
        lambda *args: [
            {"name": "Built-in Mic", "max_input_channels": 1, "max_output_channels": 0},
            {
                "name": "Monitor of Built-in Audio Analog Stereo",
                "max_input_channels": 2,
                "max_output_channels": 0,
            },
        ],
    )
    monkeypatch.setattr(device.sd, "query_hostapis", lambda: [{"name": "ALSA"}])

    resolved_index, resolved_label, overrides = device.resolve_input_device(
        requested_device=None,
        source="system",
    )
    assert resolved_index == 1
    assert "monitor" in resolved_label.lower()
    assert overrides == {}


def test_resolve_system_device_uses_windows_wasapi_default_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeWasapiSettings:
        def __init__(self, *, loopback: bool):
            self.loopback = loopback

    def fake_query_devices(index=None):
        devices = [
            {"name": "Mic", "max_input_channels": 1, "max_output_channels": 0, "hostapi": 0},
            {
                "name": "Speakers (Realtek)",
                "max_input_channels": 0,
                "max_output_channels": 2,
                "hostapi": 1,
            },
        ]
        if index is None:
            return devices
        return devices[index]

    monkeypatch.setattr(device.platform, "system", lambda: "Windows")
    monkeypatch.setattr(device.sd, "query_devices", fake_query_devices)
    monkeypatch.setattr(
        device.sd,
        "query_hostapis",
        lambda: [{"name": "MME"}, {"name": "Windows WASAPI"}],
    )
    monkeypatch.setattr(device.sd, "WasapiSettings", FakeWasapiSettings)
    monkeypatch.setattr(device.sd, "default", type("Default", (), {"device": (0, 1)})())

    resolved_index, resolved_label, overrides = device.resolve_input_device(
        requested_device=None,
        source="system",
    )
    assert resolved_index == 1
    assert "loopback" in resolved_label.lower()
    assert isinstance(overrides.get("extra_settings"), FakeWasapiSettings)
    assert overrides["extra_settings"].loopback is True


def test_resolve_system_device_marks_unavailable_when_no_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(device.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        device.sd,
        "query_devices",
        lambda *args: [
            {"name": "MacBook Microphone", "max_input_channels": 1, "max_output_channels": 0},
        ],
    )
    monkeypatch.setattr(device.sd, "query_hostapis", lambda: [{"name": "Core Audio"}])

    resolved_index, resolved_label, overrides = device.resolve_input_device(
        requested_device=None,
        source="system",
    )
    assert resolved_index is None
    assert resolved_label == "system-unavailable"
    assert overrides.get("system_unavailable") is True


def test_resolve_mic_prefers_builtin_over_iphone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(device.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        device.sd,
        "query_devices",
        lambda *args: [
            {"name": "iPhone Microphone", "max_input_channels": 1, "max_output_channels": 0},
            {"name": "MacBook Air Microphone", "max_input_channels": 1, "max_output_channels": 0},
        ],
    )
    monkeypatch.setattr(device.sd, "query_hostapis", lambda: [{"name": "Core Audio"}])

    resolved_index, resolved_label, overrides = device.resolve_input_device(
        requested_device=None,
        source="mic",
    )
    assert resolved_index == 1
    assert "macbook" in resolved_label.lower()
    assert overrides == {}
