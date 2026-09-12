# Refactoring Plan

## 1. Executive Summary

This is a ComfyUI integration package, a pair of reference workflows, a prompt library, a vendored inference stack, and release/demo tooling. Its architecture is understandable and already has valuable foundations: explicit node registration, lightweight shared naming and logging helpers, content-based prompt fingerprints, metadata version definitions, compatibility tests, and a documented distinction between restoration and mastering. A wholesale rewrite, generic node framework, or mass relocation would create more risk than benefit.

The recommended strategy is incremental extraction behind the existing root modules and node classes. First capture the public contracts and reproduce concrete defects. Then centralize path/encoding operations, audio conversion policies, prompt-library services, and model lifecycle management. Keep DSP algorithms and third-party model internals largely intact. Treat bug fixes as separately reviewed changes, never as incidental consequences of moving code.

Highest-value work:

1. Protect saved workflows and prompt edits from migration/frontend lifecycle defects.
2. Prevent upstream audio mutation and make FlashSR device/resource ownership accurate.
3. Extract the unusually broad LLM resource compatibility code without discarding its repeated-run workarounds.
4. Consolidate duplicated output-path, FFmpeg, prompt-file, preset, and metadata concepts while preserving their intentional differences.
5. Expand tests beyond schema shape and fake inference to cover numerical behavior, lifecycle failures, frontend adapters, and actual package startup.
6. Audit vendored inference reachability and installation requirements before considering any pruning.

**Scope and evidence.** Analysis reflects the local 2.1.1 tree. Inventory: 32 root Python modules, 261 vendored Python files, 14 Python maintenance scripts, 17 Python test files, one JavaScript test file, six frontend JavaScript modules, 28 node identifiers, 239 bundled user prompts, and 11 system prompts. The full workflow has 43 top-level nodes, 117 links, and one embedded subgraph; AudioEnhance has 15 nodes and 16 links. Counts describe files, not effective test coverage.

All Python files were parsed in memory successfully. Read-only, in-memory probes reproduced sparse workflow slot corruption, an over-budget trim result, and nested input mutation in metadata migration. The full test suite, ComfyUI, FFmpeg processing, downloads, and model inference were **not** run during this analysis; tests and tools that create files were deliberately left for implementation validation. No throughput or VRAM benchmark is claimed. Vendor coverage consisted of a complete syntax/import inventory and tracing the active inference path plus representative duplicated/training utilities, not a claim that every research implementation was numerically audited. Existing source files were not changed.

## 2. Repository Architecture

### Runtime entry point and node ownership

`__init__.py` explicitly imports 20 node-owning modules, merges their class/display mappings, applies `ui_help.install_input_tooltips()`, exports `WEB_DIRECTORY = "./web"`, and calls `prompt_library.register_routes()`. Only route registration is wrapped at the entry point. Most optional dependencies have guarded or deferred imports in their owner modules; a failure in an unguarded import still prevents package discovery. Mapping merges currently do not detect duplicate identifiers.

| Owner | Registered node identifiers | Responsibility and important consumers |
|---|---|---|
| `minimax_batch.py` | `MiniMaxPromptBatchLoader`, `MiniMaxOutputPaths` | Legacy folder/manual parsing, variant expansion and seeds; five output prefixes consumed by savers. |
| `minimax_prompt_source.py` | `MiniMaxPromptSourceArtworkV16`, `MiniMaxLLMTemplateV16`, `MiniMaxParseExternalLLMOutputV16` | Rich section parsing, artwork fallback, legacy source/template behavior, prompt budget application, list outputs/provenance. |
| `minimax_structured_prompt.py` | `MiniMaxStructuredPromptV20` | Current editable brief, file metadata/widget precedence, system prompt, summary JSON. |
| `llm_chat.py` | `MiniMaxLLMChat`, `MiniMaxLLMUnload` | GGUF discovery, llama.cpp options, cached models/session state, streaming/reasoning extraction, ComfyUI/FlashSR cleanup. |
| `session_utils.py` | `MiniMaxLLMSessionId` | Seed-derived session identifier; also changes ComfyUI cache keys. |
| `minimax_settings.py` | `MiniMaxMusic3GenerationSettings`, `FlashSRProcessingSettings` | Scalar configuration outputs and legacy PRE/POST settings. The latter calls private helpers from `audio_lowpass.py`. |
| `ksampler_config.py` | `KSamplerWithConfig` | Thin `nodes.common_ksampler` adapter with sampler/scheduler outputs. |
| `minimax_autodownload.py` | `MiniMaxModelAutodownload` | Configured model presence/download reports; feeds parser as an ordering dependency. |
| `audio_declip.py` | `AudioDeclipRepair` | Plateau detection and bounded Hermite reconstruction, optional constant safety gain. |
| `audio_lowpass.py` | `FlashSRLowpassLab` | PRE/POST Butterworth SOS filtering, explicit causal/zero-phase behavior. |
| `flashsr_audio.py` | `MiniMaxFlashSRAudio` | Weight preparation, vendor import, runner cache, 48 kHz chunked inference, overlap-add and output resampling. |
| `audio_hf_repair.py` | `FlashSRHybridCrossover`, `HFCymbalShimmerRepair` | Source/FlashSR frequency blend; HF envelope shaping and stereo side-band reduction. |
| `audio_release_prep.py` | `AudioReleasePrep` | Final SRC, FFmpeg loudness measurement and one true-peak-capped constant gain per batch item. |
| `save_audio_absolute.py` | `SaveAudioAbsolutePath` | Legacy explicit-directory audio export. |
| `save_audio_smart_prefix.py` | `SaveAudioSmartPrefix` | Audio export, tags, cover embedding, optional legacy sidecars, save-info JSON and non-writing path preview. |
| `minimax_artwork.py` | `MiniMaxSquareImageSize`, `SaveImageSmartPrefix` | Resolution selection and first-image JPEG export. |
| `minimax_audio_tags.py` | `MiniMaxStandardAudioTags` | Small, straightforward standard-tag JSON builder. |
| `minimax_metadata.py` | `MiniMaxSongMetadata`, `MiniMaxMetadataLoader` | Legacy generation-record construction and record-to-node-output loading. |
| `minimax_json_output.py` | `MiniMaxSaveProductionJSON` | Current generation-record assembly, artifact aggregation, final JSON and companion Markdown writes. |
| `minimax_prompt_report.py` | `MiniMaxPromptReport` | ComfyUI prompt-builder-based report, with explicitly labeled raw fallback and frontend UI output. |

The MiniMax music generator and FLUX artwork generator are predominantly **ComfyUI core workflow nodes**, not locally implemented model pipelines. Do not move or reimplement them inside this package.

### Shared modules and dependency relationships

- `filename_utils.py`: `safe_filename_component()` and `apply_filename_mode()` already unify Album/Title basenames across smart audio, artwork and production JSON.
- `prompt_library.py`: safe selected-file resolution, enumeration, UTF-8 loading, content fingerprints, custom writes and five HTTP endpoints. It imports `prompt_metadata` inside operations and imports the structured node to invalidate its cache after a save, creating a reverse service-to-node dependency.
- `prompt_metadata.py`: curated vocabularies, field names/labels/aliases, front-matter parser, brief assembly and metadata aggregation.
- `prompt_budget.py`: character-based token estimate and line-preserving trimming. Only the rich LLM parser applies its budget; legacy folder inputs are not automatically budgeted.
- `metadata_schema.py`: v7 production schema and registered v6-to-v7 migration. Runtime loader/writer do not consistently use this migration boundary.
- `model_downloader.py`: model config, ComfyUI base/model path resolution, file checks, download/report operations and a legacy ZIP extraction API.
- `toolkit_logging.py`, `progress_utils.py`, `project_info.py`: existing simple logging, progress fallback and release identity.
- `workflow_schema.py`: serialized parser/JSON input-order migrations and external-node detection. Its current traversal is top-level only.
- `ui_help.py`: declarative help data and an idempotent wrapper that deep-copies schemas before adding tooltips. This is useful existing behavior, not a reason to redesign all node declarations.

Two avoidable dependency directions are particularly concrete: `minimax_json_output.py` imports `_pick_path`/`_resolve_prefix` from the audio saver, and `minimax_structured_prompt.py` imports default prompt data and `_clean_source_name` from another node module.

### End-to-end data flow

1. Structured/library/manual prompt -> LLM text -> unload dependency -> rich parser -> list-mapped song variants, seeds and provenance. Disabled LLM returns empty text so parser manual fallbacks can run.
2. Generation settings plus parser outputs feed the embedded MiniMax subgraph. Original audio is archived separately.
3. Restoration chain: source -> declip -> PRE lowpass -> FlashSR -> hybrid crossover against the source branch -> HF repair -> POST lowpass -> release preparation -> FLAC/MP3.
4. Parser image prompt feeds ComfyUI FLUX nodes -> JPEG saver -> cover embedding in audio outputs.
5. Tags and five path prefixes coordinate audio/artwork/JSON naming. The central JSON node consumes saver outputs, which enforce execution order. Its artifact records are authoritative even when independently incremented filenames differ.
6. Prompt report uses `comfy.ldm.minimax_music.prompt` when available; Markdown is both shown in the node and passed to the final writer.

Most restoration nodes accept `[B,C,T]` tensors, explicitly transfer processing to CPU float32, and return CPU tensors. Their bypass modes generally return the original AUDIO object. FlashSR instead normalizes to `[C,T]`, currently selecting batch zero for a 3-D tensor, runs each channel as an inference batch member, then returns `[1,C,T]`. This distinction must not disappear inside a generalized helper.

### Vendored inference and resources

`flashsr_audio._ensure_vendor_on_path()` prepends `flashsr_inference` to `sys.path`. `FlashSR.FlashSR` uses the uppercase `TorchJaekwon.Model`/`Util` hierarchy, `FlashSR.AudioSR`, and BigVGAN. The tree also contains a newer lowercase `TorchJaekwon/torch_jaekwon` implementation, training/evaluation/data-processing modules, external diffusion implementations, configs, scripts, and component licenses.

Active path: `FlashSR.__init__()` loads student weights, a `VAEWrapper`, and `SRVocoder`; diffusion invokes VAE encoding, one-step inference and vocoder decoding. `VAEWrapper` is not an `nn.Module`, so the outer model's `.to()` does not automatically manage it; `FlashSR.preprocess()` moves it explicitly. Its autoencoder samples a posterior, and diffusion creates random values: the audio input alone does not guarantee deterministic output.

Root requirements declare NumPy, SciPy, SoundFile, imageio-ffmpeg, Mutagen and Pillow. Torch comes from ComfyUI. llama-cpp-python is optional. The live vendor import path also reaches libraries not declared at the root, including plotting/scikit-learn through `UtilTorch`, librosa through mel helpers, YAML through `UtilData`, and other model dependencies. Do not install the whole research framework's dependency list to solve this.

### Frontend, tools, tests and documentation

- `web/prompt_library.js`: legacy template library choices and grouped display labels.
- `web/structured_prompt.js`: current library choices, metadata/text prefill, custom saving, widget headings/order and refresh lifecycle.
- `web/preset_sync.js`: mirrors Python DSP presets; changes custom controls to Custom mode and synchronizes widgets after load.
- `web/migration_utils.js`: pure repair decisions; `web/workflow_migration.js`: mutations of live graphs/widgets. Python and JS operate on different representations and should share fixtures, not necessarily identical code.
- `web/prompt_report_preview.js`: optional frontend Markdown-preview API adapter with plain-text fallback.
- `scripts/validate_release.py`: syntax, package/workflow/docs/privacy checks and conditional Node migration test execution.
- `scripts/build_public_workflow.py`: source-workflow sanitizer with fixed node IDs and boundary-link protection. `upgrade_workflow_to_v2.py` is a large, fixed-template historical transformation, not a generic user-workflow migrator.
- `scripts/package_release.py`, `bump_version.py`: archive selection, release summaries/assets, synchronized version changes. `.comfyignore` independently controls Registry contents.
- `check_model_paths.py`, `toolkit_diagnostics.py`, `preview_output_paths.py`, `comfyui_smoke_test.py`: model/path/support checks and isolated ComfyUI smoke execution.
- `annotate_prompt_metadata.py`, `normalize_prompt_descriptions.py`, `calibrate_prompt_tokens.py`: offline prompt maintenance/calibration.
- `update_demo_catalog.py`, `prepare_demo_covers.py`: selective production-metadata-to-public-gallery export; `docs/index.html`, `docs/demo-tracks.js`, branding/covers are presentation assets, not runtime dependencies.
- Tests cover prompt parsing/precedence, naming/Windows cases, fake LLM and FlashSR helpers, downloads, metadata, workflows, release tooling, progress and gallery behavior. The schema test compares current examples to selected module schemas; it is not an immutable full historical snapshot of all 28 nodes.
- `DEVELOPMENT.md`, `WORKFLOW.md`, `AUDIO_PIPELINE.md`, installation/troubleshooting, node help, release notes and notices establish compatibility and intentional audio behavior. Local handoff files are excluded by existing policies; their private contents should never be copied into public fixtures or documentation.

## 3. Key Findings

Priorities describe urgency; implementation risk describes the chance of unintended behavior change. “Bug” identifies an intended behavioral correction. “Performance candidate” requires measurements before implementation. No catastrophic production failure or measured speedup is asserted.

### F01 — Coverage does not yet freeze the complete integration contract

- **Files/functions:** `tests/test_node_schema_compat.py::load_toolkit_modules`, `NodeSchemaCompatibilityTests`; `__init__.py`; `.github/workflows/ci.yml`; all node mappings.
- **Problem:** Tests manually list selected modules/types, iterate top-level example nodes, compare current schemas with current workflows, and primarily check input names/order and output arity. Simultaneous edits to Python and examples can pass while breaking older workflows. They do not exercise the actual package entry point or tooltip/route startup path. CI uses Python 3.11/Linux and installs no Torch; JS migration checks are conditional on Node availability.
- **Why/approach:** Add independent historical fixtures and an all-28-node contract snapshot; keep lightweight tests and add explicit Torch/ComfyUI integration tiers. Require Node in the frontend test job. Do not substitute synthetic package tests for a real startup test.
- **Priority:** High. **Risk:** Low. **Kind:** Architecture/validation.
- **Compatibility:** Freeze identifiers, ordered required/optional/hidden inputs, types, combo values/order, defaults/ranges/options, return names/types/order, `FUNCTION`, `OUTPUT_IS_LIST`, `INPUT_IS_LIST` where present, `OUTPUT_NODE`, category and intentional cache behavior. Normalize environment-driven choices without erasing their ordering/default rules.

### F02 — Prompt graph loading can overwrite saved edits; asynchronous responses can arrive stale

- **Files/functions:** `web/structured_prompt.js::attach`, `refreshAll`, `prefillStructuredFields`, `prefillSystemPrompt`, `loadedGraphNode`; `web/prompt_library.js::refreshKind`.
- **Problem:** `loadedGraphNode` calls `refreshAll()`, which unconditionally prefills fields and system text, before its later “only fill empty values” logic. `attach()` queues another `refreshAll()`. This contradicts the stated preservation of serialized edits and Python's authoritative widget semantics. Fetch results have no generation/selection guard, so an earlier selection can overwrite a newer selection or intervening edit.
- **Why/approach:** Separate list refresh, explicit-selection prefill and graph-load initialization. Apply each only once per lifecycle event. Guard responses with per-node/per-kind request generation and current selection; preserve edits made while a request is pending. Extract shared HTTP/choice helpers only after the two node behaviors are characterized.
- **Priority:** High. **Risk:** High. **Kind:** Bug + architecture.
- **Compatibility:** Preserve user edits, Custom sentinels, grouped labels and historical serialization. Initial creation may prefill defaults; loading an existing graph must preserve saved values. Explicit selection can still replace the fields it currently owns. Empty-description restoration needs a tested, explicit policy rather than an accidental overwrite.

### F03 — Option refresh and HTTP validation have mismatched contracts

- **Files/functions:** `web/structured_prompt.js::refreshOptionLists`; `prompt_library.py::register_routes`, `_prompt_metadata`, `_save_prompt`, `_save_system_prompt`; `collect_file_field_values` in `prompt_metadata.py`.
- **Problem:** Option-only refresh sends `file=`. The backend calls `load_prompt_file` before aggregation and rejects the empty selection, so no options are returned. POST bodies are assumed to be dictionaries before the error boundary; malformed `fields` can fail later. Async handlers do synchronous recursive filesystem reads. Each metadata lookup re-reads the entire library.
- **Why/approach:** Allow an absent selection to return options without loading one file, while retaining the existing response envelope. Validate body/fields at the HTTP boundary. Move filesystem work into a small service callable off the event loop; preserve request-specific selection state. Aggregate only safe, permitted prompt files with size bounds.
- **Priority:** High. **Risk:** Medium. **Kind:** Bug/reliability/performance candidate.
- **Compatibility:** Keep all five route URLs, field names, normal success payloads and existing selected-file error behavior. Empty-selection options become an explicit supported operation. External directories remain supported; do not impose an unrelated new root restriction.

### F04 — Workflow migration can corrupt sparse inputs and misses nested cases

- **Files/functions:** `workflow_schema.py::migrate_workflow`, `find_external_node_dependencies`; `scripts/build_public_workflow.py::normalize_artwork_saver_inputs`; `web/workflow_migration.js::repairStructuredPromptNode`; `web/migration_utils.js::structuredPromptWidgetRepairs`.
- **Problem:** Python rebuilds only present inputs but calculates target slots from the full canonical order. An in-memory old node with only `structured_llm_output` and `song_count` becomes two inputs with its text link targeting slot 6. It also drops unknown inputs, does not recurse into definitions, and assumes array links. JS unconditionally writes `widgets_values_named.meter = "custom"` even when the named map already contains a valid meter. Current pure decision tests do not cover that adapter mutation.
- **Why/approach:** Build target indices from the actual rebuilt list and explicitly preserve unknown inputs. Introduce small graph/link representation helpers for array and object links and recursive definitions, retaining virtual boundary nodes. Correct the JS named-map update to the resolved value. Add repeated-load/save tests for the adapter, not just decision functions.
- **Priority:** High. **Risk:** High. **Kind:** Bug + compatibility architecture.
- **Compatibility:** Current workflows must be no-ops; old graphs must be idempotently repaired by names/evidence. Do not blindly reorder every graph to a conceptual Python order: the frontend can serialize sockets and widget inputs in separate groups. Unknown/future fields survive. Do not turn fixed-ID release builders into general migrations without explicit input-version preconditions.

### F05 — Release gain can mutate upstream audio through a NumPy view

- **Files/functions:** `audio_release_prep.py::_resample_hq`, `AudioReleasePrep.process`.
- **Problem:** A CPU float32 tensor's `.numpy()` shares storage. Same-rate `_resample_hq` returns `np.asarray(..., dtype=np.float32)` without copying. The loudness branch performs `y[b] *= gain`. With `keep` or a matching requested rate, the original AUDIO tensor can be changed, affecting other graph branches and cached results.
- **Why/approach:** Establish an explicit ownership boundary: copy the work buffer before the first mutating operation. Do not add copies to every read-only helper.
- **Priority:** High. **Risk:** Low. **Kind:** Bug.
- **Compatibility:** Processed output should remain numerically identical; only unintended upstream mutation changes. Bypass should retain original-object passthrough. Test a branched graph and direct CPU float32 calls, not just GPU inputs that already cause a copy.

### F06 — Audio validation/conversion is duplicated, but policies differ

- **Files/functions:** `_validate_audio` in the four restoration modules and two savers; `flashsr_audio.py::_to_channel_samples`, `_make_audio`.
- **Problem:** Six validators repeat shape/type checks with different sample-rate validation. Optional `torch = None` discovery works, but execution can dereference `torch.Tensor` and yield an AttributeError rather than a dependency message. Empty dimensions/nonfinite inputs have no consistent explicit handling. FlashSR silently selects the first item of `[B,C,T]`, unlike the other batch-capable nodes.
- **Why/approach:** Extract a minimal AUDIO validation/CPU conversion helper with documented ownership, expected shapes and caller labels. Keep node-specific adapters. Add positive-rate/empty-shape errors as explicit invalid-input fixes. Assess nonfinite policy separately; do not add silent sanitization.
- **Priority:** High. **Risk:** Medium. **Kind:** Architecture/reliability; FlashSR batch issue is a separate bug candidate.
- **Compatibility:** Never flatten B and C globally. Preserve FlashSR tuple/frame-first heuristics and valid B=1 output. True B>1 FlashSR support or rejection changes behavior; implement only as a documented bug fix after tests and memory accounting, not during extraction.

### F07 — Similar resamplers and filters are not interchangeable

- **Files/functions:** `_resample_hq` in `audio_hf_repair.py`, `audio_release_prep.py`, `flashsr_audio.py`; `_filter_channel_zero_phase`, `_highpass_zero_phase`, `_fir_lowpass`.
- **Problem:** Release and HF resamplers duplicate the Kaiser-beta-14.769656459379492 polyphase operation. FlashSR intentionally tries soxr, then SciPy with its default window, then interpolation. HF `sosfiltfilt` has no short-clip guard, unlike lowpass. In additive hybrid mode, `low_o` is computed but not used; both source and FlashSR filter designs are repeated.
- **Why/approach:** Share the identical polyphase kernel, retaining wrappers and missing-dependency timing. Keep FlashSR's backend precedence separate. Avoid unused original FIR convolution in additive mode while preserving the `fir_taps` report. Reuse coefficients within a call. Handle HF short signals as a separately specified bug fix, retaining existing normal-length padding/numerics.
- **Priority:** Medium. **Risk:** High for numerical changes, Low for extraction. **Kind:** Architecture/performance candidate/edge-case bug.
- **Compatibility:** Preserve sample lengths, axis, dtype, window parameters, phase, cutoff clipping, no-normalization policy and reports. Do not route HF through the lowpass padding algorithm indiscriminately. A different resampler is an audible change, not cleanup.

### F08 — FlashSR fallback/device/cache ownership is incomplete

- **Files/functions:** `flashsr_audio.py::_get_runner`, `_ensure_flashsr_weights`, `clear_flashsr_cache`; vendor `FlashSR.__init__`, `VAEWrapper.to`.
- **Problem:** Failed `model.to("cuda")` logs “continuing on CPU” but leaves `runner["device"]` as CUDA and does not restore the potentially partially moved model. Cache keys use generic `cuda`, not a concrete device index; they contain no file identity. The missing-weight check in `_ensure_flashsr_weights` is inside `if auto_download`, so disabled downloads defer failure to runner creation. VAE ownership is separate from the outer module. Student/vocoder `torch.load` calls lack explicit CPU map location, unlike VAE loading.
- **Why/approach:** Make runner construction transactional: resolve actual device, fully place components, cache only success, and ensure any fallback really is wholly CPU (or fail clearly). Use explicit device identity without changing default selection. Check required weights consistently before construction. Centralize teardown for model and VAE references. Audit checkpoint load locations with real supported weights.
- **Priority:** High. **Risk:** High. **Kind:** Bug/resource management.
- **Compatibility:** Preserve weight directory/names, model state-dict layout, float32 inference, default CUDA preference and cache reuse. File-fingerprint invalidation is a separate lifecycle behavior change; do not hash multi-GB weights on every chunk. Avoid making `VAEWrapper` an `nn.Module` casually because that can change state keys/registration.

### F09 — FlashSR retains every prediction before stitching and redirects process-wide streams

- **Files/functions:** `flashsr_audio.py::MiniMaxFlashSRAudio.upscale`, `_iter_chunks`, `_wola_stitch`, `_import_flashsr_model`.
- **Problem:** `predictions` retains full padded chunk outputs and then allocates a full accumulator and weights. Chunk spans are built twice. Inference redirects stdout/stderr to growing StringIO objects per chunk; redirection affects the process, not only this model, and suppresses useful diagnostics.
- **Why/approach:** Allocate overlap-add accumulators once and consume predictions in the same order immediately; retain `_wola_stitch` as a compatibility/testing wrapper if used externally. Iterate spans once. Prefer a narrowly scoped vendor progress-disable option/local patch with captured diagnostic tail on failure rather than redirecting all output throughout inference. Add cancellation checks between chunks using the supported host capability.
- **Priority:** Medium. **Risk:** Medium. **Kind:** Performance/reliability.
- **Compatibility:** Preserve 48 kHz, 5.12 seconds, 0.50 seconds, zero padding, Hann weights, first-sample behavior and floating-point addition order. The existing identity test explicitly tolerates the zero first sample; do not “repair” it in this refactor. Peak RAM remains proportional to final output length even after eliminating the prediction list.

### F10 — LLM lifecycle is monolithic and replacement can temporarily retain two large models

- **Files/functions:** `llm_chat.py::_get_model`, `_free_comfyui_model_cache`, `unload_llm_models`, `_pick_llm_main_gpu`, `MiniMaxLLMUnload.unload`.
- **Problem:** The 1,074-line module combines discovery, backend negotiation, placement policy, diagnostics, streaming, sessions and 227 lines of ComfyUI cleanup. The new Llama instance is constructed before old cached Llama instances are closed, causing avoidable peak residency on model/options changes. Cleanup releases private ComfyUI prefetch/cast/staging resources and even discovers `ModelVBAR` objects via GC. These host-sensitive operations are difficult to test in place.
- **Why/approach:** Extract a narrowly scoped host-resource adapter and an LLM runtime module. Retain cleanup order and capability checks initially. Serialize acquire/inference/unload so resources cannot be closed mid-use. On replacement, validate files/options first, then explicitly release the old model before allocation when single-model ownership is required; document the changed failure behavior. Keep GPU auto-routing policy separately testable.
- **Priority:** High. **Risk:** High. **Kind:** Architecture/resource performance.
- **Compatibility:** Do not remove dynamic-VRAM workarounds because they look unusual. Preserve release counts, trigger passthrough, `unload_now`/`unload_flashsr` semantics and the current meaning of default GPU 0 auto-routing. Verify classic and dynamic-VRAM hosts, repeated runs and multi-GPU. Constructor failure after early release means the old model is no longer available; make that tradeoff explicit.

### F11 — Session state identity and lifetime are under-specified

- **Files/functions:** `llm_chat.py::_sessions`, `MiniMaxLLMChat.chat`, `_run_chat`, `unload_llm_models`, `_clear_llm_sessions`.
- **Problem:** State is keyed only by session ID, retained without bounds, and can outlive a cached model replacement. Restoration calls `set_state`, saving calls `save_state`, and failures are swallowed at debug level. `_run_chat` always sends only the system message and current user message; saved backend KV state is not demonstrated to provide conversational message history. The annotation says `bytes`, but backend state type is not validated.
- **Why/approach:** Characterize the installed public backend state API with a fake and an opt-in real test before changing it. Track model/options identity with state; prevent cross-model restoration. Introduce explicit lifecycle accounting and cleanup. Separate API-capability adaptation from session semantics.
- **Priority:** High. **Risk:** High. **Kind:** Reliability/bug candidate.
- **Compatibility:** Do not claim to fix conversations merely by adding history; that changes generated text/context usage. Preserve `reset_session=True` default, status strings and seed-based cache-buster behavior. Any state eviction limit or corrected conversation behavior needs explicit policy, tests and release notes; do not silently evict existing sessions during a pure refactor.

### F12 — Model config normalization and downloader robustness need one boundary

- **Files/functions:** `model_downloader.py::load_models_config`, `check_file_entries`, `download_file`, `download_and_extract_zip`; `minimax_autodownload.py::check`; FlashSR weight preparation; `llm_chat.py::_configured_llm_entry`, `_llm_directories`; diagnostics scripts.
- **Problem:** Group/default-target expansion is repeated. The config's top-level `auto_download` and LLM `directory` are not uniformly consumed. Config validation only checks the top-level dictionary. Downloads use one global lock and fixed `.part` names, validate hashes only when supplied, and can publish an empty/short response when no checksum is configured; transient errors leave staging files. ZIP extraction only filters `..`/empty parts, without a resolved containment check; it reads the archive response wholly into RAM and has no runtime call site in the node path.
- **Why/approach:** Normalize model entries once while preserving current precedence and report statuses. Validate filenames separately from configurable target directories. Check nonempty downloads and declared length, stage uniquely, clean up on failure, then atomically replace. Retain existing global lock until contention is measured; per-destination locks are optional. Harden ZIP member containment if retaining the public helper; do not restore runtime code downloads.
- **Priority:** High for integrity, Medium for consolidation. **Risk:** Medium. **Kind:** Reliability/architecture; unused-API cleanup optional.
- **Compatibility:** Preserve `folder_paths.models_dir`, extra LLM path precedence, env fallbacks, explicit base-path semantics, absolute targets, tokens from configured env vars, and `present/downloaded/missing/failed`. Do not suddenly make dormant config keys authoritative. Auto-check with downloads off currently reports missing files without necessarily failing; preserve that distinction from inference, which needs weights.

### F13 — Output path and naming policy is duplicated across writers

- **Files/functions:** smart audio/artwork `_javaish_date_to_strftime`, `_expand_date_macros`, `_is_abs_any_platform`, `_resolve_prefix`, `_pick_path`; absolute saver `_clean_filename`, `_pick_output_path`; `filename_utils.py`; `minimax_json_output.py`; preview tools.
- **Problem:** Smart audio and artwork have almost identical path code, but Windows absolute-path handling differs (drive separator regex and leading-backslash handling). JSON imports private audio-saver functions and inherits audio-specific errors. Absolute saver naming intentionally differs from the shared sanitizer. Portable component truncation counts Python characters, not UTF-16 units, and separately safe album/title components can still produce an overlong combined basename.
- **Why/approach:** Add dependency-light path resolution and collision selection functions next to the existing naming helpers. Keep explicit legacy naming adapters. Centralize logical path planning for previews and actual writes. Reproduce cross-platform path and combined-length failures before changing them.
- **Priority:** High. **Risk:** High. **Kind:** Architecture/portability bug candidates.
- **Compatibility:** Freeze macro expansion order/time behavior, environment/user expansion, relative output-root semantics, explicit absolute/UNC paths, `_001` collision and `_b001` batch suffixes. Preserve absolute saver extension stripping, `audio` fallback and reserved-name policy. Longer-name truncation changes external paths: preserve normal names and document an edge-case migration rule. Never rewrite existing files.

### F14 — Artifact writes are not uniformly failure-safe or collision-safe

- **Files/functions:** saver `save` methods; `save_audio_smart_prefix.py::_write_sidecar`; `minimax_json_output.py::save`; `prompt_library.py::save_custom_prompt`, `save_custom_system_prompt`.
- **Problem:** Audio and artwork write directly to final paths; a tag/encoder failure can leave partial results. Exists-then-write collision handling races. JSON/Markdown/sidecars use predictable `.tmp` names; Markdown is published before JSON so a later failure leaves an orphan. A standalone existing Markdown companion is not considered by JSON collision selection. Custom prompt writes lack the resolved containment protection used for reads, so `_custom` or an existing target symlink can escape the selected root.
- **Why/approach:** Introduce a small same-directory staging/write helper and per-output collision reservation strategy, with explicit cleanup. Finish tags before publishing audio. Resolve/check custom prompt targets, including symlink/junction behavior, and use exclusive creation when overwrite is false. Define companion-file failure behavior; do not pretend a filesystem offers multi-file atomicity.
- **Priority:** High. **Risk:** High. **Kind:** Reliability/bug fixes.
- **Compatibility:** Preserve existing single-run names and supported absolute output destinations. Keep preview non-writing and advisory. Do not globally synchronize counters across formats: production JSON must keep recording actual independently selected artifact paths. Refusing symlink escapes and preventing accidental overwrite are explicit bug fixes. Decide existing-file metadata preservation on overwrite before adopting replacement semantics.

### F15 — FFmpeg/encoding/tagging responsibilities are mixed and repeated

- **Files/functions:** `_find_ffmpeg` and `_write_mp3` in both audio savers; release `_find_ffmpeg`, `_run`, `_measure_bs1770`; smart saver `_prepare`, `_load_cover_bytes`, `_write_standard_tags`; diagnostics `_check_ffmpeg`.
- **Problem:** Discovery, subprocess flags, quality mapping, temporary WAV cleanup and peak preparation repeat. Absolute MP3 encoding includes `-map_metadata -1`; smart encoding does not. Tags and covers make the smart saver 564 lines. Cover decode/resize is repeated per batch item. Loudness uses two temporary WAV/FFmpeg passes per item. Diagnostics only checks PATH, falsely reporting no FFmpeg when the runtime's imageio fallback works.
- **Why/approach:** Extract shared FFmpeg discovery/process execution, codec operations and tag/cover writing, with explicit legacy flag policies. Decode the cover once per save call. Share peak preparation while retaining wrapper errors. Profile WAV I/O before considering piping; keep both loudness measurements until equivalence is demonstrated.
- **Priority:** Medium. **Risk:** Medium. **Kind:** Architecture/performance candidate/diagnostic bug.
- **Compatibility:** Preserve encoder arguments, quality choices, sample formats, ID3v2.3, FLAC tag keys, WAV's deliberately limited tags, cover size/clamping, normalization-only-if-clipping gain and saver return values. Do not replace static gain with dynamic loudnorm, a limiter, or an inferred second measurement.

### F16 — Prompt duplication should be consolidated below parser semantics

- **Files/functions:** `minimax_batch.py::_read_text`, `_resolve_prompt_directory`, `_clean_source_name`, `_new_seed`, `load`; corresponding helpers and list expansion in `minimax_prompt_source.py`; structured-node imports.
- **Problem:** File decoding, extension discovery, source sanitation, seeds and variant expansion repeat. But parsers differ deliberately: legacy batch accepts strict bracket headings, appends repeated sections, and rejects invalid counts; rich parsing supports Markdown/inline forms, last-section-wins, clamped/decorated counts, image fallbacks and reasoning stripping. Rich parser `parse()` uses explicit `song_count`, whereas folder source can honor file counts.
- **Why/approach:** Extract shared file reading/discovery, source naming, default prompt constants and variant iteration. Keep two small parser entry points with explicit policies instead of one over-configurable parser framework. Keep front-matter parsing distinct from generated `[Caption]/[Lyrics]` parsing.
- **Priority:** Medium. **Risk:** High. **Kind:** Architecture.
- **Compatibility:** Preserve UTF-8/BOM/CP1252 for legacy sources versus strict UTF-8 and size limits for library selection, sort order, origin markers, all list-output positions, per-file run indices, global incremental seed modulo, and always-rerun NaN fingerprints. Do not start applying prompt budgets to legacy paths without a separate behavioral decision.

### F17 — Prompt options cache is owned by a node and differs from safe library enumeration

- **Files/functions:** `minimax_structured_prompt.py::_collect_options`, `invalidate_library_options_cache`; `prompt_library.py::_iter_prompt_paths`, route save invalidation; `prompt_metadata.py::collect_file_field_values`.
- **Problem:** Initial options scan all files below the bundled user directory rather than the safe extension/symlink-filtered iterator. Metadata aggregation has no byte limit. The global node cache is invalidated only through one save route; external edits can leave initial schemas stale, while HTTP requests repeatedly rebuild everything. `_library_options_version` increments but is not used to resolve this.
- **Why/approach:** Move option aggregation/cache ownership to the library service, use one safe enumeration policy, and key bounded caches by root/library changes. Keep selected-prompt content fingerprints independent and authoritative. Provide deliberate refresh invalidation; do not rely only on coarse mtimes.
- **Priority:** Medium. **Risk:** Medium. **Kind:** Architecture/performance/reliability.
- **Compatibility:** Preserve curated-first options, casefold sorting, 200-per-field limit and arbitrary runtime values allowed by `VALIDATE_INPUTS`. Cached data must not change manual/file precedence or prevent same-filename edits from triggering execution.

### F18 — Token trimming can violate its own postcondition

- **Files/functions:** `prompt_budget.py::_trim_lines_to_budget`, `trim_prompt_to_budget`; rich parser `_apply_prompt_budget`; `scripts/calibrate_prompt_tokens.py`.
- **Problem:** Caption trimming is calculated separately after a residual lyrics character has already been retained. In-memory input `caption='x'*20000`, `lyrics='y'*20000`, budget 4500 returns an estimate of 4501. `_apply_prompt_budget` does not recheck. The 3.5-character estimate is calibrated on limited material; statements that it always bounds real tokenizer usage are stronger than the implementation establishes, especially for the multilingual library.
- **Why/approach:** Preserve line-first semantics but enforce the combined final estimate and accumulate hard-cut flags across both fields. Test oversized caption/lyrics combinations, tiny budgets, Unicode and orphan tags. Keep exact-tokenizer evaluation in an optional calibration/integration test; avoid loading the text model at node discovery.
- **Priority:** High. **Risk:** Medium. **Kind:** Bug; estimator improvements optional.
- **Compatibility:** Keep defaults 4500/5000, under-budget text and existing accepted trim behavior. Correct only out-of-contract results initially. Changing the estimator globally alters prompts and output music; require multilingual evidence and release notes before doing so.

### F19 — Metadata builders and migration policy are disconnected

- **Files/functions:** `minimax_json_output.py::_generation_metadata`, `_parse_object`; `minimax_metadata.py::MiniMaxSongMetadata.build`, `MiniMaxMetadataLoader.load`; `metadata_schema.py::_v6_to_v7`, `migrate_metadata_payload`; `scripts/update_demo_catalog.py`.
- **Problem:** Legacy builder tolerates malformed JSON via `{raw: ...}`; central writer demands objects and manually overlaps many fields. Loader never migrates, and writer stamps v7 over the supplied base. Migration and central assembly shallow-copy dictionaries; `_v6_to_v7` demonstrably adds `flashsr.settings` to the caller's input. Writer's `restoration` update can also mutate a nested legacy object. Loader lacks a file-content `IS_CHANGED`, so editing a file in place can leave cached outputs stale. Current direct writer inputs omit sampler/scheduler and detailed LLM model/options, so “complete reproduction from JSON alone” is overstated.
- **Why/approach:** Extract pure section builders and explicit parsing policies, retaining legacy wrappers. Make supported migrations nonmutating. Use migrations internally for known historical versions, with a compatibility policy for currently accepted unversioned/unknown records; do not blindly call the strict helper everywhere. Add loader fingerprints. Treat extra reproducibility fields as an additive schema/API feature in a later change.
- **Priority:** High. **Risk:** High. **Kind:** Architecture/bug/reproducibility gap.
- **Compatibility:** Preserve v7 payloads, unknown keys, zero/false versus omitted inputs, strict-versus-permissive behavior and legacy defaults. Loader currently returns reserialized source JSON; distinguish its public raw output from internal normalized data. Never reject previously readable files solely because they lack a schema during a structural refactor. New optional fields must be appended and versioned according to `metadata_schema.py` policy.

### F20 — Presets/configuration are duplicated across Python and JavaScript

- **Files/functions:** `audio_lowpass.py::PRESETS`; `audio_declip.py::_preset`; `audio_hf_repair.py::_preset_repair`; `audio_release_prep.py::_preset_values`; `minimax_settings.py`; `web/preset_sync.js`; workflow builders.
- **Problem:** Python is authoritative, but JS mirrors numeric presets and labels manually. Settings nodes call an audio node's private helper. Workflow upgrade scripts repeat schema/preset/default literals. Similar-looking values can mean a node default, a historical default, or a selected example value, and must not be conflated.
- **Why/approach:** First add Python/JS parity fixtures. Move current DSP preset data/resolution into one lightweight owner only if doing so simplifies callers. Prefer checked-in generated JS data or a parity check over an asynchronous startup dependency. Keep historical migration constants frozen separately.
- **Priority:** Medium. **Risk:** Medium. **Kind:** Consistency/architecture.
- **Compatibility:** Exact labels, case (`CUSTOM` versus `Custom`), ordering, values, override precedence and edit-to-Custom behavior are contracts. Do not synchronize examples by changing their audio settings to node defaults.

### F21 — Vendor boundary hides dependency and namespace risks

- **Files/functions:** `flashsr_audio.py::_ensure_vendor_on_path`, `_import_flashsr_model`; `flashsr_inference/FlashSR`, uppercase/lowercase TorchJaekwon trees; root manifests and notices.
- **Problem:** Generic top-level packages `FlashSR` and `TorchJaekwon` can collide with other custom nodes already in `sys.modules`. The active utility import path drags in plotting/scikit-learn even for inference. Both old/new research trees and training code are bundled; notices describe exclusions that do not fully match the inventory. No exact upstream revisions/patch manifest are recorded in the vendor notice.
- **Why/approach:** Record origin/revision if recoverable and local patches; check resolved module origins and give clear conflicts before invasive import rewriting. Trace a real inference import closure, then move unused optional plotting imports to their point of use as minimal documented vendor patches where safe. Add only proven inference dependencies. Pruning unreachable trees is optional and requires dynamic-import/config/checkpoint coverage.
- **Priority:** High for dependency verification, Low for pruning. **Risk:** High. **Kind:** Reliability/optional footprint improvement.
- **Compatibility:** Preserve import paths, YAML/config assets, checkpoint structure and all notices/licenses. Do not replace vendored diffusion or vendor TorchJaekwon with the newer lowercase implementation. Do not label uncalled training code dead merely because root nodes do not reference it textually.

### F22 — Logging and failure reporting need targeted changes, not a new framework

- **Files/functions:** `toolkit_logging.py::_level_from_env`; `llm_chat.py::_get_model`, `chat`, `_run_chat_streamed`, cleanup functions; FlashSR fallback paths.
- **Problem:** LLM constructor error ends with a non-f-string literal, so it displays `{type(exc).__name__}: {exc}`. Stream chunk count is reported as exact tokens although a chunk is not guaranteed to equal one token. Full LLM output/reasoning is emitted at INFO and also stored in metadata. Some failed cleanup/resampling paths silently pass. `_level_from_env` accepts any matching `logging` attribute, not just integer level constants, and can fail import for unsuitable env values.
- **Why/approach:** Correct error interpolation, validate level values, distinguish progress updates from backend usage, and use actionable contextual logs for fallback/cleanup. Retain the existing logger/no-root-handler design. Treat reducing full-text INFO logs as an explicit operational/privacy policy change, with metadata outputs preserved.
- **Priority:** Medium. **Risk:** Low for errors, Medium for logging policy. **Kind:** Code quality/reliability.
- **Compatibility:** Keep node status/report outputs stable unless intentionally corrected. Do not swallow processing failures or expose tokens in logs. Broad catches at optional host boundaries can be appropriate; narrow them only with demonstrated exception behavior.

### F23 — Release/tooling policies have drift and should remain separate from runtime architecture

- **Files/functions:** `pyproject.toml`, `requirements.txt`, `INSTALLATION.md`, `install_requirements.bat`; diagnostics; `scripts/package_release.py::should_include`, `privacy_scan_summary`; release validator; fixed-ID workflow builders; demo scripts.
- **Problem:** Docs say NumPy is not replaced, but both dependency manifests constrain it. Tooling uses `tomllib` while runtime metadata declares Python >=3.10; CI tests only 3.11. ZIP selection excludes ZIP files but not the `dist` directory or generated non-ZIP assets, and differs from Registry exclusions. Privacy scan patterns/scope differ between validator and packager. Several scripts/tests repeat synthetic-package loaders; public workflow builders assume historical node IDs. Demo update `--dry-run` still creates the cover directory before checking whether writes should happen.
- **Why/approach:** Document host/runtime versus tooling Python requirements or add a tooling-only compatibility fallback. Reconcile NumPy install policy deliberately. Share pure archive/privacy selection where equivalent, while preserving intended GitHub-versus-Registry content differences. Add dry-run/no-write and archive manifest tests. Clearly constrain historical builders to supported input templates. Consolidate test import bootstrap without introducing a runtime service locator.
- **Priority:** Medium. **Risk:** Medium. **Kind:** Tooling/reliability; some optional cleanup.
- **Compatibility:** Keep script entry points and current defaults. Do not run historical rewrite tools on the current workflow as part of refactoring. Keep public gallery allowlisted fields, IDs, duplicate-take matching, SoundCloud URLs and cover locations. Do not put private handoff content in snapshots. Release/version management should use the existing bump/check tooling rather than a new runtime version system.

## 4. Cross-Cutting Refactoring Opportunities

| Shared concept | Consolidate these implementations | Keep distinct / safe boundary |
|---|---|---|
| Output path planning | Smart audio and image macro/root/collision helpers; JSON private imports; previews | Absolute saver legacy basename policy; source-name sanitizer; real platform filesystem behavior. |
| Safe text publication | JSON, Markdown, sidecar and custom prompt staging/cleanup | Collision mode and companion-file policy remain caller decisions. No generic transaction framework. |
| Audio ownership | Repeated tensor validation and CPU float32 conversion | BCT processing versus FlashSR CT adapter; bypass identity; copy only before mutation. |
| Resampling | Release/HF Kaiser polyphase kernel | FlashSR soxr/default-polyphase/interpolation chain and vendor mel resampling. |
| Encoding/processes | FFmpeg resolution, hidden Windows process setup, error/temporary cleanup, MP3 quality mapping | Loudness analysis versus encoding arguments; legacy metadata stripping; both measurements. |
| Tags/covers | Smart saver tag and cover codec helpers | Artwork image selection/JPEG export is a different output contract. |
| Prompt I/O/variants | Legacy BOM/CP1252 reading, extension parsing, source names, seed/variant iteration | Strict library UTF-8 and containment; strict batch parser versus tolerant LLM parser versus front matter. |
| Library service | Safe enumeration, metadata options, cache invalidation, custom writes | Thin HTTP adapter; node schemas/ComfyUI cache rules stay in nodes. |
| Metadata sections | Pure source/generation/restoration/FlashSR builders and known migrations | Legacy raw-JSON fallback and fixed outputs; canonical strict object parsing. |
| Model configuration | Group/default expansion shared by check node, FlashSR and diagnostics | LLM category search/extra paths and configured download targets have distinct precedence. |
| Resource ownership | Host cleanup adapter invoked by LLM runtime; separate FlashSR runner cache | Llama and Torch models need different lifecycle implementations; no universal model registry. |
| Frontend utilities | HTTP envelopes, widget lookup, grouped choices, dirty-canvas and guarded callbacks | Node-specific refresh/restore/selection policy and migration semantics. |
| Preset consistency | Current DSP data plus Python/JS equivalence fixtures | Historical migration values; reference workflow selections. |
| Graph traversal | Node/link/boundary interpretation in migrations, validator, builder and smoke conversion | Mutation, validation and subgraph-to-API lowering remain separate operations. |

Avoid an omnibus `utils.py`, a universal node base class, reflective node auto-discovery, a DI container, generalized DSP graphs, or a Pydantic schema rewrite. Small functions and a few explicit state owners are sufficient. Existing `toolkit_logging`, `progress_utils`, `filename_utils`, `prompt_metadata` and `metadata_schema` should be extended where appropriate rather than duplicated.

## 5. Proposed Target Architecture

Keep existing root filenames/classes as stable adapters and re-export helpers where existing tests/scripts or external integrations may import them. New modules are implementation-phase proposals, not files created by this analysis. Add each only when extracting a real responsibility; names below are a concrete starting point, not a mandate for empty layers.

```text
__init__.py                   explicit mappings + help + route registration
existing root node modules    unchanged ComfyUI schemas/signatures/return adapters
    |
    +-- prompt_sources.py     common file/variant/default helpers, parser policies
    +-- prompt_library.py     filesystem library service + bounded option cache
    +-- prompt_routes.py      HTTP adapter (register_routes compatibility export)
    +-- prompt_metadata.py    existing vocabulary/front matter/brief assembly
    +-- prompt_budget.py      existing pure estimate/trim
    +-- production_metadata.py pure section assembly + legacy parsing policies
    +-- metadata_schema.py    existing version/migration policy
    +-- audio_utils.py        validation/conversion/ownership + shared SRC kernel
    +-- audio_presets.py      current DSP preset data/resolution, if justified
    +-- output_paths.py       prefix/date/collision planning, no codec imports
    +-- file_writes.py        small staging/publication primitives
    +-- audio_encoding.py     SoundFile/FFmpeg format operations
    +-- audio_tags.py         tag/cover encoding
    +-- ffmpeg_utils.py       executable lookup/subprocess boundary
    +-- llm_runtime.py        llama capability/options/chat/model/session owner
    +-- comfy_resources.py    capability-checked host cleanup + diagnostics
    +-- flashsr_runtime.py    vendor adapter + runner lifecycle (only if useful)
    +-- model_downloader.py   config/path/download/report boundary

web existing extensions      lifecycle adapters, original extension names
    +-- prompt_ui_utils.js   shared UI/network helpers with stale-result guards
    +-- migration_utils.js   pure decisions + shared historical fixtures
scripts/tests                consume pure helpers; no runtime dependency on scripts
flashsr_inference            separate, documented vendor boundary
```

Dependency direction: node adapters -> domain helpers -> filesystem/process/backend boundaries. Pure data/algorithm modules must not import node classes or register routes. HTTP adapter -> library service; the library must not import the structured node to clear cache. JSON/path previews must not import audio codecs just to plan a filename. LLM and FlashSR can call a narrow host resource adapter but should not depend on each other's node classes. Use explicit cleanup callbacks or a small function import; do not create an event bus.

Keep DSP implementations in their current focused modules initially. At 256–373 lines, restoration modules are not intrinsically too large; the mixed concerns and duplicated boundaries matter more than line count. Keep the simple settings, tag, image-size, session-ID and sampler wrappers straightforward. Keep frontend plain JavaScript and the demo static site independent of runtime packaging.

## 6. Refactoring Phases

### Phase 1 — Freeze contracts and establish regression evidence

#### Objective
Make every later change distinguishable from an accidental compatibility break.

#### Files affected
`tests/`, `.github/workflows/ci.yml`, `scripts/validate_release.py`, both example workflows as read-only fixtures, all node modules for inspection. No behavior changes required.

#### Changes
Capture all 28 registered contracts and representative historical graphs; cover frontend adapter loading and mutation. Add failing regressions for F02–F05, F08, F18 and F19 before fixes. Add tests for model replacement ordering and independent audio branches. Separate lightweight unit, Torch DSP, frontend and real-host tiers.

#### Dependencies
None. Record the unmodified baseline, runtime/backend versions and any pre-existing failures first.

#### Compatibility risks
Snapshots must retain ordering and options; do not use the edited current workflow as the only expected result. Dynamic combos need deterministic fixtures and separate integration assertions.

#### Validation/tests required
Existing Python/JS tests and release validation; actual package-import smoke with fake host modules, then real ComfyUI discovery. Verify legacy nodes absent from current workflows still register.

#### Expected benefit
Reliable change boundaries and a usable rollback reference.

### Phase 2 — Correct workflow/prompt preservation and bounded correctness defects

#### Objective
Stop corrupting existing user data or producing invalid outputs before restructuring broad components.

#### Files affected
`workflow_schema.py`, `web/{migration_utils,workflow_migration,structured_prompt}.js`, `prompt_library.py`, `prompt_budget.py`, `audio_release_prep.py`, `metadata_schema.py`, relevant tests.

#### Changes
Fix actual-list slot mapping, preserve unknown inputs and named meter values, distinguish graph restore from explicit prefill, guard stale requests, support option-only refresh, validate HTTP payload types, copy before release gain, enforce trim postcondition and prevent nested migration mutation. Keep each bug fix separate from extraction commits. Introduce graph traversal helpers only as needed for verified nested fixtures.

#### Dependencies
Phase 1 regressions. This phase does not depend on a new architecture.

#### Compatibility risks
Saved edits/valid graphs remain unchanged; previously broken edge cases change intentionally. Do not silently add message history, change DSP kernels or reject unversioned metadata here.

#### Validation/tests required
Load/save/reload historical/current/nested graphs; delayed request ordering; saved edits and Custom omission; all trim branches; input tensor unchanged at matching rate; migration input immutability.

#### Expected benefit
Immediate protection of workflows, source audio and prompts.

### Phase 3 — Consolidate output paths, publication and encoding

#### Objective
Remove saver-to-saver coupling and make export failure handling consistent.

#### Files affected
`filename_utils.py`, proposed `output_paths.py`, `file_writes.py`, `ffmpeg_utils.py`, `audio_encoding.py`, `audio_tags.py`; both audio savers, artwork, production JSON, custom prompt writers, preview/diagnostic scripts and tests.

#### Changes
Extract path planning with legacy adapters, shared FFmpeg discovery and peak preparation. Stage outputs before final publication, preserving explicit format flags and tag behavior. Resolve custom prompt write containment. Reuse cover bytes within a save. Remove JSON's dependency on smart audio internals through compatibility exports. Separate companion Markdown policy from single-file atomic writes.

#### Dependencies
Phases 1–2; naming/codec characterization before shared implementations.

#### Compatibility risks
High: filenames, collision selection, error modes, codec/tag details and observable partial-file behavior. Treat path/overwrite fixes as explicit changes. Do not synchronize artifact counters or change legacy sanitizer output.

#### Validation/tests required
Windows and POSIX paths, UNC/date/env expansion, Unicode, all modes, batches and failures; audio decodes/tags/covers; preview/write parity; no final partial artifacts after injected failures; `_custom` symlink/junction escapes; JSON references actual files.

#### Expected benefit
Less duplication and fewer incorrect or partial exports, with lightweight previews.

### Phase 4 — Consolidate prompt and metadata services

#### Objective
Reduce cross-node imports and make configuration/data policies explicit.

#### Files affected
Legacy/rich/structured prompt modules, `prompt_library.py`, `prompt_metadata.py`, proposed `prompt_sources.py`, `prompt_routes.py`, `production_metadata.py`; metadata nodes/schema; frontend shared helpers; relevant scripts/tests.

#### Changes
Extract common file/seed/variant helpers without merging parser dialects. Move option cache into the library service and offload blocking route work. Share pure metadata section builders with named strict/legacy parse policies. Integrate known-schema migration carefully, retain raw loader output compatibility and add content invalidation. Add parity checks for duplicated current presets; extract a preset owner only if useful.

#### Dependencies
Phase 2 lifecycle fixes and Phase 3 safe writer/path interfaces.

#### Compatibility risks
High: parser semantics, manual/file precedence, cache behavior, JSON merge/omission rules and historical input signatures. Extra reproducibility fields remain a later feature, not required to complete extraction.

#### Validation/tests required
Legacy strict/repeated/count cases; rich Markdown/reasoning/fallback cases; variant order/seeds; same-filename prompt edits; option refresh after additions/deletions; known/unknown/unversioned metadata; raw fallback, zero values and nested-key preservation.

#### Expected benefit
One owner per shared concept without replacing established user-facing formats.

### Phase 5 — Isolate and harden model/resource lifecycle

#### Objective
Make model acquisition, placement, reuse and release testable and failure-safe.

#### Files affected
`llm_chat.py`, `flashsr_audio.py`, `model_downloader.py`, `minimax_autodownload.py`, proposed `llm_runtime.py`, `comfy_resources.py`, optional `flashsr_runtime.py`; diagnostics/config tests; narrowly necessary vendor patches.

#### Changes
Extract cleanup adapter preserving order/capability guards. Establish acquire/use/unload synchronization and single-model LLM replacement policy. Identify session state by backend/model/options, characterize restore API, and make cleanup explicit. Correct FlashSR fallback and component placement. Normalize model config entries and harden download staging/integrity. Add module-origin diagnostics at vendor imports.

#### Dependencies
Phase 1 lifecycle tests; existing node adapters must remain stable. Independent of broad DSP optimization.

#### Compatibility risks
High: model-switch failure behavior, GPU auto-routing, ComfyUI private APIs, checkpoint loading and session behavior. No arbitrary TTL/LRU or conversation-history rewrite. Preserve all external model paths.

#### Validation/tests required
Fake constructor/transfer/load/close failures; cache hits/misses; same/different session/model/options; concurrent use/unload; CPU/CUDA/multi-GPU; repeated LLM -> music -> FlashSR -> LLM runs; download disabled/missing/short/failed; real supported checkpoint import/load/release.

#### Expected benefit
Lower peak memory during replacement, actionable failures and predictable resource ownership.

### Phase 6 — Apply measured audio performance improvements

#### Objective
Reduce unnecessary memory/I/O/work while preserving audio numerics.

#### Files affected
Restoration modules, `flashsr_audio.py`, shared audio helpers, FFmpeg/encoding helpers and dedicated regression/benchmark tests.

#### Changes
Extract common AUDIO ownership/validation and identical Kaiser SRC. Stream overlap-add accumulation; avoid unused original FIR convolution and repeated designs. Consider vectorizing channel filters only after parity evidence. Optimize cover reuse first; consider FFmpeg pipes or broader allocations only if profiles justify them. Add host cancellation checks at safe iteration boundaries.

#### Dependencies
Phases 3 and 5 lifecycle/process boundaries; baseline DSP fixtures from Phase 1.

#### Compatibility risks
High for output samples. Preserve RNG order, chunk/padding/window boundaries, filter phase, dtype and report fields. Full B>1 FlashSR support remains separately scoped.

#### Validation/tests required
Deterministic fake runner equivalence, actual seeded model comparisons on a pinned stack, impulse/sweep/silence/short/long/stereo/batch tests, spectral and level metrics, RSS/VRAM/time profiles before/after. Every optimization must show a measurable benefit or be omitted.

#### Expected benefit
Reduced FlashSR prediction retention and redundant filtering without changing sound.

### Phase 7 — Finish integration, packaging and maintainability checks

#### Objective
Ensure the final structure is installable, documented and maintainable on supported hosts.

#### Files affected
Manifests/install/docs, vendor notices, release/diagnostic/demo scripts, `.comfyignore`, CI, tests; optional confirmed-unused internal code only.

#### Changes
Reconcile dependency/tooling Python policy, verify vendor import closure in a minimal supported environment, record vendor provenance/patches, tighten archive selection and dry-run behavior, unify overlapping privacy checks, and consolidate test bootstrap. Document fixed-template historical scripts. Remove only proven unused internals after searches and runtime coverage; retain public exports and vendor compatibility assets.

#### Dependencies
All selected preceding phases. Vendor pruning and new metadata features may be deferred without blocking completion.

#### Compatibility risks
Manifest/install changes can affect ComfyUI's environment; packaging can omit required YAML/vendor/web data. Do not update unrelated libraries, prompts, defaults or model weights.

#### Validation/tests required
Complete test matrix, both real workflows, package-from-clean-tree and package-from-dirty-tree manifest checks, fresh install/ComfyUI discovery, all docs/JS assets present, deterministic archive contents, no private/generated files, dry-run no writes.

#### Expected benefit
An implementable, distributable refactor with an explicit maintenance boundary.

## 7. Detailed Implementation Tasks

These tasks are for the implementation agent. Every task must retain the public adapter until tests prove compatibility; do not perform all mechanical moves in one commit.

- [x] **T01 / F01 — Capture all public node contracts.** Inspect every mapping listed in section 2, import the real entry point in a controlled host fixture, and store independent expected schemas and execution flags. Include hidden inputs and tooltip decoration invariants. Expected: all 28 identifiers and their old workflows remain discoverable.
  - **Done (2026-09-10).** Added `tests/_toolkit_bootstrap.py` (fake `aiohttp`/`server` host + synthetic-package loader for the real `__init__.py`; owns `NODE_OWNER`, the expected route table and the contract normalizer), `tests/test_node_contracts.py` (28 identifiers, display names, no duplicate mappings, owner module per node, `WEB_DIRECTORY`, all 5 HTTP routes against a fake `PromptServer`, tooltip coverage + idempotent `install_input_tooltips`, full snapshot comparison) and the checked-in fixture `tests/fixtures/node_contracts.json` (ordered required/optional/hidden inputs with types/options/defaults, returns, flags, category, class name; tooltips stripped). `scripts/dump_node_contracts.py` regenerates and `--check`s the fixture. 12 new tests.
- [x] **T02 / F01,F04 — Establish historical graph fixtures.** Extend `tests/test_workflow_schema.py`, `test_node_schema_compat.py`, `test_workflow_migration.mjs` with parser/JSON old-order, missing optional inputs, unknown fields, nested object links, virtual boundaries and named/positional pre-meter cases. Expected: valid graphs are unchanged; migrations are repeatable.
  - **Done (2026-09-10).** `tests/test_workflow_schema.py` rewritten around explicit fixtures: the exact pre-2.0.0 parser serialization (verified against git tag `v1.0.3`), sparse old-order nodes, unknown/future inputs, STRING-on-INT artifacts, malformed slots, nested `definitions.subgraphs` with object-form links, virtual boundary nodes, and no-op assertions for both bundled workflows. `tests/test_node_schema_compat.py` gained required-present/optional-omittable cases. `tests/test_workflow_migration.mjs` gained adapter-level cases (saved meter preserved, pre-2.0.5 named to custom, repeated load/save idempotency, current positional serialization untouched, parser/LLM adapter mutations).
- [x] **T03 / F04 — Correct migration mutation.** In `migrate_workflow`, map from actual rebuilt inputs, retain unknown names and handle malformed slots deliberately; reject/skip unsupported link shapes without partial corruption. In `repairStructuredPromptNode`, preserve the resolved meter value in the named map. Expected: no target outside `inputs`, no saved meter reset.
  - **Done (2026-09-10).** `workflow_schema.migrate_workflow` rewritten: it now captures the stored slot-to-name mapping *before* rebuilding, rebuilds group-aware (socket inputs first, then widgets, each in canonical definition order - exactly what the ComfyUI frontend serializes), preserves unknown inputs in their original group, recurses into `definitions.subgraphs`, accepts array-form *and* object-form links, refuses to guess unresolvable links (collected via the new optional `diagnostics` list) and never writes a `target_slot` outside `range(len(inputs))`. **Concrete defect found and fixed:** the old implementation detected the *current* bundled workflow as old-order and silently rebuilt node 53, destroying the frontend's socket/widget grouping; both bundled workflows are now byte-for-byte no-ops (new regression test). The frontend mutation code moved from `web/workflow_migration.js` into `web/migration_utils.js` as `repairParserNodeLinks` / `repairJsonNodeLinks` / `repairStructuredPromptWidgets` / `repairLLMChatWidgets` so it is Node-testable; `workflow_migration.js` is now only the extension wiring. `repairStructuredPromptWidgets` no longer resets `widgets_values_named.meter` to custom - it writes back the value that was actually resolved and applied.
- [x] **T04 / F02 — Split frontend lifecycle operations.** Change `refreshAll`, `attach`, `loadedGraphNode` into explicit create/restore/select refresh paths. Use guards for source/directory/file/request generation and edits while awaiting. Expected: reopening a graph keeps edited description/system/fields and rapid file selection cannot apply stale text.
  - **Done (2026-09-10).** New shared frontend module `web/prompt_ui_utils.js` (no ComfyUI imports) owns the lifecycle mechanics: request generations (`beginRequest`/`isCurrentRequest`/`invalidateRequest`, WeakMap-keyed per node and per request key), selection snapshots (`readSelection`/`sameSelection`), pure widget application (`applyStructuredFields`/`applyDescription`/`applySystemPromptText`) and `scheduleInit` (last scheduler wins, so `nodeCreated` and `loadedGraphNode` cannot both initialize). `web/structured_prompt.js` no longer has a `refreshAll` that prefills unconditionally: it now has `refreshLibraryLists` (lists only, never touches edits), `applyCreateDefaults` (new node) and `restoreSavedValues` (graph load - structured fields are left at their serialized values, only an empty description/system prompt is filled). Field and system-prompt prefills run through `runGuardedMetadataPrefill`/`runGuardedSystemPrefill`, which discard a payload when a newer request started or when the selection changed while it was in flight, and return an explicit `applied`/`stale`/`skipped`/`error` status. `web/prompt_library.js::refreshKind` got the same guards and both hooks now share one scheduled refresh instead of queuing two. New Node test `tests/test_structured_prompt_frontend.mjs` (17 assertions) covers delayed/out-of-order responses in both arrival orders, source changes while pending, stale-error suppression, restore-mode edit preservation and create-vs-restore scheduling; `scripts/validate_release.py` now runs both `.mjs` frontend suites.
- [x] **T05 / F03 — Repair option-only requests.** In `_prompt_metadata`, compute options independently of optional selected-file loading; preserve response envelope. Validate POST objects and string field values inside the handled boundary. Expected: refresh works in Custom file mode and malformed requests get controlled errors.
  - **Done (2026-09-10).** `prompt_library.py`: the `prompt_metadata` handler no longer calls `load_prompt_file` for an absent/empty selection - `fields`/`description` are returned empty while `unique_values` is still aggregated, keeping the exact same success envelope (and the existing selected-file error behavior). The two POST handlers (`save_prompt`, `save_system_prompt`) now validate inside the handled boundary via new `_body_string` / `_body_bool` / `_body_fields` helpers: non-object bodies, non-string `source`/`directory`/`file`/`text`/`description`, non-string field names or values and non-boolean `overwrite` all return a controlled HTTP 400 instead of being silently coerced. New `tests/test_prompt_routes.py` (12 tests) drives the real handlers through the fake `PromptServer`: option-only refresh with and without `file`, selected-file metadata, missing selection, malformed/`bad-json` bodies, duplicate-name rejection and the `_custom/<name>.txt` output.
- [x] **T06 / F05 — Fix release buffer ownership.** In `AudioReleasePrep.process`, copy the same-rate work buffer before `*= gain`. Test matching-rate CPU float32 input with a stub meter and branched consumer. Expected: output unchanged from the intended algorithm, input unchanged.
  - **Done (2026-09-10).** `audio_release_prep.py`: the static-gain branch (`target_lufs is not None`) now takes an explicit ownership boundary - the preset targets are resolved *before* the branch and the work buffer is replaced by `np.array(y, dtype=np.float32, copy=True)` whenever the branch may scale in place. Root cause: `_resample_hq` returns `np.asarray(x, dtype=np.float32)`, which is a view of the caller's tensor because `Tensor.to(cpu, float32)` is a no-op for CPU float32 input, so `y[b] *= gain` wrote straight into the upstream AUDIO. The resample helper itself was left read-only. New `tests/test_release_prep.py` (7 tests, stubbed `_measure_bs1770`) covers same-rate CPU float32 mutation, shared-storage detection, a branched consumer holding a reference to the original tensor, the resampled path, resample-only (meter must not run), bypass pass-through and float64 input.
- [x] **T07 / F18 — Enforce combined trim budget.** In `trim_prompt_to_budget`, reserve room for both fields, retain line-first policy, combine hard-cut flags and recheck the result. Include the 20,000/20,000-character reproduction. Expected: final estimate <= requested valid budget without altering under-budget inputs.
  - **Done (2026-09-10).** `prompt_budget.py` gained `_combined_char_limit` (with one token of slack so `ceil()` cannot round past the budget) and `_shorten_to_fit`, plus a final recheck stage in `trim_prompt_to_budget`: after the line-wise lyrics and caption passes, the lyrics remainder is shortened first (they are the soft field) and then the caption, and the hard-cut flag is now accumulated with `or` across both fields instead of being overwritten. The 20,000/20,000 reproduction now returns 4499/4500 instead of 4501/4500. `tests/test_prompt_budget.py` gained the reproduction, a 7-case budget/shape matrix (tiny budgets, Unicode, multiline), an under-budget no-op test, a hard-cut accumulation test and orphan-tag retention.
- [x] **T08 / F13 — Extract output path planning.** Move shared smart helpers to `output_paths.py`; leave root helper wrappers accepting old arguments. Give callers explicit error labels and legacy absolute-path/naming policies. Update central JSON and preview imports. Expected: same normal output strings with no codec imports needed for previews.
  - **Done (2026-09-10).** New dependency-light `output_paths.py` owns date-macro expansion (`expand_date_macros` with an injectable `now`, so ordering/time behaviour is frozen), `is_abs_any_platform`, `resolve_prefix`, `pick_path` and `preview_output_files` - all with a caller-supplied `error_prefix` and injectable `exists` so previews never touch the filesystem. `save_audio_smart_prefix.py` and `minimax_artwork.py` keep their private helper names as thin delegating wrappers (`_resolve_prefix`, `_pick_path`, `_javaish_date_to_strftime`, `_expand_date_macros`, `_is_abs_any_platform`, `_comfy_output_dir`, `preview_output_files`), so existing callers and tests keep working. `minimax_json_output.py` no longer imports `_pick_path`/`_resolve_prefix` from the audio saver: it imports `output_paths` directly with the label `Save Production JSON`, which removes the saver-to-saver coupling and the whole audio/codec import chain from the JSON writer. `scripts/preview_output_paths.py` loads only `filename_utils`/`toolkit_logging`/`output_paths`. New `tests/test_output_paths.py` (20 tests) covers macros, the absolute/relative/UNC matrix, escape rejection, all collision modes, preview semantics, audio-vs-artwork wrapper parity and an import-isolation test (subprocess proof that planning a filename pulls in no numpy/torch/soundfile/mutagen/PIL/scipy).
  - **Retracted finding (2026-09-10, verified).** I initially reported that the per-format subdirectories collapse into one path, based on the assumption that `MiniMaxOutputPaths` emits `base_output + subdir` (ending in the separator). That assumption was wrong: `MiniMaxOutputPaths._join()` appends the cleaned **source name** as a placeholder basename, so the real prefix is `.../org-32flac/<source_name>` and `apply_filename_mode` replaces only that placeholder. Re-running the diagnostic through `MiniMaxOutputPaths.build()` itself yields **5 distinct targets, one per subdirectory** (`.../Example Album/org-32flac/Example Album - Example Song.flac`, `.../highres-44flac/...flac`, `.../highres-44mp3/...mp3`, `.../artwork/...jpg`, `.../log/...json`), with no collision between the two FLAC savers. This also matches the real output on disk (`D:\Daten2\ComfyUI\output\audio_minimax3-new\2026-08-30\Chillout Vibes\32flac\Amber Stillness.flac`). No decision is needed and nothing must change; the extraction is behaviour-preserving.
  - **Minor finding.** The `"...may not escape the ComfyUI output directory"` message in `resolve_prefix` is unreachable: the raised `ValueError` is swallowed by the surrounding `except ValueError` that maps `commonpath` failures to `"invalid relative filename_prefix"`. Behaviour preserved; documented in the new test.
- [x] **T09 / F13 — Specify portability bug fixes separately.** Add Windows slash/backslash/UNC and combined UTF-16-length cases for `apply_filename_mode`, smart prefix resolution and absolute filename cleanup. Change only failing cases with documented names and no renaming of existing artifacts. Expected: portable edge-case paths without basename drift for ordinary inputs.
  - **Done (2026-09-10).** Three concrete failures reproduced and fixed. (1) **Component length counted Python characters, not UTF-16 units** - `filename_utils` gained `utf16_length`/`truncate_to_utf16` (never splits a surrogate pair) and `safe_filename_component` now budgets `MAX_COMPONENT_LENGTH` in UTF-16 units, so astral titles (emoji) can no longer produce a 360-unit component on a 255-unit filesystem limit. (2) **Combined `album - title` could exceed the limit** even though each component was individually safe (180 + " - " + 180 = 363): `apply_filename_mode` now bounds the combined basename, shortening the title tail while keeping the album prefix readable. (3) **The absolute saver had no length cap at all**: `save_audio_absolute._clean_filename` now applies the same UTF-16 budget while preserving extension stripping, the `audio` fallback and the `_CON` reserved-name policy. Ordinary names are byte-identical to before (regression assertions included). `tests/test_windows_paths.py` gained `PortableLengthAndSeparatorTests` (12 cases): astral/mixed titles, surrogate-pair safety, ordinary-name no-drift, combined album+title budget, `title only`/`prefix as provided`/invalid-mode behaviour, absolute-saver cleanup policy, and forward/backward slash plus drive/UNC resolution parity between the audio and artwork savers.
- [x] **T10 / F14 — Introduce staged publication.** Use unique same-directory staging files and cleanup in audio/image/text writers; reserve names safely according to existing collision modes. Finish tags before publication. Document Markdown/JSON partial failure and companion collisions. Expected: failed operations do not leave misleading final audio/JSON files or overwrite another producer's output.
  - **Done (2026-09-10).** New `file_writes.py` with `staged_write` (context manager yielding a unique same-directory `.<stem>.part-<pid>-<n>.<ext>` staging path, preserving the extension so SoundFile/FFmpeg/Pillow/Mutagen still infer the format), `reserve_target` (re-checks the collision policy at publication time) and `write_text_staged`. The staging file is moved onto the final path with `os.replace` only after the whole operation succeeded; any exception removes it and leaves the final path untouched. Wired into all four artifact writers: `SaveAudioSmartPrefix` (encode *and* tags/covers now happen on the staging file, so the final path only ever receives a finished tagged file), `SaveImageSmartPrefix` (JPEG export), `SaveAudioAbsolutePath` (legacy saver) and `MiniMaxSaveProductionJSON` (JSON + Markdown). The collision policy is re-checked immediately before publication: `auto_increment` moves to the next free name when another producer took it during encoding, `error_if_exists` fails loudly, `overwrite` replaces as before. The JSON writer no longer uses predictable `target + ".tmp"` names, records `outputs.prompt_report` *before* serializing (so the on-disk file contains it), counts a standalone existing `Album - Title.md` as a collision when choosing the JSON name, and now publishes the canonical JSON **before** the Markdown - a companion can never exist without its JSON, and a failure between the two leaves a JSON without its companion (documented; no multi-file atomicity is claimed). New `tests/test_staged_writes.py` (9 tests): publish/cleanup on success, injected encoder and tagging failures leaving no final file and no leftovers, an existing artifact not being touched, a failing publish, name reservation under a race for all three collision modes, UTF-8 text staging and staging-name uniqueness. New finding fixed along the way: my first version set `outputs.prompt_report` after `json.dumps`, which the returned string hid but the written file would not have contained.
- [x] **T11 / F14 — Secure custom prompt writes.** Share user/system target preparation, resolve containment under the selected root, reject escaping symlinks/junctions and use exclusive creation for overwrite=false. Preserve `_custom/<name>.txt`, labels and UTF-8 newline output. Expected: writes have the same root protection as reads.
  - **Done (2026-09-10).** `prompt_library.py` gained `_custom_target(root, stem, kind)` and `_exclusive_write_text(target, payload, overwrite, kind)`, and both `save_custom_prompt` / `save_custom_system_prompt` now use them. Containment: the `_custom` directory is created and then *resolved*, and a target that resolves outside the selected library root is rejected - reads already had this protection via `_safe_selected_path`, writes did not. A target that is itself a symlink is refused outright. Creation is now atomic: `overwrite=False` uses `O_CREAT|O_EXCL`, so a file appearing between the existence check and the write fails the call instead of being silently replaced; `overwrite=True` stages a same-directory `.<name>.<pid>.part` file and publishes it with `os.replace`, leaving no truncated prompt behind. `_custom/<name>.txt`, the field labels, the UTF-8/newline output and the existing error text are unchanged. `tests/test_prompt_routes.py` gained `CustomPromptContainmentTests` (5 cases): `_custom` symlink escape, existing-target symlink, atomic overwrite with no staging leftovers, exclusive-creation race, and the equivalent containment check for system-prompt writes.
- [x] **T12 / F15 — Extract FFmpeg and encoding helpers.** Preserve both `_write_mp3` signatures as wrappers, move quality mapping/process creation/temp cleanup and peak preparation into shared helpers, retain `-map_metadata -1` only where currently used. Update diagnostics to use runtime fallback discovery. Expected: codec/tag parity and accurate dependency checks.
  - **Done (2026-09-10).** New stdlib-only `ffmpeg_utils.py`: `discover_ffmpeg` (PATH, then the `imageio-ffmpeg` fallback), `find_ffmpeg(not_found_message)`, `run_ffmpeg(cmd, failure_message, tail)` (hidden-window subprocess, caller-supplied error text and stderr cap), `mp3_quality_args` (the shared quality mapping), `write_mp3(...)` (FLOAT WAV interchange + guaranteed temp cleanup) and `prepare_samples(...)` (the shared peak policy, imported numpy lazily). Everything that differs between the three callers is an explicit parameter, so nothing was normalised away: `save_audio_smart_prefix` keeps its "MP3 needs FFmpeg" / "FFmpeg failed:" wording and **no** `-map_metadata -1`, `save_audio_absolute` keeps its own wording, its soundfile error and **does** strip container metadata, `audio_release_prep` keeps its message and the `[-5000:]` stderr cap. All original private names (`_find_ffmpeg`, `_write_mp3`, `_prepare`, `_prepare_samples`, `_run`) survive as thin wrappers with unchanged signatures. `scripts/toolkit_diagnostics.py::_check_ffmpeg` now reports the FFmpeg the toolkit would actually use: a machine without FFmpeg on PATH but with the bundled `imageio-ffmpeg` build is no longer reported as broken. Now-unused `shutil`/`subprocess`/`tempfile` imports were removed from the three modules. New `tests/test_ffmpeg_utils.py` (14 tests) asserts the **exact argv** of both MP3 paths (parity plus the intentional `-map_metadata -1` difference), temp-WAV cleanup on failure, discovery precedence and fallback, the peak policy matrix and both callers' error texts.
- [x] **T13 / F15 — Separate tag/cover code.** Extract `_load_cover_bytes`/`_write_standard_tags` from smart saver; cache resized bytes only within one save invocation, with correct per-file tags. Expected: same JPEG dimensions/ID3/FLAC content with fewer repeated decodes.
  - **Done (2026-09-10).** New `audio_tags.py` owns the cover decode/resize and the tag/cover writer (the ~160 lines moved verbatim; `save_audio_smart_prefix.py` shrank from 469 to 333 lines). Added `CoverCache`: one production run embedded the same cover into every batch element and every format, so the source JPEG was decoded and re-encoded once per output file; the cache is created inside `save()` and therefore lives exactly as long as that one invocation - nothing survives it, and no global state was introduced. `_write_standard_tags` gained an optional keyword-only `cover_cache=`, and the saver's `_load_cover_bytes`/`_write_standard_tags` remain as thin wrappers with unchanged signatures. The tag mapping, the FLAC picture fields, the JPEG quality/size policy and every error message are unchanged. The now-dead Pillow/Mutagen/`BytesIO` imports were removed from the saver (the guards live in `audio_tags.py`). New `tests/test_audio_tags.py` (13 tests) covers square resize to the requested side, non-square thumbnail bounding, side clamping, the missing-cover error, cache hit counting for repeated and size-varied calls, cache isolation between invocations, reuse of a supplied cache by the tag writer, and wrapper/module parity. One test is skipped in this interpreter because `mutagen` is not installed here - the FLAC/ID3 content path could therefore **not** be verified locally; the tag mapping itself is byte-for-byte the moved code.
- [x] **T14 / F16 — Extract prompt I/O and variants.** Share decoding/discovery/source-name/seed iteration between `MiniMaxPromptBatchLoader.load`, `MiniMaxPromptSourceArtworkV16.load` and rich parser expansion; preserve error prefixes, strict count versus tolerant count, sort order and per-node tuple projections. Expected: identical prompts/provenance/seeds for deterministic fixtures.
  - **Done (2026-09-10).** New `prompt_sources.py` owns what was genuinely duplicated: `clean_source_name`, `new_seed`, `read_prompt_text` (UTF-8 BOM/UTF-8/CP1252), `resolve_prompt_directory(value, error_prefix=...)`, `normalize_extensions`, `iter_prompt_files(directory, allowed, recursive, relative_sort=...)`, `iter_variants(...)` and the bundled default system/user prompt constants (moved verbatim, including the concise discovery-time fallback). **Every place where the two loader dialects differ is an explicit caller decision, not normalised away:** the node name in error messages (`error_prefix`), whether an empty `extensions` list is an error (legacy loader: yes; rich source: no), the discovery sort key (legacy sorts by path relative to the directory, rich by absolute path), and the `[Count]` policy (legacy strict - an explicit 0 produces no songs; rich tolerant - a falsy override falls back to `song_count`), both passed as `count_of`. The variant/seed loop is shared because two independent implementations would silently diverge on generated seeds; the seed rule is unchanged (`(base_seed + global_index) % (2**63 - 1)` across *all* entries, or a fresh random seed per song). All historic private names stay as thin wrappers with unchanged messages, and `minimax_prompt_source` keeps re-exporting the default prompt constants. The structured node now imports those constants and `clean_source_name` from `prompt_sources` instead of from the parser node, removing one of the two documented reverse node-to-node dependencies. New `tests/test_prompt_sources.py` (16 tests): naming parity across all four consumers, Windows-invalid replacement, seed range, all four decoding paths plus the undecodable error, per-caller error prefixes, extension parsing, discovery filtering/sorting (flat and recursive), the seed-sequence/variant-index rules, the strict-versus-tolerant count policy, random mode, a **differential loader test** proving both loaders yield identical captions/lyrics/titles/source names/seeds/run indices for one fixture, and an import-graph guard that the structured node no longer references the parser node.
- [x] **T15 / F17 — Move option cache out of node classes.** Have `prompt_library` own safe aggregation/invalidation and `prompt_routes` own handlers; keep `register_routes` and existing cache invalidation import paths as delegates. Reuse selected-file byte limits and test external edits/refresh. Expected: no service-to-node import and responsive option refresh.
  - **Done (2026-09-10).** The HTTP adapter moved out of the service: new `prompt_routes.py` holds `register_routes` and all five handlers unchanged (same URLs, payloads, status codes), and `prompt_library.register_routes()` is now a lazy compatibility delegate (no import cycle). The aggregated option cache moved the other way, into `prompt_library`: `library_options(kind, source, directory)`, `invalidate_library_options(kind="user"|"all")` and `library_option_version()`. Because it now lives in the service, the save route invalidates it with a plain call - `prompt_library` and `prompt_routes` no longer import `minimax_structured_prompt` at all, which removes the documented service-to-node dependency (regression-guarded by tests that read both modules' source). Aggregation also got the safety it was missing: it now uses the same `_iter_prompt_paths` enumeration as every other library read (extension filter, hidden-file skip, symlink containment) instead of a raw `rglob("*")`, and `collect_file_field_values` gained an optional `max_bytes` that the service sets to `MAX_PROMPT_BYTES`, so the selected-prompt byte limit now applies to aggregation too. The structured node keeps `_collect_options` and `invalidate_library_options_cache` as delegates, and the dead node-local `_library_options_cache`/`_library_options_version` state plus four now-unused imports were removed. New `tests/test_library_options.py` (11 tests): curated+library aggregation, caching and invalidation, rebuild after an external file change, unsupported/hidden/oversized/symlinked files being ignored, the no-node-import guarantees for both library and routes modules, the node delegates, and the save route bumping the library version. **Bug found by these tests:** my first `invalidate_library_options` popped the bare `kind` key while cache keys are `kind|source|directory`, so a targeted invalidation silently dropped nothing - fixed to prefix-match all entries of that kind.
- [x] **T16 / F19 — Extract pure metadata sections.** Move `_generation_metadata` implementation into a dependency-light builder, copy nested sections before mutation and factor legacy permissive JSON parsing separately. Keep output key order/omissions/defaults/unknown fields. Expected: caller metadata untouched and existing payload fixtures unchanged.
  - **Done (2026-09-10).** New `production_metadata.py` owns `parse_object` (strict), `parse_legacy_object` (tolerant, ``{"raw": ...}``), `overlay` and `build_generation_metadata` (moved verbatim, `DEFAULT_WORKFLOW_NAME` moved with it). **F19 bug fixed:** the `restoration` branch used `payload.setdefault("restoration", {})["declip"] = declip`, which mutated the caller's nested legacy dict (the top-level `dict(legacy_metadata)` is only a shallow copy); it now copies that section like every other one. The legacy tolerant policy was factored out of the seven identical `try/except` blocks in `minimax_metadata.build`, so strict and permissive parsing are now explicit, named and separately testable rather than duplicated. `minimax_json_output` keeps `_parse_object`/`_overlay`/`_generation_metadata` as delegating wrappers and `_artifact_from_save_info` locally (it describes the saver's output contract, not metadata assembly). Output shape is unchanged: same key order, same omission rules for empty sections, same zero/false handling, unknown legacy keys preserved. New `tests/test_production_metadata.py` (11 tests): strict-vs-tolerant parsing, wrapper delegation, the caller-metadata non-mutation guarantee (including nested `restoration`), independence between repeated calls, schema stamping, omission of empty sections, whitespace-stripping overlay semantics, zero/false survival and unknown-key preservation.
- [x] **T17 / F19 — Integrate migrations compatibly.** Make `_v6_to_v7` nonmutating. Define known/current/unknown/unversioned loader policies before wiring it into `MiniMaxMetadataLoader.load`; preserve raw returned JSON where required. Add content `IS_CHANGED` with deterministic error fingerprints. Expected: edited files rerun and supported old records load without newly rejecting legacy data.
  - **Done (2026-09-10).** `metadata_schema._v6_to_v7` no longer mutates its input: the nested `flashsr` section is copied before `settings` is defaulted (the top-level `dict(payload)` was only a shallow copy, so the caller's dict gained `flashsr.settings`). Added `migrate_metadata_payload_if_known()` as the explicit **loader** policy, deliberately softer than the writer's strict `migrate_metadata_payload`: current schema is a no-op, a known older schema migrates, and an **unversioned or unknown** payload is passed through unchanged with a note instead of raising - so no previously readable file is rejected. `MiniMaxMetadataLoader.load` now uses that policy and returns the payload it actually used (v6 files come back as v7), and the shared `_resolve_metadata_path` helper is used by both `load` and the new `IS_CHANGED`. `MiniMaxMetadataLoader.IS_CHANGED` hashes the file content (SHA-256), so editing a metadata file in place re-runs the node instead of serving stale cached outputs; a missing/unreadable file yields a deterministic `unreadable:<path>:<exc>` fingerprint, so the failure is cached too and graph construction never sees an exception. New `tests/test_metadata_migration.py` (15 tests): the non-mutation guarantee (including the nested `flashsr` case), v7 defaults, current-payload pass-through, strict-writer-vs-tolerant-loader policies for unversioned/unknown schemas, end-to-end loading of v6/unversioned/unknown files, and content/error fingerprint determinism.
- [x] **T18 / F20 — Check preset parity.** Cover all Python preset results against `web/preset_sync.js` values, names and custom transitions. Extract lightweight preset data/resolution only after parity is green. Expected: UI reflects backend values without changing any DSP defaults or workflow selection.
  - **Done (2026-09-10).** New `tests/test_preset_parity.py` (9 tests) reads `web/preset_sync.js` (it cannot be imported - it pulls in ComfyUI's `app.js`) with a brace-matching scanner and compares all four mirrored families against the authoritative Python: `DECLIP_PRESETS` against `audio_declip._preset`, `HF_PRESETS` against `audio_hf_repair._preset_repair`, `RELEASE_PRESETS` against `audio_release_prep._preset_values`, `LOWPASS_PRESETS` against `audio_lowpass.PRESETS` (cutoff/order/phase mapping included). It also guards the contract details F20 calls out: every JS preset must exist in the corresponding node combo, every Python low-pass preset must be mirrored in JS, and the `CUSTOM` sentinel stays uppercase for the low-pass node. The scanner has its own tests so a broken reader cannot silently make parity pass. **Result: parity is green in all four families - no drift found, so no DSP default, label or workflow selection was touched.** The optional extraction of a shared preset owner is **deliberately deferred**: the gate is met, Python is authoritative, each preset table is small and currently sits next to the DSP code that consumes it, and the plan makes extraction conditional on it simplifying callers. It is now safe to do later without behaviour risk, guarded by this test.
- [x] **T19 / F10 — Extract host cleanup unchanged.** Move `_free_comfyui_model_cache` into `comfy_resources.py` with a compatibility wrapper; keep prefetch/cast/unload/staging/allocator ordering and guarded GC fallback. Expected: existing fake dynamic-staging test and real repeated-run behavior remain valid.
  - **Done (2026-09-10).** The ~227-line cleanup moved **verbatim** into `comfy_resources.py::free_comfyui_model_cache` (only the logger name changed, from `llm` to `comfy_resources`); `llm_chat` keeps `_free_comfyui_model_cache()` as a delegating wrapper, so existing callers and tests are untouched. The module docstring now states the ordering contract explicitly so a later refactor cannot quietly reorder it: FlashSR cache -> collect dynamic models -> prefetch/CUDA-graph queues -> cast buffers -> `unload_all_models()` -> `partially_unload()` -> allocator (`empty_cache` + `soft_empty_cache(force=True)`) -> diagnostics -> guarded `ModelVBAR` force-release fallback. The three synthetic-package loaders that enumerate modules explicitly (`tests/test_integrated_nodes.py`, `tests/test_node_schema_compat.py`, `scripts/check_model_paths.py`) were updated to register the new module. New `tests/test_comfy_resources.py` (7 tests) drives a recording fake host and asserts the **call order** (prefetch before cast before unload before partially_unload before allocator), that a failing `partially_unload` is guarded and does not abort the cleanup, that non-dynamic models are never partially unloaded, that an absent `comfy.model_management` is a no-op, that missing optional capabilities are tolerated, and that the wrapper delegates to the real implementation while the GC fallback survived the move. `scripts/check_model_paths.py` still runs correctly after the loader change. **Deliberately deferred: T20.** It is the largest and highest-risk task in the plan (moving acquisition/options/chat out of an 851-line module that drives the user's live 2-GPU dynamic-VRAM setup); a half-applied version would be worse than a deferred one.
- [ ] **T20 / F10,F11 — Establish LLM ownership and session identity.** Move acquisition/options/chat into `llm_runtime`; serialize use/unload, prevalidate replacement, close old instances before new allocation under the selected policy, tag states with model/options, and test actual save/restore capabilities. Preserve node signatures/status/disabled path. Expected: no simultaneous unintended model residency or cross-model state reuse; no unreviewed conversation rewrite.
- [x] **T21 / F08 — Fix FlashSR runner construction.** Resolve concrete execution device, handle failed/partial moves, account for VAE placement, publish cache only after success, and validate required filenames early. Keep weights/config paths. Expected: CPU fallback actually uses CPU and reports it, failure leaves no cached broken runner.
  - **Done (2026-09-10).** New `_resolve_execution_device()` keeps the selection rule (CUDA when available, else CPU) but makes the identity explicit (`cuda:0` instead of the generic `cuda`), so two device indices can no longer share a cache entry. `_get_runner` is now transactional: weights are checked **before** the model is constructed, a failed `model.to(device)` logs the reason, explicitly moves the model **back to CPU** to undo a partial transfer, and records `device="cpu"` - previously it logged "continuing on CPU" while still reporting `cuda`, so the node moved every chunk to a device the model was not wholly on. The runner is only published after construction succeeded, and the VAE is deliberately left alone (`VAEWrapper` is not an `nn.Module`; `preprocess()` places it), now documented at the call site so nobody "fixes" it by changing the state-dict keys. `_ensure_flashsr_weights` also fails on missing files **regardless of `auto_download`** instead of deferring it to runner construction - its only caller is `upscale`, which needs the weights, so the earlier failure carries a better message. Weight/config paths, float32 inference and cache reuse are unchanged. New `tests/test_flashsr_runner.py` (13 tests): device resolution (CPU, index, broken torch, failing `current_device`), missing weights failing before construction, a successful runner recording the concrete device, a failed transfer falling back to CPU **and undoing the partial move**, cache reuse and per-device isolation, cache clear/rebuild, and the three weight-preparation outcomes. **Not verified locally:** the real `VAEWrapper` placement and the vendored `torch.load` map locations need actual weights; the latter is a vendor patch belonging to T27.
- [x] **T22 / F12 — Normalize model entry preparation.** Share FlashSR/default-target and group expansion among check node/runtime/diagnostics; validate shapes without changing dormant config-key precedence. Expected: each consumer resolves the same configured entries and preserves status/report contracts.
  - **Done (2026-09-10).** New `model_downloader.normalize_model_entries(config, *, minimax=, flux2=, flashsr=, llm=)` is the single owner of group expansion: group-level notes, the FlashSR default `weights.target` and the LLM `example` entry are applied once, and explicit per-entry values still win. All three consumers now call it - `MiniMaxModelAutodownload.check`, `flashsr_audio._ensure_flashsr_weights` (flashsr only) and `scripts/toolkit_diagnostics.py::_check_models` (which previously did **no** note/default-target expansion at all, so a config entry without an explicit target was reported as failed by the diagnostics but resolved correctly by the node). Added `validate_model_entry`: config validation used to cover only the top-level dict, so a malformed `files` value crashed the consumer while expanding the group (`{**42}`); non-dict/mis-typed entries are now skipped with a warning and a failed-report contract is preserved for genuinely missing names/targets. No dormant config key became authoritative. New `tests/test_model_downloads.py` (19 tests) includes **consumer-parity tests** that capture the entries each consumer passes to `check_file_entries` and assert they match the shared expansion exactly.
- [x] **T23 / F12 — Harden file downloads.** Add unique staging cleanup, nonempty/declared-length validation and hash-failure tests; preserve atomic replace and opt-out semantics. Retain/harden ZIP extraction with resolved containment if it remains public; do not re-enable code downloads. Expected: incomplete transfers cannot be reported as successfully installed models.
  - **Done (2026-09-10).** `download_file` now stages into a **unique** same-directory name (pid + counter) instead of a fixed `.<name>.part`, always removes the staging file on any failure, and validates the transfer *before* publishing: a zero-byte body and a body shorter than a declared `Content-Length` are hard failures (previously an empty or truncated response could be `os.replace`d into place and reported as a successfully installed model when no checksum was configured). The SHA-256 check and the atomic `os.replace` are unchanged, as is the "already present" short-circuit. `download_and_extract_zip` was hardened with resolved containment (each member's target must resolve inside the destination, absolute and drive-letter members are skipped), a unique staging ZIP that is always cleaned up, an empty-archive rejection and a docstring stating explicitly that it has **no runtime call site** - code downloads stay disabled. New tests cover: atomic publish, empty body, short body, checksum mismatch, network error (all four leaving no file and no `.part` leftover), the no-redownload short-circuit, staging-name uniqueness, ZIP path-escape/absolute-member rejection, empty-archive rejection and the marker short-circuit.
- [x] **T24 / F06,F07 — Extract minimal audio helpers.** Standardize BCT validation/CPU conversion ownership and identical Kaiser SRC behind existing wrappers. Preserve FlashSR CT adaptation and normal-length filter behavior. Add explicit dependency/invalid-shape tests. Expected: fewer duplicated helpers without silent batch or numerical changes.
  - **Done (2026-09-10).** New `audio_utils.py` (138 lines) with exactly two responsibilities. (1) **BCT validation** - `audio_problem()` returns the first problem code (`not_mapping`/`missing_fields`/`torch_missing`/`not_tensor`/`wrong_ndim`/`invalid_rate`) and `validate_audio(audio, error_label=..., template=..., require_positive_rate=...)` raises the caller's historic message. All six `_validate_audio` copies are now 2-line wrappers, each keeping its own label, message template (`compact` for declip/hf-repair/release-prep/smart-saver, `separate` for lowpass/absolute-saver) and - importantly - its own sample-rate policy (three modules never checked the rate, three reject a non-positive one). A missing torch now produces a real dependency message instead of the documented `AttributeError`. (2) **The identical Kaiser SRC kernel** (`KAISER_BETA = 14.769656459379492`): `resample_kaiser_polyphase()` owns the polyphase call, both `_resample_hq` wrappers delegate, and each keeps its own missing-SciPy wording and timing (`_require_scipy()` still runs first in HF repair). The same-rate shortcut still returns a float32 *view* - unchanged, and now pinned by a test. FlashSR's `[C,T]` adapter was deliberately **not** merged: a 2-D waveform stays valid there and stays rejected by the BCT validator (tested). New `tests/test_audio_utils.py` (15 tests): the problem matrix, opt-in rate checking, both message templates, per-caller labels/messages/rate policies, the float32-view shortcut, length scaling, **bit-exact parity with a direct SciPy `resample_poly` call using the same Kaiser window**, agreement of all three SRC entry points, the caller-specific missing-SciPy message, and the FlashSR adapter separation. Net effect: 70 lines removed from four modules (32 added), with the numerically dangerous duplication now single-sourced.
  - One deliberate wording unification: the low-pass saver's "expected waveform shape [B,C,T]" and the absolute saver's "expected waveform [B,C,T]" are now the same string. Both messages stay precise (they include the offending shape); the test pins the unified text.
- [x] **T25 / F09 — Stream overlap-add.** Refactor `MiniMaxFlashSRAudio.upscale` to update accumulator/weights per chunk in original order; remove retained prediction list and duplicate span enumeration. Keep `_wola_stitch` behavior testable. Expected: same fake-runner samples/length and lower peak RSS on long clips.
  - **Done (2026-09-10).** `upscale` now builds the chunk spans **once** (`_iter_chunks` was called twice - once for the count, once for the loop), allocates the overlap-add accumulator lazily on the first prediction (channel count still taken from the prediction, exactly as the stitch did) and adds each chunk **as it is produced**. The retained prediction list is gone, so peak RAM is the output-sized accumulator plus the weight sum instead of every padded chunk output *plus* the accumulator; per-chunk tensors are deleted right after accumulation. The arithmetic was factored into `_ola_accumulate`/`_finalize_ola`, and `_wola_stitch` remains as the list-based compatibility/testing wrapper - both paths share the same helper, so they cannot drift. The process-wide `stdout`/`stderr` redirection still suppresses the vendored tqdm bar, but now reuses **one** buffer pair (truncated per chunk) instead of allocating two fresh `StringIO` objects per chunk, and a failing chunk re-raises with the captured stderr tail and the chunk index, so the previously swallowed diagnostics are recoverable. New `tests/test_flashsr_streaming.py` (7 tests): bit-exact accumulator-vs-stitch parity across three hop sizes and four clip lengths (including exact chunk length and chunk+1), the empty-prediction and single-chunk cases, span construction, and an **end-to-end `upscale` test with a deterministic fake runner** that rebuilds the historical list-then-stitch result from the same input and asserts `assert_array_equal` against the streamed output - plus the unchanged settings contract and the failure-tail diagnostic. Inference rate, chunk length, overlap, padding, Hann window, first-sample behaviour, device handling and the settings JSON are untouched. **Not measured:** no real RSS/VRAM profiling was possible without weights; the memory claim is structural (no prediction list), not benchmarked.
- [x] **T26 / F07 — Eliminate unused FIR work.** In additive hybrid mode, retain only needed FlashSR lowpass convolution; reuse designed coefficients and report taps. Do not change modes requiring source lowpass. Expected: identical output/report, reduced convolution time.
  - **Done (2026-09-10).** `audio_hf_repair` now separates design from application: `_design_lowpass(sr, cutoff, transition, attenuation)` returns the shared Kaiser FIR and its tap count, `_apply_fir(x, h)` convolves one signal, and `_fir_lowpass(...)` stays as the single-signal compatibility wrapper (same maths, same clamping, same odd-tap rule). The crossover branch designs **once** per run and reuses that kernel for both signals - the two designs were provably identical, so this is pure saved work. In `"Original + FlashSR air"` mode the whole-signal `low_o = lowpass(o48)` convolution is **gone**: the output only ever used `o48` and `high_f`, so the most expensive operation in the node was computed and discarded every run. `"Hybrid replace above crossover"` still needs both convolutions and is unchanged, and `fir_taps` is still reported from the same design in every filtering mode. New `tests/test_hybrid_crossover.py` (8 tests): the design wrapper/reuse equivalence, the unchanged clamping rules, **bit-exact output parity** for both filtering modes against a locally rebuilt reference of the old algorithm, identical tap reporting across modes, and two counting tests that assert the new work profile (one design + one convolution for the additive mode, one design + two convolutions for replace mode) - plus the pass-through modes still skipping the filter entirely with `fir_taps = 0`. **Not measured:** no wall-clock benchmark; the saving is structural (one fewer whole-signal overlap-add convolution), not a profiled speedup.
- [ ] **T27 / F21 — Audit vendor runtime closure.** Trace a real import/inference session, verify package origins, list exact external requirements and record provenance/patches. Make minimal local-import/device patches only where proven. Expected: inference installs predictably without copying the research dependency manifest or breaking checkpoints.
- [x] **T28 / F22 — Correct targeted diagnostics.** Fix LLM error interpolation, integer logging-level validation, chunk-count labeling and useful fallback diagnostics; test failure logs. Make full-text verbosity a separate explicit policy change. Expected: accurate troubleshooting without a new logging framework.
  - **Done (2026-09-10).** Four targeted fixes, no new framework. (1) The LLM constructor-failure message ended in a **non-f-string** literal, so users were shown `{type(exc).__name__}: {exc}` instead of the underlying llama.cpp error - now interpolated. (2) `toolkit_logging._level_from_env` validated nothing: `getattr(logging, raw)` also matches non-level attributes, and `MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL=BASIC_FORMAT` passed a *string* to `setLevel` at import time, taking the whole package import down. It now accepts only integer level constants and in-range numeric strings, warns once about anything else and falls back to INFO. (3) The streaming completion line claimed an exact token count while counting *stream chunks*; it now reports chunks plus the token budget. (4) `unload_llm_models` swallowed close failures with a bare `pass`, hiding why a model kept its memory - it now logs a warning with the model path and the error. The full-text INFO logging of LLM output was deliberately **left alone** (the plan calls that a separate operational/privacy policy change, and metadata outputs must be preserved). New `tests/test_diagnostics.py` (10 tests): default/named/numeric/blank/unknown/out-of-range env values (including the `BASIC_FORMAT` import-survival case, verified in an isolated module import), source guards for the two message fixes, and a captured-log test proving a failing `model.close()` is reported at WARNING level while `unload_llm_models` still returns normally.
- [x] **T29 / F23 — Align release tooling.** Add archive include/exclude tests covering `dist` and local-only files, unify overlap in privacy scanning, test no-write dry-run in demo updater, document fixed-template builder preconditions and Python tooling requirements. Expected: reproducible packages and diagnostics matching runtime behavior.
  - **Done (2026-09-10).** New `scripts/release_common.py` is the single owner of archive selection and privacy rules, and both scripts use it. **Two real defects fixed:** (a) `package_release.should_include` excluded `.zip` files and `SHA256SUMS.txt` but **not** the `dist/` directory, so a rebuilt archive swallowed the previous build's standalone workflow `.json` assets - `dist` is now an excluded part; (b) the two privacy scans had *different* pattern sets, and the validator's Windows-path pattern required **doubled** backslashes, so it could never match a real single-backslash user-profile path while the packager's could. The validator's local-only-file guard was also text-based (`if '"KONTEXT.md"' not in package_release.py`), which a refactor could satisfy by accident; it is now a **behavioural** check against the shared selection. Unifying on the stricter pattern turned out to be safe: with the corrected rule the whole published tree scans clean (the only hit was the test fixture itself, now built programmatically). The demo updater no longer creates the cover directory during `--dry-run` (the `mkdir` ran before the dry-run check). `build_public_workflow.py` and `upgrade_workflow_to_v2.py` now document their fixed-template preconditions and that they must never be run on the current public workflow, and `DEVELOPMENT.md` gained a *Tooling requirements* section (tooling needs Python 3.11+ for `tomllib`, independently of the ComfyUI runtime; the packager and validator share `release_common.py`). New `tests/test_release_tooling_alignment.py` (14 tests): archive inclusion/exclusion for `dist`, VCS/caches, local-only files and nested archives; packager/validator sharing; single-backslash detection; `published_only` scope; `dist` not being scanned; the dry-run summary; and a **functional demo-sync test** that runs `main()` against a temp docs directory and asserts a dry run writes nothing while a real run updates the catalog.
- [ ] **T30 / F01–F23 — Final integration gate.** Run section 9, compare frozen contract snapshots, inspect packaged web/vendor/config assets, execute both workflows and repeat resource cycles. Record each intentional bug delta and measured optimization. Expected: a reviewable refactor whose remaining optional work is explicitly deferred.
  - **Gate status (2026-09-10) — partially complete, deliberately NOT ticked.** The automated half of section 9 passes; the real-host half cannot be executed in this environment (no ComfyUI process, no model weights, no GPU here), so ticking this task would claim verification that does not exist.
  - **Verified now (evidence):** `python -m compileall -q .` clean; `python -m unittest discover -s tests` **458 tests OK, 1 skipped** (baseline was 183 tests) - the skip is the mutagen-dependent FLAC/ID3 content test, because mutagen is not installed in this interpreter; `python scripts/validate_release.py` -> `Release validation OK`; `node --check` on all seven web/docs JS files; `node tests/test_workflow_migration.mjs` and `node tests/test_structured_prompt_frontend.mjs` both pass; `python scripts/dump_node_contracts.py --check` -> `contract snapshot is up to date` (all 28 identifiers unchanged); `python scripts/preview_output_paths.py` -> 5 collision-free paths in 5 distinct subdirectories; `python scripts/package_release.py --dry-run` -> `privacy scan: CLEAN`, 783 files; a **real archive build into a temporary directory** contains all ten new modules (`prompt_routes.py`, `audio_utils.py`, `comfy_resources.py`, `production_metadata.py`, `prompt_sources.py`, `file_writes.py`, `ffmpeg_utils.py`, `output_paths.py`, `audio_tags.py`, plus the root adapters) and none of `dist/`, `KONTEXT.md`, `PROJECT_STATE.md` or `__pycache__`; `scripts/toolkit_diagnostics.py` reports FFmpeg OK via the runtime fallback and models/probe results consistent with the pre-existing baseline.
  - **Vendor import closure recorded for T27 (new evidence):** `import FlashSR.FlashSR` succeeds **without weights** and pulls in a research-framework footprint far beyond the four declared runtime dependencies - the probe observed `PIL, librosa, matplotlib, numba/llvmlite, scikit-learn, scipy, soundfile, torchaudio, tqdm, yaml, einops, pydub, sympy, joblib, psutil, pywin32` among others, and the vendored code itself prints `There is no Hparams` / `import error: torch` during import. This confirms F21's claim; recording and narrowing it remains T27.
  - **Intentional behavioural deltas produced by this refactor (all with reproducers/tests):** migration no longer rewrites current workflows (they were silently rebuilt before); a saved `meter` value is no longer reset to `custom`; the option-only route no longer fails on an empty selection and malformed POST bodies get controlled 400s; the release gain no longer mutates upstream audio; the trim postcondition is enforced (20,000/20,000 now ends at 4499/4500); `AudioReleasePrep` never shares storage with its input; custom-prompt writes reject symlink escapes and use exclusive creation; downloads reject empty/short bodies and stage uniquely; `_v6_to_v7` no longer mutates its input; the loader accepts unversioned/unknown schemas; the FlashSR runner reports its real (possibly CPU) device and undoes partial moves; `logs` now show the LLM load error instead of a literal placeholder; a failed model close is warned about instead of swallowed; the packager no longer packs `dist/` into a new ZIP; an invalid `MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL` can no longer break the package import; a demo dry run creates nothing.
  - **Not verifiable here (must be done on the real host):** ComfyUI package discovery with the real entry point; loading/queueing **both** bundled workflows; real MiniMax/FLUX generation; FlashSR inference on real weights (VAE placement, `torch.load` map locations, cross-device determinism); FFmpeg encode/tag/cover content (blocked by the missing mutagen); model download integration; repeated LLM -> music -> FlashSR -> LLM resource cycles and any VRAM/RSS measurement. The T25/T26 improvements are structural, not benchmarked.
  - **Deferred work:** T20 (LLM runtime/session extraction - largest and riskiest, needs the real 2-GPU dynamic-VRAM host) and T27 (vendor closure narrowing/provenance). Optional items explicitly left undone: preset-owner extraction (parity gate is green), FFmpeg pipes, filter vectorization, additive reproducibility metadata, vendor pruning, and the dead `may not escape` message branch in `output_paths.resolve_prefix`.
  - **Resolved policy question:** `REFACTOR-PLAN.md` is now excluded from every release artifact. It is listed in `.comfyignore` (so it cannot reach the Comfy Registry) and in `release_common.PACKAGING_EXCLUDED_NAMES`, which the packager's archive rule and the validator both use - a real archive build confirms it is absent (782 entries; `REFACTOR-PLAN.md`, `KONTEXT.md` and `PROJECT_STATE.md` all absent, `dist/` empty of entries, the standalone workflow JSON and every new module present). It is deliberately **not** in `.gitignore`: the maintainer asked for "not in the release", so the document may still live under version control. Moving it to the full local-only class later is a two-line change (add it to `LOCAL_ONLY_NAMES` and to `.gitignore`); the validator's guard for packaging-excluded documents already checks `.comfyignore` plus the archive rule.

## 8. Things That Should NOT Be Changed

- All 28 mapping identifiers, Python node class names, root module import paths, method signatures, input/output names/types/order, serialized widget choices/defaults and list/output flags. Keep compatibility delegates when implementations move. Legacy version suffixes are identifiers, not stale branding.
- Legacy nodes absent from the main workflow: batch/source/template, song metadata/loader, FlashSR settings, absolute saver and sampler wrapper. Their absence is not evidence that users do not rely on them.
- ComfyUI core MiniMax/FLUX generation, `nodes.common_ksampler`, custom types and the embedded subgraph's IDs, virtual endpoints and boundary links.
- The existing public workflow's production choices, seeds, layout/serialization, control-after-generate behavior and graph dependencies. Do not regenerate it with a historical fixed-ID upgrade script.
- LLM default disable/fallback semantics, automatic template selection, seed/session cache-buster behavior and default GPU routing during pure extraction. Do not introduce conversation history or stricter tensor-split parsing incidentally.
- Static release gain, true-peak cap, two actual measurements, SRC-before-meter ordering, lack of compression/AGC, source archival branch and no hidden normalization in filters/crossover.
- Declip's bounded reconstruction and constant safety gain, HF shared-channel envelope/stereo handling, PRE/POST phase differences and bypass behavior.
- FlashSR inference rate/chunk/overlap/padding/window/RNG order and current first-sample boundary behavior. Do not change precision, compile models, replace schedulers, combine chunks into larger GPU batches or move CPU DSP to CUDA without a separately validated performance proposal.
- Existing model config files, targets, filenames, custom ComfyUI model/output directories, explicit absolute output paths, `_custom` prompt locations and user-edited libraries. No automatic moves or renaming of user assets.
- Folder-source CP1252 compatibility, strict versus tolerant parser dialects, repeated-heading/count semantics, Custom omission, editable system/description authority, prompt prohibition text and bundled prompt content.
- Album/Title basename conventions, format-specific tags/covers, legacy sidecars, central JSON/Markdown locations and saver passthroughs. Canonical JSON must depend on saver results and store the actual outputs.
- Production metadata v7 shape and legacy unknown fields during extraction. Do not “clean” every JSON through one strict validator. Schema expansion is a distinct later feature.
- Vendor research code, duplicate uppercase/lowercase trees, licenses and config assets solely for neatness. No upstream upgrade as part of architectural cleanup.
- Small useful helpers (`MiniMaxStandardAudioTags`, `MiniMaxSquareImageSize`, `MiniMaxLLMSessionId`, `KSamplerWithConfig`, `progress_utils`) need tests, not frameworks.
- Static gallery design, catalog identity/link preservation, release names and private-file exclusion policies. No frontend build-system migration or demo redesign is required.

## 9. Validation Strategy

### Baseline and change discipline

Before implementation, save a read-only baseline of schemas, both current workflows, selected historical fixtures, deterministic DSP outputs and representative export metadata. Record Python, NumPy/SciPy, SoundFile/libsndfile, FFmpeg, Torch/CUDA, ComfyUI/frontend, llama-cpp-python and model identities. Run baseline tests first and classify pre-existing failures; never update expected results merely to make a refactor pass.

Pure extraction commits must match baseline. Bug fixes must have a reproducer and an explicit expected delta. Numerical optimizations need both parity and measured resource benefit. Roll back at phase boundaries if a real-host result cannot be explained.

### Existing checks

During implementation, run `python scripts/validate_release.py` and `python -m unittest discover -s tests -v`. Run `node tests/test_workflow_migration.mjs` explicitly even though the validator also attempts it. Syntax-check all six `web/*.js` files and `docs/demo-tracks.js`. Use Python in-memory AST parsing or `compileall` in the implementation checkout as appropriate; the present analysis used only in-memory parsing.

Retain these test groups:

| Area | Existing tests to retain | Additional high-value coverage |
|---|---|---|
| Schemas/graphs | `test_node_schema_compat.py`, `test_workflow_schema.py`, `test_workflow_structure.py`, `test_workflow_builder.py`, `test_workflow_migration.mjs` | Full independent node snapshot, actual entry point, legacy examples, nested/object/sparse/unknown inputs, adapter meter/restore behavior. |
| Prompts | `test_prompt_library.py`, `test_structured_prompt.py`, `test_prompt_consistency.py`, `test_prompt_budget.py` | Route payloads, option-only refresh, stale responses, load-edit preservation, cache invalidation, both parser dialects, combined trim postconditions. |
| Models | `test_integrated_nodes.py`, `test_model_downloader.py`, `test_progress_utils.py` | Replacement ordering, concurrent unload, component cleanup, session identity/state API, concrete device cache, failed transfer/partial download, module-origin collision. |
| Exports/metadata | `test_filename_naming.py`, `test_windows_paths.py`, `test_production_json.py` | Actual codecs/tags/covers, staging failures/collision races, immutable nested metadata, loader file edits, companion collisions, legacy raw and unversioned records. |
| Release/demo | `test_release_tooling.py`, `test_repository_metadata.py`, `test_demo_catalog.py` | Dirty-tree archive selection, vendor assets/imports, dry-run no writes, diagnostics fallback, identical public catalog identities/URLs. |

### Imports, startup and discovery

1. In a lightweight environment, confirm missing Torch/llama.cpp/vendor optional dependencies do not remove unrelated node definitions. Execution-time errors must be actionable. A basic core dependency such as NumPy may remain required; do not promise a dependency-free package.
2. Import the actual package, not only submodules through synthetic packages. Assert all mappings/display names, no duplicate keys, `WEB_DIRECTORY`, tooltip installation twice, and route registration behavior with/without a server instance.
3. Run the documented `scripts/comfyui_smoke_test.py` against an isolated real ComfyUI base directory. It validates the graph and executes a disabled-LLM/manual-parser section; it is not a full audio/model proof.
4. Test supported Python runtime versions including 3.10 if still advertised; use a supported tooling version for tomllib-based scripts. Test Windows and Linux. Provision Node explicitly rather than depending on its incidental runner availability.

### Workflow and frontend behavior

Load both bundled workflows in the real UI, queue a short run and save/reload. Add old parser/JSON orders, pre-meter and old-system-field order, named and positional widgets, multiple instances and nested definitions. Assert link IDs/slots and virtual endpoints, not just node count.

Test disabled LLM with manual fallback, enabled LLM, legacy folder/manual source, one/multiple variants and both cache-buster modes. For frontend tests, simulate delayed/out-of-order file and metadata responses, switching roots, Custom selection, saved edits, deliberate clearing, refresh, cloning, repeated load and node removal. Verify UI report fallback when Markdown API is absent and that serialized data inputs are not displaced by buttons/headings.

### DSP and inference behavior

Use deterministic signals: silence, impulse, ramps, sine/sweep, fixed noise, clipped plateaus, short clips around pad thresholds, exact chunk length, chunk-plus-one, overlap boundaries, stereo mid/side and B>1 restoration. Cover 32/44.1/48/96 kHz where each node supports them. Include noncontiguous/float64 tensors and CPU float32 aliasing; define expected invalid-input errors for empty/rate/nonfinite cases before broadening validation.

- Assert sample rate, shape, duration, dtype, bypass identity and unchanged inputs. Check all report schemas and numerical values.
- For extraction, demand bitwise equality where operation order is unchanged. Where a different library call changes rounding, establish a justified tolerance from the baseline and spectral/peak checks; do not invent a single universal tolerance.
- FlashSR: use a deterministic fake runner to prove exact stitching parity, including first/last samples, then real weights on a pinned stack with fixed RNG state. Document backend nondeterminism; do not promise cross-device bitwise identity.
- Declip: candidate/repair/skipped counts, edge exclusion and global safety gain. Lowpass: phase/padding/peak behavior. Hybrid/HF: preservation of low bands, channel alignment and shared envelope. Release: measured loudness/true peak at final rate and constant gain/no pumping.
- Use `recommended_test_matrix.json` as a listening/filter matrix, not as the authoritative defaults for every current workflow. Include a representative musical transient/vocal/stereo listening comparison for numerical changes.

### Exports and filesystem behavior

In temporary directories owned by the tests, cover all codec/bit-depth/quality choices, 1/multiple items, each collision mode, existing companion files, long Unicode names, date macros, Windows drive/UNC paths and missing directories. Inspect decoded samples for lossless formats; MP3 is lossy and version-dependent, so compare decoded duration/rate/channel count, codec arguments, expected quality and tags rather than insisting on byte identity across FFmpeg versions.

Read back Mutagen tags and cover dimensions, verify all returned paths/save-info objects and central JSON references. Fault-inject encoder, tag, replace, disk and Markdown/JSON failures. Assert cleanup and selected collision semantics. Test `_custom` symlinks/junctions and overwrite=false races. Preview and dry-run tools must create nothing.

### Resource and performance checks

Exercise cold load, same-key reuse, different model/options, constructor failure, CPU fallback, explicit unload, failed close and cancellation. Test classic ComfyUI management plus a dynamic-VRAM build with the private APIs both present and absent. Verify VAE placement explicitly. Repeat the full LLM -> music/FLUX -> FlashSR -> unload cycle enough to identify retention trends, with synchronization before measuring GPU memory. Measure driver free VRAM as well as Torch allocator figures because llama.cpp/aimdo allocations are not fully visible to Torch.

Record peak RSS, load/inference/export duration, VRAM allocation and temporary disk usage on a short fixture and representative multi-minute audio. Compare streaming OLA and FIR changes separately. Do not assert `empty_cache()` proves release or add aggressive collection after every node. Any retained backend pool must be distinguished from a live model leak.

### Packaging and completion criteria

Build release artifacts only during implementation validation, using isolated output directories. Verify GitHub ZIP and Registry manifests independently: root adapters, every needed new module, vendor inference/config/license data, prompts, web JS/help and example workflows must be present. Generated archives, private context and machine outputs must be absent. Check installation without replacing ComfyUI's Torch and verify the resolved NumPy policy.

Completion requires: frozen public contracts unchanged; existing and new relevant tests passing; both workflows loading/queueing; real model/resource checks recorded where affected; no unexplained audio delta; no changed user file locations; documented bug fixes and optional deferrals. Full resource or codec verification cannot be replaced with “unit tests passed.”

### Second-pass and plan review record

The second repository pass checked frontend adapters against their Python services, runtime versus schema tests, metadata migration consumers, package/diagnostic policy, both workflow inventories, and uppercase/lowercase vendor imports. It added F02–F04's lifecycle/migration discrepancies, F18's concrete trim postcondition failure, F19's shallow-copy issue, and tooling/vendor boundaries that an isolated node review would miss.

Implementation order was reviewed so fixtures precede fixes, output helpers precede writer consolidation, resource ownership precedes inference optimization, and packaging follows new module selection. Intentional parser/resampler/naming differences are retained explicitly. New module proposals are optional extraction destinations rather than a required framework. No implementation was performed by this analysis.

## 10. Final Prioritized Checklist

### P0 – essential

- [ ] Freeze all 28 node contracts and historical/current workflow fixtures before moving code.
- [ ] Fix graph-load prompt overwrites, stale responses, named meter reset and sparse slot migration; preserve unknown fields/boundaries.
- [ ] Prevent same-rate release gain from mutating input audio; enforce combined prompt trim budget.
- [ ] Correct FlashSR device fallback and prove model/VAE placement before caching.
- [ ] Keep source paths, serialization, DSP defaults and legacy adapters intact; separate every bug fix from mechanical extraction.

### P1 – strongly recommended

- [ ] Consolidate path/FFmpeg/publication helpers, protect custom write containment and verify codecs/tags/collisions.
- [ ] Repair option-only refresh; move library/cache ownership out of node modules and preserve edited-file invalidation.
- [ ] Extract LLM host cleanup/runtime boundaries, avoid overlapping replacement loads, and validate session identity/lifecycle.
- [ ] Normalize model entries, prevent invalid download publication and verify active vendor dependencies.
- [ ] Make metadata assembly/migration nonmutating and integrate loader evolution without rejecting legacy records.
- [ ] Add actual package startup, frontend adapter, DSP and real resource-cycle validation.

### P2 – useful improvements

- [ ] Share compatible prompt I/O/variant helpers, AUDIO conversion and Kaiser SRC while keeping policy differences.
- [ ] Stream FlashSR overlap-add, skip unused FIR convolution and reuse covers after parity/profile evidence.
- [ ] Check Python/JS preset parity and consolidate only current preset definitions.
- [ ] Correct diagnostic/logging inconsistencies and align archive, dependency, dry-run and tooling-version policies.
- [ ] Consolidate test bootstrap and shared graph interpretation; retain explicit registries and simple wrappers.

### P3 – optional cleanup

- [ ] Prune vendor/research or unused internal code only after import/config/checkpoint reachability proof; preserve public helpers and notices.
- [ ] Consider additive reproducibility metadata for sampler/scheduler/model/backend options with an explicit schema change and appended optional inputs.
- [ ] Consider multilingual tokenizer calibration, bounded session eviction, FFmpeg pipes, filter vectorization or further caching only as separately justified changes.
- [ ] Remove confirmed unused variables/imports and update stale comments after substantive behavior is secured; avoid formatting-only churn.
