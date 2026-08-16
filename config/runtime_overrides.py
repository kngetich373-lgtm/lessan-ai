"""Runtime compatibility and selected-model integration for Lessan."""
from __future__ import annotations

import os
import threading
import time


def install_genai_overrides():
    """Patch Gemini Live model/voice settings and install UI model routing."""
    try:
        from google import genai
        from google.genai import types
    except Exception:
        genai = None
        types = None

    if genai is not None and not getattr(genai, "_lessan_overrides", False):
        original_client = genai.Client

        class _LiveProxy:
            def __init__(self, live):
                self._live = live

            def connect(self, model, config=None, *args, **kwargs):
                model = os.environ.get("LESSAN_GEMINI_LIVE_MODEL") or model
                voice = os.environ.get("LESSAN_GEMINI_VOICE")
                enabled = os.environ.get("LESSAN_GEMINI_VOICE_ENABLED", "1") != "0"
                if config is not None and voice and enabled:
                    try:
                        config.speech_config = types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice
                                )
                            )
                        )
                    except Exception:
                        pass
                return self._live.connect(model=model, config=config, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._live, name)

        class _AioProxy:
            def __init__(self, aio): self._aio = aio
            @property
            def live(self): return _LiveProxy(self._aio.live)
            def __getattr__(self, name): return getattr(self._aio, name)

        class _ClientProxy:
            def __init__(self, client):
                self._client = client
                self.aio = _AioProxy(client.aio)
            def __getattr__(self, name): return getattr(self._client, name)

        def client_factory(*args, **kwargs):
            return _ClientProxy(original_client(*args, **kwargs))

        genai.Client = client_factory
        genai._lessan_overrides = True

    _install_ui_model_router_async()


def _install_ui_model_router_async() -> None:
    """Patch LessanUI once its module finishes defining the class.

    This keeps the legacy main.py entrypoint untouched while making the
    Settings model selector an actual execution control for text messages.
    """
    def worker():
        for _ in range(200):
            module = __import__("sys").modules.get("lessan_ui")
            ui_cls = getattr(module, "LessanUI", None) if module else None
            if ui_cls is not None and not getattr(ui_cls, "_selected_model_router_installed", False):
                original = ui_cls._on_user_input

                def _on_user_input(self, text, file_path):
                    self.current_file = file_path or None
                    if not text:
                        return
                    try:
                        model = self._window.model_combo.currentData()
                        label = self._window.model_combo.currentText()
                        if not model:
                            original(self, text, file_path)
                            return
                        from config.model_runtime import complete_selected_model
                        self._window.set_state("THINKING")
                        self._window.write_log(f"SYS: Routing to {label}")
                        response, provider, model_id = complete_selected_model(text, str(model))
                        self._window.write_log(f"Lessan [{provider} / {model_id}]: {response}")
                        self._window.set_state("LISTENING")
                    except Exception as exc:
                        self._window.write_log(f"ERR: Model routing — {exc}")
                        self._window.set_state("LISTENING")

                ui_cls._on_user_input = _on_user_input
                ui_cls._selected_model_router_installed = True
                return
            time.sleep(0.05)

    threading.Thread(target=worker, name="lessan-ui-model-router", daemon=True).start()
