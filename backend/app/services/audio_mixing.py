from __future__ import annotations

import io
import sys

# Handle Python 3.13 compatibility - audioop was removed
try:
    from pydub import AudioSegment
    _PYDUB_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    _PYDUB_AVAILABLE = False
    AudioSegment = None

_MUSIC_VOLUME_REDUCTION_DB = 18.0
_FADE_MS = 1500


class AudioMixingError(Exception):
    pass


def mix_narration_with_music(narration_bytes: bytes, music_file_path: str) -> bytes:
    """Mix narration over a background music bed.

    Music is lowered 18dB, faded in/out, and looped or trimmed to match
    narration duration. Output format matches narration input format.

    Raises AudioMixingError if either input can't be decoded or if pydub
    is not available (Python 3.13+ compatibility).
    """
    if not _PYDUB_AVAILABLE:
        raise AudioMixingError(
            "Audio mixing requires pydub, which is not compatible with Python 3.13+. "
            "Please use Python 3.12 or earlier for audio mixing functionality, "
            "or install the audioop compatibility package."
        )

    fmt = _detect_format(narration_bytes)
    try:
        narration = AudioSegment.from_file(io.BytesIO(narration_bytes), format=fmt)
    except Exception as exc:
        raise AudioMixingError(f"Could not decode narration audio: {exc}") from exc

    try:
        music = AudioSegment.from_file(music_file_path)
    except Exception as exc:
        raise AudioMixingError(f"Could not read music file '{music_file_path}': {exc}") from exc

    fitted = _fit_to_duration(music - _MUSIC_VOLUME_REDUCTION_DB, len(narration))
    mixed = fitted.fade_in(_FADE_MS).fade_out(_FADE_MS).overlay(narration)

    buf = io.BytesIO()
    mixed.export(buf, format=fmt)
    return buf.getvalue()


def _fit_to_duration(music: AudioSegment, target_ms: int) -> AudioSegment:
    if not _PYDUB_AVAILABLE:
        raise AudioMixingError("Audio mixing not available - pydub incompatible with Python 3.13+")
    if len(music) == 0:
        return AudioSegment.silent(duration=target_ms)
    if len(music) >= target_ms:
        return music[:target_ms]
    looped = music
    while len(looped) < target_ms:
        looped += music
    return looped[:target_ms]


def _detect_format(data: bytes) -> str:
    if data[:4] == b"RIFF":
        return "wav"
    return "mp3"
