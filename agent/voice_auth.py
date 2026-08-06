"""
voice_auth.py

Speaker verification layer for Lessan AI. Compares incoming audio against your
enrolled voice fingerprint so Lessan AI only reacts to YOUR voice.

Drop this file into your `core/` (or `agent/`) folder.

Install once:
    pip install resemblyzer numpy soundfile --break-system-packages
    (inside your venv: just `pip install resemblyzer numpy soundfile`)

Usage:
    from core.voice_auth import is_authorized_speaker

    audio = recognizer.listen(mic)          # speech_recognition AudioData
    if not is_authorized_speaker(audio):
        print("Ignored: not my voice.")
        continue

    text = recognizer.recognize_google(audio)
    ...
"""

import io
import numpy as np
from pathlib import Path
from resemblyzer import VoiceEncoder, preprocess_wav

EMBED_PATH = Path(__file__).parent / "memory" / "voice_profile.npy"
THRESHOLD = 0.75  # cosine similarity cutoff, tune between 0.70-0.85

_encoder = None  # lazy-loaded, loading the model takes a moment


def _get_encoder() -> VoiceEncoder:
    global _encoder
    if _encoder is None:
        _encoder = VoiceEncoder()
    return _encoder


def _audiodata_to_wav_array(audio_data) -> np.ndarray:
    """
    Converts a speech_recognition AudioData object into a float32 waveform
    at 16kHz mono, which is what resemblyzer expects.
    """
    wav_bytes = audio_data.get_wav_data(convert_rate=16000, convert_width=2)
    import soundfile as sf
    wav_np, _sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
    if wav_np.ndim > 1:
        wav_np = wav_np.mean(axis=1)
    return wav_np


def enroll_from_wavs(wav_paths: list[str]) -> None:
    """
    Builds and saves your voice fingerprint from a list of wav file paths.
    Use 3-5 short (3-8 second) clean recordings of just your voice.
    """
    encoder = _get_encoder()
    embeddings = []
    for path in wav_paths:
        wav = preprocess_wav(path)
        embeddings.append(encoder.embed_utterance(wav))

    avg_embedding = np.mean(embeddings, axis=0)
    EMBED_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.save(EMBED_PATH, avg_embedding)
    print(f"Voice profile saved to {EMBED_PATH}")


def is_authorized_speaker(audio_data, threshold: float = THRESHOLD) -> bool:
    """
    Returns True if the given speech_recognition AudioData matches your
    enrolled voice, False otherwise. If no profile is enrolled yet, this
    always returns True (fails open) so you're not locked out.
    """
    if not EMBED_PATH.exists():
        print("[voice_auth] No voice profile enrolled yet — run enroll_voice.py first.")
        return True

    my_embedding = np.load(EMBED_PATH)
    encoder = _get_encoder()

    wav_np = _audiodata_to_wav_array(audio_data)
    incoming_embedding = encoder.embed_utterance(wav_np)

    similarity = np.dot(my_embedding, incoming_embedding) / (
        np.linalg.norm(my_embedding) * np.linalg.norm(incoming_embedding)
    )

    authorized = similarity >= threshold
    print(f"[voice_auth] similarity={similarity:.3f} authorized={authorized}")
    return authorized
