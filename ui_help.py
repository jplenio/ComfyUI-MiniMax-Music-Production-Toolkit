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
    "workflow_name": "Descriptive workflow/version string written into the reproducibility metadata and final production JSON. It has no audio effect but helps identify which workflow version created the files.",
    "llm_system_prompt": "Complete external-LLM system prompt stored in the reproducibility metadata/final production JSON. Keeping it makes later prompt regeneration or auditing possible; this metadata node does not execute an LLM.",
    "release_prep_json": "JSON report from Audio Release Prep containing effective sample-rate, loudness, true-peak and static-gain measurements. Connect it to preserve final mastering/release settings.",
    "hybrid_crossover_json": "JSON report from the FlashSR Hybrid Crossover. It records sample rates, crossover parameters, HF mix and processing mode for reproducibility.",
    "hf_repair_json": "JSON report from HF Cymbal / Shimmer Repair. It stores the effective preset/custom parameters and measured processing statistics.",
    "declip_json": "JSON report from Audio Declip / Overload Repair. It records clipping detection, repaired/skipped regions, effective reconstruction parameters, safety gain and the algorithm limitations.",
    "metadata_file": "Path to a previously saved production JSON. The loader reads compatible generation/settings fields so a configuration can be inspected or reused. Legacy per-audio sidecars remain compatible when they contain the same schema.",
    "collision_mode": "What to do when the target file already exists: auto_increment creates a new numbered filename, overwrite replaces it, and error_if_exists stops with an error.",
    "create_directories": "Create missing output folders automatically. Disable only if you deliberately want saving to fail when the destination directory does not already exist.",
    "filename_prefix": "Output path/prefix supplied by the central path node. Its directory is always used. With filename_mode=album - title or title only, the saver replaces only the basename using standard metadata tags; prefix as provided keeps the original basename.",
    "format": "Audio file format to write. FLAC is lossless, WAV is uncompressed PCM/float, and MP3 is lossy and intended mainly for convenient previews/distribution where appropriate.",
    "mp3_quality": "MP3 encoder quality/bitrate. V0 is high-quality variable bitrate; fixed 320 kbps is the highest listed constant bitrate. This setting has no effect when saving FLAC or WAV.",
    "flac_bit_depth": "PCM bit depth used inside the lossless FLAC file. 24-bit is recommended for a release/master archive; 16-bit is smaller and appropriate when explicitly required.",
    "wav_bit_depth": "Sample representation used for WAV. 32-bit float preserves headroom without integer clipping; 24-bit is a common release/master format; 16-bit is lower precision.",
    "peak_handling": "Optional final safety handling in the saver. leave_unchanged writes the signal as received; normalize_only_if_clipping applies one constant gain only when sample peaks exceed full scale. It does not perform loudness normalization.",
    "write_json_sidecar": "Legacy per-audio sidecar option. For new workflows keep OFF and use Save Production JSON for one canonical JSON in configuration_subdir.",
    "embed_basic_metadata": "Embed standard title/artist/album/etc. tags in the audio file when supported. Detailed generation configuration belongs in the canonical production JSON rather than custom audio tags.",
    "metadata_json": "Complete production/reproducibility JSON to save beside the audio. The saver writes it unchanged apart from file handling.",
    "audio_tags_json": "Standard audio-tag JSON (artist, album, year, genre, etc.) produced by MiniMax Standard Audio Tags and embedded into compatible audio formats.",
    "cover_image_path": "Path to the generated cover JPG. When connected, the saver embeds a JPEG copy as cover art in supported formats. The source JPG is never modified.",
    "filename_mode": "Controls only the filesystem filename, never the metadata Title. album - title creates [Album] - [Title].extension from audio_tags_json; title only uses only the Title tag; prefix as provided keeps the basename supplied by MiniMax Output Paths. Invalid filename characters are sanitized safely.",
    "embedded_cover_size": "Target square resolution in pixels for the cover image embedded inside FLAC/MP3 metadata. In the supplied workflow this is linked directly to MiniMax Square Image Size, so a 1024x1024 JPG also embeds as 1024x1024. Larger embedded art increases audio-file size and some older players may prefer 512 or 1024.",
    "absolute_directory": "Absolute filesystem directory for the audio output, for example D:\\Music\\Masters. Unlike the smart-prefix saver this destination is not relative to ComfyUI's output folder.",
    "filename": "Base filename without extension for Save Audio Absolute Path. Collision handling may add a numeric suffix depending on collision_mode.",
    "image": "ComfyUI IMAGE tensor to save as the cover JPG.",
    "jpeg_quality": "JPEG encoding quality from 50 to 100. Higher values preserve more detail at larger file size; around 90–95 is normally visually transparent for album artwork.",
    "size_preset": "Square artwork resolution preset (256 up to 3096). Larger images cost more VRAM/time. Choose custom to use custom_size instead of a fixed preset. Note: the FLUX.2 latent stage quantizes to multiples of 16, so 3096 is effectively rendered as 3088 - prefer 3072x3072 for an exact size.",
    "custom_size": "Square width/height in pixels used only when size_preset is custom. Values are kept equal to guarantee a 1:1 cover image.",
    "artist": "Primary performing artist tag embedded in the final audio files.",
    "album": "Album/release title tag embedded in the final audio files.",
    "year": "Release/copyright year tag. Use a four-digit year when possible for broad player compatibility.",
    "track": "Track-number tag, for example 01 or 3/12. This value is metadata only and does not change filename ordering unless you include it separately in the filename.",
    "genre": "Genre tag embedded in compatible audio files. Keep it reasonably concise for broad media-player compatibility.",
    "comment": "Free-form standard comment tag. Suitable for copyright or short production notes; detailed generation configuration belongs in the canonical production JSON.",
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
    "user_prompt_file": "Prompt file selected from the active user-prompt library. The dropdown lists the categories alphabetically as directory labels first, with the files of each directory indented beneath them; directory labels are display-only. Use Refresh prompt lists after adding files while ComfyUI is running.",
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
        "preset": "Select a predefined Butterworth low-pass configuration or CUSTOM. PRE presets are intended before FlashSR (light=preserves most MiniMax HF content; recommended 12 kHz=strong suppression of 14-16 kHz while keeping the core spectrum; strong 10 kHz and aggressive 8 kHz ask FlashSR to reconstruct more of the upper spectrum). POST presets are intended after FlashSR (gentle 20 kHz=leaves ~16-18 kHz largely intact and suppresses the extreme top; slightly stronger 19 kHz=for harsh or artificial air). The visible custom cutoff/order/phase fields update to the selected preset so the effective values are obvious.",
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
        "configuration_subdir": "Subfolder for the ONE canonical production JSON per song. Default: json. This replaces duplicated JSON sidecars beside every audio encoding in the bundled workflow.",
        "append_variant_index": "Append the run/variant number to filenames when multiple variants are generated. Recommended to avoid collisions and keep variants easy to associate with metadata.",
        "variant_padding": "Number of digits used for the variant suffix, for example 2 produces _01 and 3 produces _001.",
    },
    "SaveImageSmartPrefix": {
        "filename_prefix": "Output prefix/path for the JPG cover, normally produced by MiniMax Output Paths. The directory is preserved; with filename_mode=album - title the basename is rebuilt from the connected Album and generated Title so it matches the audio/JSON files.",
        "title": "Generated song title. In the bundled workflow this comes from the structured LLM parser and participates in final artwork naming.",
        "audio_tags_json": "Standard audio-tag JSON containing Album/Title. Connect the same tag output used by the audio savers so artwork, audio and the canonical JSON share identical naming data.",
        "filename_mode": "Artwork filesystem naming: album - title (recommended/default), title only, or prefix as provided. The first two modes use the same shared filename helper as the audio and centralized JSON savers.",
    },
    "SaveAudioSmartPrefix": {
        "filename_prefix": "Output prefix/path for the audio file, normally supplied by MiniMax Output Paths. The node adds the selected extension and a collision suffix if required.",
        "write_json_sidecar": "Legacy compatibility option. When enabled, write a JSON sidecar beside this individual audio file. The bundled example workflow keeps this OFF and uses Save Production JSON instead, producing one canonical JSON in the configurable json/ directory.",
    },
    "MiniMaxSaveProductionJSON": {
        "metadata_json": "LEGACY base payload from the pre-2.0.0 song-metadata node. The direct inputs below overlay it; leave unconnected in the current example workflow.",
        "configuration_prefix": "Destination prefix from MiniMax Output Paths. Its directory is controlled by configuration_subdir (default json); the node creates the final .json filename from Album/Title by default.",
        "audio_tags_json": "Standard tags containing Title/Artist/Album/etc. They are copied into the canonical JSON and are also used for consistent Album - Title JSON naming.",
        "title": "Generated song title. Used as a filename fallback and retained in the canonical configuration JSON; it does not alter audio metadata here.",
        "original_audio_save_json": "Save-info JSON emitted by the original-audio saver. Connecting it makes this node wait until the original audio file has been written and records path, format, sample rate, peak and applied save gain.",
        "release_flac_save_json": "Save-info JSON emitted by the release FLAC saver. Connecting it makes this node wait until the FLAC exists and records its output details.",
        "release_mp3_save_json": "Save-info JSON emitted by the release MP3 saver. Connecting it makes this node wait until the MP3 exists and records its output details.",
        "artwork_path": "Saved JPG path. This dependency makes the configuration JSON run after artwork saving and records the cover path in the outputs section.",
        "collision_mode": "How to handle an existing JSON with the same Album - Title filename. auto_increment is recommended for batches; overwrite replaces it; error_if_exists stops the run.",
        "filename_mode": "Filesystem naming for the JSON only. 'album - title' is recommended so the configuration file matches the release audio naming. Embedded audio TITLE metadata is unaffected.",
        "create_directories": "Create the configured JSON directory automatically when it does not yet exist. Recommended: ON.",
        "llm_system_prompt": "The system prompt that was sent to the LLM; recorded in the canonical JSON so the exact prompt is reproducible.",
        "llm_user_prompt": "The assembled user prompt that was sent to the LLM (structured brief + description).",
        "llm_output": "The raw assistant text returned by the LLM, before parsing.",
        "llm_status": "Status line from the LLM chat node (model, session, character count) for diagnostics.",
        "structured_summary_json": "Summary of the structured prompt resolution (origin, resolved fields, overrides).",
        "caption": "Generated Caption sent to MiniMax Music 3.",
        "lyrics": "Generated Lyrics / structural section map sent to MiniMax Music 3.",
        "image_prompt": "Generated artwork prompt used by the FLUX.2 cover branch.",
        "source_name": "Stable source name derived from the prompt selection or title.",
        "source_path": "Where the prompt came from (prompt file path, <manual> or the LLM marker).",
        "prompt_origin": "Origin marker: folder / manual / external_comfyui_llm / manual_override.",
        "prompt_provenance_json": "Parser provenance record (source mode, user prompt, budget/trim info, manual-field usage).",
        "generation_seed": "Seed used for the song generation.",
        "run_index": "Variant index of this song within the batch.",
        "variant_count": "Total number of variants generated for this prompt.",
        "max_duration": "MiniMax Music 3 maximum duration in seconds (300 = 5 minutes).",
        "text_seed": "Seed for the MiniMax text encoder.",
        "text_cfg_scale": "CFG scale for the MiniMax text encoder.",
        "text_top_k": "Top-k for the MiniMax text encoder.",
        "ksampler_seed": "Seed for the MiniMax sampler.",
        "ksampler_steps": "Sampler step count.",
        "ksampler_cfg": "Sampler CFG.",
        "denoise": "Sampler denoise strength.",
        "flashsr_settings_json": "FlashSR settings report (inference rate, chunk/overlap sizes, low-pass flag, output rate, device).",
        "pre_preset": "PRE low-pass preset name.",
        "pre_settings_json": "PRE low-pass effective settings report.",
        "post_preset": "POST low-pass preset name.",
        "post_settings_json": "POST low-pass effective settings report.",
        "hybrid_crossover_json": "FlashSR Hybrid Crossover report (sample rates, crossover, HF mix, mode).",
        "hf_repair_json": "HF Cymbal / Shimmer Repair report.",
        "declip_json": "Audio Declip / Overload Repair report.",
        "release_prep_json": "Release Prep report (sample rate, measured/effective loudness, true peak, gain).",
        "workflow_name": "Workflow name recorded in the canonical JSON.",
    },
    "MiniMaxStructuredPromptV20": {
        "user_prompt_source": "Where the structured song prompt comes from. manual uses only the fields and description below; bundled_library loads a bundled prompt file; external_directory loads from a folder on the machine running ComfyUI.",
        "user_prompt_directory": "Folder containing prompt files when user_prompt_source is external_directory. Environment variables and ~ are expanded. Files stay inside this folder.",
        "user_prompt_file": "Selected prompt file. 'custom' (the first choice) is the free mode: no file is loaded and the fields stay exactly as you set them, so you compose the prompt yourself. The dropdown lists the categories alphabetically as directory labels first, with the files of each directory indented beneath them. Files may optionally start with a metadata block that prefills Genre/Tempo/Key/Lyrics/Language/Voice/Theme/Length; the file's body text is copied into description_override on selection.",
        "genre": "Music genre. Select 'custom' to leave this part out of the LLM prompt. Selecting a prompt file prefills this field, but you can override it.",
        "tempo": "Tempo as a curated BPM range (Slow to Very fast), so a selection always leaves the LLM a comfortable musical window. Select 'custom' to leave this part out of the LLM prompt. Selecting a prompt file with a Tempo metadata value prefills this field.",
        "key": "Musical key / scale, ordered along the circle of fifths (majors first, then minors). Select 'custom' to leave this part out of the LLM prompt.",
        "lyrics": "Whether the song has lyrics: yes, sparse, only voice - no words (wordless vocalization like humming or syllables), or instrumental. Select 'custom' to leave this part out of the LLM prompt.",
        "language": "Lyrics language. The most important languages come first, then more languages in alphabetical order. Select 'custom' to leave this part out of the LLM prompt.",
        "voice": "Vocal description (gender, timbre, style). Select 'custom' to leave this part out of the LLM prompt.",
        "theme": "Lyrics theme / topic. Select 'custom' to leave this part out of the LLM prompt.",
        "length": "Target song length (for example '4-5 minutes'). Select 'custom' to leave this part out of the LLM prompt.",
        "description_override": "Further description appended to the structured brief. Selecting a prompt file copies its body text into this field, and only this field's content is used afterwards - edit it freely, or clear it to remove the description.",
        "system_prompt": "Manual system prompt text used when system_prompt_source is manual.",
        "system_prompt_source": "Where the system prompt comes from: manual, the bundled library or an external directory.",
        "system_prompt_directory": "Folder containing system prompt files when system_prompt_source is external_directory.",
        "system_prompt_file": "Selected system prompt file from the bundled or external library.",
        "source_name_override": "Optional stable source name used for output paths and provenance. When empty, the selected prompt filename stem is used.",
    },
    "MiniMaxParseExternalLLMOutputV16": {
        "max_prompt_tokens": "Token budget for the combined Caption+Lyrics sent to MiniMax Music 3. The MiniMax text encoder hard-rejects prompts over 5000 tokens, so the default 4500 keeps a safety margin for the estimation error. The estimate is conservative (calibrated against the real MiniMax tokenizer).",
        "trim_long_prompt": "When the estimated prompt exceeds the budget: ON trims softly (whole lines from the end of the lyrics, orphan section tags removed, caption intact) and logs a warning; OFF raises a clear error instead so the MiniMax encoder never fails cryptically.",
    },
    "MiniMaxFlashSRAudio": {
        "audio": "Audio signal to super-resolve. FlashSR reconstructs high-frequency content at 48 kHz; the hybrid crossover later combines it with the original signal.",
        "lowpass_input": "When enabled, FlashSR applies an internal low-pass to its input first. The example workflow keeps this OFF because the PRE low-pass node already controls the input bandwidth.",
        "output_sr": "Sample rate of the delivered audio. FlashSR itself always works at 48 kHz; other rates are produced by a clean resample afterwards. The example workflow uses 48000 and handles delivery rate later.",
        "auto_download": "When enabled, the missing FlashSR weights (student_ldm.pth, sr_vocoder.pth, vae.pth) are downloaded automatically on first use (see models_config.json) and logged with progress. Disable to fail fast instead. The inference code itself is bundled with the toolkit in flashsr_inference/ and is never downloaded.",
    },
    "MiniMaxLLMChat": {
        "enabled": "Master switch for the LLM section. When disabled, the node returns empty text without loading any model and the parser node can fall back to its manual fields — so the LLM part of the workflow can be switched off without an error.",
        "user_text": "Assembled user prompt text, normally from the Structured Song Prompt node.",
        "system_prompt": "System prompt text, normally from the Structured Song Prompt node or the LLM Prompt Library / Template node.",
        "session_id": "Session/cache-buster string from LLM Session ID / Cache Buster. A new value makes the node generate a fresh response instead of reusing ComfyUI's output cache.",
        "model": "llama.cpp-compatible GGUF from models/llm. The example workflow references the same example model as before; provide the file or configure a download URL in models_config.json.",
        "max_tokens": "Maximum number of tokens the LLM may generate. The example workflow uses 16384 so complete Caption/Lyrics/Title/Image Prompt sections fit.",
        "temperature": "Sampling temperature. Lower values are more deterministic; the example uses 0.7.",
        "top_p": "Nucleus sampling threshold. The example uses 0.8.",
        "n_gpu_layers": "Number of model layers offloaded to the GPU. -1 offloads as many as possible. The model is reloaded when this or n_ctx changes.",
        "n_ctx": "Context window size in tokens. The example uses 32768 for the long production system prompt plus response.",
        "reset_session": "When enabled, every run is a fresh single-turn chat (the recommended example setting). When disabled, llama.cpp session state is kept per session_id for multi-turn conversations.",
        "auto_download": "When enabled and a download URL is configured in models_config.json, a missing GGUF is downloaded automatically. Missing models without a configured URL always produce a clear error.",
        "chat_format": "Chat template applied to the conversation. auto picks the verified template for the model family (chatml for Qwen-style models with clean <think> handling, the model's own embedded template for Gemma); none uses the GGUF's own template; chatml/qwen/gemma/llama-3 pass the named template through. Models verified with auto: Qwen3.8-27B and Gemma 4.",
        "thinking": "Reasoning/thinking output handling. off asks the backend to disable reasoning where supported and always splits any <think> blocks off the answer (they are logged and recorded separately); on/auto keep them. The parsed Caption/Lyrics/Title/Image_Prompt only ever see the clean answer.",
        "top_k": "Top-K sampling limit (LM Studio default 40). Restricts sampling to the K most likely tokens per step.",
        "min_p": "Minimum probability (Min-P) sampling; tokens below min_p times the top probability are excluded. 0 disables it (default).",
        "repeat_penalty": "Penalty applied to tokens that already appeared in the text (1.0 = off, 1.1 is the common default).",
        "presence_penalty": "Per-token penalty for any token that appeared at least once; discourages reuse (0 = off).",
        "frequency_penalty": "Per-token penalty proportional to how often a token appeared; discourages repetition (0 = off).",
        "seed": "Random seed for sampling; -1 uses a random seed for every run.",
        "split_mode": "Multi-GPU distribution mode (default: none = no splitting). layer distributes whole layers sequentially across GPUs; row (a.k.a. split parallel) splits layer tensors row-wise across GPUs and can help with large contexts. Only relevant when more than one GPU is present.",
        "tensor_split": "VRAM distribution across GPUs. Empty = llama.cpp auto-distributes. 'even' = split evenly across all detected GPUs. Or give comma-separated fractions/weights (e.g. 2,3 or 0.4,0.6); weights are normalized to sum to 1. The resolved split is logged.",
        "main_gpu": "GPU index used for the intermediate results buffer when splitting across GPUs (normally 0).",
        "tensor_parallel": "Request true tensor parallelism across GPUs when the installed llama-cpp-python build supports it (0.3.48 does not; upgrade llama-cpp-python to use it). If unsupported, the node logs a warning and falls back to split_mode/tensor_split.",
    },
    "MiniMaxLLMUnload": {
        "trigger": "Any value; connect the LLM chat text output so this node runs after the LLM finished and frees its memory before music generation.",
        "unload_now": "Release the loaded LLM model(s) and session state when enabled.",
        "unload_flashsr": "Also release cached FlashSR model instances (only used when the audio stage already finished).",
    },
    "MiniMaxModelAutodownload": {
        "minimax_models": "Check the MiniMax Music 3 files referenced by the workflow (dit, text encoder, VAE).",
        "flux2_models": "Check the FLUX.2 Klein artwork branch files (dit, text encoder, VAE).",
        "flashsr_models": "Check the FlashSR weight files used by the integrated Audio Super Resolution node.",
        "llm_model": "Check the example LLM GGUF referenced by the workflow.",
        "auto_download": "Download every missing file that has a configured URL. Missing files without a URL are only reported with guidance.",
    },
}

NODE_DESCRIPTIONS = {
    "MiniMaxStructuredPromptV20": "Structured prompt control for the LLM: optional metadata-prefilled fields (Genre, Tempo, Key, Lyrics, Language, Voice, Lyrics theme, Target length) plus a further-description text. Selecting a bundled/external prompt file prefills the fields and copies the file's body text into description_override, which is authoritative from then on; every field can be overridden, and 'custom' leaves the part out of the LLM prompt. Outputs the assembled user prompt and the resolved system prompt for the integrated LLM chat node.",
    "MiniMaxFlashSRAudio": "Integrated Audio Super Resolution (FlashSR): reconstructs high-frequency content at 48 kHz with 5.12 s chunks and 0.50 s overlap-add stitching. Replaces the external Egregora node; the inference code is bundled with the toolkit (flashsr_inference/) and only the weights are auto-downloaded on first use per models_config.json. Emits a settings_json report for the production JSON.",
    "MiniMaxLLMChat": "Integrated LLM chat via llama-cpp-python: one system+user turn against a GGUF in models/llm, with optional session state per session_id. Replaces the external ComfyUI-LLM-Session chat node in the example workflow. Exposes the full LM Studio-style sampling set (temperature, top_k, top_p, min_p, repeat/presence/frequency penalty, seed), a chat-format selector, a thinking toggle (reasoning is split off, logged and recorded separately) and multi-GPU controls (split_mode, tensor_split 'even', main_gpu, tensor_parallel when the backend supports it). Verified with Qwen3.8-27B and Gemma 4.",
    "MiniMaxLLMUnload": "Releases the loaded LLM model (and optionally cached FlashSR runners) so VRAM/RAM is free for the music and artwork stages.",
    "MiniMaxModelAutodownload": "Checks the model files referenced by the example workflow and downloads missing ones when a URL is configured in models_config.json. Reports presence/download results in the log and as a text report.",
    "AudioDeclipRepair": "Detects near-ceiling hard-clipping plateaus and reconstructs plausible missing peak curvature before FlashSR. Uses local cubic-Hermite interpolation and only a single optional whole-track safety gain; it cannot recover exact information destroyed by clipping.",
    "FlashSRHybridCrossover": "Combines a cleanly resampled original with FlashSR in a controlled high-frequency crossover, preserving original transients while adding only as much reconstructed 'air' as desired.",
    "HFCymbalShimmerRepair": "Reduces smeared cymbal/hi-hat sustain and artificial high-frequency shimmer while protecting attacks and leaving low/mid-band level untouched.",
    "AudioReleasePrep": "High-quality sample-rate conversion plus optional BS.1770 loudness/true-peak measurement and constant full-program gain. It never uses compressor/AGC/time-varying loudness riding.",
    "FlashSRLowpassLab": "Configurable Butterworth low-pass for controlled pre/post FlashSR cleanup, with presets, custom cutoff/order/phase and reproducibility outputs.",
    "FlashSRProcessingSettings": "LEGACY (removed from the example workflow since 2.0.0): Centralizes PRE/POST low-pass settings and FlashSR lowpass_input so one configuration can drive the processing nodes and metadata consistently. The example workflow now sets these values directly on the PRE/POST low-pass nodes. The node stays registered so older saved workflows keep loading.",
    "MiniMaxMusic3GenerationSettings": "Derives MiniMax Music generation parameters and reproducible text/sampler seeds from the primary generation seed.",
    "MiniMaxSongMetadata": "LEGACY (removed from the example workflow since 2.0.0): Builds the complete reproducibility metadata containing prompts, seeds, MiniMax settings, FlashSR/filter/repair/release settings and optional LLM system prompt. The canonical production JSON now works without this payload (metadata_json is optional). The node stays registered so older saved workflows keep loading.",
    "MiniMaxMetadataLoader": "Loads compatible values from a previously saved MiniMax production JSON (or compatible legacy sidecar) for inspection or reconstruction of a generation setup.",
    "MiniMaxLLMTemplateV16": "Resolves manual, bundled-library or external-directory user/system prompts for any external ComfyUI LLM. It performs no network/model call itself and keeps legacy workflow compatibility while providing a reusable file-backed prompt library.",
    "MiniMaxParseExternalLLMOutputV16": "Parses the external LLM's structured [Caption]/[Lyrics]/[Title]/[Image_Prompt] response, validates required music sections, and creates per-song seeds and provenance. Section order is tolerated defensively even though the bundled system prompt requires the canonical order.",
    "MiniMaxLLMSessionId": "Creates a changing text session ID from a seed so an external LLM node is re-executed when the creative prompt itself is unchanged. Set the seed widget's control-after-generate mode to Randomize or Increment for batch use.",
    "MiniMaxPromptSourceArtworkV16": "Folder/manual structured prompt source retained for non-LLM or file-driven workflows.",
    "MiniMaxPromptBatchLoader": "Loads prompt files or manual prompt fields and emits one or more song variants with reproducible source metadata and seeds.",
    "MiniMaxOutputPaths": "Creates consistent relative output prefixes for original audio, release FLAC/MP3, artwork and one centralized production-configuration JSON directory.",
    "MiniMaxStandardAudioTags": "Builds standard interoperable audio metadata tags such as Artist, Album, Year, Genre and Composer.",
    "MiniMaxSquareImageSize": "Produces equal width/height values for square album artwork using common presets or a custom size.",
    "SaveImageSmartPrefix": "Saves generated artwork as JPEG with smart paths, collision handling and Album - Title filename parity with the audio/JSON outputs.",
    "SaveAudioSmartPrefix": "Saves FLAC/MP3/WAV with smart relative paths, Album - Title filesystem naming, configurable embedded-cover resolution and standard tags. It also emits machine-readable save details for the centralized production JSON; per-audio sidecars remain available only for backward compatibility.",
    "MiniMaxSaveProductionJSON": "Writes one canonical, atomic production JSON after original audio, release FLAC, release MP3 and artwork have all been saved. The JSON contains the complete generation record (LLM prompt and answer, parsed sections, seeds, MiniMax settings, every audio-enhancement report) plus the written files - enough to recreate the song from the JSON alone. The destination directory is configurable in MiniMax Output Paths (default json).",
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
