"""Read the tags and embedded artwork of an existing audio file.

The audio-enhancement workflow takes a finished recording and writes a new one.
When the source already carries metadata, the enhanced file should look the same:
the same title, artist, album, year, track, genre and comment, and the same
cover art.  This node reads them so :class:`SaveAudioSmartPrefix` can write them
onto the new file.

Nothing is invented: a field the source does not carry stays empty, and the
report says which file, which container and which fields were actually found.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from .toolkit_logging import get_logger

LOGGER = get_logger("audio_tag_copy")

SELECT_AUDIO = "<select audio>"

# Source field -> the tag name SaveAudioSmartPrefix already understands.
FIELD_ALIASES = {
    "title": ("title", "TIT2", "\xa9nam"),
    "artist": ("artist", "TPE1", "\xa9ART"),
    "album": ("album", "TALB", "\xa9alb"),
    "album_artist": ("albumartist", "TPE2", "aART"),
    "year": ("date", "TDRC", "TYER", "\xa9day"),
    "track": ("tracknumber", "TRCK", "trkn"),
    "genre": ("genre", "TCON", "\xa9gen"),
    "comment": ("comment", "COMM", "\xa9cmt"),
    "composer": ("composer", "TCOM", "\xa9wrt"),
}


def _first(mapping: Dict, names) -> str:
    for name in names:
        value = mapping.get(name)
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
            if value is None:
                continue
        text = str(getattr(value, "text", value)).strip()
        if text:
            return text
    return ""


def read_tags(path: Path) -> Dict[str, str]:
    """Text tags of one audio file, using whichever container it actually is."""
    from mutagen import File as MutagenFile

    audio = MutagenFile(str(path))
    if audio is None:
        return {}
    tags: Dict[str, str] = {}
    source = getattr(audio, "tags", None)
    mapping: Dict = {}
    if source is not None:
        try:
            mapping = dict(source)
        except (TypeError, ValueError):
            mapping = {}
    for field, names in FIELD_ALIASES.items():
        value = _first(mapping, names)
        if value:
            tags[field] = value
    # 'track' often arrives as "3/12"; keep the number the saver expects.
    if tags.get("track"):
        tags["track"] = tags["track"].split("/")[0].strip()
    if tags.get("year"):
        tags["year"] = tags["year"][:4]
    return tags


def extract_cover_art(path: Path, directory: str) -> str:
    """Write the first embedded picture to a temporary file; '' when there is none."""
    try:
        from mutagen import File as MutagenFile
        from mutagen.flac import FLAC
        from mutagen.id3 import ID3
    except Exception:  # pragma: no cover - dependency guard
        return ""
    data = None
    mime = "image/jpeg"
    try:
        audio = MutagenFile(str(path))
        pictures = getattr(audio, "pictures", None)
        if pictures:
            data = pictures[0].data
            mime = getattr(pictures[0], "mime", mime) or mime
        else:
            tags = getattr(audio, "tags", None)
            if tags is not None:
                for key in getattr(tags, "keys", lambda: [])():
                    if str(key).startswith("APIC"):
                        frame = tags[key]
                        data = frame.data
                        mime = getattr(frame, "mime", mime) or mime
                        break
    except Exception as exc:  # pragma: no cover - a broken tag must not stop the run
        LOGGER.warning("Could not read embedded cover art from %s: %s", path.name, exc)
        return ""
    if not data:
        return ""
    suffix = ".png" if "png" in str(mime).lower() else ".jpg"
    target = Path(directory) / f"source-cover{suffix}"
    target.write_bytes(data)
    return str(target)


def source_basename(filename) -> str:
    import re
    from pathlib import PurePosixPath
    name = re.sub(r"\s+\[(?:input|output|temp)\]$", "", str(filename).strip())
    return PurePosixPath(name.replace("\\", "/")).name


def audio_file_inventory() -> List[str]:
    """The audio files of the ComfyUI input directory, for the picker."""
    files: List[str] = []
    try:
        import folder_paths
        root = Path(folder_paths.get_input_directory())
        if root.is_dir():
            files = folder_paths.filter_files_content_types(
                [entry.name for entry in root.iterdir() if entry.is_file()], ["audio", "video"])
    except (ImportError, AttributeError, OSError):
        pass
    return sorted(files)


class MiniMaxAudioTagReader:
    """Read tags and cover art from an existing audio file for the new output."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_file": ([SELECT_AUDIO] + audio_file_inventory(),
                               {"default": SELECT_AUDIO, "audio_upload": True}),
            },
            "optional": {
                "copy_cover_art": ("BOOLEAN", {"default": True}),
                "overrides_json": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("audio_tags_json", "cover_image_path", "tag_report_json")
    FUNCTION = "read"
    CATEGORY = "Music Production Toolkit/audio"
    DESCRIPTION = (
        "Reads the title, artist, album, year, track, genre, comment and composer of an existing audio "
        "file, plus its embedded cover art, so an enhanced export carries exactly the same metadata as the "
        "original. Empty fields stay empty; nothing is invented. Connect the output to Save Audio Smart "
        "Prefix's audio_tags_json and cover_image_path inputs."
    )

    @classmethod
    def VALIDATE_INPUTS(cls, **kwargs):
        return True

    @classmethod
    def IS_CHANGED(cls, audio_file=SELECT_AUDIO, **kwargs):
        try:
            import folder_paths
            stat = Path(folder_paths.get_annotated_filepath(audio_file)).stat()
            signature = (stat.st_mtime_ns, stat.st_size)
        except (ImportError, OSError, AttributeError):
            signature = float("nan")
        return signature

    def read(self, audio_file=SELECT_AUDIO, copy_cover_art=True, overrides_json=""):
        name = source_basename(audio_file)
        if not name or name == SELECT_AUDIO:
            raise ValueError("Read audio tags: select the audio file to read the tags from.")
        import folder_paths
        path = Path(folder_paths.get_annotated_filepath(audio_file))
        if not path.is_file():
            raise ValueError(f"Read audio tags: audio file not found: {name}")

        overrides: Dict[str, str] = {}
        raw = str(overrides_json or "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                overrides = {str(key): str(value) for key, value in parsed.items() if str(value).strip()}

        tags = read_tags(path)
        # Explicit values win, so a user can correct one field without losing the rest.
        tags.update(overrides)

        cover = ""
        if copy_cover_art:
            cover = extract_cover_art(path, tempfile.gettempdir())

        report = {
            "schema": "music_source_tags_v1",
            "source_file": name,
            "fields_found": sorted(tags),
            "fields_missing": sorted(set(FIELD_ALIASES) - set(tags)),
            "overridden": sorted(overrides),
            "cover_art": bool(cover),
        }
        LOGGER.info(
            "Read audio tags from %s: %s%s",
            name, ", ".join(sorted(tags)) or "no tags found",
            " plus embedded cover art" if cover else "",
        )
        return (json.dumps(tags, ensure_ascii=False), cover, json.dumps(report, ensure_ascii=False))


NODE_CLASS_MAPPINGS = {"MiniMaxAudioTagReader": MiniMaxAudioTagReader}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxAudioTagReader": "Read tags from source audio"}


__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "extract_cover_art",
    "read_tags",
]
