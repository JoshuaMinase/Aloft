"""
Licensed background music track catalog for Aloft.

All tracks are sourced from Mixkit (mixkit.co/free-stock-music/) under the
Mixkit Free License: https://mixkit.co/license/#musicFree

Mixkit Free License key terms:
  - Free for use in video/audio projects, apps, and digital products.
  - No attribution required.
  - Commercial use permitted.
  - You MAY NOT redistribute the tracks as standalone audio files.
  - Full terms: https://mixkit.co/license/

DOWNLOADING TRACKS
==================
Tracks are not bundled with this repo. Download them once and store locally
(default path: ./music_assets/). Run the download helper:

    python scripts/download_music.py

Or manually fetch from Mixkit:
  1. Visit the track's `page_url`
  2. Click "Download Free Music"
  3. Save to ./music_assets/{track_id}.mp3

The `preview_url` below is the low-quality 30s preview stream from the
Mixkit CDN -- useful for a quick listen/validation but NOT suitable for
production mixing. Always download the full track via the page_url.

ADDING / UPDATING TRACKS
=========================
1. Browse https://mixkit.co/free-stock-music/mood/atmospheric/ or
   https://mixkit.co/free-stock-music/tag/documentary/ for documentary/
   cinematic/ambient tracks (the key moods for flight narration).
2. Add an entry here following the existing format.
3. Run scripts/download_music.py to fetch the new file.
4. Run scripts/validate_music.py to confirm all files are valid audio.

TRACK SELECTION CRITERIA
=========================
Chosen for suitability as a background narration bed:
  - Slow tempo (avoids competing with speech rhythm)
  - Minimal or no vocals
  - Atmospheric / cinematic mood (appropriate for looking at landscape below)
  - Duration ≥ 90s (long enough to be looped for typical POI stories)
  - Not culturally region-specific where possible (global playlist)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MusicTrack:
    track_id: str  # Unique identifier for this catalog
    title: str
    artist: str
    duration_seconds: int  # Approximate -- Mixkit rounds to seconds
    tags: list[str]
    page_url: str  # Mixkit page to download from
    preview_url: str  # CDN stream URL (30s preview only, not full track)
    local_filename: str  # Expected filename in ./music_assets/


# ---------------------------------------------------------------------------
# Curated track list -- all verified on Mixkit as of 2026-07-01
# ---------------------------------------------------------------------------
TRACKS: list[MusicTrack] = [
    MusicTrack(
        track_id="mixkit-feedback-dreams",
        title="Feedback Dreams",
        artist="Eugenio Mininni",
        duration_seconds=149,
        tags=["atmospheric", "mysterious", "cinematic", "documentary", "synth"],
        page_url="https://mixkit.co/free-stock-music/atmospheric/",
        preview_url="https://assets.mixkit.co/music/preview/mixkit-feedback-dreams-319.mp3",
        local_filename="mixkit-feedback-dreams-319.mp3",
    ),
    MusicTrack(
        track_id="mixkit-forest-mist-whispers",
        title="Forest Mist Whispers",
        artist="Alejandro Magaña (A.M.)",
        duration_seconds=151,
        tags=["hopeful", "atmospheric", "piano", "synth", "documentary"],
        page_url="https://mixkit.co/free-stock-music/ambient/",
        preview_url="https://assets.mixkit.co/music/preview/mixkit-forest-mist-whispers-608.mp3",
        local_filename="mixkit-forest-mist-whispers-608.mp3",
    ),
    MusicTrack(
        track_id="mixkit-voxscape",
        title="Voxscape",
        artist="Eugenio Mininni",
        duration_seconds=300,
        tags=["atmospheric", "mystical", "synth", "relaxation", "background"],
        page_url="https://mixkit.co/free-stock-music/ambient/",
        preview_url="https://assets.mixkit.co/music/preview/mixkit-voxscape-321.mp3",
        local_filename="mixkit-voxscape-321.mp3",
    ),
    MusicTrack(
        track_id="mixkit-relaxation-07",
        title="Relaxation 07",
        artist="Lily J",
        duration_seconds=144,
        tags=["atmospheric", "reflective", "electric-guitar", "piano", "documentary"],
        page_url="https://mixkit.co/free-stock-music/ambient/",
        preview_url="https://assets.mixkit.co/music/preview/mixkit-relaxation-07-569.mp3",
        local_filename="mixkit-relaxation-07-569.mp3",
    ),
    MusicTrack(
        track_id="mixkit-vastness",
        title="Vastness",
        artist="Andrew Ev",
        duration_seconds=230,
        tags=["electronica", "atmospheric", "relaxed", "cinematic"],
        page_url="https://mixkit.co/free-stock-music/ambient/",
        preview_url="https://assets.mixkit.co/music/preview/mixkit-vastness-614.mp3",
        local_filename="mixkit-vastness-614.mp3",
    ),
    MusicTrack(
        track_id="mixkit-forest-walk",
        title="Forest Walk",
        artist="Eugenio Mininni",
        duration_seconds=174,
        tags=["electronica", "mysterious", "atmospheric", "cinematic"],
        page_url="https://mixkit.co/free-stock-music/ambient/",
        preview_url="https://assets.mixkit.co/music/preview/mixkit-forest-walk-361.mp3",
        local_filename="mixkit-forest-walk-361.mp3",
    ),
    MusicTrack(
        track_id="mixkit-rest-now",
        title="Rest Now",
        artist="Eugenio Mininni",
        duration_seconds=300,
        tags=["atmospheric", "meditative", "synth", "space"],
        page_url="https://mixkit.co/free-stock-music/ambient/",
        preview_url="https://assets.mixkit.co/music/preview/mixkit-rest-now-322.mp3",
        local_filename="mixkit-rest-now-322.mp3",
    ),
    MusicTrack(
        track_id="mixkit-deep-meditation",
        title="Deep Meditation",
        artist="Alejandro Magaña (A.M.)",
        duration_seconds=147,
        tags=["chillout", "atmospheric", "relaxed", "cinematic"],
        page_url="https://mixkit.co/free-stock-music/ambient/",
        preview_url="https://assets.mixkit.co/music/preview/mixkit-deep-meditation-590.mp3",
        local_filename="mixkit-deep-meditation-590.mp3",
    ),
]

# Alias the full list for convenience
ALL_TRACK_IDS = [t.track_id for t in TRACKS]


def get_track(track_id: str) -> MusicTrack | None:
    """Look up a track by its catalog track_id. Returns None if not found."""
    for track in TRACKS:
        if track.track_id == track_id:
            return track
    return None


def tracks_by_tag(*tags: str) -> list[MusicTrack]:
    """Return tracks that have ALL the given tags."""
    tag_set = set(tags)
    return [t for t in TRACKS if tag_set.issubset(set(t.tags))]
