from __future__ import annotations

import io
import tempfile
from pathlib import Path

# Handle Python 3.13 compatibility - audioop was removed
try:
    from pydub import AudioSegment

    _PYDUB_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    _PYDUB_AVAILABLE = False
    AudioSegment = None

# Python 3.13+ compatible audio processing using numpy + soundfile
try:
    import numpy as np
    import soundfile as sf

    _NUMPY_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    _NUMPY_AVAILABLE = False
    np = None
    sf = None

_MUSIC_VOLUME_REDUCTION_DB = 18.0
_FADE_MS = 1500
_MUSIC_VOLUME_RATIO = 0.1  # -18dB ≈ 0.125, using 0.1 for safety


class AudioMixingError(Exception):
    pass


def mix_narration_with_music(narration_bytes: bytes, music_file_path: str) -> bytes:
    """Mix narration over a background music bed.

    Music is lowered 18dB, faded in/out, and looped or trimmed to match
    narration duration. Output format matches narration input format.

    Raises AudioMixingError if either input can't be decoded or if no
    audio processing library is available.
    """
    # Try numpy + soundfile first (Python 3.13+ compatible)
    if _NUMPY_AVAILABLE:
        return _mix_with_numpy(narration_bytes, music_file_path)

    # Fall back to pydub (Python 3.12 and earlier)
    if _PYDUB_AVAILABLE:
        return _mix_with_pydub(narration_bytes, music_file_path)

    raise AudioMixingError(
        "Audio mixing requires either numpy+soundfile (Python 3.13+) or pydub (Python 3.12-). "
        "Install with: pip install numpy soundfile"
    )


def _mix_with_numpy(narration_bytes: bytes, music_file_path: str) -> bytes:
    """Mix audio using numpy + soundfile (Python 3.13+ compatible)."""
    try:
        # Detect input format
        fmt = _detect_format(narration_bytes)

        # Load narration audio
        with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as temp_narration:
            temp_narration.write(narration_bytes)
            temp_narration_path = temp_narration.name

        try:
            narration_audio, sr = sf.read(temp_narration_path, always_2d=True)
        finally:
            Path(temp_narration_path).unlink(missing_ok=True)

        # Load music audio
        try:
            music_audio, music_sr = sf.read(music_file_path, always_2d=True)
        except Exception as exc:
            raise AudioMixingError(f"Could not read music file '{music_file_path}': {exc}") from exc

        # Resample music to match narration if needed (simple linear interpolation)
        if music_sr != sr:
            import numpy as np

            num_samples = int(len(music_audio) * sr / music_sr)
            indices = np.linspace(0, len(music_audio) - 1, num_samples)
            music_audio = music_audio[np.clip(indices.astype(int), 0, len(music_audio) - 1)]

        # Reduce music volume and fit to narration duration
        music_audio = _fit_music_to_narration(music_audio, len(narration_audio))

        # Apply fade in/out to music
        music_audio = _apply_fade(music_audio, _FADE_MS, sr)

        # Mix narration with music (narration takes priority)
        mixed_audio = narration_audio + music_audio

        # Normalize to prevent clipping
        max_val = np.max(np.abs(mixed_audio))
        if max_val > 0.95:
            mixed_audio = mixed_audio / max_val * 0.95

        # Export to bytes
        with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as temp_output:
            temp_output_path = temp_output.name

        try:
            sf.write(temp_output_path, mixed_audio, sr)
            with open(temp_output_path, "rb") as f:
                return f.read()
        finally:
            Path(temp_output_path).unlink(missing_ok=True)

    except Exception as exc:
        raise AudioMixingError(f"Audio mixing failed: {exc}") from exc


def _mix_with_pydub(narration_bytes: bytes, music_file_path: str) -> bytes:
    """Mix audio using pydub (Python 3.12 and earlier)."""
    fmt = _detect_format(narration_bytes)
    try:
        narration = AudioSegment.from_file(io.BytesIO(narration_bytes), format=fmt)
    except Exception as exc:
        raise AudioMixingError(f"Could not decode narration audio: {exc}") from exc

    try:
        music = AudioSegment.from_file(music_file_path)
    except Exception as exc:
        raise AudioMixingError(f"Could not read music file '{music_file_path}': {exc}") from exc

    fitted = _fit_to_duration_pydub(music - _MUSIC_VOLUME_REDUCTION_DB, len(narration))
    mixed = fitted.fade_in(_FADE_MS).fade_out(_FADE_MS).overlay(narration)

    buf = io.BytesIO()
    mixed.export(buf, format=fmt)
    return buf.getvalue()


def _fit_music_to_narration(music: np.ndarray, narration_length: int) -> np.ndarray:
    """Fit music to narration duration by looping or trimming."""
    if len(music) == 0:
        return np.zeros((narration_length, music.shape[1]))

    if len(music) >= narration_length:
        return music[:narration_length] * _MUSIC_VOLUME_RATIO

    # Loop music to match narration length
    looped = music.copy()
    while len(looped) < narration_length:
        looped = np.concatenate([looped, music])

    return looped[:narration_length] * _MUSIC_VOLUME_RATIO


def _apply_fade(audio: np.ndarray, fade_ms: int, sample_rate: int) -> np.ndarray:
    """Apply fade in/out to audio."""
    fade_samples = int(fade_ms * sample_rate / 1000)

    if len(audio) < 2 * fade_samples:
        # Audio too short for full fade, just apply half fade
        fade_samples = len(audio) // 2

    if fade_samples <= 0:
        return audio

    # Fade in
    fade_in_curve = np.linspace(0, 1, fade_samples)
    audio[:fade_samples] *= fade_in_curve[:, np.newaxis]

    # Fade out
    fade_out_curve = np.linspace(1, 0, fade_samples)
    audio[-fade_samples:] *= fade_out_curve[:, np.newaxis]

    return audio


def _fit_to_duration_pydub(music: AudioSegment, target_ms: int) -> AudioSegment:
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
