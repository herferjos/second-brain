"""Unit tests for the llama.cpp HTTP service wrapper."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1] / "services" / "llama_cpp"
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from src import app as llama_app  # type: ignore[import-not-found]
from src.config import LlamaCppSettings  # type: ignore[import-not-found]


pytestmark = pytest.mark.unit


class FakeLlama:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_chat_completion(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"ok":true}',
                    }
                }
            ]
        }


def test_ensure_model_path_autodownloads_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    download_root = tmp_path / "downloaded"
    created_model = download_root / "nested" / "model.gguf"

    def fake_snapshot_download(**kwargs: object) -> str:
        assert kwargs["repo_id"] == "org/model"
        assert kwargs["revision"] == "main"
        assert kwargs["local_dir_use_symlinks"] is False
        assert kwargs["allow_patterns"] == ["*.gguf"]
        created_model.parent.mkdir(parents=True, exist_ok=True)
        created_model.write_text("gguf", encoding="utf-8")
        return str(download_root)

    fake_hf = types.ModuleType("huggingface_hub")
    fake_hf.snapshot_download = fake_snapshot_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hf)

    settings = LlamaCppSettings(
        host="127.0.0.1",
        port=9100,
        model_id="org/model",
        model_path=None,
        model_file="nested/model.gguf",
        model_dir=tmp_path / "models",
        revision="main",
        n_ctx=4096,
        n_gpu_layers=0,
        n_threads=0,
        temperature=0.2,
    )

    model_path = llama_app._ensure_model_path(settings)

    assert model_path == created_model
    assert model_path.exists()
    assert settings.model_dir.exists()


def test_chat_completions_forwards_response_format(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = FakeLlama()
    monkeypatch.setattr(llama_app, "_llama", fake)
    monkeypatch.setattr(
        llama_app,
        "_settings",
        LlamaCppSettings(
            host="127.0.0.1",
            port=9100,
            model_id=None,
            model_path=None,
            model_file=None,
            model_dir=tmp_path,
            revision=None,
            n_ctx=4096,
            n_gpu_layers=0,
            n_threads=0,
            temperature=0.2,
        ),
    )

    payload = llama_app.ChatCompletionRequest(
        messages=[{"role": "user", "content": "Return JSON"}],
        response_format={"type": "json_object"},
    )

    response = llama_app.chat_completions(payload)

    assert fake.calls
    assert fake.calls[0]["response_format"] == {"type": "json_object"}
    assert fake.calls[0]["messages"] == [{"role": "user", "content": "Return JSON"}]
    assert response["choices"][0]["message"]["content"] == '{"ok":true}'
    assert response["object"] == "chat.completion"
    assert response["model"] == "local-llama"


def test_list_models_uses_loaded_model_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        llama_app,
        "_settings",
        LlamaCppSettings(
            host="127.0.0.1",
            port=9100,
            model_id="org/model",
            model_path=None,
            model_file=None,
            model_dir=tmp_path,
            revision=None,
            n_ctx=4096,
            n_gpu_layers=0,
            n_threads=0,
            temperature=0.2,
        ),
    )

    response = llama_app.list_models()

    assert response["object"] == "list"
    assert response["data"][0]["id"] == "org/model"
