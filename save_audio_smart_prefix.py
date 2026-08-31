from __future__ import annotations

from .toolkit_logging import get_logger

LOGGER = get_logger("save_audio_smart_prefix")

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import torch

try:
    import soundfile as sf
except Exception as exc:
    sf = None
    _SOUNDFILE_IMPORT_ERROR = exc
else:
    _SOUNDFILE_IMPORT_ERROR = None

try:
    from PIL import Image
except Exception as exc:
    Image = None
    _PIL_IMPORT_ERROR = exc
else:
    _PIL_IMPORT_ERROR = None

try:
    from mutagen.flac import FLAC, Picture
    from mutagen.mp3 import MP3
    from mutagen.wave import WAVE
    from mutagen.id3 import ID3, APIC, COMM, TALB, TCOM, TCON, TIT2, TPE1, TPE2, TRCK, TDRC
except Exception as exc:
    FLAC = Picture = MP3 = WAVE = ID3 = APIC = COMM = TALB = TCOM = TCON = TIT2 = TPE1 = TPE2 = TRCK = TDRC = None
    _MUTAGEN_IMPORT_ERROR = exc
else:
    _MUTAGEN_IMPORT_ERROR = None

_DATE_RE = re.compile(r"%date:([^%]+)%")
_WIN_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _validate_audio(audio: Any) -> Tuple[torch.Tensor, int]:
    if not isinstance(audio, dict) or "waveform" not in audio or "sample_rate" not in audio:
        raise ValueError("Save Audio Smart Prefix: expected ComfyUI AUDIO with waveform and sample_rate.")
    waveform = audio["waveform"]
    sample_rate = int(audio["sample_rate"])
    if not isinstance(waveform, torch.Tensor) or waveform.ndim != 3:
        raise ValueError("Save Audio Smart Prefix: waveform must be torch.Tensor [B,C,T].")
    if sample_rate <= 0:
        raise ValueError("Save Audio Smart Prefix: invalid sample rate.")
    return waveform, sample_rate


def _javaish_date_to_strftime(pattern: str) -> str:
    replacements = [
        ("yyyy", "%Y"), ("yy", "%y"),
        ("MM", "%m"), ("dd", "%d"),
        ("HH", "%H"), ("mm", "%M"), ("ss", "%S"),
    ]
    out = pattern
    for src, dst in replacements:
        out = out.replace(src, dst)
    return out


def _expand_date_macros(value: str) -> str:
    now = _dt.datetime.now()

    def repl(match):
        pattern = match.group(1)
        try:
            return now.strftime(_javaish_date_to_strftime(pattern))
        except Exception:
            return match.group(0)

    return _DATE_RE.sub(repl, value)


def _is_abs_any_platform(path: str) -> bool:
    return os.path.isabs(path) or bool(_WIN_ABS_RE.match(path)) or path.startswith("\\\\") or path.startswith("//")


def _comfy_output_dir() -> str:
    try:
        import folder_paths
        return folder_paths.get_output_directory()
    except Exception:
        return os.path.join(os.getcwd(), "output")


def _resolve_prefix(prefix: str) -> str:
    raw = (prefix or "").strip()
    if not raw:
        raise ValueError("Save Audio Smart Prefix: filename_prefix is empty.")
    raw = _expand_date_macros(raw)
    raw = os.path.expanduser(os.path.expandvars(raw))
    if _is_abs_any_platform(raw):
        return os.path.normpath(raw)

    root = os.path.abspath(_comfy_output_dir())
    candidate = os.path.abspath(os.path.join(root, raw))
    try:
        if os.path.commonpath([root, candidate]) != root:
            raise ValueError("Save Audio Smart Prefix: relative filename_prefix may not escape the ComfyUI output directory.")
    except ValueError:
        raise ValueError("Save Audio Smart Prefix: invalid relative filename_prefix.")
    return candidate


def _pick_path(prefix: str, ext: str, collision_mode: str) -> str:
    target = f"{prefix}.{ext}"
    if collision_mode == "overwrite":
        return target
    if collision_mode == "error_if_exists":
        if os.path.exists(target):
            raise FileExistsError(f"Save Audio Smart Prefix: file exists: {target}")
        return target
    if collision_mode != "auto_increment":
        raise ValueError(f"Save Audio Smart Prefix: invalid collision mode '{collision_mode}'.")
    if not os.path.exists(target):
        return target
    for i in range(1, 1_000_000):
        p = f"{prefix}_{i:03d}.{ext}"
        if not os.path.exists(p):
            return p
    raise RuntimeError("Save Audio Smart Prefix: no free auto-increment filename found.")



_FILENAME_INVALID_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename_component(value: str) -> str:
    """Sanitize one filename component for Windows/macOS/Linux output."""
    text = _FILENAME_INVALID_RE.sub("_", str(value or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text or "song"


def _apply_filename_mode(resolved_prefix: str, tags_meta: Dict[str, Any], title: str, filename_mode: str) -> str:
    """Replace only the basename while keeping the directory from filename_prefix.

    Metadata TITLE is never changed here; this only controls the filesystem name.
    """
    mode = str(filename_mode or "album - title").strip().lower()
    directory = os.path.dirname(resolved_prefix)
    fallback_base = os.path.basename(resolved_prefix)

    tag_title = str(tags_meta.get("title", "") or title or fallback_base).strip()
    album = str(tags_meta.get("album", "") or "").strip()

    if mode == "prefix as provided":
        base = fallback_base
    elif mode == "title only":
        base = _safe_filename_component(tag_title or fallback_base)
    elif mode == "album - title":
        clean_title = _safe_filename_component(tag_title or fallback_base)
        clean_album = _safe_filename_component(album) if album else ""
        base = f"{clean_album} - {clean_title}" if clean_album else clean_title
    else:
        raise ValueError(
            "Save Audio Smart Prefix: filename_mode must be "
            "'album - title', 'title only', or 'prefix as provided'."
        )
    return os.path.join(directory, base) if directory else base


def _find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass
    raise RuntimeError("Save Audio Smart Prefix: MP3 needs FFmpeg. Run install_requirements.bat.")


def _prepare(samples: np.ndarray, peak_handling: str):
    samples = np.asarray(samples, dtype=np.float32)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    gain = 1.0

    if peak_handling == "normalize_only_if_clipping":
        # Do nothing when the signal is already within full scale.
        # Only reduce gain if the waveform would actually clip.
        if peak > 1.0:
            gain = 0.999 / peak
            samples = samples * np.float32(gain)
    elif peak_handling == "leave_unchanged":
        pass
    else:
        raise ValueError(f"Save Audio Smart Prefix: unknown peak_handling '{peak_handling}'.")

    return samples, peak, gain


def _write_mp3(target: str, data_tc: np.ndarray, sample_rate: int, quality: str):
    ffmpeg = _find_ffmpeg()
    temp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
            temp = t.name
        sf.write(temp, data_tc, sample_rate, format="WAV", subtype="FLOAT")
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", temp, "-codec:a", "libmp3lame"]
        if quality == "V0 (~245 kbps)":
            cmd += ["-q:a", "0"]
        elif quality == "V2 (~190 kbps)":
            cmd += ["-q:a", "2"]
        elif quality in ("192 kbps", "256 kbps", "320 kbps"):
            cmd += ["-b:a", quality.split()[0] + "k"]
        else:
            raise ValueError(f"Save Audio Smart Prefix: invalid MP3 quality '{quality}'.")
        cmd += ["-id3v2_version", "3", target]
        kwargs = {}
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs)
        if p.returncode != 0:
            raise RuntimeError("Save Audio Smart Prefix: FFmpeg failed:\n" + p.stderr.strip())
    finally:
        if temp:
            try:
                os.remove(temp)
            except OSError:
                pass


def _parse_json_maybe(text: str) -> Dict[str, Any]:
    if not (text or "").strip():
        return {}
    value = json.loads(text)
    return value if isinstance(value, dict) else {"value": value}


def _write_sidecar(target: str, meta: Dict[str, Any], audio_tags: Dict[str, Any], fmt: str, sample_rate: int, peak: float, gain: float, filename_mode: str = "album - title", embedded_cover_size: int = 512) -> str:
    payload = dict(meta) if isinstance(meta, dict) else {"metadata": meta}
    if audio_tags:
        payload["standard_audio_tags"] = dict(audio_tags)
    payload["output"] = {
        "audio_path": os.path.abspath(target),
        "audio_file": os.path.basename(target),
        "format": fmt,
        "sample_rate": int(sample_rate),
        "peak_before_save": float(peak),
        "applied_gain": float(gain),
        "filename_mode": str(filename_mode),
        "embedded_cover_size": int(embedded_cover_size),
    }
    sidecar = os.path.splitext(target)[0] + ".json"
    tmp = sidecar + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, sidecar)
    return sidecar


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


def _write_standard_tags(target: str, fmt: str, tags_data: Dict[str, Any], cover_image_path: str = "", embedded_cover_size: int = 512) -> None:
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
    cover_bytes = _load_cover_bytes(cover_image_path, target_side=embedded_cover_size) if (cover_image_path or "").strip() else b""
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


class SaveAudioSmartPrefix:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio": ("AUDIO",),
                "filename_prefix": ("STRING", {"forceInput": True}),
                "format": (["flac", "mp3", "wav"], {"default": "flac"}),
                "collision_mode": (["auto_increment", "overwrite", "error_if_exists"], {"default": "auto_increment"}),
                "create_directories": ("BOOLEAN", {"default": True}),
                "mp3_quality": (["V0 (~245 kbps)", "V2 (~190 kbps)", "320 kbps", "256 kbps", "192 kbps"], {"default": "V0 (~245 kbps)"}),
                "flac_bit_depth": (["24-bit", "16-bit"], {"default": "24-bit"}),
                "wav_bit_depth": (["32-bit float", "24-bit", "16-bit"], {"default": "32-bit float"}),
                "peak_handling": (["leave_unchanged", "normalize_only_if_clipping"], {"default": "leave_unchanged"}),
                "write_json_sidecar": ("BOOLEAN", {"default": True}),
                "embed_basic_metadata": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "title": ("STRING", {"forceInput": True}),
                "metadata_json": ("STRING", {"forceInput": True}),
                "audio_tags_json": ("STRING", {"forceInput": True}),
                "cover_image_path": ("STRING", {"forceInput": True}),
                "filename_mode": (["album - title", "title only", "prefix as provided"], {"default": "album - title"}),
                "embedded_cover_size": ("INT", {"default": 512, "min": 64, "max": 4096, "step": 64}),
            },
        }

    RETURN_TYPES = ("AUDIO", "STRING", "STRING")
    RETURN_NAMES = ("audio", "saved_path", "metadata_path")
    FUNCTION = "save"
    CATEGORY = "MiniMax Music Production Toolkit/save"
    OUTPUT_NODE = True

    def save(self, audio, filename_prefix, format, collision_mode, create_directories, mp3_quality,
             flac_bit_depth, wav_bit_depth, peak_handling, write_json_sidecar, embed_basic_metadata,
             title="", metadata_json="", audio_tags_json="", cover_image_path="", filename_mode="album - title", embedded_cover_size=512):
        if sf is None:
            raise RuntimeError(
                "Save Audio Smart Prefix requires soundfile. Run install_requirements.bat. "
                f"Original import error: {_SOUNDFILE_IMPORT_ERROR}"
            )

        waveform, sample_rate = _validate_audio(audio)
        resolved_prefix = _resolve_prefix(filename_prefix)
        directory = os.path.dirname(resolved_prefix)
        if directory and not os.path.exists(directory):
            if create_directories:
                os.makedirs(directory, exist_ok=True)
            else:
                raise FileNotFoundError(f"Save Audio Smart Prefix: directory does not exist: {directory}")

        x = waveform.detach().to(device="cpu", dtype=torch.float32).numpy()
        saved: List[str] = []
        sidecars: List[str] = []
        fmt = format.lower()
        base_meta = _parse_json_maybe(metadata_json) if (metadata_json or "").strip() else {}
        tags_meta = _parse_json_maybe(audio_tags_json) if (audio_tags_json or "").strip() else {}
        if title and not tags_meta.get("title"):
            tags_meta["title"] = title
        if title and not base_meta.get("title"):
            base_meta["title"] = title

        # Filesystem naming is independent from metadata TITLE. In the default
        # mode the directory comes from filename_prefix while the basename is
        # rebuilt from standard Album + Title tags.
        resolved_prefix = _apply_filename_mode(resolved_prefix, tags_meta, title, filename_mode)
        embedded_cover_size = max(64, min(4096, int(embedded_cover_size or 512)))

        for b in range(x.shape[0]):
            prefix = resolved_prefix if x.shape[0] == 1 else f"{resolved_prefix}_b{b+1:03d}"
            target = _pick_path(prefix, fmt, collision_mode)
            samples_ct, peak, gain = _prepare(x[b], peak_handling)
            data_tc = np.ascontiguousarray(samples_ct.T, dtype=np.float32)

            if fmt == "flac":
                subtype = "PCM_24" if flac_bit_depth == "24-bit" else "PCM_16"
                sf.write(target, data_tc, sample_rate, format="FLAC", subtype=subtype)
            elif fmt == "wav":
                subtype = {"32-bit float": "FLOAT", "24-bit": "PCM_24", "16-bit": "PCM_16"}[wav_bit_depth]
                sf.write(target, data_tc, sample_rate, format="WAV", subtype=subtype)
            elif fmt == "mp3":
                _write_mp3(target, data_tc, sample_rate, mp3_quality)
            else:
                raise ValueError(f"Save Audio Smart Prefix: unsupported format '{format}'.")

            if embed_basic_metadata and tags_meta:
                _write_standard_tags(target, fmt, tags_meta, cover_image_path, embedded_cover_size)

            sidecar = ""
            if write_json_sidecar and base_meta:
                sidecar = _write_sidecar(target, base_meta, tags_meta, fmt, sample_rate, peak, gain, filename_mode, embedded_cover_size)
                sidecars.append(sidecar)

            saved.append(target)
            LOGGER.info(
                "Saved %s | sr=%d | peak=%.4f | gain=%.6f%s",
                target, sample_rate, peak, gain, f" | metadata={sidecar}" if sidecar else "",
            )

        return (audio, "\n".join(saved), "\n".join(sidecars))


NODE_CLASS_MAPPINGS = {"SaveAudioSmartPrefix": SaveAudioSmartPrefix}
NODE_DISPLAY_NAME_MAPPINGS = {"SaveAudioSmartPrefix": "Save Audio Smart Prefix"}
