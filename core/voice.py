"""Voice I/O.

Input:  faster-whisper running locally on CPU (no API, no cost).
Output: Microsoft Edge TTS (free, natural voices).

All heavy imports are lazy so `import core.voice` never crashes the app —
callers get a clear RuntimeError only when they actually try to use voice.
"""

import asyncio
import tempfile
from pathlib import Path

from config.settings import settings
from core.logger import get_logger

log = get_logger("voice")

_whisper_model = None
SAMPLE_RATE = 16000


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel  # lazy: model download on first use

        log.info("Loading whisper model (base, CPU)…")
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model


def record(seconds: float = 5.0):
    """Record from the default microphone. Returns a float32 numpy array."""
    import numpy as np
    import sounddevice as sd

    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    return np.squeeze(audio)


def transcribe(audio) -> str:
    """Transcribe a numpy float32 mono 16kHz array to text."""
    model = _get_whisper()
    segments, _info = model.transcribe(audio, language="en", vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


def listen(seconds: float = 6.0) -> str:
    """Record + transcribe in one call."""
    return transcribe(record(seconds))


# ---------- output ----------

async def _tts_to_file(text: str, path: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, settings.agent_voice)
    await communicate.save(path)


def _play_mp3(path: str) -> None:
    """Play an mp3 without extra dependencies (Windows: PowerShell MediaPlayer)."""
    import platform
    import subprocess

    system = platform.system()
    if system == "Windows":
        # winsound only does wav; use Windows Media Player COM via PowerShell
        cmd = (
            "Add-Type -AssemblyName presentationCore; "
            f"$p = New-Object System.Windows.Media.MediaPlayer; "
            f"$p.Open('{Path(path).resolve().as_uri()}'); $p.Play(); "
            "Start-Sleep -Milliseconds 500; "
            "while ($p.NaturalDuration.HasTimeSpan -and "
            "$p.Position -lt $p.NaturalDuration.TimeSpan) { Start-Sleep -Milliseconds 200 }; "
            "$p.Close()"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=False)
    elif system == "Darwin":
        subprocess.run(["afplay", path], check=False)
    else:
        subprocess.run(["mpg123", "-q", path], check=False)


def speak(text: str) -> None:
    """Speak text out loud. Long texts are trimmed to keep replies snappy."""
    text = text.strip()
    if not text:
        return
    if len(text) > 800:
        text = text[:800] + "… I've put the rest on screen."
    tmp = Path(tempfile.gettempdir()) / "aria_response.mp3"
    try:
        asyncio.run(_tts_to_file(text, str(tmp)))
        _play_mp3(str(tmp))
    except Exception as e:
        log.warning("TTS failed: %s", e)
