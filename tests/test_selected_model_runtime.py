import json


def test_selected_model_requires_import(monkeypatch, tmp_path):
    import config.model_runtime as runtime
    monkeypatch.setattr(runtime, "API_FILE", tmp_path / "api_keys.json")
    runtime.API_FILE.write_text(json.dumps({"models": [], "providers": []}), encoding="utf-8")
    try:
        runtime.complete_selected_model("hello", "missing-model")
    except RuntimeError as exc:
        assert "not imported" in str(exc)
    else:
        raise AssertionError("missing imported model should fail")


def test_openai_compatible_selected_model(monkeypatch, tmp_path):
    import config.model_runtime as runtime
    monkeypatch.setattr(runtime, "API_FILE", tmp_path / "api_keys.json")
    runtime.API_FILE.write_text(json.dumps({
        "models": [{"id": "local-model", "provider": "lmstudio"}],
        "providers": [{"id": "lmstudio", "base_url": "http://localhost:1234/v1", "api_key": "", "enabled": True}],
    }), encoding="utf-8")

    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "hello from local"}}]}

    monkeypatch.setattr(runtime.requests, "post", lambda *a, **k: Response())
    text, provider, model = runtime.complete_selected_model("hello", "local-model")
    assert (text, provider, model) == ("hello from local", "lmstudio", "local-model")
