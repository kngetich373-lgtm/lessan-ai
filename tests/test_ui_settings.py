import json


def test_provider_presets_and_voice_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    import lessan_ui

    monkeypatch.setattr(lessan_ui, "API_FILE", tmp_path / "api_keys.json")
    config = lessan_ui.load_config()

    assert "Gemini" in lessan_ui.PROVIDER_PRESETS
    assert "OpenRouter" in lessan_ui.PROVIDER_PRESETS
    assert "Ollama" in lessan_ui.PROVIDER_PRESETS
    assert config["voice"]["provider"] == "gemini"
    assert config["voice"]["voice"] == "Kore"
    assert config["voice"]["enabled"] is True


def test_openai_compatible_model_discovery(monkeypatch):
    import lessan_ui

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "test-model", "context_length": 8192}]}

    monkeypatch.setattr(lessan_ui.requests, "get", lambda *args, **kwargs: Response())
    models = lessan_ui.discover_models("openai", "http://localhost:1234/v1", "secret")

    assert models == [{
        "id": "test-model",
        "name": "test-model",
        "provider": "openai",
        "context_length": 8192,
    }]
