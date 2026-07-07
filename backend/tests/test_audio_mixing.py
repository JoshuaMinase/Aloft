"""
Mixing tests use WAV for synthetic fixtures (no ffmpeg needed for WAV
encode/decode) -- the service itself takes and returns MP3 bytes in
production, but the mixing logic is identical regardless of container format.
The service-level AudioMixingError tests use raw bytes to trigger decode
failures without needing ffmpeg at all.

NOTE: These tests are skipped on Python 3.13+ due to pydub incompatibility
(audioop module was removed in Python 3.13). They can be re-enabled when
running on Python 3.12 or when pydub is updated.
"""

from __future__ import annotations

import io
import sys

import pytest

# Skip all audio mixing tests on Python 3.13+ due to pydub incompatibility
if sys.version_info >= (3, 13):
    pytest.skip(
        "pydub is incompatible with Python 3.13 (audioop module removed)", allow_module_level=True
    )

from pydub import AudioSegment
from pydub.generators import Sine

from app.services.audio_mixing import AudioMixingError, _fit_to_duration, mix_narration_with_music


def _wav_bytes(duration_ms: int, freq: int = 440) -> bytes:
    """WAV export requires no external codec."""
    buf = io.BytesIO()
    Sine(freq).to_audio_segment(duration=duration_ms).export(buf, format="wav")
    return buf.getvalue()


def _wav_file(tmp_path, name: str, duration_ms: int, freq: int = 220) -> str:
    path = tmp_path / name
    Sine(freq).to_audio_segment(duration=duration_ms).export(str(path), format="wav")
    return str(path)


# --- _fit_to_duration unit tests (pure logic, no ffmpeg) ---


def test_fit_trims_music_longer_than_target():
    music = Sine(220).to_audio_segment(duration=5000)
    result = _fit_to_duration(music, 2000)
    assert len(result) == 2000


def test_fit_loops_music_shorter_than_target():
    music = Sine(220).to_audio_segment(duration=1000)
    result = _fit_to_duration(music, 3000)
    assert len(result) == 3000


def test_fit_returns_silence_for_empty_segment():
    result = _fit_to_duration(AudioSegment.empty(), 2000)
    assert len(result) == 2000


def test_fit_exact_duration_unchanged():
    music = Sine(220).to_audio_segment(duration=2000)
    result = _fit_to_duration(music, 2000)
    assert len(result) == 2000


# --- mix_narration_with_music integration tests (WAV fixtures, no ffmpeg) ---


def test_mix_produces_output_matching_narration_duration(tmp_path):
    narration = _wav_bytes(3000)
    music_path = _wav_file(tmp_path, "music.wav", 1000)

    mixed_bytes = mix_narration_with_music(narration, music_path)
    mixed = AudioSegment.from_file(io.BytesIO(mixed_bytes), format="wav")

    assert abs(len(mixed) - 3000) < 100


def test_mix_short_music_is_looped(tmp_path):
    narration = _wav_bytes(3000)
    music_path = _wav_file(tmp_path, "short.wav", 1000)

    result = mix_narration_with_music(narration, music_path)
    assert len(result) > 0


def test_mix_long_music_is_trimmed(tmp_path):
    narration = _wav_bytes(3000)
    music_path = _wav_file(tmp_path, "long.wav", 10000)

    mixed = AudioSegment.from_file(
        io.BytesIO(mix_narration_with_music(narration, music_path)), format="wav"
    )
    assert abs(len(mixed) - 3000) < 100


def test_mix_reduces_music_volume(tmp_path):
    narration = _wav_bytes(3000)
    music_path = _wav_file(tmp_path, "loud.wav", 3000)
    loud_dbfs = Sine(220).to_audio_segment(duration=3000).dBFS

    mixed = AudioSegment.from_file(
        io.BytesIO(mix_narration_with_music(narration, music_path)), format="wav"
    )
    assert mixed.dBFS < loud_dbfs + 6


def test_raises_on_corrupt_narration(tmp_path):
    music_path = _wav_file(tmp_path, "music.wav", 1000)
    with pytest.raises(AudioMixingError, match="Could not decode narration"):
        mix_narration_with_music(b"not audio", music_path)


def test_raises_on_corrupt_music_file(tmp_path):
    narration = _wav_bytes(3000)
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not audio")
    with pytest.raises(AudioMixingError, match="Could not read music file"):
        mix_narration_with_music(narration, str(bad))


def test_silent_music_does_not_crash(tmp_path):
    narration = _wav_bytes(3000)
    path = tmp_path / "silent.wav"
    AudioSegment.silent(duration=2000).export(str(path), format="wav")
    assert len(mix_narration_with_music(narration, str(path))) > 0
