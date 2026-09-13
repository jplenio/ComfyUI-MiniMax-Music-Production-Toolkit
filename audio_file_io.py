"""SoundFile export diagnostics shared by the two audio savers."""
from __future__ import annotations


def write_soundfile(sf, path, data, sample_rate, *, format, subtype, error_label):
    try:
        sf.write(path, data, sample_rate, format=format, subtype=subtype)
    except AssertionError:
        # soundfile 0.13.x asserts on a short libsndfile write without supplying
        # an error message. The caller's staging context discards this file.
        raise RuntimeError(
            f"{error_label}: {format}/{subtype} encoder wrote fewer samples than requested "
            f"({len(data)} frames, {data.shape[1]} channels, {sample_rate} Hz). "
            f"soundfile={getattr(sf, '__version__', 'unknown')}, "
            f"libsndfile={getattr(sf, '__libsndfile_version__', 'unknown')}. "
            "The incomplete file was discarded. Check free disk space and the soundfile/libsndfile installation."
        ) from None
