"""
Validate downloaded music tracks for the Aloft mixing pipeline.

Usage:
    python scripts/validate_music.py [--music-dir ./music_assets]

Checks:
  1. File exists and is non-empty.
  2. pydub can decode the file without error.
  3. Duration is at least 10s (catches truncated downloads).
  4. Audio has at least one channel (catches corrupt/silent-only files).

Exits non-zero if any track fails.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from app.services.music_catalog import TRACKS, MusicTrack

_MIN_DURATION_MS = 10_000  # 10 seconds minimum


def validate_track(track: MusicTrack, music_dir: Path) -> bool:
    path = music_dir / track.local_filename

    # 1. File existence
    if not path.exists():
        print(
            f"  [FAIL] {track.title!r}: file not found at {path}\n"
            f"         Run: python scripts/download_music.py"
        )
        return False

    size = path.stat().st_size
    if size == 0:
        print(f"  [FAIL] {track.title!r}: file is empty ({path})")
        return False

    # 2. Decode with pydub
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(path))
    except Exception as exc:
        print(f"  [FAIL] {track.title!r}: pydub could not decode: {exc}")
        return False

    # 3. Duration check
    duration_ms = len(audio)
    if duration_ms < _MIN_DURATION_MS:
        print(
            f"  [FAIL] {track.title!r}: too short ({duration_ms}ms < "
            f"{_MIN_DURATION_MS}ms). File may be truncated."
        )
        return False

    # 4. Channel check
    if audio.channels < 1:
        print(f"  [FAIL] {track.title!r}: audio has no channels")
        return False

    duration_s = duration_ms / 1000
    print(
        f"  [OK  ] {track.title!r} -- {duration_s:.1f}s, "
        f"{audio.channels}ch, {audio.frame_rate}Hz, {size:,} bytes"
    )
    return True


def main(music_dir: Path) -> int:
    try:
        from pydub import AudioSegment  # noqa: F401
    except ImportError:
        print("ERROR: pydub is not installed. Run: pip install pydub")
        return 1

    print(f"Validating {len(TRACKS)} track(s) in {music_dir} ...")
    print()

    all_ok = True
    for track in TRACKS:
        if not validate_track(track, music_dir):
            all_ok = False

    print()
    if all_ok:
        print("All tracks valid.")
        return 0
    else:
        print("One or more tracks FAILED validation. See output above.")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate Aloft background music files.")
    parser.add_argument(
        "--music-dir",
        default="./music_assets",
        type=Path,
        help="Directory containing downloaded MP3 files (default: ./music_assets)",
    )
    args = parser.parse_args()
    sys.exit(main(args.music_dir))
