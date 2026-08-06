"""
enroll_voice.py

Run this ONCE to record your voice and build your fingerprint.
Put it in your project root (next to main.py) or in `core/`.

Run:
    python enroll_voice.py

It records 4 short clips (4 seconds each) — just talk normally, like you
would when giving Lessan AI a command. Try to do it somewhere quiet-ish and
avoid other people talking during the recording.
"""

import speech_recognition as sr
import soundfile as sf
import numpy as np
from pathlib import Path
from core.voice_auth import enroll_from_wavs  # adjust import path if needed

TMP_DIR = Path("tmp_enroll")
TMP_DIR.mkdir(exist_ok=True)

NUM_SAMPLES = 4
SECONDS_EACH = 4


def record_sample(index: int) -> str:
    r = sr.Recognizer()
    with sr.Microphone(sample_rate=16000) as mic:
        r.adjust_for_ambient_noise(mic, duration=0.5)
        print(f"\nSample {index + 1}/{NUM_SAMPLES} — speak now for {SECONDS_EACH}s...")
        audio = r.record(mic, duration=SECONDS_EACH)

    wav_path = TMP_DIR / f"sample_{index}.wav"
    with open(wav_path, "wb") as f:
        f.write(audio.get_wav_data(convert_rate=16000, convert_width=2))
    print(f"Saved {wav_path}")
    return str(wav_path)


def main():
    print("=== Lessan AI Voice Enrollment ===")
    print(f"We'll record {NUM_SAMPLES} samples of {SECONDS_EACH}s each.")
    input("Press Enter when ready...")

    paths = [record_sample(i) for i in range(NUM_SAMPLES)]

    print("\nBuilding voice profile...")
    enroll_from_wavs(paths)
    print("Done! Lessan AI will now only respond to your voice.")


if __name__ == "__main__":
    main()
