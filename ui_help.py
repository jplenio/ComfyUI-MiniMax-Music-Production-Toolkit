"""Central UI help/tooltip support for the custom-node package.

ComfyUI displays the ``tooltip`` option from INPUT_TYPES when the user hovers
an input label/widget.  Keeping the help text in one file makes it possible to
add detailed help to every input without duplicating processing code.
"""
from __future__ import annotations

from copy import deepcopy

# Tooltips shared by fields with the same semantics across nodes.
GENERIC_INPUT_TOOLTIPS = {
    "audio": "ComfyUI AUDIO signal to process. The node preserves channel layout unless its processing explicitly states otherwise; check the node's Info/JSON output for sample-rate or level changes.",
    "title": "Song title used for metadata, filenames or the reproducibility JSON, depending on the node. This does not alter the audio signal itself.",
    "base_seed": "Base integer used when deterministic/incrementing seed generation is selected. With random_each_song it is not the source of the random values; with increment_from_base each variant is derived from this value.",
    "seed_mode": "Controls how generation seeds are created for multiple songs. random_each_song chooses a fresh seed per item; increment_from_base produces reproducible sequential seeds starting from base_seed.",
    "song_count": "Number of song variants to emit from the selected source. Higher values repeat the downstream workflow for additional variants and therefore increase total generation time.",
    "prompt_directory": "Directory containing prompt files for folder mode. Files are read according to the configured extensions and recursive setting.",
    "extensions": "Comma-separated filename extensions accepted in folder mode, for example .txt,.prompt,.md. Other files are ignored.",
    "recursive": "When enabled, prompt files are also discovered in subfolders below prompt_directory. Disable it to process only files directly inside the selected folder.",
    "manual_title": "Fallback/manual song title used in manual source mode. It may later be replaced by an LLM-generated title depending on the workflow branch.",
    "manual_caption": "Manual MiniMax Music caption used when manual source mode is selected. Put musical/production instructions here, not structural Lyrics tags.",
    "manual_lyrics": "Manual MiniMax Music Lyrics field. Use supported section tags and lyric text only; instrumental tracks should contain structural tags rather than prose production instructions.",
    "source_name": "Stable source identifier used to derive output paths and provenance. It normally comes from the prompt filename or manual/LLM source name.",
    "run_index": "1-based variant index for the current song run. It is used for reproducible metadata and optional filename suffixes.",
    "variant_count": "Total number of variants produced from the current source. Used for metadata and to decide whether a variant index should be appended.",
    "generation_seed": "Primary song seed. In this workflow it is the reproducibility anchor used to derive MiniMax text/sampler seeds and can also be reused for artwork generation.",
    "max_duration": "Maximum MiniMax Music generation duration in seconds. This is an upper bound; the model can still end earlier if the musical/Lyrics structure encourages a shorter track.",
    "text_cfg_scale": "Classifier-free guidance strength for the MiniMax text/autoregressive stage. Higher values generally enforce the prompt more strongly but can reduce naturalness or introduce artifacts when pushed too far.",
    "text_top_k": "Top-k sampling limit for the MiniMax text/autoregressive stage. Lower values make sampling more conservative/repetitive; higher values allow more alternatives and variability.",
    "ksampler_steps": "Number of diffusion/sampling steps used by the MiniMax audio sampler. More steps cost more time and are not guaranteed to improve quality beyond the model's useful range.",
    "ksampler_cfg": "Guidance strength for the MiniMax diffusion/audio sampler. Higher values follow conditioning more aggressively but excessive values can sound strained or artificial.",
    "denoise": "Sampling denoise strength. 1.0 performs the full denoising process; lower values retain more of an existing latent/input state where applicable.",
    "sampler_name": "Sampling algorithm used by ComfyUI. Changing it alters the numerical denoising trajectory and can change detail, texture and reproducibility even with the same seed.",
    "scheduler": "Noise/sigma schedule paired with the sampler. It controls how sampling effort is distributed across the denoising trajectory and can affect character and convergence.",
    "pre_preset": "Preset for the low-pass stage before FlashSR. Lower cutoffs remove more original high-frequency content and force FlashSR to reconstruct more; use stronger presets only when the source top end is already problematic.",
    "post_preset": "Preset for the low-pass stage after FlashSR. It gently removes extreme reconstructed high-frequency energy; lower cutoffs sound darker but can better hide artificial 'air' or shimmer.",
    "pre_settings_json": "JSON produced by the pre-FlashSR filter settings node. Connect it to metadata so the exact effective filter settings are preserved for reproducibility.",
    "post_settings_json": "JSON produced by the post-FlashSR filter settings node. Connect it to metadata so the exact effective filter settings are preserved for reproducibility.",
    "flashsr_lowpass_input": "Passes the lowpass_input switch to the FlashSR node. Keep OFF when you already perform the explicit PRE low-pass in this workflow; enabling both can apply unintended extra filtering.",
    "caption": "Final structured MiniMax Music Caption generated or supplied for this song. Stored in the reproducibility JSON and fed to MiniMax Music.",
    "lyrics": "Final MiniMax Music Lyrics/structure field. For pure instrumentals this should contain only supported structural tags; for vocal tracks it contains tags plus singable lyrics.",
    "image_prompt": "Positive Flux artwork prompt associated with the song. It is stored for reproducibility and should describe visual content while avoiding requested text/logos if the workflow requires text-free covers.",
    "source_path": "Original prompt-file path when the song came from a file. Empty/manual values are valid for prompts entered directly in the workflow.",
    "prompt_origin": "Human-readable provenance label describing where the prompt came from, such as manual input, folder file or external LLM.",
    "prompt_provenance_json": "Structured provenance JSON from the prompt/parser stage. Preserve this input if you want to recreate how the final MiniMax prompt was produced.",
    "text_seed": "Seed used by the MiniMax text/autoregressive generation stage. Normally derived from generation_seed for reproducibility.",
    "ksampler_seed": "Seed used by the MiniMax diffusion/audio sampling stage. Normally derived from generation_seed plus the configured offset.",
    "workflow_name": "Descriptive workflow/version string written into the sidecar JSON. It has no audio effect but helps identify exactly which production workflow created a file.",
    "llm_system_prompt": "Complete external-LLM system prompt stored in the sidecar JSON. Keeping it makes later prompt regeneration/auditing possible; it does not itself execute an LLM in this metadata node.",
    "release_prep_json": "JSON report from Audio Release Prep containing effective sample-rate, loudness, true-peak and static-gain measurements. Connect it to preserve final mastering/release settings.",
    "hybrid_crossover_json": "JSON report from the FlashSR Hybrid Crossover. It records sample rates, crossover parameters, HF mix and processing mode for reproducibility.",
    "hf_repair_json": "JSON report from HF Cymbal / Shimmer Repair. It stores the effective preset/custom parameters and measured processing statistics.",
    "declip_json": "JSON report from Audio Declip / Overload Repair. It records clipping detection, repaired/skipped regions, effective reconstruction parameters, safety gain and the algorithm limitations.",
    "metadata_file": "Path to a previously saved song sidecar JSON. The loader reads compatible generation/settings fields from this file so a configuration can be inspected or reused.",
    "collision_mode": "What to do when the target file already exists: auto_increment creates a new numbered filename, overwrite replaces it, and error_if_exists stops with an error.",
    "create_directories": "Create missing output folders automatically. Disable only if you deliberately want saving to fail when the destination directory does not already exist.",
    "filename_prefix": "Output path/prefix supplied by the central path node. Its directory is always used. With filename_mode=album - title or title only, the saver replaces only the basename using standard metadata tags; prefix as provided keeps the original basename.",
    "format": "Audio file format to write. FLAC is lossless, WAV is uncompressed PCM/float, and MP3 is lossy and intended mainly for convenient previews/distribution where appropriate.",
    "mp3_quality": "MP3 encoder quality/bitrate. V0 is high-quality variable bitrate; fixed 320 kbps is the highest listed constant bitrate. This setting has no effect when saving FLAC or WAV.",
    "flac_bit_depth": "PCM bit depth used inside the lossless FLAC file. 24-bit is recommended for a release/master archive; 16-bit is smaller and appropriate when explicitly required.",
    "wav_bit_depth": "Sample representation used for WAV. 32-bit float preserves headroom without integer clipping; 24-bit is a common release/master format; 16-bit is lower precision.",
    "peak_handling": "Optional final safety handling in the saver. leave_unchanged writes the signal as received; normalize_only_if_clipping applies one constant gain only when sample peaks exceed full scale. It does not perform loudness normalization.",
    "write_json_sidecar": "Write the connected metadata_json next to the audio file using the same base name. Recommended for reproducibility.",
    "embed_basic_metadata": "Embed standard title/artist/album/etc. tags in the audio file when the selected format supports them. Production configuration stays in the JSON sidecar rather than custom audio tags.",
    "metadata_json": "Complete production/reproducibility JSON to save beside the audio. The saver writes it unchanged apart from file handling.",
    "audio_tags_json": "Standard audio-tag JSON (artist, album, year, genre, etc.) produced by MiniMax Standard Audio Tags and embedded into compatible audio formats.",
    "cover_image_path": "Path to the generated cover JPG. When connected, the saver embeds a JPEG copy as cover art in supported formats. The source JPG is never modified.",
    "filename_mode": "Controls only the filesystem filename, never the metadata Title. album - title creates [Album] - [Title].extension from audio_tags_json; title only uses only the Title tag; prefix as provided keeps the basename supplied by MiniMax Output Paths. Invalid filename characters are sanitized safely.",
    "embedded_cover_size": "Target square resolution in pixels for the cover image embedded inside FLAC/MP3 metadata. In the supplied workflow this is linked directly to MiniMax Square Image Size, so a 1024x1024 JPG also embeds as 1024x1024. Larger embedded art increases audio-file size and some older players may prefer 512 or 1024.",
    "absolute_directory": "Absolute filesystem directory for the audio output, for example D:\\Music\\Masters. Unlike the smart-prefix saver this destination is not relative to ComfyUI's output folder.",
    "filename": "Base filename without extension for Save Audio Absolute Path. Collision handling may add a numeric suffix depending on collision_mode.",
    "image": "ComfyUI IMAGE tensor to save as the cover JPG.",
    "jpeg_quality": "JPEG encoding quality from 50 to 100. Higher values preserve more detail at larger file size; around 90–95 is normally visually transparent for album artwork.",
    "size_preset": "Square artwork resolution preset. Larger images cost more VRAM/time. Choose custom to use custom_size instead of a fixed preset.",
    "custom_size": "Square width/height in pixels used only when size_preset is custom. Values are kept equal to guarantee a 1:1 cover image.",
    "artist": "Primary performing artist tag embedded in the final audio files.",
    "album": "Album/release title tag embedded in the final audio files.",
    "year": "Release/copyright year tag. Use a four-digit year when possible for broad player compatibility.",
    "track": "Track-number tag, for example 01 or 3/12. This value is metadata only and does not change filename ordering unless you include it separately in the filename.",
    "genre": "Genre tag embedded in compatible audio files. Keep it reasonably concise for broad media-player compatibility.",
    "comment": "Free-form standard comment tag. Suitable for copyright or short production notes; detailed generation configuration belongs in the JSON sidecar.",
    "album_artist": "Album Artist tag used to group tracks from the same release, especially useful when individual track artists differ.",
    "composer": "Composer/songwriter metadata tag embedded in supported audio formats.",
    "model": "ComfyUI model object to sample. This wrapper does not modify the model; it forwards it to the core KSampler while also returning sampler/scheduler names.",
    "positive": "Positive conditioning supplied to the KSampler. It guides sampling toward the requested content.",
    "negative": "Negative conditioning supplied to the KSampler. It guides sampling away from unwanted content; some model families use zeroed/empty negative conditioning instead.",
    "latent_image": "Initial latent tensor to denoise/sample. Its dimensions and batch size determine the generated latent output shape.",
    "seed": "Random seed for the KSampler. The same model, inputs, settings and seed are intended to reproduce the same sampling trajectory, subject to backend/device determinism.",
    "steps": "Number of KSampler denoising steps. More steps increase computation and are not always better; use the range recommended for the model/workflow.",
    "cfg": "Classifier-free guidance scale for the KSampler. Higher values force conditioning more strongly; too high can create harsh or unstable results.",
    "source_name_override": "Optional explicit source name. When non-empty it replaces the automatically derived source identifier used for filenames/provenance.",
    "user_prompt": "Short user/music request sent to the external LLM or stored with the parsed result. This is the concise creative request that the long system prompt expands into MiniMax fields.",
    "user_prompt_source": "Select where the effective user/music prompt comes from. manual uses the editable user_prompt field; bundled_library loads a file shipped in prompts/user; external_directory loads the selected UTF-8 prompt file from user_prompt_directory.",
    "user_prompt_directory": "External user-prompt library directory. Used only when user_prompt_source is external_directory. Type or paste an absolute/local path; the frontend refreshes the file dropdown recursively for .txt, .md and .prompt files. Bundled-library mode ignores this field.",
    "user_prompt_file": "Prompt file selected from the active user-prompt library. The dropdown is populated recursively and shows paths relative to the library root. Use Refresh prompt lists after adding files while ComfyUI is running.",
    "system_prompt_source": "Select where the effective LLM system prompt comes from. manual uses the editable system_prompt field; bundled_library loads a file shipped in prompts/system; external_directory loads the selected file from system_prompt_directory.",
    "system_prompt_directory": "External system-prompt library directory. Used only when system_prompt_source is external_directory. Keep reusable system prompts as UTF-8 .txt, .md or .prompt files and refresh the dropdown after changes.",
    "system_prompt_file": "System-prompt file selected from the active library. The bundled default is the production system prompt included with this toolkit; external files remain outside the repository and are read only when selected.",
    "prefix": "Text prepended to the numeric seed when creating an external-LLM session ID. 'song_' is a clear default. The prefix has no sampling effect; it only makes the session identifier easier to recognize.",
}

# Node-specific help for fields whose names are ambiguous or whose behavior is unique.
NODE_INPUT_TOOLTIPS = {
    "AudioDeclipRepair": {
        "audio": "Original MiniMax/source audio before FlashSR processing. The node searches this signal for near-ceiling flat-topped regions and reconstructs plausible peak curvature before later enhancement stages can exaggerate clipping distortion.",
        "mode": "De-clipping preset. Auto / conservative repairs only strong near-peak plateau evidence and is recommended for unattended batches. Standard widens detection and allows longer repairs. Strong is intentionally aggressive and may alter merely limited peaks. Custom uses the visible values exactly. Analyze only reports clipping without changing audio. Bypass performs no analysis or repair.",
        "detection_threshold_percent": "Lower edge of the region considered for peak reconstruction, expressed as a percentage of each channel's own maximum absolute sample peak. Lower values replace a wider portion around each clipped crest and can smooth harsher clipping, but values that are too low may reshape legitimate loud transients. Used exactly in Custom/Analyze only; presets show their effective value.",
        "plateau_tolerance_percent": "Maximum allowed sample-to-sample change inside a supposed flat top, expressed as a percentage of the channel peak. Very small values detect genuinely flat hard-clipping plateaus and avoid mistaking naturally rounded sine/bass peaks for clipping. Larger values also catch slightly processed/rounded clipping but raise false-positive risk.",
        "min_flat_samples": "Minimum length of a sufficiently flat near-ceiling plateau before the region is treated as clipping. Auto uses 3 samples to avoid reshaping ordinary smooth peaks; Standard can detect shorter two-sample flat tops. A value of 1 is extremely aggressive because any above-threshold peak can qualify.",
        "slope_context_samples": "Number of clean samples outside each clipped region used to estimate entry and exit slopes for the cubic-Hermite reconstruction. More context smooths the estimate and helps low-frequency peaks; too much context can ignore a very fast transient's local shape.",
        "max_repair_ms": "Maximum duration of one clipped region that the node is willing to reconstruct. Very long flat tops contain too much missing information for reliable interpolation; those regions are left unchanged and counted as skipped. Increase only when the source has clearly audible long hard-clipped crests.",
        "max_peak_extension_db": "Safety cap on how far a reconstructed peak may rise above the detected clipping ceiling before final whole-track safety scaling. Higher values allow more natural recovery of strongly chopped peaks but also permit larger speculative overshoot. This is not a loudness boost; the output is subsequently capped with one constant gain when required.",
        "output_ceiling_dbfs": "Sample-peak safety ceiling applied only when actual repairs create peaks above this level. The node then applies ONE constant gain to the entire track, never a limiter or time-varying gain. -1 dBFS is a safe default before FlashSR and later release processing.",
        "mix": "Wet/dry blend between the original clipped waveform and reconstructed waveform. 1.0 uses the full repair, 0.0 leaves the original unchanged. Intermediate values can soften a repair that sounds too reconstructed, but also blend some clipping distortion back in.",
    },
    "FlashSRHybridCrossover": {
        "original_audio": "Original MiniMax/source audio before FlashSR. It is resampled cleanly to the FlashSR sample rate and provides the trustworthy low/mid and original transient information for hybrid modes.",
        "flashsr_audio": "FlashSR-upscaled audio. Hybrid modes mainly use its reconstructed high-frequency content rather than blindly replacing the complete original signal.",
        "mode": "Select how original and FlashSR signals are combined. 'Original + FlashSR air' preserves the complete clean-resampled original and adds only a controlled FlashSR high band. 'Hybrid replace above crossover' uses original low frequencies plus FlashSR high frequencies. Original/FlashSR only are useful A/B references.",
        "crossover_hz": "Center/cutoff of the linear-phase crossover used to isolate FlashSR high-frequency content. Lower values let FlashSR influence more of cymbals/upper harmonics; higher values preserve more original source information. A good starting range is roughly 13–15 kHz for 32 kHz MiniMax sources.",
        "transition_hz": "Width/softness of the FIR crossover transition. Wider values produce a gentler spectral blend and reduce sharp crossover behavior; narrower values separate bands more decisively but require a longer/more selective filter.",
        "flashsr_hf_mix": "Amount of reconstructed FlashSR high band used in hybrid modes. 0 removes the FlashSR HF contribution; 1 uses it at full level; values below 1 are safer for watery cymbals/shimmer. Values above 1 intentionally exaggerate reconstructed air and are normally not recommended for mastering.",
    },
    "HFCymbalShimmerRepair": {
        "audio": "Audio entering the high-frequency repair stage, normally the output of FlashSR Hybrid Crossover. Only the high-frequency band is dynamically shaped; low/mid frequencies keep constant gain.",
        "mode": "Processing preset. Gentle is conservative batch-safe cleanup; Cymbal clarity suppresses smeared sustain more strongly while preserving attacks; Reverb / shimmer control is stronger for diffuse artificial HF tails; Custom uses the visible parameters exactly; Bypass returns the signal unchanged. The visible controls automatically update when a preset is selected.",
        "start_frequency_hz": "Frequency above which the repair detector/process works. Lower values affect more presence/upper harmonics; higher values restrict treatment to air/cymbal frequencies. Too low can dull instruments/vocals, while too high may miss problematic hi-hat smear. Used exactly in Custom; presets overwrite it with their displayed value.",
        "sustain_reduction_db": "Maximum dynamic attenuation applied to sustained/non-transient high-frequency energy. Larger values reduce watery cymbal tails and artificial shimmer more strongly but can make cymbals unnaturally short or dark. Used exactly in Custom; presets set their own displayed value.",
        "fast_envelope_ms": "Time constant of the fast HF envelope used to recognize attacks/transients. Smaller values react more quickly to hi-hat/cymbal attacks; values that are too small can follow fine waveform fluctuations rather than musical transients.",
        "slow_envelope_ms": "Time constant of the slow HF envelope representing sustained energy. Larger values classify longer tails/reverb as sustain; too large can make the detector slow to adapt when the arrangement changes.",
        "transient_sensitivity": "Controls how different the fast and slow envelopes must be before HF energy is treated as a transient and protected from reduction. Lower values protect transients more readily; higher values classify more energy as sustain and therefore apply more reduction.",
        "side_hf_reduction_db": "Static reduction of high-frequency stereo Side information (M/S processing). Useful when artificial reverb/shimmer is excessively wide. Higher values narrow only the HF region; 0 leaves HF stereo width untouched.",
        "static_hf_trim_db": "Constant gain applied to the processed high-frequency band in addition to dynamic sustain reduction. Negative values gently darken the top end; positive values add brightness and can re-expose artifacts.",
        "min_hf_level_dbfs": "Detector floor. HF energy below this level is considered too quiet to process dynamically, preventing the node from riding very low-level noise/reverb tails. A more negative value makes the detector active deeper into quiet material.",
        "mix": "Wet/dry blend for the complete HF repair result. 1.0 is fully processed; 0.0 is original audio; intermediate values parallel-blend the repair and are useful when a preset is slightly too strong.",
    },
    "AudioReleasePrep": {
        "audio": "Final processed audio to prepare for release, normally after HF repair and POST low-pass. Sample-rate conversion happens before loudness/true-peak measurement so the reported values represent the actual output rate.",
        "target_sample_rate": "Final sample rate. 44100 gives standard 44.1 kHz release files, 48000 keeps a 48 kHz production master, and keep leaves the incoming sample rate unchanged. Conversion uses high-quality polyphase FIR resampling.",
        "processing": "Release-prep mode. Resample only changes sample rate without loudness gain. The LUFS presets measure ITU-R BS.1770 loudness/true peak and apply ONE constant gain to the whole track, capped by the true-peak target—no compressor, AGC or time-varying gain. Custom uses the two custom target fields; Bypass changes nothing.",
        "custom_target_lufs": "Integrated loudness target used only when processing=Custom. The node applies a single constant full-program gain; if reaching this target would violate the true-peak ceiling, it stops lower instead of compressing or riding the level.",
        "custom_true_peak_dbtp": "Maximum true-peak target used only when processing=Custom. More negative values leave more codec/playback headroom. This limit can prevent the requested LUFS target from being reached, by design, to preserve internal dynamics.",
    },
    "FlashSRLowpassLab": {
        "preset": "Select a predefined Butterworth low-pass configuration or CUSTOM. PRE presets are intended before FlashSR; POST presets are intended after FlashSR. The visible custom cutoff/order/phase fields update to the selected preset so the effective values are obvious.",
        "custom_cutoff_hz": "Low-pass cutoff used when preset=CUSTOM. Lower frequencies remove more treble; before FlashSR that forces the model to reconstruct more bandwidth, while after FlashSR it more strongly suppresses artificial air.",
        "custom_order": "Butterworth filter order used when preset=CUSTOM. Higher order gives a steeper cutoff. In zero_phase mode the filter runs forward and backward, effectively steepening the magnitude response further.",
        "custom_phase_mode": "Filter phase behavior used when preset=CUSTOM. zero_phase uses forward/backward offline filtering to avoid phase rotation; causal is a one-way filter with normal phase shift and is useful for gentle post-processing.",
        "bypass": "When enabled, return the audio unchanged while still providing settings/info outputs. Useful for A/B testing without rewiring the graph.",
        "preset_override": "Optional connected STRING that overrides the preset widget. Intended for centralized settings nodes; when connected it becomes the effective preset at execution time.",
        "custom_cutoff_override": "Optional connected FLOAT that overrides custom_cutoff_hz. It matters when the effective preset resolves to CUSTOM.",
        "custom_order_override": "Optional connected INT that overrides custom_order. It matters when the effective preset resolves to CUSTOM.",
        "custom_phase_override": "Optional connected STRING overriding custom_phase_mode. Use 'zero_phase' or 'causal'; it matters when the effective preset is CUSTOM.",
        "bypass_override": "Optional connected BOOLEAN overriding the local bypass widget. This allows one centralized settings node to control whether the filter is active.",
    },
    "FlashSRProcessingSettings": {
        "pre_custom_cutoff_hz": "Custom PRE low-pass cutoff used when pre_preset=CUSTOM. Lower values discard more source treble before FlashSR; do not lower it unnecessarily on cymbal-rich material.",
        "pre_custom_order": "Butterworth order for the custom PRE filter. Higher orders make the cutoff steeper; zero-phase processing effectively doubles magnitude attenuation.",
        "pre_custom_phase": "Phase mode for the custom PRE filter. zero_phase is normally preferred before FlashSR because it avoids phase rotation; causal applies a one-way filter.",
        "pre_bypass": "Disable the explicit PRE low-pass while leaving the rest of the FlashSR chain connected. Useful for testing whether original source highs are already cleaner without filtering.",
        "post_custom_cutoff_hz": "Custom POST low-pass cutoff used when post_preset=CUSTOM. Lower values hide more reconstructed extreme treble but can make the release darker.",
        "post_custom_order": "Butterworth order for the custom POST filter. Higher values produce a steeper roll-off near the selected cutoff.",
        "post_custom_phase": "Phase mode for the custom POST filter. causal is intentionally available for a natural one-way roll-off; zero_phase avoids phase rotation but changes the effective magnitude slope because filtering is applied twice.",
        "post_bypass": "Disable the explicit POST low-pass for A/B comparison while preserving the rest of the chain.",
    },
    "MiniMaxPromptBatchLoader": {
        "mode": "Choose folder to read multiple prompt files or manual to use the fields in this node. Folder mode ignores the manual caption/lyrics/title except as implementation fallbacks.",
    },
    "MiniMaxPromptSourceArtworkV16": {
        "source_mode": "Choose folder to parse structured prompt files or manual to use the fields entered in this node. This legacy/source node does not call an LLM itself; it remains available for structured file/manual workflows and backward compatibility.",
        "manual_image_prompt": "Manual positive image prompt used for artwork in manual mode. Describe concrete visual content; avoid text/logos when you want a text-free album cover.",
    },
    "MiniMaxLLMTemplateV16": {
        "system_prompt": "Editable manual system prompt. It is used only when system_prompt_source=manual; library modes load the selected system-prompt file instead. The bundled production prompt enforces Caption → Lyrics → Title → Image_Prompt, robust instrumental structure and artifact-avoidance guidance.",
        "source_name_override": "Optional stable source label. Leave empty to derive a name from the selected user-prompt filename in library mode; manual mode may leave it empty and let the downstream parser derive the song title/source.",
    },
    "MiniMaxParseExternalLLMOutputV16": {
        "structured_llm_output": "Complete assistant text returned by the external LLM. The bundled production prompt requires the order [Caption], [Lyrics], [Title], [Image_Prompt]. The parser remains order-tolerant but malformed or empty required sections raise an error instead of silently generating with missing fields.",
        "fallback_title": "Title used only when a usable [Title] cannot be extracted. It does not replace valid LLM-generated titles.",
    },
    "MiniMaxMusic3GenerationSettings": {
        "ksampler_seed_offset": "Integer offset added to generation_seed to create the diffusion/audio sampler seed. 0 keeps text and sampler seeds aligned; changing it lets you vary the sampler while retaining the same primary generation seed reference.",
    },
    "MiniMaxOutputPaths": {
        "base_output": "Base path relative to ComfyUI's output directory. Date placeholders such as %date:yyyy-MM-dd% are expanded by the saver/path logic; all subdirectories below are appended to this base.",
        "original_subdir": "Subfolder for untouched/original MiniMax audio, typically the 32 kHz FLAC archive.",
        "sr_flac_subdir": "Subfolder for the final/upscaled lossless FLAC output. The name is only a folder label; actual sample rate comes from the audio signal entering the saver.",
        "sr_mp3_subdir": "Subfolder for final/preview MP3 output. The name is only a folder label; encoder quality is controlled in the saver node.",
        "artwork_subdir": "Subfolder for generated cover JPG files. The same base filename is used so cover embedding can be matched to the song.",
        "append_variant_index": "Append the run/variant number to filenames when multiple variants are generated. Recommended to avoid collisions and keep variants easy to associate with metadata.",
        "variant_padding": "Number of digits used for the variant suffix, for example 2 produces _01 and 3 produces _001.",
    },
    "SaveImageSmartPrefix": {
        "filename_prefix": "Output prefix/path for the JPG cover, normally produced by MiniMax Output Paths. The node adds .jpg and resolves collisions according to collision_mode.",
    },
    "SaveAudioSmartPrefix": {
        "filename_prefix": "Output prefix/path for the audio file, normally supplied by MiniMax Output Paths. The node adds the selected extension and a collision suffix if required.",
    },
}

NODE_DESCRIPTIONS = {
    "AudioDeclipRepair": "Detects near-ceiling hard-clipping plateaus and reconstructs plausible missing peak curvature before FlashSR. Uses local cubic-Hermite interpolation and only a single optional whole-track safety gain; it cannot recover exact information destroyed by clipping.",
    "FlashSRHybridCrossover": "Combines a cleanly resampled original with FlashSR in a controlled high-frequency crossover, preserving original transients while adding only as much reconstructed 'air' as desired.",
    "HFCymbalShimmerRepair": "Reduces smeared cymbal/hi-hat sustain and artificial high-frequency shimmer while protecting attacks and leaving low/mid-band level untouched.",
    "AudioReleasePrep": "High-quality sample-rate conversion plus optional BS.1770 loudness/true-peak measurement and constant full-program gain. It never uses compressor/AGC/time-varying loudness riding.",
    "FlashSRLowpassLab": "Configurable Butterworth low-pass for controlled pre/post FlashSR cleanup, with presets, custom cutoff/order/phase and reproducibility outputs.",
    "FlashSRProcessingSettings": "Centralizes PRE/POST low-pass settings and FlashSR lowpass_input so one configuration can drive the processing nodes and metadata consistently.",
    "MiniMaxMusic3GenerationSettings": "Derives MiniMax Music generation parameters and reproducible text/sampler seeds from the primary generation seed.",
    "MiniMaxSongMetadata": "Builds the complete sidecar JSON containing prompts, seeds, MiniMax settings, FlashSR/filter/repair/release settings and optional LLM system prompt.",
    "MiniMaxMetadataLoader": "Loads compatible values from a previously saved MiniMax sidecar JSON for inspection or reconstruction of a generation setup.",
    "MiniMaxLLMTemplateV16": "Resolves manual, bundled-library or external-directory user/system prompts for any external ComfyUI LLM. It performs no network/model call itself and keeps legacy workflow compatibility while providing a reusable file-backed prompt library.",
    "MiniMaxParseExternalLLMOutputV16": "Parses the external LLM's structured [Caption]/[Lyrics]/[Title]/[Image_Prompt] response, validates required music sections, and creates per-song seeds and provenance. Section order is tolerated defensively even though the bundled system prompt requires the canonical order.",
    "MiniMaxLLMSessionId": "Creates a changing text session ID from a seed so an external LLM node is re-executed when the creative prompt itself is unchanged. Set the seed widget's control-after-generate mode to Randomize or Increment for batch use.",
    "MiniMaxPromptSourceArtworkV16": "Folder/manual structured prompt source retained for non-LLM or file-driven workflows.",
    "MiniMaxPromptBatchLoader": "Loads prompt files or manual prompt fields and emits one or more song variants with reproducible source metadata and seeds.",
    "MiniMaxOutputPaths": "Creates consistent relative output prefixes for original audio, release FLAC/MP3 and artwork.",
    "MiniMaxStandardAudioTags": "Builds standard interoperable audio metadata tags such as Artist, Album, Year, Genre and Composer.",
    "MiniMaxSquareImageSize": "Produces equal width/height values for square album artwork using common presets or a custom size.",
    "SaveImageSmartPrefix": "Saves generated artwork as JPEG using the workflow's smart filename prefix and collision handling.",
    "SaveAudioSmartPrefix": "Saves FLAC/MP3/WAV with smart relative paths, Album - Title filesystem naming, configurable embedded-cover resolution, standard tags and JSON sidecar.",
    "SaveAudioAbsolutePath": "Saves FLAC/MP3/WAV to an explicit absolute directory with configurable quality, bit depth and safe clipping handling.",
    "KSamplerWithConfig": "Core KSampler-compatible wrapper that additionally returns the effective sampler and scheduler names for reproducibility metadata.",
}


def _fallback_tooltip(name: str) -> str:
    pretty = name.replace("_", " ")
    return f"Configuration input '{pretty}'. This value is passed directly to the node's processing logic; keep it at the workflow default unless you intentionally want to change that part of the production chain."


def _decorate_spec(spec, tooltip: str):
    """Return a copy of an INPUT_TYPES spec with a ComfyUI tooltip option."""
    if not isinstance(spec, tuple) or not spec:
        return spec
    items = list(spec)
    if len(items) >= 2 and isinstance(items[1], dict):
        opts = dict(items[1])
        opts["tooltip"] = tooltip
        items[1] = opts
    else:
        items.insert(1, {"tooltip": tooltip})
    return tuple(items)


def install_input_tooltips(node_class_mappings):
    """Decorate every required/optional INPUT_TYPES field in every registered node."""
    for comfy_name, cls in node_class_mappings.items():
        if getattr(cls, "_minimax_tooltips_installed", False):
            continue
        original = getattr(cls, "INPUT_TYPES", None)
        if original is None:
            continue
        class_name = getattr(cls, "__name__", comfy_name)

        def wrapped_input_types(_cls, _original=original, _comfy_name=comfy_name, _class_name=class_name):
            data = deepcopy(_original())
            specific = NODE_INPUT_TOOLTIPS.get(_comfy_name, {})
            if not specific:
                specific = NODE_INPUT_TOOLTIPS.get(_class_name, {})
            for section in ("required", "optional"):
                fields = data.get(section, {})
                for name, spec in list(fields.items()):
                    tooltip = specific.get(name) or GENERIC_INPUT_TOOLTIPS.get(name) or _fallback_tooltip(name)
                    fields[name] = _decorate_spec(spec, tooltip)
            return data

        cls.INPUT_TYPES = classmethod(wrapped_input_types)
        if comfy_name in NODE_DESCRIPTIONS:
            cls.DESCRIPTION = NODE_DESCRIPTIONS[comfy_name]
        elif class_name in NODE_DESCRIPTIONS:
            cls.DESCRIPTION = NODE_DESCRIPTIONS[class_name]
        cls._minimax_tooltips_installed = True


def find_missing_explicit_tooltips(node_class_mappings):
    """Developer/test helper: list inputs that would need the generic fallback text."""
    missing = []
    for comfy_name, cls in node_class_mappings.items():
        original = getattr(cls, "INPUT_TYPES", None)
        if original is None:
            continue
        data = original()
        specific = NODE_INPUT_TOOLTIPS.get(comfy_name, {}) or NODE_INPUT_TOOLTIPS.get(getattr(cls, "__name__", comfy_name), {})
        for section in ("required", "optional"):
            for name in data.get(section, {}):
                if name not in specific and name not in GENERIC_INPUT_TOOLTIPS:
                    missing.append((comfy_name, section, name))
    return missing
