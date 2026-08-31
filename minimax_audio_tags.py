from __future__ import annotations

import json


def _clean(v):
    return str(v).strip() if v is not None else ""


class MiniMaxStandardAudioTags:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "title": ("STRING", {"forceInput": True}),
                "artist": ("STRING", {"default": "", "multiline": False}),
                "album": ("STRING", {"default": "", "multiline": False}),
                "year": ("STRING", {"default": "", "multiline": False}),
                "track": ("STRING", {"default": "", "multiline": False}),
                "genre": ("STRING", {"default": "", "multiline": False}),
                "comment": ("STRING", {"default": "", "multiline": True}),
                "album_artist": ("STRING", {"default": "", "multiline": False}),
                "composer": ("STRING", {"default": "", "multiline": False}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("audio_tags_json",)
    FUNCTION = "build"
    CATEGORY = "MiniMax Music Production Toolkit/metadata"

    def build(self, title, artist, album, year, track, genre, comment, album_artist, composer):
        data = {
            "title": _clean(title),
            "artist": _clean(artist),
            "album": _clean(album),
            "year": _clean(year),
            "track": _clean(track),
            "genre": _clean(genre),
            "comment": _clean(comment),
            "album_artist": _clean(album_artist),
            "composer": _clean(composer),
        }
        return (json.dumps(data, ensure_ascii=False),)


NODE_CLASS_MAPPINGS = {"MiniMaxStandardAudioTags": MiniMaxStandardAudioTags}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxStandardAudioTags": "MiniMax Standard Audio Tags"}
