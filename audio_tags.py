"""Cover decoding and audio tag/cover writing for the smart saver.

Extracted from ``save_audio_smart_prefix`` so the tag/cover code has one owner.
The messages and the tag mapping are unchanged; the only behavioural addition is
:class:`CoverCache`, which decodes and resizes the cover JPEG **at most once per
save invocation** instead of once per audio file.
"""
from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from PIL import Image
except Exception as exc:  # pragma: no cover - dependency guard
    Image = None
    _PIL_IMPORT_ERROR = exc
else:
    _PIL_IMPORT_ERROR = None

try:
    from mutagen.flac import FLAC, Picture
    from mutagen.mp3 import MP3
    from mutagen.wave import WAVE
    from mutagen.id3 import ID3, APIC, COMM, TALB, TCOM, TCON, TIT2, TPE1, TPE2, TRCK, TDRC
except Exception as exc:  # pragma: no cover - dependency guard
    FLAC = Picture = MP3 = WAVE = ID3 = APIC = COMM = TALB = TCOM = TCON = TIT2 = TPE1 = TPE2 = TRCK = TDRC = None
    _MUTAGEN_IMPORT_ERROR = exc
else:
    _MUTAGEN_IMPORT_ERROR = None


class CoverCache:
    """Per-save cache for the encoded cover JPEG.

    One production run embeds the same cover into every batch element and every
    output format; without this the source image was decoded and re-encoded for
    each file.  The cache lives exactly as long as the caller (one ``save()``
    call) and nothing survives beyond it.
    """

    def __init__(self) -> None:
        self._entries: Dict[tuple, bytes] = {}
        self.misses = 0

    def get(self, path: str, target_side: int = 512) -> bytes:
        key = (str(path or ""), int(target_side or 512))
        if key not in self._entries:
            self.misses += 1
            self._entries[key] = _load_cover_bytes(path, target_side=key[1])
        return self._entries[key]


def _load_cover_bytes(path: str, target_side: int = 512) -> bytes:
    if not path:
        return b""
    if Image is None:
        raise RuntimeError(
            "Save Audio Smart Prefix: cover embedding requires Pillow. Run install_requirements.bat. "
            f"Original import error: {_PIL_IMPORT_ERROR}"
        )
    p = Path(os.path.expandvars(os.path.expanduser(path))).resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"Save Audio Smart Prefix: cover image not found: {p}")

    img = Image.open(p).convert("RGB")
    side = max(64, min(4096, int(target_side or 512)))

    # The workflow generates square covers. Keep exact parity with the configured
    # artwork resolution when possible; preserve aspect ratio for unexpected
    # non-square source images.
    if img.width == img.height:
        if img.width != side:
            img = img.resize((side, side), Image.LANCZOS)
    else:
        img.thumbnail((side, side), Image.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95, optimize=True)
    return buf.getvalue()


def _write_standard_tags(
    target: str,
    fmt: str,
    tags_data: Dict[str, Any],
    cover_image_path: str = "",
    embedded_cover_size: int = 512,
    *,
    cover_cache: Optional[CoverCache] = None,
) -> None:
    if not tags_data:
        return
    if FLAC is None:
        raise RuntimeError(
            "Save Audio Smart Prefix: writing audio tags requires mutagen. Run install_requirements.bat. "
            f"Original import error: {_MUTAGEN_IMPORT_ERROR}"
        )

    title = str(tags_data.get("title", "") or "")
    artist = str(tags_data.get("artist", "") or "")
    album = str(tags_data.get("album", "") or "")
    year = str(tags_data.get("year", "") or "")
    track = str(tags_data.get("track", "") or "")
    genre = str(tags_data.get("genre", "") or "")
    comment = str(tags_data.get("comment", "") or "")
    album_artist = str(tags_data.get("album_artist", "") or "")
    composer = str(tags_data.get("composer", "") or "")
    if (cover_image_path or "").strip():
        cover_bytes = (
            cover_cache.get(cover_image_path, embedded_cover_size)
            if cover_cache is not None
            else _load_cover_bytes(cover_image_path, target_side=embedded_cover_size)
        )
    else:
        cover_bytes = b""
    cover_width = cover_height = 0
    if cover_bytes and Image is not None:
        try:
            with Image.open(BytesIO(cover_bytes)) as embedded_img:
                cover_width, cover_height = embedded_img.size
        except Exception:
            cover_width = cover_height = 0

    if fmt == "flac":
        audio = FLAC(target)
        mapping = {
            "TITLE": title,
            "ARTIST": artist,
            "ALBUM": album,
            "DATE": year,
            "TRACKNUMBER": track,
            "GENRE": genre,
            "DESCRIPTION": comment,
            "COMMENT": comment,
            "ALBUMARTIST": album_artist,
            "COMPOSER": composer,
        }
        for key, value in mapping.items():
            if value:
                audio[key] = [value]
        if cover_bytes:
            audio.clear_pictures()
            pic = Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.desc = "Cover"
            pic.width = int(cover_width)
            pic.height = int(cover_height)
            pic.depth = 24
            pic.colors = 0
            pic.data = cover_bytes
            audio.add_picture(pic)
        audio.save()
        return

    if fmt == "mp3":
        audio = MP3(target, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags

        def set_one(frame_id, frame):
            tags.delall(frame_id)
            tags.add(frame)

        if title:
            set_one("TIT2", TIT2(encoding=3, text=[title]))
        if artist:
            set_one("TPE1", TPE1(encoding=3, text=[artist]))
        if album:
            set_one("TALB", TALB(encoding=3, text=[album]))
        if year:
            set_one("TDRC", TDRC(encoding=3, text=[year]))
        if track:
            set_one("TRCK", TRCK(encoding=3, text=[track]))
        if genre:
            set_one("TCON", TCON(encoding=3, text=[genre]))
        if comment:
            tags.delall("COMM")
            tags.add(COMM(encoding=3, lang="eng", desc="", text=[comment]))
        if album_artist:
            set_one("TPE2", TPE2(encoding=3, text=[album_artist]))
        if composer:
            set_one("TCOM", TCOM(encoding=3, text=[composer]))
        if cover_bytes:
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_bytes))
        audio.save(v2_version=3)
        return

    if fmt == "wav":
        # WAV tagging is inconsistent across apps. Keep it minimal and sidecar JSON as canonical record.
        if not any([title, artist, album, year, track, genre, comment, album_artist, composer]):
            return
        audio = WAVE(target)
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        tags.delall("TIT2")
        if title:
            tags.add(TIT2(encoding=3, text=[title]))
        if artist:
            tags.delall("TPE1")
            tags.add(TPE1(encoding=3, text=[artist]))
        if album:
            tags.delall("TALB")
            tags.add(TALB(encoding=3, text=[album]))
        if year:
            tags.delall("TDRC")
            tags.add(TDRC(encoding=3, text=[year]))
        if track:
            tags.delall("TRCK")
            tags.add(TRCK(encoding=3, text=[track]))
        if genre:
            tags.delall("TCON")
            tags.add(TCON(encoding=3, text=[genre]))
        if comment:
            tags.delall("COMM")
            tags.add(COMM(encoding=3, lang="eng", desc="", text=[comment]))
        if album_artist:
            tags.delall("TPE2")
            tags.add(TPE2(encoding=3, text=[album_artist]))
        if composer:
            tags.delall("TCOM")
            tags.add(TCOM(encoding=3, text=[composer]))
        audio.save()
