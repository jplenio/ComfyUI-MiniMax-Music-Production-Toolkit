# Save Image Smart Prefix

Saves generated artwork as JPEG using the workflow's smart filename prefix and collision handling.

**Node ID:** `SaveImageSmartPrefix`  
**Category:** `MiniMax Music Production Toolkit/artwork`

## Inputs

### Required

- **`image`** (`IMAGE`) — ComfyUI IMAGE tensor to save as the cover JPG.
- **`filename_prefix`** (`STRING`) — Output prefix/path for the JPG cover, normally produced by MiniMax Output Paths. The node adds .jpg and resolves collisions according to collision_mode.
- **`collision_mode`** (choice: `auto_increment`, `overwrite`, `error_if_exists`) — What to do when the target file already exists: auto_increment creates a new numbered filename, overwrite replaces it, and error_if_exists stops with an error.
- **`create_directories`** (`BOOLEAN`) — Create missing output folders automatically. Disable only if you deliberately want saving to fail when the destination directory does not already exist.
- **`jpeg_quality`** (`INT`) — JPEG encoding quality from 50 to 100. Higher values preserve more detail at larger file size; around 90–95 is normally visually transparent for album artwork.

## Outputs

- **`saved_path`** (`STRING`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
