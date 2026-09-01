# MiniMax Standard Audio Tags

Builds standard interoperable audio metadata tags such as Artist, Album, Year, Genre and Composer.

**Node ID:** `MiniMaxStandardAudioTags`  
**Category:** `MiniMax Music Production Toolkit/metadata`

## Inputs

### Required

- **`title`** (`STRING`) — Song title used for metadata, filenames or the reproducibility JSON, depending on the node. This does not alter the audio signal itself.
- **`artist`** (`STRING`) — Primary performing artist tag embedded in the final audio files.
- **`album`** (`STRING`) — Album/release title tag embedded in the final audio files.
- **`year`** (`STRING`) — Release/copyright year tag. Use a four-digit year when possible for broad player compatibility.
- **`track`** (`STRING`) — Track-number tag, for example 01 or 3/12. This value is metadata only and does not change filename ordering unless you include it separately in the filename.
- **`genre`** (`STRING`) — Genre tag embedded in compatible audio files. Keep it reasonably concise for broad media-player compatibility.
- **`comment`** (`STRING`) — Free-form standard comment tag. Suitable for copyright or short production notes; detailed generation configuration belongs in the canonical production JSON.
- **`album_artist`** (`STRING`) — Album Artist tag used to group tracks from the same release, especially useful when individual track artists differ.
- **`composer`** (`STRING`) — Composer/songwriter metadata tag embedded in supported audio formats.

## Outputs

- **`audio_tags_json`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
