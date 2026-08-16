"""Runtime overrides driven by Lessan settings.

Keeps the legacy realtime Gemini entrypoint compatible while allowing
the UI settings to choose the Live model and prebuilt voice.
"""

def install_genai_overrides():
    try:
        from google import genai
        from google.genai import types
    except Exception:
        return
    if getattr(genai, "_lessan_overrides", False):
        return
    original_client = genai.Client

    class _LiveProxy:
        def __init__(self, live):
            self._live = live

        def connect(self, model, config=None, *args, **kwargs):
            import os
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
        def __init__(self, aio):
            self._aio = aio

        @property
        def live(self):
            return _LiveProxy(self._aio.live)

        def __getattr__(self, name):
            return getattr(self._aio, name)

    class _ClientProxy:
        def __init__(self, client):
            self._client = client
            self.aio = _AioProxy(client.aio)

        def __getattr__(self, name):
            return getattr(self._client, name)

    def client_factory(*args, **kwargs):
        return _ClientProxy(original_client(*args, **kwargs))

    genai.Client = client_factory
    genai._lessan_overrides = True
