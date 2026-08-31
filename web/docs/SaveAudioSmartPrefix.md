# Save Audio Smart Prefix

Saves FLAC/MP3/WAV with smart relative paths, Album - Title filesystem naming, configurable embedded-cover resolution, standard tags and JSON sidecar.

**Node ID:** `SaveAudioSmartPrefix`  
**Category:** `MiniMax Music Production Toolkit/save`

## Inputs

### Required

- **`audio`** (`AUDIO`) — ComfyUI AUDIO signal to process. The node preserves channel layout unless its processing explicitly states otherwise; check the node's Info/JSON output for sample-rate or level changes.
- **`filename_prefix`** (`STRING`) — Output prefix/path for the audio file, normally supplied by MiniMax Output Paths. The node adds the selected extension and a collision suffix if required.
- **`format`** (choice: `flac`, `mp3`, `wav`) — Audio file format to write. FLAC is lossless, WAV is uncompressed PCM/float, and MP3 is lossy and intended mainly for convenient previews/distribution where appropriate.
- **`collision_mode`** (choice: `auto_increment`, `overwrite`, `error_if_exists`) — What to do when the target file already exists: auto_increment creates a new numbered filename, overwrite replaces it, and error_if_exists stops with an error.
- **`create_directories`** (`BOOLEAN`) — Create missing output folders automatically. Disable only if you deliberately want saving to fail when the destination directory does not already exist.
- **`mp3_quality`** (choice: `V0 (~245 kbps)`, `V2 (~190 kbps)`, `320 kbps`, `256 kbps`, `192 kbps`) — MP3 encoder quality/bitrate. V0 is high-quality variable bitrate; fixed 320 kbps is the highest listed constant bitrate. This setting has no effect when saving FLAC or WAV.
- **`flac_bit_depth`** (choice: `24-bit`, `16-bit`) — PCM bit depth used inside the lossless FLAC file. 24-bit is recommended for a release/master archive; 16-bit is smaller and appropriate when explicitly required.
- **`wav_bit_depth`** (choice: `32-bit float`, `24-bit`, `16-bit`) — Sample representation used for WAV. 32-bit float preserves headroom without integer clipping; 24-bit is a common release/master format; 16-bit is lower precision.
- **`peak_handling`** (choice: `leave_unchanged`, `normalize_only_if_clipping`) — Optional final safety handling in the saver. leave_unchanged writes the signal as received; normalize_only_if_clipping applies one constant gain only when sample peaks exceed full scale. It does not perform loudness normalization.
- **`write_json_sidecar`** (`BOOLEAN`) — Write the connected metadata_json next to the audio file using the same base name. Recommended for reproducibility.
- **`embed_basic_metadata`** (`BOOLEAN`) — Embed standard title/artist/album/etc. tags in the audio file when the selected format supports them. Production configuration stays in the JSON sidecar rather than custom audio tags.

### Optional

- **`title`** (`STRING`) — Song title used for metadata, filenames or the reproducibility JSON, depending on the node. This does not alter the audio signal itself.
- **`metadata_json`** (`STRING`) — Complete production/reproducibility JSON to save beside the audio. The saver writes it unchanged apart from file handling.
- **`audio_tags_json`** (`STRING`) — Standard audio-tag JSON (artist, album, year, genre, etc.) produced by MiniMax Standard Audio Tags and embedded into compatible audio formats.
- **`cover_image_path`** (`STRING`) — Path to the generated cover JPG. When connected, the saver embeds a JPEG copy as cover art in supported formats. The source JPG is never modified.
- **`filename_mode`** (choice: `album - title`, `title only`, `prefix as provided`) — Controls only the filesystem filename, never the metadata Title. album - title creates [Album] - [Title].extension from audio_tags_json; title only uses only the Title tag; prefix as provided keeps the basename supplied by MiniMax Output Paths. Invalid filename characters are sanitized safely.
- **`embedded_cover_size`** (`INT`) — Target square resolution in pixels for the cover image embedded inside FLAC/MP3 metadata. In the supplied workflow this is linked directly to MiniMax Square Image Size, so a 1024x1024 JPG also embeds as 1024x1024. Larger embedded art increases audio-file size and some older players may prefer 512 or 1024.

## Outputs

- **`audio`** (`AUDIO`)
- **`saved_path`** (`STRING`)
- **`metadata_path`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
