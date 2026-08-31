# Save Audio Absolute Path

Saves FLAC/MP3/WAV to an explicit absolute directory with configurable quality, bit depth and safe clipping handling.

**Node ID:** `SaveAudioAbsolutePath`  
**Category:** `MiniMax Music Production Toolkit/save`

## Inputs

### Required

- **`audio`** (`AUDIO`) — ComfyUI AUDIO signal to process. The node preserves channel layout unless its processing explicitly states otherwise; check the node's Info/JSON output for sample-rate or level changes.
- **`absolute_directory`** (`STRING`) — Absolute filesystem directory for the audio output, for example D:\Music\Masters. Unlike the smart-prefix saver this destination is not relative to ComfyUI's output folder.
- **`filename`** (`STRING`) — Base filename without extension for Save Audio Absolute Path. Collision handling may add a numeric suffix depending on collision_mode.
- **`format`** (choice: `mp3`, `flac`, `wav`) — Audio file format to write. FLAC is lossless, WAV is uncompressed PCM/float, and MP3 is lossy and intended mainly for convenient previews/distribution where appropriate.
- **`collision_mode`** (choice: `auto_increment`, `overwrite`, `error_if_exists`) — What to do when the target file already exists: auto_increment creates a new numbered filename, overwrite replaces it, and error_if_exists stops with an error.
- **`create_directories`** (`BOOLEAN`) — Create missing output folders automatically. Disable only if you deliberately want saving to fail when the destination directory does not already exist.
- **`mp3_quality`** (choice: `V0 (~245 kbps)`, `V2 (~190 kbps)`, `320 kbps`, `256 kbps`, `192 kbps`) — MP3 encoder quality/bitrate. V0 is high-quality variable bitrate; fixed 320 kbps is the highest listed constant bitrate. This setting has no effect when saving FLAC or WAV.
- **`flac_bit_depth`** (choice: `24-bit`, `16-bit`) — PCM bit depth used inside the lossless FLAC file. 24-bit is recommended for a release/master archive; 16-bit is smaller and appropriate when explicitly required.
- **`wav_bit_depth`** (choice: `32-bit float`, `24-bit`, `16-bit`) — Sample representation used for WAV. 32-bit float preserves headroom without integer clipping; 24-bit is a common release/master format; 16-bit is lower precision.
- **`peak_handling`** (choice: `leave_unchanged`, `normalize_only_if_clipping`) — Optional final safety handling in the saver. leave_unchanged writes the signal as received; normalize_only_if_clipping applies one constant gain only when sample peaks exceed full scale. It does not perform loudness normalization.

## Outputs

- **`saved_paths`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
