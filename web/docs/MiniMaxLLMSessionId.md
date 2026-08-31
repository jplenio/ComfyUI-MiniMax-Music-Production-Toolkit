# LLM Session ID / Cache Buster

Creates a changing text session ID from a seed so an external LLM node is re-executed when the creative prompt itself is unchanged. Set the seed widget's control-after-generate mode to Randomize or Increment for batch use.

**Node ID:** `MiniMaxLLMSessionId`  
**Category:** `MiniMax Music Production Toolkit/utilities`

## Inputs

### Required

- **`seed`** (`INT`) — Random seed for the KSampler. The same model, inputs, settings and seed are intended to reproduce the same sampling trajectory, subject to backend/device determinism.
- **`prefix`** (`STRING`) — Text prepended to the numeric seed when creating an external-LLM session ID. 'song_' is a clear default. The prefix has no sampling effect; it only makes the session identifier easier to recognize.

## Outputs

- **`session_id`** (`STRING`)
- **`seed`** (`INT`)

## Usage notes

Start with the defaults used by the bundled example workflow unless you have a specific reason to change this stage. Hover each input label in ComfyUI for parameter guidance.
