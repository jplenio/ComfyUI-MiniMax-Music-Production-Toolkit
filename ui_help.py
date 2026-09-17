"""Central UI help/tooltip support for the custom-node package.

ComfyUI displays the ``tooltip`` option from INPUT_TYPES when the user hovers
an input label/widget.  Keeping the help text in one file makes it possible to
add detailed help to every input without duplicating processing code.

Resolution order for every input (first hit wins):

1. the node's own inline ``tooltip`` written next to the field declaration -
   the most local and usually the most specific text;
2. :data:`NODE_INPUT_TOOLTIPS` for that node, exact name first, then ``re:``
   pattern keys;
3. :data:`GENERIC_INPUT_TOOLTIPS`, for fields with the same meaning everywhere;
4. :data:`GENERIC_PATTERN_TOOLTIPS`, for indexed families such as
   ``candidate_3``;
5. :func:`_fallback_tooltip`, which exists only so no input is ever left
   without help - ``tests/test_node_documentation.py`` fails as soon as an input
   would need it.
"""
from __future__ import annotations

import re
from copy import deepcopy

# Tooltips shared by fields with the same semantics across nodes.
GENERIC_INPUT_TOOLTIPS = {
    "cover_source_json": "Source audio identity and shared transcription mode from Cover song / Source audio. Used only for YuE2 Cover; the filename owns the final title.",
    "cover_abc": "Original SheetSage2 transcription. YuE2 Cover passes this score unchanged to music generation and uses it to guide the LLM arrangement.",
    "sheetsage2_models": "Include SheetSage2 only when YuE2 Cover and yue2_models are selected. auto_download controls whether missing configured weights are downloaded. Enabled by default.",
    "yue2_mode": "Full or melody score planning for new YuE2 songs. YuE2 Cover instead uses the single mode selected on Cover song / Source audio for both transcription and generation.",
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
    "yue2_max_duration": "YuE2 maximum generation time in seconds. Length is an approximate musical target and never lowers this ceiling: phrases and decay may finish beyond the target. Leave headroom for a natural ending; the model and context can still end generation earlier.",
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
    "image": "ComfyUI IMAGE tensor to save as cover artwork: a JPEG named like the audio export (Album - Title).",
    "jpeg_quality": "JPEG encoding quality from 50 to 100. Higher values preserve more detail at larger file size; around 90–95 is normally visually transparent for album artwork.",
    "size_preset": "Square artwork resolution preset (256 up to 3096). Larger images cost more VRAM/time. Choose custom to use custom_size instead of a fixed preset. Note: the FLUX.2 latent stage quantizes to multiples of 16, so 3096 is effectively rendered as 3088 - prefer 3072x3072 for an exact size.",
    "custom_size": "Square width/height in pixels used only when size_preset is custom. Values are kept equal to guarantee a 1:1 cover image.",
    "artist": "Primary performing artist tag embedded in the final audio files.",
    "album": "Album or release title embedded into the final audio files, and used by path templates with %album%.",
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
    "MusicCoverSource": {
        "audio": "Upload or select the source audio. Only read in YuE2 Cover mode. The filename without its last extension plus -cover becomes the song title.",
        "mode": "Full (default) retains melody and harmony; melody keeps the tune with greater freedom for new accompaniment. Drives both SheetSage2 and YuE2.",
        "sheetsage2_model": "Audio encoder filename in models/audio_encoders. Autoload provides sheetsage2_bf16.safetensors; custom filenames must already be installed or configured in the model catalog.",
        "lyrics_mode": "What happens to the vocals. New lyrics: the LLM writes words that fit timed source phrases and the transcribed melody; note counts are not syllable counts. Original lyrics: Whisper transcribes the source words and the LLM only distributes them across the score's sections. Instrumental: the score is rewritten so the melodic line that carried the vocals is played by an instrument and Lyrics carries section tags only.",
        "lead_instrument": "Instrumental mode only: which instrument takes over the former vocal melody, or 'Remove vocal line' to keep the accompaniment alone. The rewritten score moves the melody into Ins; overlapping Ins notes in those blocks are replaced and reported.",
    },
    "MusicCoverScore": {
        "cover_source_json": "Connect Cover song / source audio. The lyrics mode decides whether the score is rewritten.",
        "cover_abc": "Connect Cover song / SheetSage2 transcription. An empty transcription stops the cover run.",
    },
    "MusicCoverLyrics": {
        "model_profile_json": "Connect 00 - Song model / Production choices. Whisper runs for YuE2 Cover with new or original lyrics; instrumental and other models skip it.",
        "cover_source_json": "Connect Cover song / source audio; it carries the lyrics mode and the audio file.",
        "model_check_report": "Connect the model check node so configured downloads finish before Whisper loads.",
        "whisper_model": "CTranslate2 Whisper checkpoint from models_config.json. The bundled default is whisper-large-v3; no singing-specific quality optimum is claimed. Extend the catalog for another checkpoint.",
        "language": "Auto detects the language; forcing it improves accuracy and is the documented remedy for wrong-language or repeated output. Use the language actually sung.",
        "device": "Auto prefers CUDA and falls back to CPU with int8 precision when the GPU cannot run the checkpoint.",
        "compute_type": "Precision for the checkpoint. Auto uses float16 on CUDA and int8 on CPU, which is the recommended default on a 16 GB card.",
        "vad_filter": "Off by default for songs. Speech detection may miss singing. If enabled and it retains less than half the audio or no segments, retry the full audio without VAD and record both attempts. Review recognition errors/hallucinations either way.",
        "beam_size": "Beam width for decoding; 5 is the accuracy/speed default. Higher values are slower and hear slightly more.",
        "condition_on_previous_text": "Off is the documented default for music: carrying text between chunks can repeat a line into the next section.",
    },
    "MusicProductionControl": {
        "artifact_reduction_enabled": "Independent experimental spectral outlier reduction after Refinement and before Mastering. On by default with Balanced sensitivity; audition removed_audio to judge the effect on a song. Works with every song model.",
        "model": "Select the actual song generator and matching prompt family. YuE2 is the default in the dual-model workflow.",
        "cover_artwork_enabled": "On creates and previews the FLUX.2 cover artwork and enables its model check/download. Off skips the whole image branch; the audio export continues without artwork. This switch is not the 'YuE2 Cover' song mode: it only decides whether artwork is generated.",
        "refinement": "Model default means OFF for YuE2 and ON for MiniMax. On/Off override that choice. Controls declipping, filtering, FlashSR, crossover and HF repair, including FlashSR model downloads.",
        "mastering_enabled": "On runs Auto-EQ, manual EQ, sample-rate preparation and mastering compression. Off passes incoming audio through at its existing sample rate. Independent of Refinement.",
    },
    "MusicOptionalStage": {
        "enabled": "Connect the central refinement or mastering Boolean. Off skips both audio processing and report dependencies.",
        "stage": "Labels bypass records. Refinement slots 2 and 4 carry preset names; other report slots carry JSON.",
        "original_audio": "Audio before this stage. Requested only when the stage is disabled.",
        "processed_audio": "Audio after this stage. Lazy: requested only while the gate is enabled.",
    },
    "MusicOptionalCoverPreview": {
        "images": "Generated artwork. Requested only while cover creation is enabled.",
        "enabled": "Connect the central cover Boolean to skip rendering and clear the preview when disabled.",
    },
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
        "configuration_subdir": "Subfolder for the ONE canonical production configuration file per song. Default: log/. This replaces duplicated JSON sidecars beside every audio encoding in the bundled workflow.",
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
        "configuration_prefix": "Destination prefix from MiniMax Output Paths. Its directory is controlled by configuration_subdir (default log/); the node creates the final .json filename from Album/Title by default.",
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
        "llm_output": "Raw assistant text the LLM returned, before parsing, recorded in the JSON.",
        "llm_status": "Status line from the LLM chat node (model, session, character count) for diagnostics.",
        "structured_summary_json": "Summary of the structured prompt resolution (origin, resolved fields, overrides).",
        "caption": "Generated Caption that was sent to the music model, recorded in the production JSON.",
        "lyrics": "Generated Lyrics / structural section map sent to MiniMax Music 3.",
        "image_prompt": "Artwork prompt used by the FLUX.2 cover branch, recorded in the production JSON.",
        "source_name": "Stable source name derived from the prompt selection or title.",
        "source_path": "Where the prompt came from (prompt file path, <manual> or the LLM marker).",
        "prompt_origin": "Origin marker: folder / manual / external_comfyui_llm / manual_override.",
        "prompt_provenance_json": "Parser provenance record (source mode, user prompt, budget/trim info, manual-field usage).",
        "generation_seed": "Seed of this song's generation, recorded in the production JSON.",
        "run_index": "1-based variant index of this song within the batch, recorded in the JSON.",
        "variant_count": "Total number of variants generated for this prompt, recorded in the JSON.",
        "max_duration": "MiniMax Music 3 maximum duration in seconds (300 = 5 minutes).",
        "text_seed": "Seed the text encoder ran with, recorded in the production JSON.",
        "text_cfg_scale": "CFG scale of the text encoder, recorded in the production JSON.",
        "text_top_k": "Top-k of the text encoder, recorded in the production JSON.",
        "ksampler_seed": "Seed the music sampler ran with, recorded so the take can be reproduced.",
        "ksampler_steps": "Sampler step count this song ran with, recorded in the production JSON.",
        "ksampler_cfg": "Sampler CFG this song ran with, recorded in the production JSON.",
        "denoise": "Sampler denoise strength, recorded in the production JSON.",
        "flashsr_settings_json": "FlashSR settings report (inference rate, chunk/overlap sizes, low-pass flag, output rate, device).",
        "pre_preset": "Name of the PRE low-pass preset that was used, recorded in the JSON.",
        "pre_settings_json": "Effective PRE low-pass settings report, recorded in the production JSON.",
        "post_preset": "Name of the POST low-pass preset that was used, recorded in the JSON.",
        "post_settings_json": "Effective POST low-pass settings report, recorded in the production JSON.",
        "hybrid_crossover_json": "FlashSR Hybrid Crossover report (sample rates, crossover, HF mix, mode).",
        "hf_repair_json": "High-frequency cymbal/shimmer repair report, recorded in the production JSON.",
        "declip_json": "De-clipping / overload repair report, recorded under the restoration section.",
        "release_prep_json": "Release Prep report (sample rate, measured/effective loudness, true peak, gain).",
        "workflow_name": "Name of the workflow that produced this run, recorded in the canonical JSON.",
        "cover_score_json": "Cover-only: the score adaptation record (lyrics mode, lead instrument, whether and how the vocal line was rewritten, and the vocal note counts and phrase grids). Omitted for normal songs.",
        "cover_lyrics_json": "Cover-only: the Whisper transcription and timestamp record for new/original-lyrics covers (checkpoint, device, precision, detected language and confidence, segment count, transcript). Omitted when the mode does not use Whisper.",
    },
    "MiniMaxStructuredPromptV20": {
        "cover_lyrics": "Cover-only: the original sung words transcribed from the source audio with Whisper. Used as the authoritative lyrics text when the cover lyrics mode is 'original lyrics'. Connect the report output to retain timestamps. Original mode verifies the complete word order; new mode uses source phrasing as guidance.",
        "user_prompt_source": "Where the structured song prompt comes from. manual uses only the fields and description below; bundled_library loads a bundled prompt file; external_directory loads from a folder on the machine running ComfyUI.",
        "user_prompt_directory": "Folder containing prompt files when user_prompt_source is external_directory. Environment variables and ~ are expanded. Files stay inside this folder.",
        "user_prompt_file": "Selected prompt file. 'custom' (the first choice) is the free mode: no file is loaded and the fields stay exactly as you set them, so you compose the prompt yourself. The dropdown lists the categories alphabetically as directory labels first, with the files of each directory indented beneath them. Files may optionally start with a metadata block that prefills Genre/Tempo/Time signature/Key/Lyrics/Language/Voice/Theme/Length; your explicit field values always win over that block. The file's body text is copied into description_override on selection.",
        "genre": "Music genre, and part of the style this node owns: the template, the fields and the description are the master for the song's sound. Select 'custom' to leave this part out of the LLM prompt. Selecting a prompt file prefills this field, but you can override it.",
        "tempo": "Tempo as a curated BPM range (Slow to Very fast), so a selection always leaves the LLM a comfortable musical window. Select 'custom' to leave this part out of the LLM prompt. Selecting a prompt file with a Tempo metadata value prefills this field.",
    "meter": "Time signature as a curated list (4/4 (common time), 3/4 (waltz), 6/8, odd meters, changing time signatures, free time / rubato). Select 'custom' to leave this part out of the LLM prompt. Selecting a prompt file with a Meter metadata value prefills this field.",
        "key": "Musical key / scale, ordered along the circle of fifths (majors first, then minors). Select 'custom' to leave this part out of the LLM prompt.",
        "lyrics": "Whether the song has lyrics: yes, sparse, only voice - no words (wordless vocalization like humming or syllables), or instrumental. Select 'custom' to leave this part out of the LLM prompt. For a YuE2 Cover the selected cover lyrics mode overrides this field ('instrumental' and 'original lyrics' both force a value), so a template's lyrics setting cannot decide the vocals of a cover.",
        "language": "Lyrics language. The most important languages come first, then more languages in alphabetical order. Select 'custom' to leave this part out of the LLM prompt. Special cases: for an instrumental cover the mode removes this field, and for 'original lyrics' the language comes from the Whisper transcription instead of from here.",
        "voice": "Vocal description (gender, timbre, style). Select 'custom' to leave this part out of the LLM prompt. An instrumental cover removes this field, and 'original lyrics' preserves the source voice, so the cover lyrics mode wins here too.",
        "theme": "Lyrics theme / topic. It is what the words of a 'new lyrics' cover are written from, so it stays active there. An instrumental cover or one that keeps the original words removes it from the brief, because the mode - not the theme - decides the vocals. Select 'custom' to leave this part out of the LLM prompt.",
        "length": "Approximate song length (for example '4-5 minutes'). Prompts plan the arrangement and natural ending near this target. YuE2 may finish phrases and decay beyond it; this does not lower yue2_max_duration. Select 'custom' to leave this part out of the LLM prompt.",
        "description_override": "Further description appended to the structured brief. Selecting a prompt file copies its body text into this field, and only this field's content is used afterwards - edit it freely, or clear it to remove the description.",
        "system_prompt": "Effective system prompt sent to the LLM. Selecting a system prompt file copies its text into this field, and only this field's content is used afterwards - edit it freely. In manual mode this field is the whole system prompt.",
        "system_prompt_source": "Where the system prompt comes from: the bundled library (default), manual text or an external directory.",
        "system_prompt_directory": "Folder containing system prompt files when system_prompt_source is external_directory.",
        "system_prompt_file": "Selected system prompt file from the bundled or external library. The bundled default is minimax-music3-production.txt; additional variants emphasize fantasy/free creativity, genre fidelity, cinematic scope, dance energy, emotional storytelling, minimalism/space, fast tempo/high BPM, brevity, lyrics/vocals and instrumentation/arrangement.",
        "source_name_override": "Optional stable source name used for output paths and provenance. When empty, the selected prompt filename stem is used.",
    },
    "MiniMaxParseExternalLLMOutputV16": {
        "max_prompt_tokens": "Token budget for the combined Caption+Lyrics sent to MiniMax Music 3. The MiniMax text encoder hard-rejects prompts over 5000 tokens, so the default 4500 keeps a safety margin for the estimation error. The estimate is conservative (calibrated against the real MiniMax tokenizer).",
        "trim_long_prompt": "When the estimated prompt exceeds the budget: ON trims softly (whole lines from the end of the lyrics, orphan section tags removed, caption intact) and logs a warning; OFF raises a clear error instead so the MiniMax encoder never fails cryptically.",
        "cover_lyrics": "Cover-only: source transcript with timestamps. Original words are placed in measured score sections, restored after LLM rewrites, then checked for complete word order including repetitions. New lyrics use the timing as guidance.",
    "cover_lyrics_lock": "Cover Studio only, and empty by default. A deliberately locked lyrics block: when connected and non-empty it replaces the LLM's words verbatim and marks them as intentional, so the 'new lyrics' copy guard does not mistake a user lock for a lazy model answer. Leave it empty to keep the previous behaviour.",
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
        "model": "llama.cpp-compatible GGUF from models/llm. The example workflow references the same example model as before; provide the file or configure a download URL in models_config.json.",
        "max_tokens": "Maximum number of tokens the LLM may generate. The example workflow uses 16384 so complete Caption/Lyrics/Title/Image Prompt sections fit.",
        "temperature": "Sampling temperature. Lower values are more deterministic; the example uses 0.7.",
        "top_p": "Nucleus sampling threshold (the example uses 0.8). Lower values restrict sampling to more likely tokens.",
        "n_gpu_layers": "Number of model layers offloaded to the GPU. -1 offloads as many as possible. The model is reloaded when this or n_ctx changes.",
        "n_ctx": "Context window size in tokens. It holds the production system prompt, the response and any thinking, and is sized so that even a maximum-length answer fits; the example uses 37376.",
        "reset_session": "Integrated GGUF only: keep enabled for independent songs. Off reuses the default llama.cpp state cache (advanced). ComfyUI still executes the LLM on every queued run either way.",
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
        "llm_model": "Also check the example LLM GGUF referenced by the workflow. Turn it off when you use a cloud or local-server model.",
        "auto_download": "Download every missing file that has a configured URL. Missing files without a URL are only reported with guidance.",
        "whisper_models": "Check the Whisper checkpoint for new/original lyrics in YuE2 Cover only. Off excludes it from this check; auto_download controls downloads. Instrumental and other models never request it.",
        "cover_source_json": "Connect Cover song / source audio so this node can see the selected lyrics mode and only request the Whisper weights the run actually uses.",
    },
}

NODE_DESCRIPTIONS = {
    "MiniMaxStructuredPromptV20": "Structured prompt control for the LLM: optional metadata-prefilled fields (Genre, Tempo, Time signature, Key, Lyrics, Language, Voice, Lyrics theme, Target length) plus a further-description text. Selecting a bundled/external prompt file prefills the fields and copies the file's body text into description_override, which is authoritative from then on; every field can be overridden, and 'custom' leaves the part out of the LLM prompt. The system prompt is a separate section: selecting a system prompt file copies its text into the editable system_prompt field, which is authoritative from then on. Outputs the assembled user prompt and the resolved system prompt for the integrated LLM chat node.\n\nWHERE THE INSTRUCTIONS COME FROM: this node is the master for the song's style and musical fields - the template, the fields and the description are what the LLM is told to produce, and the style rules it forwards (including STYLE PRIORITY for covers) are what the model must follow. It resolves each field as 'your explicit value > the prompt file's metadata block > left out of the prompt'.\n\nCOVER OVERRIDES: for a YuE2 Cover the selected cover lyrics mode wins over the vocal fields, so a value left over from a template cannot bring vocals back. 'instrumental' forces the Lyrics field to instrumental and removes Voice, Language and Lyrics theme from the brief; 'original lyrics' removes the Lyrics theme (the words are the Whisper transcription) and takes the language from that transcript; 'new lyrics' keeps theme, language and voice, because they are what the new words are written from. The Cover Studio never changes these fields: it only reworks the source score, and its own target_style is a hint for that rework, never a second style source.",
    "MiniMaxFlashSRAudio": "Integrated Audio Super Resolution (FlashSR): reconstructs high-frequency content at 48 kHz with 5.12 s chunks and 0.50 s overlap-add stitching. Replaces the external Egregora node; the inference code is bundled with the toolkit (flashsr_inference/) and only the weights are auto-downloaded on first use per models_config.json. Emits a settings_json report for the production JSON.",
    "MiniMaxLLMChat": "Generate song text inside ComfyUI (GGUF), in a local app/server, or using a cloud provider. Select the mode to show its controls. External modes offer model discovery and session-only API key entry; provider keys are not stored in workflows. Each enabled queued execution generates fresh text, without a session-ID helper. Cloud requests send your prompts to the provider and may incur charges. GGUF advanced controls remain available; they do not affect external models. See docs/LLM_PROVIDERS.md for setup.",
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


# ---------------------------------------------------------------------------
# Tooltips for fields that had none (2026-09-17).  Kept in one additive block so
# the older tables above stay reviewable on their own.
# ---------------------------------------------------------------------------

GENERIC_INPUT_TOOLTIPS.update({
    "model_profile_json": "JSON profile of the selected song model: which model is active, its duration window, prompt hard limit and capabilities. This node adapts its behaviour to that profile; it comes from the song model profile node.",
    "profile_json": "JSON profile of the selected song model (id, display name, duration window, prompt hard limit, capabilities). Everything downstream adapts to it.",
    "settings_json": "Resolved model-settings JSON from the music settings node: active sampler group, clamped duration, seed handling and the instrumental-check options.",
    "model_check_report": "Text report from the model preflight: which artifacts are present, already downloaded or missing. Recorded for the log and the production JSON only.",
    "word_tolerance": "How many recognised words still count as an instrumental. Words, not letters: 0 means the render must not contain a recognisable word at all.",
})

# Indexed input families that mean the same thing in every node using them.
GENERIC_PATTERN_TOOLTIPS = {}

_NEW_NODE_TOOLTIPS = {
    "MiniMaxInstrumentalPick": {
        "max_retries": "How many extra takes may be generated when a take still contains words (0-10). A clean first take costs one generation; every retry is a full re-render.",
        "re:candidate_\\d+": "One generated take (AUDIO), numbered like its report_N. Lazy: the take is only rendered when this node actually asks for it.",
        "re:report_\\d+": "Word-check report for candidate_N: words heard, transcript, pass/fail and the path of that take's temporary WAV. Lazy, like its candidate.",
    },
    "MusicOptionalStage": {
        "re:report_\\d+": "Report of an optional stage, passed through unchanged while the stage runs. Lazy: a disabled stage never wakes the node that would produce it.",
    },
    "MiniMaxInstrumentalVocalCheck": {
        "whisper_model": "Whisper checkpoint used for the check. The pinned whisper-large-v3 checkpoint is downloaded by the model preflight when it is missing.",
        "language": "Language hint for the check, or auto to detect it. Detection is usually right; pin a language when you know the source to avoid misdetection.",
        "device": "Where Whisper runs. auto prefers CUDA and falls back to CPU after a GPU failure; cuda or cpu pins it explicitly.",
        "compute_type": "Precision of the Whisper engine. auto uses float16 on CUDA and int8 on CPU.",
        "beam_size": "Beam width of the transcription. 1 is fastest; higher values hear slightly more and take longer.",
        "candidate_label": "Name of this take in the log, the report and its temporary WAV file. The generation expansion passes take-1, take-2, ...; empty uses take.",
    },
    "MiniMaxMusicModelSettings": {
        "ksampler_seed_offset": "Integer added to the KSampler seed derived from the song seed, separately from the music model's own seed. 0 keeps the sampler seed equal to the song seed; a fixed value shifts every take by the same amount.",
        "minimax_steps": "Sampling steps for MiniMax Music 3 (default 40). More steps cost time without guaranteeing a better result.",
        "minimax_cfg": "Classifier-free guidance for MiniMax Music 3 (default 1.7). Higher values follow the caption more literally.",
        "minimax_sampler_name": "Sampler used for MiniMax Music 3. Only the selected model's group takes effect.",
        "minimax_scheduler": "Noise schedule for MiniMax Music 3. Only the selected model's group takes effect.",
        "minimax_text_cfg_scale": "Guidance scale of the MiniMax text encoder (default 1.7): how strongly the caption steers the text conditioning.",
        "minimax_text_top_k": "Top-k sampling width of the MiniMax text encoder (default 50). Lower values narrow the text conditioning.",
        "yue2_steps": "Sampling steps for YuE2 (default 32). More steps cost time; the bundled example runs 40.",
        "yue2_cfg": "Classifier-free guidance for YuE2 (default 1.0). Higher values follow the style text more literally.",
        "yue2_sampler_name": "Sampler used for YuE2 (default dpm_2). Only the selected model's group takes effect.",
        "yue2_scheduler": "Noise schedule for YuE2 (default sgm_uniform). Only the selected model's group takes effect.",
        "yue2_temperature": "Sampling temperature for YuE2 (default 1.0). Lower values are more conservative and repeatable.",
        "yue2_top_p": "Nucleus sampling threshold for YuE2 (default 0.95). Lower values cut unlikely tokens earlier.",
        "yue2_top_k": "Top-k sampling width for YuE2 (default 100). Lower values cut unlikely tokens earlier.",
        "yue2_repetition_penalty": "Repetition penalty for YuE2 (default 1.2). Higher values discourage repeated musical phrases.",
        "instrumental_check": "Enable the instrumental vocal check: every generated take is transcribed with Whisper and re-rendered while it still contains words. Only applies to a YuE2 instrumental cover and costs one transcription per take.",
        "instrumental_word_tolerance": "Words (not letters) that still count as instrumental for this run. 0 requires a take with no recognisable words.",
        "instrumental_max_retries": "Maximum extra takes the check may request (0-10). When none reaches the tolerance, the take with the fewest recognised words is used and the other candidates are deleted.",
    },
    "MiniMaxParseExternalLLMOutputV16": {
        "fallback_title": "Title used when the LLM answer and the manual fields contain none. A cover still takes its title from the source filename.",
        "structured_llm_output": "Raw text answer from the LLM chat node, with the [Style], [Lyrics], [Title] and [Image_Prompt] sections the parser expects.",
        "manual_image_prompt": "Artwork prompt used when the LLM answer contains none. The text-free prohibition is appended automatically when it is missing.",
        "llm_status": "Status line from the LLM node, kept in the provenance so a run can be traced back to the model and provider that produced it.",
        "structured_summary_json": "Summary JSON from the structured prompt node (template, fields, requested length). Used for provenance and to honour a requested song length.",
    },
    "MiniMaxSaveProductionJSON": {
        "llm_thinking": "Reasoning the model produced next to its answer. Stored in the JSON only; it never reaches the music model.",
        "minimax_prompt_md": "Markdown prompt report, written next to the JSON so the exact prompt survives with the song.",
        "eq_report_json": "Per-band EQ report from automatic and manual EQ, recorded in the EQ section of the production JSON.",
        "auto_eq_analysis_json": "Auto-EQ analysis: detected tonal difference against the target and the proposed gain per band.",
        "mastering_json": "Mastering report: measured LUFS and true peak plus the applied gain reduction.",
        "resource_profile_json": "Detected hardware profile and the model recommendation derived from it, recorded for reproducibility.",
        "llm_runtime_json": "LLM runtime details (backend, model file, context size, GPU placement) as reported by the chat node.",
        "model_identity_json": "Identifiers of the loaded song and artwork models, so the JSON records which weights produced the audio.",
        "template_version": "Version or fingerprint of the prompt template that produced the text, so a later prompt change can be told apart.",
        "artifact_reduction_json": "Artifact-reduction report: what was detected and how much was removed.",
    },
    "MiniMaxSafeAudioDecode": {
        "samples": "Latents from the sampler, decoded with the VAE. Invalid decoder output triggers one retry with smaller tiles instead of writing broken audio.",
        "vae": "VAE that decodes the latents; it must match the song model that produced them.",
    },
    "MusicGeneration": {
        "style": "Style or caption text that drives the song model. For a cover this is the style the studio produced.",
        "yue2_checkpoint": "YuE2 checkpoint file. Only read when the active profile is YuE2 or YuE2 Cover.",
        "minimax_model": "MiniMax Music 3 diffusion model. Only read when the active profile is MiniMax Music 3.",
        "minimax_encoder": "MiniMax Music 3 text encoder. Only read when the active profile is MiniMax Music 3.",
        "minimax_vae": "MiniMax Music 3 VAE. Only read when the active profile is MiniMax Music 3.",
        "tiled_decode": "Decode long audio in tiles instead of all at once. Slightly slower and much lighter on peak memory; invalid output retries once with smaller tiles.",
    },
    "MusicGenerationReceipt": {
        "abc": "Score that was handed to the song model. For MiniMax Music 3 and non-cover runs it is empty.",
        "seconds": "Requested duration in seconds that the model was given. The saved file can be shorter or longer.",
        "model_files_json": "Model files used for this song, recorded so the run can be reproduced.",
        "instrumental_check_json": "Result of the instrumental vocal check: attempts, words heard per take, the kept take and where its temporary file is.",
    },
    "MiniMaxAudioBranchSelect": {
        "profile": "Which branch this node uses: keep the original recording, a careful restore, or a reconstructed-bandwidth version. Only the selected branch is executed.",
        "mix": "Blend weight of the replacement branch against the original. 0 keeps the original audio even when a restoration branch is selected.",
        "preview_seconds": "Length of audio emitted for a quick listen, in seconds. 0 passes the complete track through.",
        "original_audio": "AUDIO input of the untouched original recording. Lazy: it is only evaluated when this branch is selected.",
        "restored_audio": "AUDIO input of the carefully restored version. Lazy: it is only evaluated when this branch is selected.",
        "bandwidth_audio": "AUDIO input of the bandwidth-reconstructed version. Lazy: it is only evaluated when this branch is selected.",
    },
    "MiniMaxAudioTagReader": {
        "audio_file": "Audio file whose title, artist, album and embedded cover art are read. Pick a file, not a path from another machine.",
        "copy_cover_art": "Also pass the embedded cover art on as an image path. Off returns an empty path.",
        "overrides_json": "Optional JSON with tag values for fields the source file does not carry. Tags from the source always win; this only fills gaps.",
    },
    "MiniMaxModelAutodownload": {
        "yue2_models": "Include the YuE2 model group in the check and download. Turn it off when you only produce MiniMax Music 3 songs or audio enhancement.",
    },
    "MiniMaxMasteringCompressor": {
        "preset": "Ready-made starting points for ratio, threshold, attack, release and knee. Custom keeps your own values; a preset overwrites the compressor controls, not the loudness targets.",
    },
}

for _node, _fields in _NEW_NODE_TOOLTIPS.items():
    NODE_INPUT_TOOLTIPS.setdefault(_node, {}).update(_fields)


def merge_input_tooltips(*tables):
    """Merge per-node tooltip tables field by field into :data:`NODE_INPUT_TOOLTIPS`.

    A plain ``dict.update`` replaces a whole node entry, which silently dropped
    every field the later table did not repeat. Later tables still win per field.
    """
    for table in tables:
        for node, fields in (table or {}).items():
            NODE_INPUT_TOOLTIPS.setdefault(node, {}).update(fields)
    return NODE_INPUT_TOOLTIPS


def _fallback_tooltip(name: str) -> str:
    pretty = name.replace("_", " ")
    return f"Configuration input '{pretty}'. This value is passed directly to the node's processing logic; keep it at the workflow default unless you intentionally want to change that part of the production chain."


_NODE_REGEX_PREFIX = "re:"

# Tooltips for indexed input families (candidate_3, report_7, ...).  Checked after
# the exact and per-node tables, so a node can still describe its own slots.
GENERIC_PATTERN_TOOLTIPS: dict = {}


def _inline_tooltip(spec) -> str:
    """The tooltip written next to the field declaration in the node itself."""
    if isinstance(spec, tuple) and len(spec) > 1 and isinstance(spec[1], dict):
        text = spec[1].get("tooltip")
        if text and str(text).strip():
            return str(text).strip()
    return None


def _table_tooltip(fields, name: str) -> str:
    """Exact entry first, then ``re:`` pattern entries, in declaration order."""
    if not fields:
        return None
    if name in fields:
        return fields[name]
    for key, text in fields.items():
        if isinstance(key, str) and key.startswith(_NODE_REGEX_PREFIX):
            if re.fullmatch(key[len(_NODE_REGEX_PREFIX):], name):
                return text
    return None


def resolve_tooltip(spec, name: str, node_names=()) -> str:
    """Best available tooltip for one input, or ``None`` when only the fallback exists."""
    inline = _inline_tooltip(spec)
    if inline:
        return inline
    for node_name in node_names:
        text = _table_tooltip(NODE_INPUT_TOOLTIPS.get(node_name), name)
        if text:
            return text
    if name in GENERIC_INPUT_TOOLTIPS:
        return GENERIC_INPUT_TOOLTIPS[name]
    for pattern, text in GENERIC_PATTERN_TOOLTIPS.items():
        if re.fullmatch(pattern, name):
            return text
    return None


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
    """Decorate every required/optional INPUT_TYPES field in every registered node.

    An inline tooltip is kept: the source next to the field is the most specific
    description available, and overwriting it with central text loses detail.
    """
    for comfy_name, cls in node_class_mappings.items():
        if cls.__dict__.get("_minimax_tooltips_installed", False):
            continue
        original = getattr(cls, "INPUT_TYPES", None)
        if original is None:
            continue
        class_name = getattr(cls, "__name__", comfy_name)
        node_names = (comfy_name, class_name)

        def wrapped_input_types(_cls, _original=original, _names=node_names):
            data = deepcopy(_original())
            for section in ("required", "optional"):
                fields = data.get(section, {})
                for name, spec in list(fields.items()):
                    tooltip = resolve_tooltip(spec, name, _names) or _fallback_tooltip(name)
                    fields[name] = _decorate_spec(spec, tooltip)
            return data

        cls.INPUT_TYPES = classmethod(wrapped_input_types)
        # Keep the undecorated declaration reachable: the documentation test must
        # judge the authored tooltips, not the text this installer generated.
        cls._minimax_raw_input_types = original
        if comfy_name in NODE_DESCRIPTIONS:
            cls.DESCRIPTION = NODE_DESCRIPTIONS[comfy_name]
        elif class_name in NODE_DESCRIPTIONS:
            cls.DESCRIPTION = NODE_DESCRIPTIONS[class_name]
        cls._minimax_tooltips_installed = True


def find_missing_explicit_tooltips(node_class_mappings):
    """Developer/test helper: list inputs that would need the generic fallback text."""
    missing = []
    for comfy_name, cls in node_class_mappings.items():
        original = getattr(cls, "_minimax_raw_input_types", None) or getattr(cls, "INPUT_TYPES", None)
        if original is None:
            continue
        data = original()
        names = (comfy_name, getattr(cls, "__name__", comfy_name))
        for section in ("required", "optional"):
            for name, spec in data.get(section, {}).items():
                if not resolve_tooltip(spec, name, names):
                    missing.append((comfy_name, section, name))
    return missing
