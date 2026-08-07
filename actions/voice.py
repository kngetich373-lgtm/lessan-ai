"""Voice module for speech recognition, text-to-speech, and wake word detection."""

import threading
import queue
import sounddevice as sd
import numpy as np
import pyttsx3
import webrtcvad
import time
from typing import Any, Callable, Dict, Optional

from core.logging import get_logger

logger = get_logger("voice")

# Audio configuration
SAMPLE_RATE = 16000
CHUNK = 1024
LISTENING_TIMEOUT = 5.0  # seconds of silence before stopping
WAKEWORD = "lessan"  # simple wake word


class VoiceEngine:
    """Singleton voice engine for speech recognition and synthesis."""

    _instance: Optional["VoiceEngine"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "VoiceEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self) -> None:
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", SAMPLE_RATE)
        self.engine.setProperty("volume", 0.9)
        self._listener_queue = queue.Queue()
        self._recording = False
        self._stop_listening = threading.Event()

    # ------------------------------------------------------------------ #
    # Text-to-Speech
    # ------------------------------------------------------------------ #
    def speak(self, text: str, rate: Optional[int] = None) -> None:
        """Speak the given text aloud."""
        if not text:
            return
        if rate:
            self.engine.setProperty("rate", rate)
        self.engine.say(text)
        self.engine.runAndWait()

    # ------------------------------------------------------------------ #
    # Speech Recognition
    # ------------------------------------------------------------------ #
    def listen(self, timeout: Optional[float] = None, callback: Optional[Callable[[str], Any]] = None) -> str:
        """Listen for speech and return the recognized text."""
        timeout = timeout or LISTENING_TIMEOUT
        self._stop_listening.clear()

        def _callback(indata, frames, time, status):
            if status:
                logger.warning(f"Listening status: {status}")
            self._listener_queue.put(indata.copy())

        with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, callback=_callback):
            logger.info("Listening for speech...")
            audio_data = b""
            last_activity = time.time()

            while True:
                try:
                    chunk = self._listener_queue.get(timeout=0.1)
                    audio_data += chunk.tobytes()
                    if time.time() - last_activity > timeout:
                        break
                    last_activity = time.time()
                except queue.Empty:
                    if self._stop_listening.is_set():
                        break

            # Simple VAD filter
            audio_np = np.frombuffer(audio_data, dtype=np.int16)
            vad = webrtcvad.Vad()
            vad.set_mode(1)
            is_speech = vad.is_speech(audio_np.tobytes(), SAMPLE_RATE)
            if not is_speech:
                logger.debug("No speech detected")
                return ""

            # Speech-to-text using Vosk (offline)
            try:
                import json
                from vosk import Model, KaldiRecognizer

                model = Model("model")  # Placeholder for vosk model path
                recognizer = KaldiRecognizer(model, SAMPLE_RATE)
                text = recognizer.AcceptWaveform(np.frombuffer(audio_data, dtype=np.int16))
                result = json.loads(text)
                return result.get("text", "")
            except Exception as exc:
                logger.error(f"Speech recognition failed: {exc}")
                return ""
        # End with

    # ------------------------------------------------------------------ #
    # Wake Word Detection
    # ------------------------------------------------------------------ #
    def detect_wake_word(self, callback: Callable[[], Any]) -> None:
        """Run background wake word detection and invoke callback when detected."""
        def _worker():
            try:
                import pyaudio
                import wave

                p = pyaudio.PyAudio()
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=CHUNK,
                )

                logger.info("Waiting for wake word...")
                while True:
                    data = stream.read(CHUNK)
                    if WAKEWORD in data.decode("utf-8", errors="ignore").lower():
                        logger.info("Wake word detected!")
                        callback()
                        break

            except Exception as exc:
                logger.error(f"Wake word detection failed: {exc}")
            finally:
                stream.stop_stream()
                stream.close()
                p.terminate()

        threading.Thread(target=_worker, daemon=True).start()


# Global voice instance
voice_engine = VoiceEngine()