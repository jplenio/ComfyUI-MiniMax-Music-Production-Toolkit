# Improvement-TODO für DeepSeek

Stand: 10. September 2026. Grundlage: aktueller Repository-Stand nach dem vom Benutzer erfolgreich getesteten Refactoring. Dieses Dokument ist ein Implementierungsauftrag; die Erstellung des Dokuments verändert keine bestehende Implementierung.

## 1. Produktziel und verbindliche Leitplanken

Die Sammlung ist ein Produkt für unterschiedliche Rechner. Keine Optimierung darf von einer bestimmten GPU, zwei GPUs, 64 GB RAM oder einem persönlichen Modellverzeichnis ausgehen. Ressourcen automatisch erkennen, Entscheidungen erklären und manuelle Einstellungen respektieren. CPU-only, wenig VRAM, wenig RAM, eine GPU und mehrere GPUs sind eigenständige Betriebsszenarien.

Prioritäten: **P0** notwendige Grundlagen/Korrektheit, **P1** wesentliche Produktfunktionen, **P2** weiterführende Verbesserungen, **P3** optionale Experimente. Aufwand: S = kleiner isolierter Eingriff, M = mehrere zusammenhängende Änderungen, L = eigenes Teilprojekt. Das sind keine Zeitversprechen.

Arbeitsregeln für DeepSeek:

- Bestehende Node-IDs, Python-Klassennamen, Rückgabereihenfolgen, Socket-Typen, Widget-Namen und gespeicherte Werte erhalten. Neue Funktionen bevorzugt in zusätzlichen Nodes oder explizit aktivierten Profilen anbieten.
- Alte Workflows dürfen beim Öffnen weder andere Modelle noch andere Audioalgorithmen oder Prompttexte erhalten. Neue Defaults gelten nur für neue, ausdrücklich ausgewählte Profile/Beispielworkflows.
- Auch optionale Widgets können positionsbasierte `widgets_values` verschieben. Änderungen mit `scripts/workflow_schema.py`, `web/workflow_migration.js`, `web/migration_utils.js` und den Vertragstests prüfen.
- Optimierungen in drei Kategorien trennen: verhaltensgleiche Beschleunigung, bewusst anderer Qualitätsmodus und Bugfix. Float16, geänderte Filter, reduzierte Schritte und neue Prompts sind keine automatisch verhaltensgleichen Optimierungen.
- Keine automatischen Paket-Upgrades, Modellwechsel, Löschungen anderer Modellbestände oder Änderungen an ComfyUI-Startparametern. Empfehlungen anzeigen und gewählte Einstellungen persistent speichern.
- Bestehende Helfer weiterverwenden. Kein neues Plugin-Framework, keine generische DSP-Graphengine, kein obligatorischer Modellserver und kein verpflichtendes CUDA-Paket für CPU-Audiobearbeitung.
- Ein Haken bedeutet: implementiert, relevante Tests bestanden, dokumentiert. Ein Benchmarkexperiment darf auch mit dokumentiertem negativem Ergebnis abgeschlossen werden; es muss dann nicht zum Produktfeature werden.

## 2. Ausgangslage und belegte Ansatzpunkte

### Architektur und bereits erledigte Arbeit

`__init__.py` registriert die Nodes; `llm_chat.py` erzeugt Caption, Lyrics, Titel und Bildprompt. `prompt_sources.py`, `prompt_library.py`, `prompt_metadata.py`, `prompt_routes.py` und `minimax_structured_prompt.py` verwalten Vorlagen und die strukturierte Eingabe. Die eigentliche MiniMax-Musikgenerierung und FLUX-Ausführung erfolgen über ComfyUI-Komponenten; diese Sammlung liefert Konfiguration, Workflow-Verbindungen und Nachbearbeitung.

Audiopfad: `audio_declip.py` → `audio_lowpass.py` → `flashsr_audio.py` samt `flashsr_inference/` → `audio_hf_repair.py` → `audio_release_prep.py` → Audio-Saver. `production_metadata.py`, `metadata_schema.py` und `minimax_json_output.py` sichern die Produktionsdaten. `model_downloader.py` wird vom Check-Node, FlashSR, LLM und Diagnoseskripten verwendet.

Das Refactoring hat bereits Streaming-WOLA bei FlashSR, gemeinsame SRC-/Audio-Validierung, gemeinsame FFmpeg-Helfer, gestufte Dateischreibvorgänge, Cover-Caching je Save-Aufruf, Metadatenmigration und Schutz vor veralteten Frontend-Antworten eingeführt. Auch die unnötige Original-FIR-Berechnung im additiven Hybridmodus wurde entfernt. Diese Aufgaben **nicht erneut implementieren**.

### Befundübersicht

| Bereich | Konkreter Befund | Konsequenz / Aufgabe |
|---|---|---|
| LLM-Laden | `_get_model()` erzeugt das neue Modell vor `other_model.close()` | Modellwechsel erzeugt vermeidbare Spitzenauslastung; R02 |
| LLM-Sitzungen | `_sessions` nur nach Sitzungs-ID; `save_state()` ohne Größenlimit; keine gemeinsame Ausführungssperre | Speicherwachstum und inkompatible Zustandswiederverwendung; R02 |
| Ressourcen | `comfy_resources.free_comfyui_model_cache()` räumt global auf, auch bei möglicher GPU-Trennung | Sichere Standardstrategie behalten; gezielte Residency nur nach Nachweis; R03 |
| GPU-Auswahl | `_pick_llm_main_gpu()` interpretiert Standardwert 0 als Auto und berücksichtigt eine grobe Dateigrößenheuristik | Auto/CPU/explizite GPU müssen unterscheidbar werden; R01/R03 |
| Reasoning | `thinking=off` setzt nur bei API-Unterstützung `reasoning_budget=0`; sonst wird Denken nachträglich abgetrennt | Abschalten der Anzeige spart nicht zwingend Tokens; L02 |
| LLM-Budget | Standard `n_ctx=32768`, `max_tokens=16384`; keine Einstellungen für `n_ubatch`, Flash Attention oder KV-Typen | Neue bedarfsgerechte Profile statt pauschal großer Reservierung; L01/L02 |
| Modellliste | `list_llm_models()` bietet jede `*.gguf` an | Auch Projektoren wie `mmproj-F16.gguf` erscheinen als Chatmodell; D01 |
| Systemprompts | 11 Dateien mit jeweils ca. 25.275–25.813 Zeichen; selbst „concise“ ca. 25.684 Zeichen | Kürzere echte Varianten evaluieren; P01 |
| Tokenlimit | `prompt_budget.py` benutzt 3,5 Zeichen/Token als vermeintlich sichere Schranke | Für die mehrsprachige Bibliothek keine garantierte Schranke; P02 |
| Downloads | atomarer Abschluss und Längenprüfung vorhanden, aber keine Wiederaufnahme/Retry-Strategie; Standarddateien ohne SHA | D02/D03 |
| Modellmanifest | MiniMax-, FLUX- und LLM-URLs leer; Normalisierung der LLM-Gruppe nutzt `example` statt alle ausgewählten Einträge | Funktionsfähiger Produktkatalog und Auswahlbezug fehlen; D01 |
| Workflow-Preflight | Check-Node 101 im Hauptbeispiel hat eine ausgehende Verbindung zur Node 53; keine allgemeine Barriere vor allen Modellladern | Verbindung allein beweist keine frühe Ausführung; D04 |
| FlashSR | BCT-Eingabe wird in `_to_channel_samples()` auf Batch 0 reduziert | Batch-Korrektheit ausdrücklich als Bugfix behandeln; A01 |
| FlashSR-VAE | `AutoencoderKL` baut einen eigenen Vocoder; Produktionspfad verwendet `FlashSR.sr_vocoder` | Separaten ungenutzten Vocoder im Inferenzpfad prüfen; A02 |
| Audio-RAM | `_finalize_ola`, HF-Reparatur und Declip erzeugen weitere ganze Arrays | Besitzverhältnisse beachten und temporäre Puffer begrenzen; A03 |
| Hybrid | Beide AUDIO-Eingaben werden immer angefordert, validiert und konvertiert | „Original SRC only“ verhindert vorgelagerte FlashSR-Ausführung nicht; A04 |
| Mastering | `AudioReleasePrep` ist ausdrücklich statischer Gain, kein Kompressor | Neuen Mastering-Node bauen, vorhandene Semantik erhalten; M01–M03 |
| Dateiverkehr | `_measure_bs1770()` schreibt für jede Messung FLOAT-WAV; MP3 ebenfalls über WAV | Transport per begrenzter Pipe prüfen; A05 |
| Bibliothek | `/prompt_metadata` aggregiert Dateien synchron im async Handler | Große Bibliotheken können UI-Anfragen bremsen; U02 |

Die Befunde sind statisch belegt. Es wurden keine Laufzeit- oder Klanggewinne gemessen. Alle Geschwindigkeitsangaben im folgenden Arbeitsauftrag sind Prüfziele, keine behaupteten Ergebnisse.

## 3. Implementierungsreihenfolge

| Phase | Ziel und Aufgaben | Freigabekriterium |
|---|---|---|
| 1 | B01, R01, R02, P02: Baseline, Ressourcenprofil, sichere Modellzustände, Tokenkorrektheit | Alte Workflows und Tests unverändert funktionsfähig |
| 2 | D01–D04, L01–L03: Modellkatalog, Downloads, LLM-Profile, reproduzierbare Auswahl | Frische Installation und Offline-Neustart getestet |
| 3 | R03, A01–A05: Audio-/Speicheroptimierungen und echte Bypass-Pfade | Gemessener Nutzen ohne unbeabsichtigte Klangänderung |
| 4 | E01–E03: parametrischer EQ und gemeinsame Analysebasis | DSP-Tests und bedienbarer EQ vollständig |
| 5 | E04, M01–M03: Auto-EQ, Kompression, True Peak, LUFS | Referenzsignale und Hörtests bestanden |
| 6 | P01, U01–U03, Q01: Prompts, Produktoberfläche, Enhancement-Profile | Neue Profile verständlich und ausdrücklich wählbar |
| 7 | V01: Metadaten, Dokumentation, Produkt-/Releaseabnahme | Getestete Pakete einschließlich neuer Ressourcen |

UI-Grundlagen können nach Phase 1 begonnen werden; Auto-EQ benötigt E01/E02, Mastering benötigt E02. P01 kann parallel zur LLM-Evaluation stattfinden. Risikoreiche Residency-/Precision-Experimente dürfen die Lieferung von EQ und Mastering nicht blockieren.

## 4. Messung und ressourcenadaptive Ausführung

### B01 — Reproduzierbare Leistungs- und Qualitätsbaseline

- [x] **P0 · M · Risiko niedrig.** `scripts/toolkit_diagnostics.py` erweitern; neues `scripts/benchmark_toolkit.py`, Fixtures unter `tests/fixtures/` und Regressionstests ergänzen.

  **Done (2026-09-11) — English summary.** Reproducible baseline harness; no
  measurement claim is made for hardware this machine does not have.

  * New `scripts/benchmark_toolkit.py` measures the audio chain on deterministic
    synthetic audio (broadband tone plus transients, 32 hard-clipped peaks and a
    quiet tail, so declip/low-pass/HF stages do real work instead of timing an
    early return). Same fixture parameters ⇒ byte-identical input ⇒ a before/after
    comparison means something.
  * Five stages run without model weights: `declip`, `lowpass`, `hf_repair`,
    `hybrid_crossover`, `release_prep`. Every widget value is taken from the
    node's own `INPUT_TYPES()` defaults; the fixture audio is injected into the
    declared audio inputs. A required input the harness cannot fill raises
    instead of guessing a value.
  * `--list` prints the measurable stages **and** the declared-but-unmeasurable
    ones with the reason (`flashsr` needs the checkpoints, `minimax_generation`
    needs the diffusion model, `flux_artwork`, `llm_chat`, `downloads`). A run
    reports them under `not_measured` — never silently omitted, never guessed.
  * Timing: warm-ups excluded, CUDA synchronisation at measurement boundaries
    only (never inside a stage), median/min/max/stdev per stage and workload, a
    single sample reporting no spread rather than a fake `0.0`.
  * Memory: process RSS and peak RSS (Windows `psapi` with the handle typed as
    a void pointer — the default `c_int` restype truncated it on 64-bit and
    silently failed; POSIX uses `resource.getrusage`). The report states why
    torch's allocated/reserved counters are not used as total memory. Unknown
    values stay `None`.
  * Visible-unmeasured honesty: `hardware_status` is `untested`, the VRAM/RAM
    classes from the matrix are listed separately, and the environment block
    records Python, platform, torch/CUDA version, devices and the R01 resource
    snapshot + recommendation.
  * `tests/fixtures/benchmark_matrix.json` (axes 10 s/1 min/5 min, mono/stereo,
    44.1/48/96 kHz, batch 1/2 → 36 workloads; VRAM classes 4/6-8/10-12/16/24/32+,
    RAM 8/16/32/64 GiB; honesty rules) and `tests/fixtures/benchmark_briefs.json`
    (20 fixed LLM briefs with seeds across instrumental, English/German vocal,
    sparse vocal, non-Latin ja/zh/ko/ur/ru and custom-lyrics cases).
  * Telemetry contains no prompt text and no audio content — pinned by a test
    that serialises the whole report and asserts no brief caption/lyrics appears.
  * `scripts/toolkit_diagnostics.py` also reports the R01 resource snapshot
    (CPU/RAM/devices/backend versions/recommendation).
  * Documented in `../DEVELOPMENT.md` under "Performance and quality baseline".

  **Verified on the dev machine (recorded as a local smoke result, not as a
  hardware claim):** all five stages run; e.g. 10 s stereo 48 kHz — declip
  16.5 ms, lowpass 19.6 ms (±0.5), hf_repair 93 ms, hybrid_crossover 29 ms,
  release_prep 26 ms, process RSS ~250 MB. FlashSR/MiniMax/FLUX/LLM remain
  unmeasured here and the matrix hardware classes remain `untested`.

  **Tests:** `tests/test_benchmark_toolkit.py` (24 tests) pins the matrix axes,
  the default-profile and full expansion, the summary statistics, warm-up
  exclusion, the `None`-not-zero rule, input-default derivation, the
  unfillable-input error, a real stage run, the `not_measured` list, the
  no-prompt-content guarantee and `--list`. Suite: **534 tests, OK**.

**Technisch:** Vorher/nachher je Stufe Wandzeit, Kaltstart/Warmstart, Prozess-RSS/Peak-RSS, verfügbaren System-RAM und VRAM je sichtbarer GPU erfassen. PyTorch allocated/reserved allein misst llama.cpp und aimdo nicht vollständig. CUDA-Synchronisation nur an Benchmarkgrenzen, nicht im normalen Hotpath. Backendversion, Treiber, effektives Device, Präzision, Modellidentität, Kontext, Chunkgröße und Samplerwerte protokollieren. Keine vollständigen privaten Prompts oder Audioinhalte in Standard-Telemetrie.

CPU-only sowie VRAM-Klassen bis 4, 6–8, 10–12, 16, 24 und mindestens 32 GiB prüfen; RAM 8/16/32/64 GiB; zusätzlich ungleiche Multi-GPU-Systeme. Gemockte Erkennung testet Entscheidungen, ersetzt aber keine echten Messungen. Nicht vorhandene Hardware ehrlich als ungetestet markieren.

Audio: 10 Sekunden, 1 Minute, 5 Minuten; Mono/Stereo; 44,1/48/96 kHz; Batch 1/2. LLM: mindestens 20 feste Briefs aus instrumentalen, deutschen/englischen Gesangs-, spärlichen Gesangs-, nichtlateinischen und benutzerdefinierten Lyrics-Fällen. Drei Wiederholungen mit festgehaltenen Seeds, Kalt-/Warmzeiten getrennt, Median und Streuung berichten. Mehrfachdurchläufe und Modellwechsel gehören ausdrücklich dazu.

**Abnahme:** Verbesserungen mit identischem Workload vergleichen. Qualitätsprofile nach Parser-Erfolg, Vorgabentreue, Lautheitsabgleich und Hörbewertung vergleichen, nicht ausschließlich Tokens/s oder Peak-VRAM.

### R01 — Ressourcenprofil und transparente Empfehlungen

- [ ] **P0 · M · Risiko mittel.** Neues `resource_profiles.py`; Integration in `llm_chat.py`, `flashsr_audio.py`, Diagnostik und neue Profil-UI.

  **Partial (2026-09-11) — module and diagnostics done, node wiring open; do not tick yet.**

  * New `resource_profiles.py`: `detect_resources()` returns a plain
    `ResourceSnapshot` (CPU cores, RAM total/available, devices with stable id,
    name, backend, logical **and** physical index, free/total VRAM, backend
    versions, capture timestamp, notes). Everything undetectable is `None`,
    never `0`; probe failures become notes, not exceptions; the module imports
    no `torch` at import time, so CPU-only installs work and no `nvidia-smi` is
    required.
  * `device_budget()` = free VRAM minus the larger of 1 GiB and 10 % of the
    device total; unknown free VRAM yields `None` (not 0, not unlimited).
  * `recommend_profiles()` returns advisory entries
    (`id`, `label`, `device`, `budget_bytes`, `confidence`, `reason`,
    `workload`, `notes`). It reports CPU-only, largely-occupied and
    unknown-VRAM devices, states that several GPUs are **separate** pools
    (budgets are per device, never summed), reports `CUDA_VISIBLE_DEVICES`
    renumbering, and on low free RAM explicitly warns against simply raising
    CPU offload. A GGUF file size is documented as a lower bound only.
  * `format_resource_report()` renders the snapshot for CLI/UI; wired into
    `scripts/toolkit_diagnostics.py` (`run_diagnostics()["resources"]`,
    `format_report()`), verified by a real run on the dev box (6 cores,
    63.9 GiB RAM, torch 2.8.0+cpu, CPU-only recommendation) and by
    diagnostics integration tests.
  * **Still open:** the `Auto` / `CPU` / explicit-device selection in
    `llm_chat.py` (legacy `main_gpu=0` must stay interpreted as before),
    `_pick_llm_main_gpu()`'s file-size heuristic, the `flashsr_audio.py`
    device wiring, and the profile UI. Those change live GPU behaviour on the
    user's machine and were deliberately not touched without the real host for
    verification.

  **Tests:** `tests/test_resource_profiles.py` (23 tests) covers the required
  table: unknown values staying unknown, CPU-only, low available RAM, occupied
  GPU, zero headroom, unequal GPUs, renumbered/invisible devices, per-device
  budgets, advisory-only recommendations and the no-top-level-torch guard.
  Suite: **510 tests, OK**; `validate_release` OK.

`detect_resources()` liefert ein schlichtes Datenobjekt: CPU-Kerne, verfügbarer/gesamter RAM, sichtbare Devices mit stabilem Bezeichner, Backend-Unterstützung, freiem/gesamtem VRAM und Zeitpunkt. Fehlende Werte sind `null`, nicht 0. NVIDIA-Erkennung optional; CPU funktioniert ohne `nvidia-smi`. Andere Backends nur anbieten, wenn die installierte Laufzeit sie tatsächlich unterstützt.

`recommend_profiles(resources, catalog, workload)` gibt geeignete Profile mit Begründung und Unsicherheit zurück. Budget aus **aktuell freiem** VRAM minus Reserve berechnen, zusätzlich RAM-Spitzen für Ladezustand, CPU-Offload und Audio berücksichtigen. Konservativer Startwert für die GPU-Reserve: max. 1 GiB und 10 % Gesamtspeicher; aufgrund realer Arbeitslast erhöhen. Dateigröße ist nur eine Untergrenzen-Näherung, kein hinreichender Fit-Test. Kontext/KV-/Recurrent-State, Compute-Puffer und Backend-Overhead gesondert berücksichtigen.

Neue Auswahl `Auto`, `CPU`, explizites Device; Legacy-`main_gpu=0` unverändert interpretieren. Physische GPU-IDs und durch `CUDA_VISIBLE_DEVICES` umnummerierte logische IDs anzeigen. Mehrere GPUs sind kein zusammenhängender Speicherpool. Bei RAM-Mangel nicht einfach mehr CPU-Offload empfehlen. Kein OOM-Probeladen während `INPUT_TYPES()` oder einer UI-Liste.

**Abnahme:** Tabellengetriebene Tests für unbekannte Werte, CPU-only, wenig verfügbaren RAM, belegte GPU, ungleich große GPUs und unsichtbare Zweitkarte; jede Empfehlung kann manuell überschrieben werden.

### R02 — Modellwechsel, Sitzungen und Abbruch korrekt verwalten

- [x] **P0 · M · Risiko hoch.** `llm_chat.py`: `_get_model`, `MiniMaxLLMChat.chat`, `_sessions`, `unload_llm_models`; `tests/test_integrated_nodes.py` und neue Lifecycle-Tests.

  **Done (2026-09-11) — English summary.** Model switches, sessions and
  cancellation are now managed explicitly. No node interface changed (the
  contract snapshot is untouched), so no workflow migration is needed.

  * **Switch order fixed.** `_get_model()` closes the no-longer-active model
    (`_close_model`) *before* constructing the new one, so two managed models
    are never resident at the same time. Previously the new model was
    instantiated first and the old one closed afterwards — the exact
    peak-memory pattern R02 names.
  * **No stale cache after a failure.** Because the old model is released
    first, a failed load cannot leave a "rollback" resident or a cache entry
    that looks valid. Pinned by a test asserting the previous model is closed
    and `_loaded_models == {}` after `RuntimeError`.
  * **Cache key carries the file signature** (name + size + mtime), so
    replacing a GGUF on disk invalidates the cached instance instead of
    silently reusing the old one.
  * **One runtime lock, documented order.** `_MODEL_LOCK` (RLock) serialises
    load, state restore, generation, state save, close and unload;
    `_SESSIONS_LOCK` guards only the snapshot mapping and is never held during
    load/generation, so the order `_MODEL_LOCK -> _SESSIONS_LOCK` cannot
    deadlock. A turn holds the model lock across restore+generate+save, so
    ``close()`` during native inference is impossible. Unload takes the same
    lock.
  * **Session identity and bounds.** Snapshot keys now include the model
    signature, `n_ctx` and the chat template (`_session_key`), not just the
    session id, so a snapshot is never restored into a different model or
    context. Storage is an LRU bounded by entry count
    (`SESSION_SNAPSHOT_MAX_ENTRIES = 4`) and total bytes; an oversized snapshot
    is dropped with a log line instead of growing RAM with every session id.
    The node default (`reset_session=True`) still stores nothing.
  * **Restore API not assumed.** `_restore_state()` prefers the documented
    `load_state` and falls back to `set_state`, warning clearly when neither
    exists; `_save_state()` degrades when the build has no `save_state`. The
    meaning of a snapshot (KV state, not chat history) is unchanged.
  * **Streaming closed on every path.** `_run_chat_streamed()` wraps the chunk
    loop in `try/finally` and releases the native generator via `_close_stream`
    on completion, error and cancellation.
  * **Cancellation works between chunks.** ComfyUI's interrupt flag is checked
    per chunk (`_processing_interrupted`) and raises the host's own
    `InterruptProcessingException` where importable, instead of running to
    `max_tokens`.
  * **Failure messages no longer blame VRAM.** The load error names the
    settings, several plausible causes (memory, damaged GGUF, unsupported
    build) and the real exception, and says the previous model was already
    released.

  **Tests:** new `tests/test_llm_lifecycle.py` (17 tests) with a fake
  `llama_cpp`: close-before-construct ordering, signature invalidation, cache
  hit, failed load, unload via the node and via the API, lock blocking unload,
  session-key identity, LRU/oversize bounds, `load_state` vs `set_state` vs
  neither, stream closed on completion/cancel/error, and two concurrent turns
  that never overlap in the native model. One pre-existing diagnostics guard
  was made precise (it greps for placeholder braces; a correct f-string
  contains the same characters, so it now parses the module and only reports
  placeholders outside an f-string). Suite: **551 tests, OK**.

  **Not verified here:** the real llama-cpp-python build (0.3.48 on the
  ComfyUI venv) — whether `save_state`/`load_state` exist, what a snapshot
  costs in bytes, and the actual VRAM peak of a real A→B switch. Structurally
  fixed and unit-tested; the live confirmation needs the user's machine.

Modellzugriff einschließlich Laden, State-Restore, Generierung, State-Save und Schließen unter einer konsistenten Laufzeitsperre verwalten. Bei Modellwechsel zuerst altes, nicht aktiv verwendetes Modell schließen, Cacheeintrag entfernen, dann neues Modell laden. Ladefehler hinterlassen keinen scheinbar gültigen Cache; vorheriges Modell nicht gleichzeitig als „Rollback“ im VRAM behalten.

Sitzungsschlüssel enthält Modellpfad/Revision, Dateisignatur, Kontext und Template-/Runtime-Konfiguration zusätzlich zur Sitzungs-ID. Vor Benutzung prüfen, ob installierte API `load_state` oder einen anderen dokumentierten Restore-Aufruf verlangt; `set_state` nicht als universell gültig behandeln. Snapshot-Speicher als nach Bytes und Anzahl begrenzte LRU führen; Standardprofil ohne Session-Snapshots. Bereits geschriebene Historie und KV-Snapshot sind verschiedene Dinge: bestehende Semantik nicht stillschweigend in Multi-Turn-Chat umwandeln. Unload kann zugehörige Snapshots explizit freigeben.

Streaming-Iterator in `finally` schließen; ComfyUI-Abbruch zwischen Chunks prüfen. Kein `close()` aus einer zweiten Anfrage während laufender nativer Inferenz. Zustandslock und Modelllock mit dokumentierter Reihenfolge, keine Deadlocks bei Unload. Fehlerursachen nicht pauschal als VRAM-Fehler deklarieren.

**Abnahme:** Wechsel A→B hat maximal ein resident verwaltetes LLM; gleichzeitige Anfragen, Abbruch, Ladefehler und State-Mismatch getestet. RAM wächst nicht unbegrenzt mit Sitzungs-IDs.

### R03 — Speicherpolitik statt pauschalem Alles-Entladen

- [ ] **P2 · L · Risiko hoch.** `comfy_resources.py`, `llm_chat.py`, `flashsr_audio.py`; vorhandene `test_comfy_resources.py` erweitern.

Drei wählbare Strategien: `memory_safe` (bestehende vollständige Bereinigung), `balanced` (begrenzte Wiederverwendung nur bei nachgewiesenem Budget) und `keep_resident` (explizit, mit Vorprüfung). `memory_safe` bleibt Kompatibilitätsstandard. Der dokumentierte aimdo/VBAR-/CUDA-Graph-Fix ist keine überflüssige Bereinigung; seine Reihenfolge nicht aufgrund theoretischer Vorteile entfernen.

Für gezielte Freigabe zunächst feststellen, ob der konkrete ComfyUI-Build Gerätebesitz und Freigabe sicher unterstützt. Nur eindeutig getrennte Devices dürfen unabhängige Residency erhalten. Sonst auf bestehende Bereinigung zurückfallen. FlashSR-Cache erhält Maximalzahl/Bytebudget und Referenzschutz; Schlüssel enthält effektives Device und Qualitätsmodus. Keine periodischen `empty_cache()`-Aufrufe pro Audioblock.

**Abnahme:** mindestens zehn vollständige Wiederholungen samt LLM→MiniMax→FlashSR→LLM; keine Hänger oder steigende Fremdallokation. Gewinn als reduzierte Ladezeit dokumentieren. Bei fehlendem Nachweis bleibt nur der sichere Modus aktiv.

## 5. LLM-Auswahl als Produktfunktion

### L01 — Modellfamilien und Hardwareprofile

- [x] **P1 · M · Risiko mittel.** Neues `llm_profiles.py` beziehungsweise deklarative Profilsektion im Modellkatalog; `llm_chat.py`, `web/docs/MiniMaxLLMChat.md`, `../INSTALLATION.md`.

  **Done (2026-09-11) — English summary.** Hardware classes now map onto
  concrete, size-anchored GGUF candidates — advisory, honest about what is
  unverified.

  * New `llm_profiles.py`: six profiles (`cpu_only`, `vram_8`, `vram_12`,
    `vram_16`, `vram_24`, `vram_32`) with a suggested context, the reason, the
    anchored candidates and the caveats. `recommend_llm_setup()` takes a
    `ResourceSnapshot` (R01) and uses `resource_profiles.device_budget()` for the
    free budget, so an occupied GPU lowers the confidence instead of being
    ignored.
  * **Every anchor size was verified against the repository** (HF API,
    read-only) on 2026-09-11 and is pinned by tests, so a typo cannot reach a
    recommendation: Qwen 3.5 9B Q4_K_M 6 169 341 984 B, Q5_K_M 7 111 487 520 B,
    Q6_K 7 958 818 848 B (`bartowski/Qwen_Qwen3.5-9B-GGUF` @ `182be2f…`);
    Gemma 4 12B QAT Q4_0 6 975 879 296 B (`google/gemma-4-12B-it-qat-q4_0-gguf` @
    `29d0977…`); Qwen 3.8 27B UD-IQ3_XXS 10 934 860 704 B, UD-IQ4_XS
    14 252 845 984 B, UD-Q4_K_M 16 464 440 224 B (`unsloth/Qwen3.8-27B-GGUF` @
    `4ca7207…`). The task's own anchors were confirmed (7.11 / 7.96 / 6.98 /
    ~10.9 GB).
  * **The honesty rules are encoded, not just documented.** The sizes are
    labelled *file size, not a VRAM promise*; every profile carries the caveats
    that context/KV state and backend overhead come on top and that the **active
    parameters of an MoE model are not its resident weight memory**. No profile
    reasons from parameter counts.
  * **No unchecked recommendation:** CPU-only and the 8 GiB class set
    `requires_artifact_check` and state that a concrete small-model artifact
    must be checked before it is recommended — the doc's own requirement —
    instead of naming a file that was never verified. The 9B Q4_K_M anchor is
    offered in the 8 GiB class only with the explicit budget-check note.
  * **Provenance is not claimed from a file name:** `match_installed()` reports
    `installed` (verified) only when the installed size equals the anchor, and
    `name_match` with "provenance not claimed" otherwise. Installed candidates
    are offered first and are not suggested for download again.
  * **Integration in `llm_chat.py`:** `describe_llm_profile()` is advisory,
    read-only and never raises (a failure degrades to a single "not available"
    line); it is logged once with the LLM environment. No generation setting is
    touched, so the R02 lifecycle guarantees are unaffected.
  * **Docs:** a profile table plus the anchored sizes in
    `web/docs/MiniMaxLLMChat.md`, and a "Which model for which machine" section
    in `../INSTALLATION.md`.

  **Tests:** `tests/test_llm_profiles.py` (20 tests) pins the anchor sizes, the
  presence of repository+revision on every candidate, the absence of projector /
  MTP / mmproj files from the candidates, the file-size caveat on every profile,
  CPU-only conservatism, the 8/12/16/24/32 GiB selections, unreadable and
  unknown device memory, the occupied-GPU budget warning, the multi-GPU pool
  warning, the three installed-file matching cases, the rendered lines, the
  `llm_chat` integration and that the recommendation JSON carries no private
  paths. Suite: **660 tests, OK**.

Empfehlungen sind Ausgangspunkte; Modellqualität für diese Musikaufgabe muss B01 bestätigen. GGUF-Gewichte, Kontext und Backend bestimmen den tatsächlichen Bedarf. „Aktive Parameter“ eines MoE-Modells sind kein Maß für dessen gesamten residenten Gewichtsspeicher.

| Ressourcenklasse | Vorschlag für die Produktvorauswahl | Betriebsprofil |
|---|---|---|
| CPU-only / sehr wenig VRAM | Kleine 2–4B-Klasse, z. B. Gemma 4 E2B/E4B in passender Quantisierung; RAM und tatsächliche Dateigröße prüfen | Kurzer Kontext, kompakter Prompt; große Modelle nicht automatisch auf CPU auslagern |
| 6–8 GiB VRAM | Kleinere 4B-Klasse bevorzugen; 9B-Q4 nur nach tatsächlicher Budgetprüfung | 4–8k Kontext für neue kompakte Prompts; volle GPU-Auslagerung nur wenn passend |
| 10–12 GiB VRAM | Qwen 3.5 9B Q5_K_M oder Gemma 4 12B QAT Q4_0 | 8k als Teststart; Headroom und Backend entscheiden |
| 16 GiB VRAM | Gemma 4 12B QAT oder Qwen 3.5 9B Q6_K als Alltagskandidaten; Qwen 3.8 27B UD-IQ3_XXS als Qualitätsvergleich | 8–16k, nach tatsächlichem Eingabeumfang; keine 32k-Reservierung allein wegen Modellmaximum |
| 24 GiB VRAM | Qwen 3.8 27B Q4/Q5 oder Gemma 4 26B-A4B QAT evaluieren | Mehr Quantisierungsqualität; großen Kontext nur bei Bedarf |
| Ab 32 GiB / geeignete Multi-GPU-Systeme | Größere Quantisierungen von 27B oder Gemma 4 31B evaluieren | Explizites Qualitätsprofil; Split-Betrieb gegen Einzel-GPU messen |

Verifizierte Anker: Qwen 3.5 9B Q5_K_M ca. 7,11 GB und Q6_K ca. 7,96 GB **Dateigröße**, nicht VRAM-Zusage. [Quantisierungsdateien des Erstellers](https://huggingface.co/bartowski/Qwen_Qwen3.5-9B-GGUF).

Google bietet Gemma 4 12B QAT als GGUF an, Hauptdatei `gemma-4-12b-it-qat-q4_0.gguf` ca. 6,98 GB; der zusätzliche Projektor ist für den Text-Workflow nicht erforderlich. [Offizielle Dateien](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf/tree/main). Die QAT-Familie ist ausdrücklich auf geringeren Speicherbedarf ausgelegt. [Google QAT-Veröffentlichung](https://blog.google/innovation-and-ai/technology/developers-tools/quantization-aware-training-gemma-4/).

Qwen 3.8 27B UD-IQ3_XXS ist bei Unsloth mit ca. 10,9 GB gelistet; Quantisierungen anderer Anbieter mit ähnlichem Namen haben andere Größen. Nicht aus `IQ3_XXS` allein die Größe ableiten. [Unsloth-Modellkarte](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF). Gemma-Varianten anhand offizieller Architekturangaben katalogisieren. [Gemma-4-Modellkarte](https://ai.google.dev/gemma/docs/core/model_card_4).

Keine persönlichen Dateien oder Laufwerksbuchstaben als Produktdefault. Bereits installierte passende Dateien zuerst anbieten, Herkunft nicht allein aus Dateinamen behaupten. Größer heißt nicht automatisch besser oder schneller. E2B/E4B-Empfehlungen erst nach Prüfung konkreter Artefakte/Backend-Unterstützung freischalten.

### L02 — Kontext, Template, Thinking und Sampling passend konfigurieren

- [x] **P1 · L · Risiko mittel.** `llm_chat.py`: `_get_model`, `_run_chat`, `_run_chat_streamed`, `_thinking_instruction`; neue Profil-/Template-Tests mit realistischen Signaturen.

  **Done (2026-09-11) — English summary.** Family templates, thinking control,
  context planning and runtime options are now explicit, capability-checked and
  honest about what the backend cannot do.

  * New `llm_sampling.py` (adapter version 1) with versioned **family adapters**:
    Qwen 3.8 / 3.5 / generic Qwen → ChatML, thinking controllable via
    `reasoning_budget`; Gemma 4 and Llama 3 → their own embedded template
    (`chat_format=none`) or the documented named format, thinking **not**
    switchable. Detection is specific-first, so `Qwen3.8-27B-UD-IQ3_XXS.gguf`
    resolves to the 3.8 adapter rather than the generic Qwen one.
  * **`thinking=off` is reported, not implied.** `thinking_support()` checks the
    installed build for `reasoning_budget` (or `chat_template_kwargs`) and the
    node logs `supported` / `NOT supported` per run; where it is unsupported the
    message says the toggle is *not a speedup* because it only splits the output
    afterwards. The existing "reasoning although thinking=off" warning now adds
    that the build cannot switch it off. An answer that was pure reasoning gets
    its own error explanation instead of a bare "empty assistant text".
  * **The Qwen 3.8 non-thinking sampler values** (temperature 0.7, top_p 0.8,
    top_k 20, repeat_penalty 1.0) are available through
    `sampling_for()` but are **never applied automatically** - only a profile
    that explicitly asks for them gets them, so no stored workflow value changes.
  * **Context planning** (`plan_context`, 4k/8k/16k/32k candidates): the smallest
    candidate that holds the estimated input + output budget + reserve, and an
    overflow returns `fits=False` with the largest candidate and a message that
    the input is never truncated silently. The estimate is labelled as an
    estimate; the authoritative number after a run comes from the backend usage.
  * **Runtime options** (`n_batch`, `n_ubatch`, `flash_attn`, `type_k`, `type_v`,
    `n_threads`) are passed only when `llama_cpp.Llama.__init__` declares the
    parameter. They are read from `models_config.json` under
    `llm.runtime_options`, so **no widget was added** and no saved workflow
    changes; accepted options go into the model options and are therefore part
    of the **cache identity** (two runtime configurations are two model
    instances). `n_ubatch` 128/256/512 are documented as the benchmark start.
    **A test found a real gap here:** unknown option names were silently ignored;
    a typo is now reported like any other unsupported option.
  * **Token statistics from the backend:** `_run_chat` / `_run_chat_streamed`
    return `(text, thinking, usage)`. Usage comes from the backend report
    (`source: backend`) when present; otherwise the stream chunk count is
    reported *as* chunks (`source: chunks`) and never as an exact token count.
    Unknown values stay `None`. The node's status string carries the number and
    its source, and the thinking control state.

  **Tests:** `tests/test_llm_sampling.py` (32 tests) covers family detection and
  ordering, the Gemma template decision, the thinking-support matrix, the
  non-thinking sampler availability, context planning (small/medium/boundary/
  overflow/never-below-input/empty candidates), runtime option validation,
  capability filtering, the cache-identity behaviour, catalog-driven options,
  token statistics, and streaming usage. The existing LLM helper tests in
  `tests/test_integrated_nodes.py` and `tests/test_llm_lifecycle.py` were updated
  to the three-value return. Suite: **692 tests, OK**; node contract snapshot
  unchanged (no widget or output change).

  **Still open in this task:** measuring per-family sampler quality (that is the
  B01 benchmark's job, and it needs the models on the user's machine), and the
  UI that would surface the profile/usage values - the data is in the status
  string and the log today.

Für neue Profile Kontext aus tokenisierter Eingabe einschließlich Chat-Template + Ausgabebudget + Sicherheitsreserve wählen. Kandidaten 4k/8k/16k/32k; nie unter die Eingabelänge kürzen. Start-Ausgabebudget für kompakte Vorlagen etwa 2–4k, lange Lyrics nach Bedarf. Kürzere Maximalwerte allein beschleunigen früh endende Antworten nicht; Gewinn entsteht durch weniger tatsächliche Ausgabe und geringere Kontextreservierung.

GGUF-Template und dokumentierte Familienunterstützung bevorzugen. Aktuelles `auto` nutzt für Nicht-Gemma pauschal ChatML; durch versionierte, getestete Familienadapter ergänzen. `thinking=off` muss die Generierung steuern. Wenn die Python-Bindings den nötigen Template-Schalter nicht unterstützen, ehrlich „nicht unterstützt“ melden; bloßes Entfernen von `<think>` nicht als Beschleunigung ausgeben.

Die Qwen-3.8-Modellkarte nennt für Non-Thinking unter anderem Temperatur 0,7, top_p 0,8, top_k 20 und repeat_penalty 1,0. Diese Werte nur im entsprechenden neuen Profil prüfen; kein pauschales Überschreiben anderer Modelle oder gespeicherter Samplerwerte. [Qwen-3.8-Modellkarte](https://huggingface.co/Qwen/Qwen3.8-27B).

Optionale Runtimeparameter `n_batch`, `n_ubatch`, `flash_attn`, `type_k`, `type_v`, CPU-Threadzahlen nur nach Capability-Prüfung anbieten und in Cacheidentität aufnehmen. Startbenchmark `n_ubatch` 128/256/512; kleiner spart temporären Speicher, größer kann Prefill beschleunigen. KV-Quantisierung ist modell-/backendabhängig, besonders bei hybriden Architekturen nicht pauschal mit einer Standard-Transformer-Formel berechnen. [Python-API](https://llama-cpp-python.readthedocs.io/en/latest/api-reference/).

Tokenstatistik aus Backend-Usage beziehen; Streaming-Chunks nicht als exakte Tokenzahl verkaufen. UI zeigt „generiert“, Budget und Zeit getrennt. Vollständige Antworten und Thinking nur im Debugmodus loggen; Produktions-JSON kann gewollte Inhalte weiterhin aufnehmen.

**Abnahme:** Keine inkompatiblen kwargs; Render-Template-Snapshots; keine leere Antwort bei Thinking-off; Überlauf vor Generierung verständlich melden. Messung pro Modellfamilie statt eines universellen Samplerpresets.

### L03 — Optionale weitere Beschleunigung

- [ ] **P3 · L · Risiko hoch.** Benchmarkzweig für Präfixwiederverwendung, native MTP/speculative decoding und optionalen lokalen Backendadapter.

Zuerst nachweisen, ob bestehendes llama.cpp bereits identische Promptpräfixe wiederverwendet. Nicht zusätzlich bei jedem Aufruf einen vollständigen KV-Snapshot kopieren. MTP benötigt konkrete Unterstützung der installierten Laufzeit, passende Draft-/Assistant-Dateien und zusätzliches Speicherbudget; ist kein einzelner universeller Python-Schalter. Ein lokaler Serveradapter ist nur gerechtfertigt, wenn ein dokumentierter Vorteil die zusätzliche Installation/Prozessverwaltung rechtfertigt. Bestehendes In-Process-Backend bleibt unterstützt. Abnahme anhand Gesamtlatenz, Speicherspitze und identischer Ausgabeverteilung, soweit der Decoder das garantiert.

## 6. Zuverlässiger Modelldownload

### D01 — Katalog, Dateientdeckung und Modellidentität vereinheitlichen

- [x] **P1 · L · Risiko mittel.** `models_config.json`, `model_downloader.py`, `llm_chat.py`, `flashsr_audio.py`, `minimax_autodownload.py`, `scripts/check_model_paths.py`.

  **Done (2026-09-11) — English summary.** One resolver, one discovery rule.

  * **`normalize_model_entries()` now expands every configured LLM artifact**
    (all of `llm.files` plus `llm.example`), deduplicated by name+target, with
    `llm.directory` as the default target. Before, only `llm.example` was
    expanded, so a second configured GGUF was invisible to the check node.
  * **Hugging Face artifacts resolve through the documented rule**
    (`resolve_entry_url`: explicit `url` wins, otherwise `repo_id` +
    `filename` + optional `repo_type`/`revision`). **`filename` is required** —
    the remote path and the local name are not interchangeable (`diffusion_models/x.safetensors`
    remotely, `x.safetensors` locally), and falling back to `name` would have
    downloaded the wrong file. An entry without repository information stays
    URL-less instead of inventing a URL.
  * **Schema versions are tolerated, not guessed:** `SUPPORTED_CONFIG_VERSIONS = (1, 2, 3)`,
    an unversioned config still reads, and a version this build does not know is
    reported (and ignored for the loader search path) rather than half-read. A
    test asserts the shipped `models_config.json` is byte-identical after being
    read — no automatic rewrite of a user's configuration.
  * **Unknown user fields survive normalization** (deep-copied per entry), and a
    group note no longer overwrites an entry's own note.
  * **FlashSR target consistency:** the group `weights.target` wins over a
    diverging per-file target, with a warning. The runtime only opens the
    standard file names in the group folder, so a diverging target would have
    downloaded a file that is then never found. The pre-existing test that
    pinned "explicit target wins" was rewritten to the new, deliberate contract
    with the reason in a comment — the old guarantee is not silently dropped.
  * **GGUF discovery classifies** projector (`mmproj`, `projector`,
    `vision-encoder`), MTP heads and split shards
    (`name-00001-of-00003.gguf`). A split model is offered **once**, under its
    first shard, with `parts_present`/`parts_expected` and the missing part
    numbers reported; projectors and MTP heads are no longer offered as
    standalone chat models. The file scan only *stats* files (size cached by
    path+size+mtime, bounded LRU) — no weights are read, nothing is renamed or
    moved.
  * **Check, download and loader share the resolved paths:** `_find_model_path()`
    and `list_llm_models()` now search the folder scan *plus* the catalog's
    resolved targets (`_llm_search_directories()`), and
    `scripts/check_model_paths.py` reports exactly that list.

  **Verified on the real machine** (not a fixture):
  `scripts/check_model_paths.py --comfy-dir D:\Daten2\ComfyUI --models-directory F:\ComfyUI\models`
  → `folder_paths.models_dir = F:\ComfyUI\models`, FlashSR target
  `F:\ComfyUI\models\audio\flashsr`, LLM search path
  `['F:\ComfyUI\models\llm']`, three chat models found
  (`gemma-4-12B-it-QAT-Q4_0`, `LFM2.5-VL-1.6B-Q4_K_M`, `Qwen3.8-27B-UD-IQ3_XXS`).

  **Still open in this task:** the richer catalog *field set* (stable `id`,
  family/role, display name, byte size, backend/quantization, access notes). The
  resolver already reads `repo_id`/`repo_type`/`revision`/`filename`/`sha256`;
  the fields are filled when the catalog gets its real artifacts in **D02**.
  `flashsr_audio.py` itself was not changed — its target handling was already
  group-based, and the config side is now consistent with it.

  **Tests:** `tests/test_model_catalog.py` (24 tests) covers the expansion, the
  URL rule (model/dataset/revision, remote-vs-local name), version handling,
  field preservation, FlashSR target, GGUF classification, shard completeness,
  the bounded stat cache and the catalog search path. Suite: **576 tests, OK**;
  node contract snapshot unchanged.

Gemeinsamer interner Modelleintrag: stabile ID, Familie/Rolle, Anzeigename, Artefakte mit `repo_id`, `repo_type`, `revision`, `filename`, lokaler Zielname/-ordner, Bytegröße, SHA256; zusätzlich unterstützte Backends/Quantisierung und optionale Zugangshinweise. Bestehendes v2-JSON inklusive `url`, `target`, `llm.example`, `llm.directory` weiter lesen. Neues Schema versionieren, unbekannte Benutzerfelder erhalten; keine vorhandene Konfiguration automatisch überschreiben.

`normalize_model_entries()` muss die tatsächlich ausgewählten LLMs und alle notwendigen Dateien verarbeiten, nicht nur `example`. Modellprüfung, Download und Loader verwenden dieselben aufgelösten Pfade. FlashSR darf keine beliebigen abweichenden Einzeldateiziele akzeptieren und anschließend trotzdem ausschließlich Standardnamen in einem anderen Ordner öffnen.

GGUF-Entdeckung klassifiziert Metadaten, Projektoren und Split-Shards. Projektoren/MTP-Heads nicht als eigenständige Chatmodelle anbieten. Splitmodelle nur einmal unter dem ersten Shard zeigen und Vollständigkeit aller Shards prüfen. Schnelle Metadatenprüfung cachen nach Pfad/Größe/mtime; keine Gewichte laden. Bestehende Dateinamen und manuell installierte Modelle erhalten.

### D02 — Konkrete Downloadquellen ergänzen

- [x] **P1 · M · Risiko mittel.** Katalogeinträge ergänzen; pro Artefakt den endgültigen Commit und Hash vor Freigabe prüfen, keine ungeprüften Platzhalter als fertig markieren.

  **Done (2026-09-11) — English summary.** `models_config.json` is now a real,
  verified catalog (schema v3) instead of a manual-download placeholder.

  * **Every artifact was verified against the Hugging Face API** (read-only
    `tree` + `revision` endpoints, no download) and every entry is pinned to the
    repository's **commit sha** as its `revision`, so the resolve URL is
    immutable even if the branch moves:
    * `Comfy-Org/MiniMax-Music-3` @ `6baad88896848433857c170ba4f05d2ea9d5f218`
      — DiT fp16 (4 914 197 682 B), pruned int8 text encoder (9 196 611 886 B),
      DAV (216 696 128 B); the int8 DiT (2 502 161 682 B) is listed as
      `"optional": true`.
    * `Comfy-Org/vae-text-encorder-for-flux-klein-4b` @ `5f526678002e43af5551dadb73ce2e8c91b43afe`
      — `split_files/diffusion_models/flux-2-klein-4b.safetensors`
      (7 751 105 712 B), `split_files/text_encoders/qwen_3_4b.safetensors`
      (8 044 982 048 B), `split_files/vae/flux2-vae.safetensors`
      (336 211 292 B).
    * `jakeoneijk/FlashSR_weights` @ `5701dea5f6a45ed964f5cb5b9280b3a1f9b39882`
      — the three `.pth` files (1 033 200 174 / 627 861 067 / 1 655 458 345 B).
  * **No hash was invented.** The HF API did not expose a sha256 for any of
    these artifacts (Xet/LFS storage), so the catalog records the exact **byte
    size** plus the pinned commit and carries `_provenance` stating the method,
    the date and explicitly that no hash was read. `validate_model_entry()` now
    enforces the *rule* instead: `bytes` must be a positive integer and any
    `sha256` present must be 64 hex characters.
  * **Base/distilled variants are not confused:** only the distilled
    `flux-2-klein-4b` and `qwen_3_4b` are listed; `flux-2-klein-base-4b` and the
    fp4 text encoder exist in the same repo and are deliberately excluded.
    `minimax_music3_dit_fp32` and the bf16 text encoders are likewise not
    downloaded.
  * **No family is pulled in as a whole:** `normalize_model_entries(...,
    include_optional=...)` skips `"optional": true` entries unless asked, and
    the FlashSR entries now use the pinned revision instead of the previous
    `?download=true` links.
  * **Corrected a wrong claim in the old catalog:** the note said the FLUX files
    were gated behind a token. The Comfy-Org mirror is publicly readable — a
    token-free HEAD request returns 200 for all three files. The note now says
    so, without promising anything about the BFL repository.

  **Verified end to end (read-only, no artifact downloaded):** a scratch check
  loads the shipped config, runs it through `normalize_model_entries()` and
  `resolve_entry_url()`, and issues a HEAD request per artifact —
  **11 entries, 10 URLs, all HTTP 200, and every declared size equals the
  catalog's `bytes`** (`.scratch/verify_catalog_urls.py` in the workspace scratch area). The
  eleventh entry is the LLM example, which deliberately has **no** URL: the
  concrete artifact belongs to L01, and an unverified URL is worse than none.

  **Tests:** `tests/test_model_catalog.py` (24) plus the rewritten
  `tests/test_model_downloader.py::test_config_is_valid_and_complete`, which now
  pins the new contract (v3, pinned revisions, exact sizes, no unverified hash)
  instead of the old "everything is empty" state.

Verifizierte Quellen und Zielzuordnungen:

| Modell | Repository / Remote-Pfad | Lokales Ziel |
|---|---|---|
| MiniMax DiT FP16 | `Comfy-Org/MiniMax-Music-3` → `diffusion_models/minimax_music3_dit_fp16.safetensors` | `models/diffusion_models/` |
| MiniMax DiT INT8, optional | dasselbe Repo → `diffusion_models/minimax_music3_dit_int8_convrot.safetensors` | `models/diffusion_models/` |
| MiniMax TE | dasselbe Repo → `text_encoders/minimax_music3_text_encoder_pruned_int8_convrot.safetensors` | `models/text_encoders/` |
| MiniMax DAV | dasselbe Repo → `vae/minimax_music3_dav.safetensors` | `models/vae/` |
| FLUX Klein 4B | `Comfy-Org/vae-text-encorder-for-flux-klein-4b` → `split_files/diffusion_models/flux-2-klein-4b.safetensors` | `models/diffusion_models/` |
| FLUX TE | dasselbe Repo → `split_files/text_encoders/qwen_3_4b.safetensors` | `models/text_encoders/` |
| FLUX VAE | dasselbe Repo → `split_files/vae/flux2-vae.safetensors` | `models/vae/` |
| FlashSR | Dataset `jakeoneijk/FlashSR_weights`, drei vorhandene `.pth`-Dateien | bisheriges `models/audio/flashsr/` |
| LLM | konkrete Artefakte aus L01 | konfiguriertes `models/llm/` |

MiniMax-Dateien sind öffentlich in der Comfy-Org-Struktur aufgelistet; die bisherige pauschale Aufforderung zum manuellen Bezug reicht für Auto-Download nicht. [MiniMax-Dateien](https://huggingface.co/Comfy-Org/MiniMax-Music-3/tree/main), [DiT-Varianten](https://huggingface.co/Comfy-Org/MiniMax-Music-3/tree/main/diffusion_models).

Beim FLUX-Katalog **base/distilled/andere Varianten nicht verwechseln**: Remote-Dateinamen und Workflow-Auswahl exakt abgleichen. Ein ähnliches Modell ist kein Ersatz für den bisherigen Checkpoint. Die aktuelle pauschale `FLUX.2-klein-dev`-Notiz entspricht nicht einer präzisen Zuordnung der gelisteten 4B-Dateien. [Comfy-Org-Splitdateien](https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b/tree/main/split_files), [BFL-4B-Repository](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B).

**Abnahme:** Keine erfundenen URLs, keine Vermischung von safetensors/Diffusers/GGUF. Token nur bei tatsächlichem Bedarf; fehlende Berechtigung gesondert anzeigen. Kein automatischer Download aller Quantisierungen einer Familie.

### D03 — Wiederaufnahme, Integrität und Ressourcenlimits

- [x] **P1 · L · Risiko mittel.** `model_downloader.py`; vorhandene `test_model_downloads.py`, `test_model_downloader.py` erweitern.

  **Done (2026-09-11) — English summary.** The transfer path is now resumable,
  retried and verified instead of single-shot.

  * **Retries with backoff and jitter** (`open_with_retries`): network errors,
    429 and 5xx are retried up to `DOWNLOAD_ATTEMPTS_DEFAULT = 4`; a server
    `Retry-After` wins over the computed delay.  **401/403/404 are fatal and not
    retried** - a permission problem is reported, not looped on.  Failures raise
    `DownloadError` with the reason and the number of attempts.
  * **Resume with a validated offset.** The staging file is now a *stable*
    `<name>.part` plus a `<name>.part.json` sidecar recording the URL, ETag,
    Last-Modified and total size.  A resume sends `Range` + `If-Range`; bytes are
    appended **only** after the `206 Content-Range` start matches the offset we
    hold.  A `200` answer to a Range request (server ignores Range, or the
    resource changed) truncates and starts over instead of concatenating two
    bodies.  A partial from a different URL, or without a usable validator, is
    discarded rather than continued.
  * **A partial is kept only when it is attributable** (known total, fewer bytes
    than the total, and a transient failure).  Empty bodies and **hash
    mismatches delete the bytes** - they must never be resumed from.  A user
    cancel (`KeyboardInterrupt`) keeps the resumable part on purpose.
  * **Publication is still the last step:** size (`expected_bytes`) and hash are
    checked before `os.replace`, so no empty or half file can look installed.
  * **Per-destination locking** replaced the single global `_DOWNLOAD_LOCK`: two
    callers for the same file are single-flight (with the check repeated *after*
    the lock is acquired), while different files still transfer in parallel.
  * **Free disk space is checked before the transfer starts** (payload, staging
    copy and a margin), and only when the expected size is known - an unknown
    size is not guessed.
  * **Hashing is block-wise** (4 MB) and verification results are cached by
    path+size+mtime, so repeated checks of a multi-GB checkpoint no longer
    re-hash it; a changed file is re-verified.
  * **No tokens in logs:** URLs are logged and reported through `redact_url()`,
    which drops the query string (signed parameters, `?token=`).
  * **Config validation tightened:** `bytes` must be a positive integer,
    `sha256` must be 64 hex characters, repository fields must be strings and a
    revision may not contain spaces.  `check_file_entries()` now passes the
    expected size into both the readiness check and the download.

  **Tests:** new `tests/test_download_resume.py` (17 tests, all against a local
  scripted HTTP server - no real download) covers interruption + resume, a
  server ignoring `Range`, a changed validator, retryable statuses with
  `Retry-After`, a fatal 403 without retry, wrong hash, wrong declared length,
  missing `Content-Length`, wrong expected size, two concurrent callers
  transferring once, low disk space refusing before any request, an intact local
  file needing no request, URL redaction (including a `?token=` that must not
  appear in the error), the verification cache, and `check_file_entries` using
  the resolved URL and size.  Three legacy tests in `test_model_downloads.py`
  pinned the old contract and were updated with the reason in a comment
  (unique staging names → stable; leftovers after a short body → a resumable
  partial; `OSError` → `DownloadError`).  Suite: **621 tests, OK**.

  **Still open in this task (not claimed as done):** the optional
  `huggingface_hub` adapter - HF artifacts currently go through the verified
  resolve URL and this hardened path, which works but is not the doc's first
  choice; a configurable cap of one or two concurrent transfers for a
  resource-poor profile; an explicit indeterminate-progress log line when
  `Content-Length` is unknown; and a real two-**process** test - the lock is
  process-local, so cross-process safety currently rests on the sidecar check.

Für HF-Artefakte bevorzugt `huggingface_hub.hf_hub_download` hinter einem kleinen Adapter verwenden; `local_dir`, explizite Revision und Einzeldateiauswahl nutzen. Abhängigkeit bewusst als optionale Downloadkomponente deklarieren. Eingesetzte Version und ihr Resume-/Xet-Verhalten testen. Kein paralleles eigenes HF-Downloadframework. [HF-Download-API](https://huggingface.co/docs/huggingface_hub/main/en/package_reference/file_download).

Für bestehende allgemeine HTTP-URLs den bisherigen Streamingpfad erweitern: limitierte Retries mit Backoff/Jitter für Netzwerkfehler, 429 und ausgewählte 5xx; `Retry-After` beachten; keine Endlosschleife bei 401/403/404. Wiederaufnahme braucht stabile Stagingidentität aus Ziel+URL/Revision, gespeicherten ETag/Last-Modified, `Range`/`If-Range` und Validierung von `206 Content-Range`. Bei `200` nach Range-Anfrage sauber neu beginnen. Nie ungeprüft Bytes anhängen. Abbruch darf einen eindeutig zuordenbaren resumierbaren Teil behalten, endgültige Zieldatei erscheint erst nach Prüfung.

Pro-Zieldatei Prozess- und Thread-Sperre statt ausschließlich globalem `_DOWNLOAD_LOCK`. Prüfung nach Lock-Erwerb wiederholen. Maximal ein oder zwei Transfers je ressourcenarmem Profil; konfigurierbare Obergrenze. Vor Start freien Speicher für vollständige Datei, Staging und eventuell doppelte Cachekopie prüfen. Hash in Blöcken, nie ganze Datei im RAM. Erstprüfung nach Download verpflichtend; wiederholte Vollprüfung großer vorhandener Dateien nur explizit oder nach Signaturänderung. Cache einer erfolgten Integritätsprüfung ist kein Beweis gegen jede externe Manipulation, genügt aber als schnelle lokale Betriebsprüfung.

Konfigurationsfehler nicht als übersprungene optionale Datei verstecken. Root-/Gruppentypen, Hashformat, Größe und Pflichtartefakte validieren. Fortschritt mit übertragenen Bytes/Gesamtbytes, Geschwindigkeit, Status und Abbruch; bei unbekannter Länge indeterminierter Fortschritt. Tokens und signierte Queryparameter nicht loggen.

**Abnahme:** Lokaler Testserver simuliert Abbruch, Neustart, falschen Hash, falsche Länge, fehlende Länge, Range ignoriert, geänderten ETag, 429, Zugang verweigert, zwei Prozesse und wenig Plattenplatz. Offline mit gültigen Dateien funktioniert ohne Netzabfrage. Keine leeren/halben Enddateien.

### D04 — Preflight vor Validierung und Modellnutzung

- [x] **P1 · L · Risiko mittel.** `minimax_autodownload.py`, neue schlanke Model-Manager-Routen/UI, `scripts/build_public_workflow.py`, Beispielworkflows.

  **Done (2026-09-11) — English summary.** The model check is now an explicitly
  triggered setup action instead of a side effect, and the guarantee that loading
  never networks is mechanical.

  * **`preflight_models()`** (in `model_downloader.py`) is the one action behind
    the node and the routes. It answers inventory, size and space: per artifact
    status, expected/present bytes, the optional flag, and a summary with
    counts, `missing_bytes`, `free_bytes`, `space_ok`, `required_missing`,
    `optional_missing` and `ok`. It **only transfers when the caller passes
    `auto_download=True`**. `format_preflight_report()` renders the same data as
    human-readable lines for the node panel and the route response.
  * **The node stays compatible and gets a structured side channel:**
    `MiniMaxModelAutodownload` keeps its single `STRING` output (same text as
    before, so saved workflows are unaffected) and returns the structured report
    through `ui.preflight_json`. Its `auto_download` toggle still decides whether
    a failure raises or is only reported.
  * **Two slim model-manager routes** (`model_manager_routes.py`, registered from
    `__init__.py`): `GET /minimax_music_toolkit/model_preflight` reports and never
    transfers; `POST` performs the download. Both run the blocking work through
    `asyncio.to_thread`, so a multi-GB transfer cannot stall ComfyUI's event loop,
    and group selection is a query/body flag (`minimax`, `flux2`, `flashsr`,
    `llm`).
  * **"Never at import, never in `INPUT_TYPES()`" is now guaranteed by a test,
    not by convention:** `socket.socket.connect` is replaced with a raising stub,
    then the **real entry point** is loaded and every registered node's
    `INPUT_TYPES()` is called. Any network attempt anywhere on that path fails the
    suite (`tests/test_model_preflight.py::NoNetworkAtLoadTests`).
  * **A successful check cannot hide a deleted file:** the report re-stats every
    artifact on each call, and `_file_is_ready()` checks existence *before* its
    signature cache — covered by a test that deletes a file between two checks.
  * **Only active branches, never optional artifacts:** the tests assert that the
    FlashSR-only selection preflights three `.pth` files and that the optional
    int8 DiT is absent unless `include_optional=True` is asked for explicitly.
  * **User documentation corrected in `../INSTALLATION.md`:** the old text claimed
    the MiniMax/FLUX weights had *no public URL*. That was wrong (D02 verified
    them), and the section now documents the preflight node, the two routes, the
    resumable/verified transfer, the token-free public mirrors and the optional
    quantizations.
  * **The graph was deliberately not changed.** The task's own point is that an
    extra wire cannot make a missing combo model load early, so the bundled
    workflow keeps its informational check node and the explicit preflight is the
    real barrier. Runtime checks in the FlashSR/LLM loaders are unchanged.

  **Tests:** `tests/test_model_preflight.py` (19 tests) covers a fresh install
  with everything missing, present/missing byte accounting, the deleted-file
  case, optional artifacts not being required, a space shortfall warning, the
  report lines, `auto_download=False` never opening a connection, the explicit
  flag reaching the transfer layer, branch selection, the node's compatible
  STRING output plus its structured payload, the raising/non-raising failure
  paths, route registration, GET vs POST behaviour, query flag parsing, and the
  no-socket-at-load guarantee. Suite: **640 tests, OK**; `validate_release` green;
  node contract snapshot unchanged.

  **Still open in this task:** the frontend panel that consumes
  `ui.preflight_json` / the route (the backend and its JSON are in place, no
  browser UI yet), and the new example workflows themselves - the plan puts those
  in V01 ("CPU/lean text path, balanced production, audio-only EQ/mastering,
  reference auto-EQ").

Produktablauf: Modelle auswählen → Bestand/Platzbedarf prüfen → fehlende gewählte Dateien laden → ComfyUI-Modelllisten aktualisieren → Workflow ausführbar. ComfyUI kann fehlende Combo-Modelle bereits **vor** Node-Ausführung ablehnen; eine zusätzliche Kabelverbindung im Graph behebt das nicht allein. Daher Preflight als gezielt ausgelöste Setup-/Downloadaktion außerhalb der eigentlichen Generierung anbieten. Netzwerkoperationen niemals beim Import oder in `INPUT_TYPES()`.

Zusätzlich Loader-Laufzeitchecks behalten; für neue Workflows Abhängigkeiten vor tatsächlicher Verwendung herstellen. Alten Check-Node mit STRING-Bericht kompatibel belassen; neue strukturierte Ergebnisse intern und in der UI anbieten. Ein erfolgreich gecachter Check darf eine später gelöschte Datei nicht überdecken.

**Abnahme:** Frische Installation ohne Modelle, erneutes Öffnen nach Download, fehlender Einzelshard, deaktiviertes Auto-Download und gelöschte Datei nach erfolgreichem Lauf. Nur aktive Modellzweige herunterladen.

## 7. Audio: Geschwindigkeit, RAM und Enhancement

### A01 — FlashSR-Batch, Device und reproduzierbare Ausführung

- [x] **P1 · M · Risiko mittel; Batchänderung ist Bugfix.** `flashsr_audio.py`: `_to_channel_samples`, `_get_runner`, `MiniMaxFlashSRAudio.upscale`; Vendor-Adaptertests.

  **Done (2026-09-11) — English summary.** The batch bug is fixed and the device/
  determinism guarantees are explicit.

  * **Bugfix: no more silent batch reduction.** `_to_batch_channel_samples()`
    keeps ``[B, C, T]`` and returns every item; `upscale()` processes each item
    through its own chunk loop and `_make_audio_batch()` returns one ``[B, C, T]``
    AUDIO. A batch of two now yields two results (pinned by a test that also
    checks item 2 is not a copy of item 1). The legacy `_to_channel_samples()`
    is kept for compatibility and documented as "item 0 only".
  * Length, channel count and sample rate survive the round trip; unequal item
    lengths would be zero-padded by the batch helper (reported as `padded`) -
    defensive, since a tensor batch is uniform by construction, and tested at the
    helper where it lives.
  * **Explicit devices:** `MINIMAX_FLASHSR_DEVICE` accepts `cpu` or `cuda:N`, is
    validated against the visible devices (an unusable value warns and falls back
    to the automatic rule instead of failing the run), and CPU-only still works.
    The automatic rule (CUDA when available, else CPU) is unchanged.
  * **No poisoned cache after a failed transfer:** the model is moved after
    construction; a failed move is undone, and if *that* also fails the instance
    is discarded and rebuilt cleanly from the checkpoints on CPU. The runner now
    records `requested_device`, `fallback` and `rebuilt_on_cpu`, so a fallback is
    visible in the settings JSON instead of being implied.
  * **Determinism as an opt-in, not a global side effect:** `upscale(..., seed=None)`
    keeps the historical random semantics. With a seed, the vendor's stochastic
    steps (``posterior.sample()`` and the diffusion noise) run inside a locked RNG
    context that saves and restores the CPU/CUDA RNG state - so the seed cannot
    leak into another node - and each chunk derives its own seed. The settings
    JSON records `seed` and a `determinism` note stating that reproducibility is
    only promised for the actually tested backend combination.
  * **Cancellation between 5.12 s chunks:** ComfyUI's interrupt flag is checked
    per chunk and raises the host's own interrupt exception, so a cancel does not
    have to wait for a whole item.
  * The settings JSON also carries `batch_items`, `device_requested` and
    `device_fallback` for reproducibility.

  **Tests:** `tests/test_flashsr_batch.py` (18 tests, no weights needed - the
  runner and model are faked) covers batch preservation, channel/rate survival,
  "every item is inferred", the padding helper, input-not-modified-in-place, seed
  reproducibility, unseeded randomness, RNG-state restoration, cancellation,
  device resolution (auto/CPU/explicit/invalid/unknown), and the three runner
  fallback paths. Suite: **710 tests, OK**.

  **Still open in this task:** the determinism promise has only been verified on
  this CPU backend with a fake model - a real GPU run must confirm it, and A02
  (model footprint) was deliberately not touched here.

BCT nicht still auf Batch 0 reduzieren. Nacheinander alle Batchitems verarbeiten und BCT wiederherstellen; Stereo-Kanäle innerhalb eines Items gemeinsam gemäß aktuellem Modellvertrag. CPU-only und explizite Devices unterstützen. Fehler beim GPU-Transfer dürfen keinen halb verschobenen Runner als CPU-Modell im CUDA-Cache hinterlassen; verwerfen und sauber neu auf CPU aufbauen, wenn der Benutzer CPU-Fallback erlaubt.

Optionalen Seed/Generator für neues deterministisches Profil über alle stochastischen Schritte verfolgen: `VAEWrapper.encode_to_z()` verwendet `posterior.sample()`, zusätzlich Diffusionsrauschen. Nicht nur `torch.manual_seed()` global setzen. Wo Generatorübergabe nicht möglich ist, lokal gesicherten RNG-Kontext mit Laufzeitsperre verwenden. Alte zufällige Semantik erhalten.

**Abnahme:** Batch 2 liefert 2 Ergebnisse; Länge, Kanalzahl und Rate stimmen. Abbruch zwischen 5,12-s-Chunks; kein vergifteter Cache nach OOM. Determinismus nur für tatsächlich getestete Backendkombination zusagen.

### A02 — FlashSR-Modellfußabdruck gezielt reduzieren

- [ ] **P2 · L · Risiko hoch.** `flashsr_inference/FlashSR/FlashSR.py`, `VAEWrapper.py`, `AudioSR/autoencoder.py`, STFT-/Mel-Helfer; `flashsr_inference/NOTICE.md` bei Vendoränderungen aktualisieren.

`AutoencoderKL(image_key='fbank')` konstruiert `self.vocoder`; FlashSR dekodiert jedoch mit `z_to_mel()` und `FlashSR.sr_vocoder`. Zunächst Parameterbytes und tatsächliche Aufrufe messen. In einem expliziten Inferenzmodus den ungenutzten Autoencoder-Vocoder nicht auf GPU verschieben; wenn Checkpoint-Kompatibilität gesichert ist, Konstruktion optional überspringen. Beim Laden nur erwartete `vocoder.*`-Schlüssel gezielt behandeln; kein pauschales `strict=False`, das echte Modellfehler verschluckt. Alte `mel_to_audio`-/Trainingspfade behalten ihre Voraussetzungen.

Checkpointladen CPU-seitig mit geprüftem `map_location`; State-Dicts nach Verwendung freigeben. `weights_only`/mmap nur nutzen, wenn Checkpoint und installierte PyTorch-Version passen. Nicht mehrmals große Gewichte kopieren.

FP32 bleibt Referenz. BF16/FP16 als experimentelle Qualitätsprofile getrennt messen, Autoencoder/Vocoder numerisch separat prüfen. `torch.compile` erst bei langen Wiederholungsjobs: Compilezeit, zusätzlicher Speicher und Windows-Unterstützung einrechnen. Melbasis und Fenster nach Device/Dtype begrenzt cachen; bestehender STFT-Pfad ruft wiederholt `.to(device)` für das Fenster auf. Diese kleinen Optimierungen nicht als größten Gewinn verkaufen.

### A03 — Temporäre Audioarrays begrenzen

- [x] **P1 · M · Risiko mittel.** `flashsr_audio._finalize_ola`, `audio_hf_repair.HFCymbalShimmerRepair.process`, `audio_declip._repair_channel/process`, `audio_utils.py`.

  **Done (2026-09-11) — English summary.** Two copies removed with bit-exact
  parity, one experiment measured and rejected, and the ownership rule written
  down as a contract.

  * **`_finalize_ola` normalizes in place** (`np.divide(acc, weight_sum, out=acc,
    where=weight_sum != 0)`): no full-size temporary, no pointless `.astype`, and
    it no longer mutates the caller's `weight_sum` as a side effect. The zero-weight
    case keeps the accumulator value, exactly as the old `weights[weights == 0] = 1.0`
    did - pinned by a test that compares against the old formula for bit equality,
    plus tests that the result *is* the accumulator and that the weights stay
    untouched. (The existing streaming suite still passes, which is the end-to-end
    parity check.)
  * **Declip keeps one deliberate owned copy.** `process` already allocated the
    owned output; the per-channel copy inside `_repair_channel` is now an optional
    reusable scratch buffer (`out=`), so the node allocates **one** channel-length
    scratch per run instead of one per channel. The function documents that it
    returns an array aliasing `out` and that the caller must consume it
    immediately - which `process` does. Tests assert bit equality against the
    owning path, that `x` is never modified, and that the buffer is really reused
    across channels (and that a retained copy is unaffected by the next call).
  * **Ownership contract** written into `audio_utils.py` (A03 asked for the shared
    rule, not just a local comment): incoming tensor/array never modified in place
    (not even when `.numpy()` shares memory), one deliberate owned output per
    stage, own scratch buffers may be reused but a returned array must not alias
    one undocumented, and a stage that removes a copy must say which copy it kept
    and why.
  * **Node inputs verified untouched:** `AudioDeclipRepair.process` and
    `HFCymbalShimmerRepair.process` are driven with their own declared widget
    defaults and the incoming tensor is compared before/after.
  * **Measured and rejected: the block-wise HF energy accumulation.** The task
    asked for it to avoid a full-track `np.square(..., dtype=np.float64)`. A/B on
    the same 5-minute stereo 48 kHz band, two fresh processes
    (`.scratch/measure_hf_memory.py`; identical checksum 637998.125000, so the
    values were bit-identical):
    * full-array expression: **+115.5 MB peak**, **368 ms**
    * block-wise (1 MiB blocks): **+67.1 MB peak**, **2493 ms**
    * block-wise (2/4 MiB): +95 / +150 MB, unchanged ~2.5 s

    It halves the temporary peak but costs 6-7x the CPU, and I could not explain
    the gap within this change (a contiguous-copy variant and a buffer-reuse
    variant were both tried and measured). Per the plan's own rule ("a benchmark
    experiment may conclude with a documented negative result"), the change was
    **reverted**: the fast full-array expression stays, with the measurement
    recorded in the code comment and here. The measurement script is kept in the
    scratch area so the experiment can be repeated.

  **Tests:** `tests/test_audio_memory.py` (11 tests) covers the ownership
  contract, the OLA parity/aliasing/no-mutation guarantees, the declip scratch
  parity and buffer reuse, and input immutability for both nodes. Suite:
  **721 tests, OK**; `validate_release` green; node contract snapshot unchanged.

  **Still open in this task:** `audio_utils.py` itself still hands out
  non-copying helpers by design (documented), the FFmpeg file transport is A05,
  and the peak-RSS figure above is a single-stage measurement - a full-pipeline
  5-minute profile belongs to the B01 harness rather than to this task.

Fünf Minuten Stereo bei 48 kHz benötigen pro float32-Vollarray rund 110 MiB, bei 96 kHz rund 220 MiB. Mehrere Zweige und temporäre float64-Arrays addieren sich. Gemeinsamen Besitzvertrag dokumentieren: eingehende Tensor-/NumPy-Views niemals in-place ändern; eigene temporäre Puffer dürfen wiederverwendet werden.

WOLA-Finalisierung auf eigenem Accumulator mit `np.divide(..., out=acc)` und abgesicherten Gewichten; unnötiges anschließendes `astype` vermeiden. HF-Energie blockweise akkumulieren, um `np.square(..., dtype=float64)` über den ganzen Track zu vermeiden; Zahlenpräzision der Summen erhalten. Ein Batchitem nach dem anderen, eigener finaler Output und begrenzte Scratch-Puffer. Declip kopiert aktuell außen und pro Kanal; nur eine bewusst verantwortete Outputkopie behalten.

Zero-phase-Filter nicht naiv in unabhängige Chunks schneiden: Randbehandlung und Vorwärts-/Rückwärtsfilterung ändern sonst den Klang. Nur Algorithmen mit explizitem State blockweise umsetzen; genaue Parität alternativ durch beschränkte temporäre Puffer ohne Änderung der Filtersemantik erreichen.

**Abnahme:** Eingabe bleibt bytegleich, Seitenzweig unverändert; Zahlenvergleich gegen Referenz; Peak-RSS für 5-Minuten-Batch dokumentiert. Mehr RAM für Caches nur explizit, nicht automatisch als „Optimierung“.

### A04 — Echte optionale Zweige und Vorschau

- [x] **P1 · M · Risiko mittel.** Neuer `MiniMaxAudioBranchSelect` oder neue Hybridversion; `audio_hf_repair.py`, neue Beispielworkflows.

  **Done (2026-09-11) — English summary.** The branch is now an explicit, lazy
  decision with its own output contract.

  * **New node `MiniMaxAudioBranchSelect`** (`minimax_audio_branch.py`) with three
    profiles: **Keep original**, **Careful restore**, **Reconstruct bandwidth**.
    The example's stored "strong PRE low-pass + full FlashSR replacement" stays as
    it is for damaged sources; it is no longer the implicit behaviour for clean
    ones.
  * **Real lazy branches:** `restored_audio` and `bandwidth_audio` are optional
    inputs and `check_lazy_status()` returns exactly the inputs the chosen profile
    still needs, so ComfyUI computes no unneeded branch. Tests cover every profile
    (Keep original requests nothing, Careful restore asks only for
    `restored_audio`, Reconstruct only for `bandwidth_audio`, a present branch is
    not requested twice, a missing `original_audio` is requested, an unknown
    profile falls back to the original-only rule).
  * **The output contract belongs to the selector:** sample rate and length always
    come from `original_audio` - that is the trap of the old ``Original SRC only``
    mode, which took both from the replacement input. A replacement at another
    rate is resampled with the shared polyphase resampler, another length is
    trimmed or padded, channels and batch are conformed; every action is listed in
    `branch_report_json` (schema `minimax_audio_branch_v1`). Pinned by tests that
    feed a 44.1 kHz/1 s replacement into a 48 kHz/2 s original and assert a
    48 kHz/2 s output plus the resample/pad notes.
  * **Preview:** `preview_seconds` (0 = full render) clamps to the documented
    15-30 s window and trims the *result*. The node's own docs state the honest
    limit: the chosen branch already ran upstream, so the preview saves the
    save/encode stages - lazy evaluation is what skips the *other* branches.
  * **Errors name the profile and the missing input** ("the 'Careful restore'
    profile needs the restored_audio input..."), and `mix=0` is reported as an
    explicit zero-weight blend instead of silently ignoring the branch.

  **Integration:** registered in `__init__.py` (class + display mappings),
  `tests/_toolkit_bootstrap.NODE_OWNER` extended, `tests/fixtures/node_contracts.json`
  regenerated (`dump_node_contracts.py --write`, 31 -> 32 nodes) and
  `web/docs/MiniMaxAudioBranchSelect.md` written, so `validate_release` stays
  green. **Tests:** `tests/test_audio_branch.py` (20 tests).

  **Still open in this task:** the new example workflows (the plan puts them in
  V01), and a *true input-side* preview would need a bounded-render parameter in
  the upstream branch node itself - deliberately not added here, because a new
  widget on an existing node can shift the positional `widgets_values` of saved
  workflows.

Lazy-AUDIO-Eingaben und `check_lazy_status()` verwenden, damit nur notwendige Zweige ausgeführt werden. Bestehendes `Original SRC only` bestimmt Rate und Länge noch anhand des FlashSR-Eingangs; ein neuer Selector braucht daher eine eigenständige Zielrate/-längenregel. Nicht einfach denselben Modus ohne FlashSR ausführen und dabei unbemerkt Länge/Rate ändern. [ComfyUI Lazy Evaluation](https://docs.comfy.org/custom-nodes/backend/lazy_evaluation).

Neue Profile: „Original erhalten“, „vorsichtig restaurieren“, „Bandbreite rekonstruieren“. Starkes PRE-10-kHz plus vollständiger FlashSR-Ersatz ist im Beispiel gespeichert und bleibt dort erhalten, wird aber nicht pauschal zum Produktstandard für saubere Quellen. Eine 15–30-s-Vorschau für Parameterwahl und separat Vollrender anbieten. Andere aktive Save-/Preview-Zweige dürfen FlashSR weiterhin benötigen; Lazy verhindert nicht jede Ausführung im gesamten Graph.

### A05 — FFmpeg ohne unnötige Austauschdateien

- [x] **P2 · M · Risiko mittel.** `ffmpeg_utils.py`, `audio_release_prep._measure_bs1770`, beide Audio-Saver.

  **Done (2026-09-11) — English summary.** The loudness measurement no longer
  writes a temporary WAV; the file transport stays as the tested fallback.

  * **`interleaved_f32le_blocks(data_tc, block_frames)`** produces the raw
    little-endian f32le stream FFmpeg expects for `-f f32le` in bounded blocks -
    time-major interleaved (frame 0's channels, then frame 1's), never one huge
    `.tobytes()` of the whole track. Tests compare the produced bytes against
    NumPy's own interleaved layout, check the block bound, the mono case, the
    single-block case and that the input array is untouched.
  * **`run_ffmpeg_with_pcm(...)`** runs FFmpeg with PCM on stdin: bounded writes,
    **concurrent bounded draining of stdout and stderr** (a chatty `loudnorm`
    would otherwise fill the pipe and deadlock), a process timeout that kills and
    reports instead of hanging, the console-less Windows flag preserved, and the
    historic failure message with its stderr tail. A failing filter and a forced
    timeout are both tested against real FFmpeg.
  * **`audio_release_prep._measure_bs1770` prefers the pipe** and falls back to
    the previous temporary-WAV path (unchanged) when the pipe is unusable; both
    return the same BS.1770 metrics through the shared `_loudnorm_metrics()`
    helper. `loudnorm` is still used only as a *meter* - no processed audio is
    taken from it, so its dynamic mode cannot alter the song's dynamics.
  * **Measured parity, real FFmpeg:** the same 1.5 s stereo signal measured
    through the pipe and through the file transport agrees to 3 decimal places on
    integrated LUFS, true peak, LRA and threshold. A test additionally *refuses*
    `tempfile.NamedTemporaryFile` to prove the pipe path needs no temporary file,
    another verifies the fallback still removes its WAV, and mono is measured too.

  **Tests:** `tests/test_ffmpeg_pipe.py` (12 tests, skipped cleanly on a machine
  without FFmpeg). Suite: **753 tests, OK**.

  **Still open in this task:** the two audio savers still hand their data to the
  MP3 encoder through the documented intermediate WAV (`ffmpeg_utils.write_mp3`);
  converting that to a PCM pipe is a further step, and the file transport is the
  tested fallback the task asks to keep either way.

Optional raw-f32le-Pipe mit expliziter Samplerate/Kanalzahl und korrektem interleavtem TC-Layout. In begrenzten Blöcken schreiben, nicht `.tobytes()` des gesamten Tracks. Stderr gleichzeitig und begrenzt drainieren, damit kein Deadlock entsteht; Prozess-Timeout/Abbruch und Windows-Hintergrundverhalten erhalten. Dateitransport als getesteten Fallback belassen.

Vorher-/Nachher-Lautheitsmessung nicht pauschal durch Addition des Gains ersetzen: absolute Gates und Ausgabequantisierung können Messergebnisse beeinflussen. Neuer Meter kann Messungen bündeln, aber finale Exportprüfung bleibt wirklich gemessen. Format, Tags, Collision-Handling und gestuftes Schreiben unverändert.

### Q01 — Enhancement gezielter und nachvollziehbarer machen

- [ ] **P2 · L · Risiko mittel.** `audio_declip.py`, `audio_hf_repair.py`, `AUDIO_PIPELINE.md`, neue Analyseberichte/Presets.

  **Partial (2026-09-11) — the traceable half is done, the DSP/listening half is not; not ticked.**

  **Implemented and tested (declip findings):**

  * Every channel report now carries **`confidence`** (`high`/`medium`/`low`/`none`)
    with a `confidence_reason`. Short flat-topped crests with context on both
    sides are `high`; when most candidates are long plateaus or sit at the signal
    edge the report says the material is probably **limiter-processed or
    intentionally distorted** and that this is *not* safely repairable clipping.
  * **`regions_for_review`**: per candidate the start/end sample, length, plateau
    length, start time in ms and a `classification`
    (`flat_top` / `long_plateau` / `edge_of_signal`), capped at 64 entries with
    `regions_truncated` saying so - so a repaired spot can be auditioned against
    the source instead of being trusted blindly.
  * **Caveats are always present:** the Hermite reconstruction *interpolates the
    surrounding waveform and does not restore the original samples*, plus the
    limiter/distortion note for low and no confidence. `Analyze only` reports the
    same findings without touching the audio (tested), and the audio result is
    unchanged by the reporting (tested).
  * Documented in `AUDIO_PIPELINE.md` under "Declip findings: what the report
    tells you (Q01)", including the explicit *not implemented* list below.

  **Tests:** `tests/test_declip_confidence.py` (11 tests) with synthetic clean,
  clipped-crest and limiter-plateau signals, the region list, its bound and
  truncation flag, the ms conversion, the presence of the caveat in every report,
  the node-level JSON and the unchanged audio output.

  **Not done (the reason this is not ticked):**

  * band-separated HF repair (presence/sibilance and upper cymbal/air) beside the
    existing broad stereo-linked envelope, which stays the legacy mode; new gain
    curves would need time smoothing, transient protection and a measured
    reduction readout;
  * hybrid level/time alignment with a **measured** SR delay and delay
    compensation only under certain correlation in the shared band (no automatic
    global phase correction from reconstructed HF);
  * a guard against stacking the same HF reduction silently across PRE, HF
    repair, Auto-EQ and POST;
  * the acceptance itself - dry hi-hats, long cymbals, voice/sibilants, ambient,
    bass, distorted guitars, percussive transients and clean sources, compared
    loudness-matched and as a difference signal, with no universal "better"
    preset as the goal.

  These are DSP and listening tasks that need the real material and a listening
  pass; they should be done in a dedicated session rather than bolted onto a
  reporting change.

Declip-Kandidaten nach Plateauform, Kontext, Länge und Konfidenz berichten; limiterbearbeitetes oder absichtlich verzerrtes Material nicht als sicher reparierbares Clipping darstellen. Hermite-Rekonstruktion erhält keine Garantie, das Original wiederherzustellen. Reparierte Regionen für Delta-Abhören und Vergleich markieren.

HF-Reparatur optional um wenige getrennte Frequenzbereiche ergänzen, etwa Präsenz/Zischeln und obere Cymbal-/Air-Region. Bestehende breite, stereo-verknüpfte Hüllkurve bleibt Legacy-Modus. Neue Gainkurven zeitlich glätten, Transienten schützen, Grenzen und gemessene Reduktion anzeigen. Nicht dieselbe Höhenabsenkung gleichzeitig in PRE, HF-Reparatur, Auto-EQ und POST unbemerkt stapeln.

Hybrid-Vergleich mit Pegel- und Zeitabgleich; mögliche SR-Verzögerung zunächst messen. Optionaler Delay-Ausgleich nur bei ausreichend sicherer Korrelation im gemeinsam vorhandenen Frequenzband. Keine automatische globale Phasenkorrektur aus unsicheren hochfrequenten Rekonstruktionen.

Abnahme mit trockenen Hi-Hats, langen Becken, Stimme/S-Lauten, Ambient, Bass, verzerrten Gitarren, perkussiven Transienten und sauberen Quellen. Lautheitsangepasstes A/B und Differenzsignal; ein universelles „besser“-Preset ist nicht das Ziel.

## 8. Neuer selbstgebauter parametrischer EQ

> **Übergabestatus (11.09.2026):** Die drei Audio-Tool-Themen aus den Abschnitten 8–10 wurden als additive Implementierung umgesetzt. Vorhanden sind `eq_config.py`, `audio_eq.py`, `audio_analysis.py`, `audio_auto_eq.py`, `audio_compressor.py`, `audio_limiter.py`, `audio_mastering.py`, die Registrierung in `__init__.py`, die EQ-Oberfläche unter `web/audio_eq.js` sowie die Dokumentation in `AUDIO_MASTERING.md` und `web/docs/`. Die bestehenden Node-Verträge bleiben erhalten. Die Implementierung soll von DeepSeek nicht dupliziert oder ersetzt werden; offen bleibt nur die spätere Integration in optionale Produktions-Metadaten und die manuelle Abnahme in einer laufenden ComfyUI-Instanz.

### E01 — DSP und serialisierbare Einstellungen

- [x] **P1 · L · Risiko mittel.** Neue `audio_eq.py`, `eq_config.py`; Registrierung in `__init__.py`, Tests und Node-Dokumentation.

  **Done (2026-09-11) — English summary.** Implemented in a parallel ChatGPT
  session at the maintainer's request (IMPROVE-TODO section 8); integrated and
  verified here.

  * `audio_eq.py` registers **`MiniMaxParametricEQ`** ("Parametric EQ – 8 Bands",
    category `MiniMax Music Production Toolkit/mastering`), outputs
    `AUDIO` + `eq_report_json` + `info`. Peak/shelf/high-pass/low-pass/notch,
    gain ±12 dB, Q 0.2–10, shelf slope 0.25–1, explicit preamp with **no hidden
    normalization**, per-band bypass and Undo. `eq_config.py` holds the
    serializable settings (JSON is the canonical state) and the SOS design.
  * CPU only — no GPU, model or download; bypass/unity returns the original
    AUDIO unchanged, active processing preserves sample count, rate, batches and
    channels.
  * **Integration verified here:** the node is registered (`__init__.py`,
    **31 nodes total**), `tests/fixtures/node_contracts.json` is current for it
    (`dump_node_contracts.py --check`), `web/docs/MiniMaxParametricEQ.md` exists
    (release validator requires it), `validate_release.py` is green, and the
    installed ComfyUI copy is byte-identical (814 files) with a clean
    `IMPORT OK - nodes: 31` under the ComfyUI venv Python.
  * **What I did not verify:** the DSP itself beyond the JS/Python coefficient
    parity suite, and any listening judgement — `AUDIO_MASTERING.md` documents
    the remaining manual acceptance.

Node-ID-Vorschlag `MiniMaxParametricEQ`. Eingaben: AUDIO, `eq_settings_json` STRING, Bypass; Ausgaben: AUDIO, `eq_report_json` STRING, `info` STRING. Ein gemeinsamer versionierter JSON-Vertrag ist die alleinige Parameterebene für manuelle UI und Auto-EQ:

```json
{"schema":"minimax_eq_v1","preamp_db":0.0,"bands":[
  {"id":"band-1","enabled":true,"type":"peak","frequency_hz":1000.0,"gain_db":0.0,"q":1.0}
]}
```

Bis zu acht Bänder: Peak, Low-/High-Shelf, Hoch-/Tiefpass und Notch. Peak-Gain zunächst ±12 dB, Q 0,2–10; Shelf verwendet im JSON ausdrücklich `slope` mit Default 1 und Bereich 0,25–1, nicht den Peak-Q. Frequenz 20 Hz bis min. 20 kHz und 0,45×Samplerate; bei niedrigen Raten verständliche Validierung. Passfilter in der ersten Version 12 dB/Oktave pro Biquad; höhere Steilheit erst als explizite Kaskade. Ungültige/NaN-Werte, überzählige Bänder und unbekannte Schemas ablehnen.

Koeffizienten nach RBJ-Biquadformeln berechnen, durch a0 normalisieren, als SOS speichern. Mathematische Referenz: [W3C Audio EQ Cookbook](https://www.w3.org/TR/audio-eq-cookbook/). Koeffizienten float64; Signalverarbeitung zuerst float64-State mit float32-Ausgabe als Qualitätsreferenz. Polstellenstabilität prüfen. Mit `scipy.signal.sosfilt` entlang der Zeitachse arbeiten, pro Batch/Kanal unabhängigen State weiterreichen. [SciPy SOS-Filter](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfilt.html).

Zunächst kausaler Minimum-Phase-EQ, kein `sosfiltfilt`: Vorwärts/Rückwärts würde Amplitudenantwort/Gain verändern. Keine versteckte Peaknormalisierung. Bypass und alle deaktivierten Bänder liefern die ursprüngliche AUDIO unverändert; aktiver EQ besitzt eigenen Output. Sampleanzahl und Rate unverändert, Startzustand/Trackgrenzen dokumentieren. Vorverstärkung ausdrücklich sichtbar; Vorschlag für Headroom aus maximalem Kurvengain, aber kein garantierter True-Peak-Schutz.

**Abnahme:** Impulsantwort, logarithmischer Sweep, Sinus pro Band, DC/Nyquist-Nähe, extreme erlaubte Q/Gains, lange Signale, Block-/Vollsignalparität, identische Behandlung beider Stereokanäle. Frequenzgang innerhalb 0,1 dB zur mathematischen Referenz im geprüften Bereich; keine NaNs/instabilen Pole.

### E02 — Gemeinsame Audioanalyse

- [x] **P1 · M · Risiko mittel.** Neues `audio_analysis.py`; Schnittstelle zu `audio_release_prep.py`, E04 und M03.

  **Done (2026-09-11) — English summary.** Implemented in the parallel ChatGPT
  session (section 8); integrated and verified here. `audio_analysis.py` is the
  shared analysis basis: band/response analysis and channel-power comparison
  that is safe for anti-phase stereo, with unreliable frequencies ignored, used
  by the Auto-EQ proposals (E04) and the mastering measurement path (M03).
  Covered by the mastering test suite (`tests/test_audio_mastering_tools.py`),
  which runs under the standard suite (603 tests, OK). I verified the module is
  present, importable and exercised by that suite — not the numerics in detail.

Analysefunktionen getrennt von Node/UI: Sample-Peak, integrierte LUFS, LRA, True Peak, Peak-to-Loudness-Verhältnis und geglättetes Leistungsspektrum. LUFS/TP zunächst über den bestehenden FFmpeg-Messpfad beziehen, damit nicht gleichzeitig ein unvalidierter eigener Loudness-Meter eingeführt wird. Bericht enthält Algorithmusversion, Rate, Kanalbelegung, analysierten Abschnitt und gültige/ungültige Messwerte.

Spektrum über blockweises Welch-Verfahren, nicht eine STFT des gesamten Tracks im RAM. Stereo über gemittelte **Leistung** statt Mono-Summensignal analysieren, sonst verschwinden gegenphasige Anteile. Stille-/Near-Silence-Gate und mindestens genügend gültige Frames verlangen. Log-Frequenzraster mit beispielsweise 1/6-Oktav-Glättung; Auflösung, Fenster und Überlappung festlegen und versionieren. Kompakte Kurven für UI, keine Millionen Audiowerte in JSON.

### E03 — EQ-Bedienung

- [x] **P1 · M · Risiko mittel.** Neues `web/audio_eq.js`, gemeinsame UI-Helfer und Browser-/Serialisierungstests.

  **Done (2026-09-11) — English summary.** Implemented in the parallel ChatGPT
  session (section 8); integrated and verified here. `web/audio_eq.js` plus the
  shared `web/eq_dsp.js` provide the curve editor: numeric controls, a graph
  preview (cyan = current curve, gold = last actual response, explicitly not
  realtime audio), per-band bypass and Undo. Connected settings are read-only
  in the editor, and the rendered first batch item is shown after execution.
  **Verified here:** `node --check` passes for both files;
  `tests/test_audio_eq_frontend.mjs` passes (72 EQ coefficient cases match
  Python, plus response and serialization). Integration fix made here: that
  suite and the optional Playwright browser check
  (`tests/test_audio_eq_browser.mjs`) are now part of the release gate in
  `scripts/validate_release.py` — previously they ran nowhere. The browser check
  now skips cleanly (exit 0, with the install hint) when Playwright is absent
  instead of crashing with `Cannot find module 'playwright'`.

Logarithmische Frequenzachse, dB-Achse, Gesamtkurve und einzelne Bänder. Ziehen ändert Frequenz/Gain; Q über eigenes Feld beziehungsweise definierte Geste. Immer numerische Eingabe, Tastatur, Band-Bypass, Reset und Undo anbieten. Kein reiner Farbcodierungszwang. Anzeige skaliert mit schmalen Nodes und hoher DPI.

JSON-Widget ist kanonisch und headless verwendbar; Canvas ist nur Editor. UI-Änderungen atomar in den JSON-Vertrag schreiben, Dirty-State setzen; Laden eines Workflows rekonstruiert die Kurve aus gespeichertem JSON. Frequenzgangdarstellung entweder aus denselben dokumentierten Formeln oder Backendkurven; Paritätstest zwingend. Native ComfyUI-Widgetreihenfolge nicht durch zusätzliche Steuerknöpfe beschädigen. Offline-Renderstatus nicht als Echtzeit-Audiofilter verkaufen.

## 9. Neuer Auto-EQ

### E04 — Referenz-/Zielkurvenabgleich mit begrenzten Korrekturen

- [x] **P1 · L · Risiko hoch.** Neues `audio_auto_eq.py`; E01/E02 verwenden; neue UI/Tests.

  **Done (2026-09-11) — English summary.** Implemented in the parallel ChatGPT
  session (IMPROVE-TODO section 9); integrated and verified here.

  * `audio_auto_eq.py` registers **`MiniMaxAutoEQAnalyze`** ("Auto-EQ –
    Analyze / Propose"): it proposes conservative EQ settings and **does not
    process audio**; the settings output feeds `MiniMaxParametricEQ`. Reference
    mode requires a reference AUDIO; warm/bright tilt are labelled as creative
    choices, not as an objectively correct spectrum. Silence, very short or
    narrow-band input returns unity with an explanation instead of a bogus
    correction. One reference can serve all source batch items, or the batch
    counts must match; multiple items produce a `minimax_eq_batch_v1` envelope
    the EQ node consumes directly. Outputs `eq_settings_json`, `analysis_json`,
    `info`; CPU only.
  * **Integration verified here:** registered (31 nodes), contract snapshot
    current, `web/docs/MiniMaxAutoEQAnalyze.md` present, `validate_release.py`
    green, and the EQ frontend/browser suites are wired into the gate (see E03).
  * **What I did not verify:** whether the proposals sound better on real
    material — that is a listening judgement, and the task's own acceptance
    (generate with L01 models, compare blind) is still open.

Node `MiniMaxAutoEQAnalyze`: AUDIO, optional Referenz-AUDIO, Zielmodus, Stärke, Maximalgain, maximale Bandzahl, Frequenzgrenzen; Ausgaben `eq_settings_json`, `analysis_json`, `info`. Anwenden erfolgt über denselben parametrischen EQ. Keine zweite Filterimplementierung. Ein optionaler Komfort-Node darf beide Schritte kombinieren, nachdem die getrennte Version funktioniert.

Algorithmus:

1. Quelle und Referenz getrennt nach E02 analysieren. Für die Analyse auf gemeinsame Rate bringen oder die Frequenzraster interpolieren; Quelle zum Rendern nicht unnötig resamplen. Stille, zu kurze Referenz und ungültige Kanäle melden.
2. Globalen Pegelunterschied aus dem Vergleich entfernen, z. B. robusten Median der dB-Differenz im gültigen Band abziehen. Auto-EQ soll Tonalität, nicht Lautheit angleichen.
3. Geglättete Differenz auf gemeinsam abgedecktem Frequenzband berechnen. Konfidenz aus aktiven Frames/Energie/zeitlicher Streuung bestimmen. Keine Boosts in Stille, Rauschen oder jenseits der Quellbandbreite. Keine theoretisch „fehlenden Höhen“ rekonstruieren.
4. Stärke 0–100 %, Default 50 %; konservative Korrektur zunächst ±3 dB, maximal ±6 dB ausdrücklich wählbar. Erste Version maximal sechs breite Peak/Shelf-Bänder, Q etwa 0,3–2. Keine schmalen Kerbfilter auf jeden Spektralzacken.
5. Größte breite Residuen zur Initialisierung wählen; Frequenzen logarithmisch parametrisieren. Bounded `scipy.optimize.least_squares` minimiert gewichteten Fehler der **tatsächlichen SOS-Gesamtantwort** gegen Zielkurve. Regularisierung für große Gains/hohes Q, begrenzte Iterationen, fester deterministischer Start; bei schlechtem Fit weniger Bänder oder unveränderte Einstellungen mit Hinweis liefern. [SciPy Optimierer](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html).
6. Nur Verbesserungen akzeptieren, die den gewichteten Zielfehler reduzieren. Report: Vorher/Ziel/erwartete Kurve, Bandliste, Fitfehler, Konfidenz, analysierte Dauer und Grenzen. Anschließend tatsächliche Ausgabe bei Abnahme nachmessen.

Zielmodi zunächst „Referenztrack“ und ausdrücklich beschriftete breite tonale Zielkurven. Eine horizontale FFT-Linie ist kein allgemeines musikalisches Ideal. Ohne Referenz keine objektiv „korrekte“ Masterkurve behaupten. Keine Raum-/Lautsprecherkorrektur versprechen; das ist eine andere Messaufgabe.

**Abnahme:** Quelle=Referenz ergibt nahezu Unity; identische Quelle mit bloßem Gainunterschied ebenfalls. Bekannte breite EQ-Verfärbung wird näherungsweise korrigiert, unbekannte Musik nicht überangepasst. Gegenphasiges Stereo, Bass-only, Stille, stark unterschiedliche Arrangements, kurze Referenzen und geringe Bandbreite testen. A/B lautheitsangepasst; Vorschlag bleibt manuell editierbar.

## 10. Mastering-Kompressor mit LUFS-Ziel

### M01 — Eigener Stereo-Kompressor

- [x] **P1 · L · Risiko hoch.** Neue `audio_compressor.py` und `audio_mastering.py`; Tests für Kennlinie und Zeitverhalten.

  **Done (2026-09-11) — English summary.** Implemented in the parallel ChatGPT
  session (IMPROVE-TODO section 10); integrated and verified here.

  * `audio_compressor.py` + `audio_mastering.py` register
    **`MiniMaxMasteringCompressor`** ("Mastering Compressor – LUFS / True
    Peak"), outputs `AUDIO` + `mastering_json` + `info`. A **separate**
    stereo-linked compressor (ratio/knee/attack/release/threshold, sidechain HP
    affecting the detector only) — not a reuse of the limiter curve.
    `compressor_enabled=false` still normalizes and limits; `bypass=true`
    returns the input unchanged, without metering or SRC. Mono/stereo and
    independent batch items are supported, multichannel layouts are rejected.
  * The semantics of the existing `AudioReleasePrep` (static gain) are
    **unchanged**, and the documentation tells users to keep it on Bypass or
    SRC-only before this node rather than having two stages fight each other.
  * **Integration verified here:** registered (31 nodes), contract snapshot
    current, `web/docs/MiniMaxMasteringCompressor.md` present,
    `validate_release.py` green, installed copy byte-identical with a clean
    31-node import, and the suite (`tests/test_audio_mastering_tools.py` +
    603-test run) is green. Metering uses real FFmpeg where present and skips
    those checks explicitly otherwise.
  * **What I did not verify:** measured LUFS/true-peak numbers against an
    external reference on real material — the doc's manual acceptance.

Neue Node-ID `MiniMaxMasteringCompressor`; bestehendes `AudioReleasePrep` nicht umdeuten. DSP-Funktionen unabhängig von ComfyUI. Eingaben im erweiterten Modus: Threshold, Ratio, Knee, Attack, Release, Sidechain-HP, Inputgain, Kompressor-Bypass; zusätzlich LUFS/True-Peak aus M03. Erster Umfang: Mono/Stereo, andere Kanalbelegungen ausdrücklich ablehnen statt falsche Surround-Lautheit berechnen.

Feed-forward, stereo-linked: Sidechain optional hochpassfiltern, geglätteten RMS-Detektor oder ausdrücklich gewählten Peak-Detektor bilden. Gemeinsame Gainkurve, im Peakmodus Maximum der Kanäle statt Monosumme. Für RMS Energie mitteln; Filter-/Detektorstate je Track/Batch zurücksetzen und über interne Blöcke fortsetzen.

Soft-Knee in dB: mit Eingangspegel x, Threshold T, Ratio R und Knee W ist Reduktion 0 unter T−W/2, oberhalb T+W/2 gleich `(1/R−1)*(x−T)`, dazwischen `(1/R−1)*(x−T+W/2)^2/(2W)`; W=0 separat behandeln. Danach Gainreduktion mit klar dokumentierten Attack-/Release-Zeitkonstanten glätten; stärkere Reduktion benutzt Attack, Erholung Release. Gain nie unbeabsichtigt positiv; Makeup ist separater Schritt.

Rekursive Hüllkurven nicht fälschlich mit beliebigen unabhängigen NumPy-Blöcken „vektorisieren“. Eine kleine getestete Referenzimplementierung und optional beschleunigter Kernel, z. B. Numba bei vorhandener Installation; kein verpflichtendes JIT-Paket für Import/Discovery. Falls die Python-Referenz für lange Tracks zu langsam ist, zuerst optimierten Kernel abschließen, nicht einen Python-Sampleloop als fertiges schnelles Produkt ausliefern. Kompilierkosten in Kaltstart berücksichtigen.

Konservatives Startpreset als Vorschlag: Ratio 1,5:1, Knee 6 dB, Attack 20 ms, Release 150 ms, Sidechain-HP 80 Hz. Threshold in Vorschau auf geringe Reduktion einstellen; kein fixer Threshold funktioniert für alle Eingangspegel. Report zeigt maximale/mittlere Reduktion und Zeitanteil starker Kompression.

### M02 — True-Peak-Limiter als eigener DSP-Baustein

- [x] **P1 · L · Risiko hoch.** Neues `audio_limiter.py`; wird von M03 genutzt, nicht mit der Kompressorkennlinie vermischt.

  **Done (2026-09-11) — English summary.** Implemented in the parallel ChatGPT
  session (section 10); integrated and verified here. `audio_limiter.py`
  provides an **oversampled lookahead true-peak limiter** as its own DSP block,
  consumed by M03 and deliberately kept separate from the compressor curve.
  Its release parameter means the time for 12 dB of linear recovery (the
  compressor's release is an exponential time constant — the docs state both so
  the two are not confused). The output true peak is measured independently and
  residual overshoots are corrected and rechecked; the docs note that a later
  MP3 encode can create new peaks that this measurement does not cover.

Lookahead und gemeinsame Stereo-Gainkurve. Zunächst 4× Oversampling für 44,1/48 kHz mit definierter bandbegrenzter Polyphase-FIR; Filterstate, Randpadding und Verzögerung exakt dokumentieren. Lookahead im Bereich 1–5 ms; vorausschauendes Spitzenfenster mit O(N)-Verfahren, nicht Python-Maximum über jedes vollständige Fenster. Reduktion vor dem Peak, kontrollierte Releasekurve, Ceiling niemals durch Glättung überschreiten lassen. Rückresampling kann neue Peaks erzeugen: finale unabhängige TP-Messung ist verpflichtend, Oversampling allein kein Beweis.

Sampleanzahl nach Latenzkompensation exakt erhalten, Anfang/Ende einschließlich Tail testen. Keine sampleweise harte Begrenzung als True-Peak-Limiter deklarieren. Bei unzureichender Implementierungsqualität vorübergehend einen klar ausgewiesenen FFmpeg-Limiteradapter anbieten; eigener Kompressor bleibt eigenes DSP. Nicht zwei ungetestete Limiter gleichzeitig stapeln.

**Abnahme:** Inter-Sample-Peak-Testsignale, einzelne Impulse, Bassimpulse, dichtes Material, Stereo-Asymmetrie, Stille und Blockgrenzen. Intern konservative Ceilingreserve; gemessene Ausgabe maximal Ziel+0,1 dBTP im Testkorpus. Bei Überschreitung korrigieren und erneut messen oder verständlich fehlschlagen, nicht „erfolgreich“ melden.

### M03 — LUFS-Regelung und Pipelineintegration

- [x] **P1 · L · Risiko hoch.** `audio_mastering.py`, E02, M01/M02, später Metadatenintegration V01.

  **Done (2026-09-11) — English summary.** Implemented in the parallel ChatGPT
  session (section 10); integrated and verified here. `audio_mastering.py`
  combines E02 analysis with M01/M02 and adds **measured LUFS targeting**
  (FFmpeg or imageio-ffmpeg for metering) plus a `mastering_json` report with
  target/actual values and `target_reached`. −14 LUFS / −1 dBTP is documented as
  a selectable starting point, **not** a universal delivery standard, and a
  gain/limiter budget may intentionally leave the output quieter. The final
  sample rate is chosen here; users are told not to resample or normalize
  afterwards, and the save-gain is not allowed to work secretly against the
  master.
  **Integration verified here:** node registered (31), contract snapshot
  current, node doc present, `validate_release.py` green, installed copy
  byte-identical with a clean 31-node import, 603 tests OK.
  **Still open from this task:** the additive production-metadata integration
  (effective profile, EQ/mastering reports) is the V01 deliverable and is not
  done yet.

Verarbeitung: optionale Restaurierung → EQ → Kompressor → finale Samplerate → Makeup/Limiter → finale LUFS-/TP-Messung → Export. Dadurch wird TP am tatsächlichen Zielformat geprüft. Keine erneute ungeprüfte SRC nach dem Limiter.

LUFS-Ziel ist kein Thresholdregler. Ablauf pro Batchitem:

1. Eingang messen, Kompressor mit gewählten Parametern anwenden.
2. Kompressorausgang am Ziel-SR messen, benötigten Gesamtgain `target_I − measured_I` berechnen.
3. Gain und Limiter anwenden, Ausgabe neu messen. Höchstens drei deterministische Iterationen; immer vom unveränderten Kompressorausgang neu rendern, nicht vorherige bereits limitierte Ausgabe erneut bearbeiten.
4. Lautheitsabweichung ≤0,3 LU als anfängliches Ziel, zusätzlich TP-Grenze einhalten. Bei starker nötiger Begrenzung, ungültiger Messung oder fehlender Konvergenz ausdrücklich „Ziel nicht erreicht“ mit Istwerten melden. Keine unbegrenzte Verstärkung bei Stille.

UI: Ziel-LUFS, Ceiling-dBTP, Kompressionsstärke/Advanced und tatsächliche Werte nebeneinander. -14 LUFS / -1 dBTP ist ein wählbarer Einstieg, kein universeller Plattformstandard. Report enthält Ziel/Ist-LUFS, LRA, TP, Kompressor-/Limiterreduktion, Makeup, Iterationen, Samplerate, Algorithmusversion und Zielerreichung. Ungültige Werte JSON-konform als `null` mit Ursache, nicht `NaN`/Infinity.

`AudioReleasePrep` bleibt im neuen Masteringworkflow auf „Bypass“ oder wird vor den finalen Master auf reines SRC beschränkt. Bestehende statische LUFS-Workflows bleiben unverändert. Saver-Normalisierung nicht heimlich gegen den Master arbeiten lassen; tatsächlichen Save-Gain protokollieren. Lossy MP3 nach Dekodierung optional erneut TP messen; Codec kann Peaks verändern. Quelle nie mehrfach verlustbehaftet encodieren.

Messreferenz bleibt zunächst vorhandenes FFmpeg-Loudness-Meter; dessen dynamische `loudnorm`-Ausgabe nicht als eigenen Kompressor ausgeben. [FFmpeg loudnorm](https://ffmpeg.org/ffmpeg-filters.html#loudnorm).

## 11. Prompts verbessern, ohne bewährte Ergebnisse zu verlieren

### P01 — Wirklich kompakte, versionierte Systemprompts und Konfliktauflösung

- [x] **P1 · L · Risiko mittel.** `prompts/system/`, `prompt_sources.py`, `prompt_metadata.assemble_structured_user_prompt`, `minimax_prompt_source.py`, Prompttests.

  **Done (2026-09-11) — English summary.** A genuinely compact opt-in core, an
  explicit-block brief, and a conflict report that runs before generation.

  * **`prompts/system/minimax-music3-compact-core.txt`** (new, opt-in, **~830
    words**): the 11 existing templates are untouched, and this one is well under
    40% of their size - pinned by tests that compare characters *and* the estimated
    LLM input tokens (`llm_sampling.estimate_input_tokens`) against
    `minimax-music3-concise.txt` and `production.txt`. So "concise" is now
    measurably shorter instead of the same 25k-character text with an extra
    instruction. It keeps the four-section output contract and documents the
    conflict precedence, the verbatim-lyrics rule and the fact that the 2:1
    instrumental ratio is a **heuristic, not a model guarantee**.
  * **`assemble_block_brief()`** produces the explicit brief the task asks for:
    `Constraints:` (the structured selection plus the sentence that constraints
    are authoritative and a contradiction must not be appended), `Creative
    description:`, and an optional `Provided lyrics:` block marked "use verbatim,
    do not rewrite, shorten or extend". `custom` and empty values stay omitted
    ("custom" means *no instruction*, not *anything*). The historic
    `assemble_structured_user_prompt()` is unchanged, so saved workflows keep
    their exact prompt shape - asserted by a test that the old path does not grow
    blocks.
  * **`detect_brief_conflicts()`** reports the known contradictions *before*
    generation instead of appending contradictory sentences: a requested element
    (bells, chimes, glockenspiel, cymbals, shimmer, metallic) against cautious
    wording in the system prompt → *the user requirement wins*; diffuse wishes
    (ambient surfaces, reverb tails) are only looked for in the free-text
    description, so a **genre named "Ambient" does not fire** (a real false
    positive my first rule table produced and a test now pins); an
    instrumental brief with supplied lyrics → *the lyrics win*; the
    "positive-only image prompt" wording → the mandatory no-text line is itself
    negative, so it means "one prompt without a separate negative field"; and a
    duration mismatch (e.g. 360 s in the brief vs 300 s in the settings) is shown
    as **both values, with nothing changed automatically**. A clean brief reports
    nothing.

  **Tests:** `tests/test_prompt_conflicts.py` (21 tests) covers the compact
  core's size, its token advantage, the kept output contract, the 12 bundled
  templates, a static pass over the 200+ user templates, the block brief
  (order, precedence sentence, `custom` omission, verbatim lyrics, legacy path
  unchanged) and every conflict rule including the quiet cases. Suite:
  **774 tests, OK**.

  **Contract note:** the new template adds one option to the system-prompt combo
  of `MiniMaxLLMTemplateV16` and `MiniMaxStructuredPromptV20`, so
  `tests/fixtures/node_contracts.json` was regenerated (additive option, same
  widget position - saved workflow values stay valid).

  **Still open in this task:** the acceptance's second half - generating with L01
  models and comparing length/tokens, format rate, language/genre/lyrics fidelity
  and creative quality blindly - needs the models on the user's machine. "Shorter
  alone is not success" is respected: no template was replaced, the compact core
  is strictly opt-in, and its quality claim stays unproven until that comparison
  exists. Optimising the *other* ten templates is also not done.

Bestehende 11 langen Vorlagen erhalten. Neue opt-in Varianten aus gemeinsamem redaktionellen Kern erstellen: Produktionsformat, instrumentale/vokale Regeln, sprachliche Vorgaben, Arrangement, Titel/Bildprompt. Stilhinweise separat kurz halten. Ziel zunächst 800–1.200 Wörter für den Kern, danach an tatsächlicher Qualität messen. „Concise“ muss tatsächlich weniger Eingabetokens erzeugen, nicht denselben 25k-Zeichen-Text mit Zusatzanweisung.

Konkrete Konflikte beheben: „positive-only Image Prompt“ präzisieren als ein einzelner Prompt ohne separates negatives Eingabefeld, denn die obligatorische No-text-Zeile ist selbst negativ formuliert. Starre Anti-Metallic-/Anti-Reverb-Regeln als optionales „artifact cautious“-Profil, nicht als pauschale Abschwächung von Glockenspiel, Becken oder gewünschten Ambientflächen. Nutzeranforderungen haben Vorrang vor Stilheuristiken. Die 2:1-Instrumentalabschnittsregel ist eine vorhandene empirische Heuristik, keine harte Modellgarantie; zunächst als kompatibles Preset erhalten und evaluieren.

Neuer User-Brief mit expliziten Blöcken `Constraints`, `Creative description`, optional `Provided lyrics`. Strukturierte explizite Auswahl gewinnt gegen widersprechende Freitextvorschläge; `custom` bleibt „keine Vorgabe“. Konflikte vor Generierung anzeigen, nicht zusätzliche widersprüchliche Sätze anhängen. Dauerziel und tatsächliches `max_duration` gemeinsam anzeigen; Prompt begrenzt bisher auf 300 s, Settings erlaubt 360 s. Alte Einstellungen nicht automatisch reduzieren; neues Profil verwendet konsistente Grenzen.

Ausgabeformat bleibt `[Caption]`, `[Lyrics]`, `[Title]`, `[Image_Prompt]`. Parserweiterentwicklung: benötigte Felder, erlaubte Abschnittstags, Instrumental-only-Regel und unzulässige Metaausgabe gezielt prüfen. Optional maximal ein Reparaturversuch mit kleinem Fehlerbericht; nie unbemerkt vom Benutzer gelieferte Lyrics neu dichten. JSON-/Grammar-Ausgabe nur als spätere gesonderte Variante, nicht sofort alle Parser und Vorlagen ersetzen.

**Abnahme:** Alle 239 User-Vorlagen statisch prüfen, repräsentative Auswahl mit L01-Modellen generieren. Wort-/Tokenumfang, Formatquote, Sprach-/Genre-/Lyrics-Treue und kreative Qualität blind vergleichen. Kürzer allein ist kein Erfolgskriterium.

### P02 — Echte MiniMax-Tokenzählung und sichere Grenzen

- [x] **P0 · M · Risiko mittel.** `prompt_budget.py`, `scripts/calibrate_prompt_tokens.py`, `minimax_prompt_report.py`, `MiniMaxParseExternalLLMOutputV16`.

  **Done (2026-09-11) — English summary.** Real MiniMax token counting with an
  honest fallback, plus the calibration bugfix.

  * `prompt_budget.count_prompt_tokens()` / `token_counter()` count the tokens of
    the exact text MiniMax sees (`comfy.ldm.minimax_music.prompt.build_prompt`)
    and report `method` = `tokenizer` / `tokenizer_text_only` / `estimate` with an
    `exact` flag and `estimate_covers_real` (does the heuristic stay at or above
    the measured count?). The estimate is never presented as a measurement.
  * `load_minimax_tokenizer()` reads **only** the `tokenizer_json` metadata
    tensor via `safe_open(framework="np")` — no weights, no GPU, no download —
    and caches tokenizers in a cache bounded to 2 entries keyed by checkpoint
    identity (file name + size + mtime). A changed or unreadable checkpoint
    falls back to the estimate and logs why.
  * `trim_prompt_to_budget(..., counter=...)` now accepts a real counter; the
    default `None` keeps the historical estimate path byte-identical (all 18
    pre-existing tests unchanged). With a counter the fitting decision and the
    final postcondition are exact, so the trim loop cannot stop short on dense
    scripts. `removed_lines` / `removed_sections` are reported.
  * `MiniMaxParseExternalLLMOutputV16._apply_prompt_budget()` decides with the
    measured count when a checkpoint is available and always labels the
    provenance (`prompt_tokens`, `prompt_token_count_method`, `prompt_tokenizer`,
    `prompt_tokens_estimated`, `removed_lines`, `removed_sections`).
    `trim_long_prompt=False` now says "measured" when it was measured.
  * `MiniMaxPromptReport` gained a "Token budget (MiniMax text encoder)" section
    that distinguishes measured vs estimated and warns when the estimate was
    below the measured count.
  * Docstrings corrected: the module no longer claims the estimate "always fits
    the 5000-token limit"; it documents the measured German/English calibration
    and that dense scripts (CJK, Urdu, unusual Unicode) can exceed 3.5
    chars/token. It also states explicitly that the MiniMax text-encoder budget
    and the LLM context are different tokenizers/budgets.
  * `scripts/calibrate_prompt_tokens.py`: **bugfix** — the script reported the
    *maximum* chars/token as the "worst case", but a conservative constant must
    stay at or below the **minimum** (the densest script); `max()` would have
    accepted a constant that undershoots. It now reports min/median/max with the
    minimum as the binding constraint, returns exit code 1 when the constant is
    too large, adds a `--json` mode, and the sample set is multilingual
    (English, German, Japanese, Chinese, Korean, Urdu, Russian, Hindi).

  **Tests:** `tests/test_prompt_token_count.py` (21 tests) and
  `tests/test_prompt_token_calibration.py` (8 tests) cover the measured/estimate
  labelling, the dense-script undershoot warning, the bounded identity-keyed
  cache, `tokenizer_json`-only reads, exact trimming with removal reporting, and
  the min-vs-max regression. Suite: 458 → **487 tests, OK**; `validate_release`
  OK.

Vorhandenes Verfahren des Kalibrierskripts nutzen: aus safetensors nur `tokenizer_json` über `safe_open` lesen, keine Textencodergewichte oder GPU laden. Tokenizer begrenzt nach Checkpointidentität cachen. Mit realem `build_prompt(caption, lyrics)` und passenden Special-Token-Regeln zählen. Textencoderbudget und LLM-Kontext sind zwei verschiedene Tokenizer/Budgets.

Fallback-Schätzung sichtbar als Schätzung kennzeichnen; 3,5 Zeichen/Token ist bei Urdu, CJK, ungewöhnlichen Unicodefolgen und neuen Tokenizern keine Garantie. Harte Zusicherungen in Kommentaren/Docs korrigieren. Kalibrierskript benutzt `max()` für „worst chars/token“, obwohl für eine konservative Zeichen-pro-Token-Schranke das **Minimum** relevant ist; getrennt als Bugfix korrigieren und multilingual testen.

Automatische Kürzung nur mit Bericht und Vorschau. Benutzerlyrics standardmäßig nicht still zerstören; in neuem Profil vor Musikgenerierung gezielte Fehlermeldung oder ausdrücklich erlaubte Kürzung. Legacy-Kürzungsverhalten bleibt kompatibel, aber Report nennt entfernte Zeilen/Abschnitte. Grenztests direkt unter/über 5.000 echten Tokens, kein teures Modell nötig.

## 12. Benutzeroberfläche als Produkt

### U01 — Verständliche Arbeitsmodi und Ergebnisse

- [ ] **P1 · L · Risiko mittel.** Neue fokussierte Frontendmodule; `web/prompt_ui_utils.js` weiterverwenden, `web/docs/`, `ui_help.py`.

Neue Profile „Speichersparend“, „Ausgewogen“, „Qualität“ mit Anzeige des wirksamen Modells, Devices, Kontextes und der Audioverarbeitung. Autoempfehlung und tatsächlich gewählte Einstellung unterscheiden. Advanced-Felder einklappbar, ohne gespeicherte Widgets zu löschen oder umzusortieren. Headless/API-Ausführung bleibt vollständig möglich.

Ergebnisse verständlich darstellen: Downloadstatus, Modell noch nicht installiert, tatsächliche CPU-Ausführung, belegtes Budget, LUFS-Ziel/Ist, Clipping-/TP-Warnung, Auto-EQ-Konfidenz und angewandte Filter. Ein zusammengefasster Status statt großer JSON-Textflächen; JSON-Ausgänge bleiben verfügbar. Fehlermeldungen nennen Ursache und konkrete nächste Aktion.

### U02 — Promptbibliothek schnell und zuverlässig

- [ ] **P2 · M · Risiko niedrig.** `prompt_routes.py`, `prompt_library.py`, `web/structured_prompt.js`, `web/prompt_library.js`.

  **Partial (2026-09-11) — the event-loop offload is done and tested; the index and frontend parts are not.**

  **Implemented and tested:**

  * **Synchronous file work moved off the event loop.** All three blocking calls
    in the prompt routes now run through `asyncio.to_thread`: the library scan in
    `/prompt_files`, the single-file read in `/prompt_text` and `/prompt_metadata`,
    and - the heavy one - the option aggregation that reads **every** prompt file
    (`merge_field_options(collect_file_field_values(...))`). A few thousand files
    can no longer stall ComfyUI while the UI waits for the route.
  * **Payloads unchanged:** the tests assert the same response envelopes
    (`ok`/`files`, `fields`/`description`/`unique_values`), the placeholder
    selection still returning options only, and that the blocking call really ran
    on a **different thread than the event loop**.
  * **The library size limit applies to `/prompt_metadata` too:** a file above
    `MAX_PROMPT_BYTES` selected through the metadata route now returns HTTP 400
    with the "too large" message instead of being read, and a normal file passes
    with its parsed fields.

  **Tests:** `tests/test_prompt_route_offload.py` (7 tests, driven through the
  real route handlers from the entry point with a fake host). Suite: **792 tests,
  OK**.

  **Already in place before this change (verified, not re-implemented):** the
  option aggregation is versioned and invalidated after a save
  (`library_option_version()` / `invalidate_library_options()` called by
  `/save_prompt`), and the per-field option list is bounded
  (`_LIBRARY_OPTIONS_MAX_PER_FIELD`).

  **Still open (the reason this is not ticked):**

  * a shared metadata index keyed by canonical root plus file signatures (with
    TTL/signature detection of external changes and a bounded entry count) - the
    current cache is a version counter, not a signature-checked index;
  * the frontend side: debounce, `AbortController`, coalescing repeated identical
    in-flight requests, preserving the current selection and an edited
    description across a refresh, search/filter by genre, language, vocals and
    length, and showing errors inside the node instead of only in the browser
    console;
  * the acceptance with the 239 bundled templates *and* a synthetic library of
    several thousand files (including a measured response time).

Synchronous Dateilesen/Aggregation aus async HTTP-Handlern über begrenztes `asyncio.to_thread` auslagern. Gemeinsamen Metadatenindex nach kanonischem Root und Dateisignaturen führen; Invalidierung nach Save und explizitem Refresh, externe Änderungen über TTL/Signaturen erkennen. Keine unbeschränkte Root-/Dateicache-Sammlung. Größenlimits der sicheren Bibliotheksfunktionen auch für `/prompt_metadata` anwenden.

Bestehende Request-Generationsguards behalten. Zusätzlich Debounce und AbortController, wiederholte identische In-flight-Anfragen zusammenfassen. Suche/Filter nach Genre, Sprache, Gesang und Länge; vorhandene Auswahl und bearbeitete Beschreibung beim Refresh erhalten. Fehler im Node anzeigen statt ausschließlich in Browserkonsole. Abnahme mit 239 sowie synthetisch mehreren Tausend Dateien.

### U03 — Vergleichbares Audio-A/B und Vorschauverwaltung

- [ ] **P1 · L · Risiko mittel.** Neuer `MiniMaxAudioCompare` samt `web/audio_compare.js`, E02.

Original/bearbeitet zeitlich ausrichten und gemeinsamen Wiedergabecursor nutzen. Optionaler Hör-Pegelabgleich ändert nur Preview, nicht Export. Original, bearbeitet und Delta wählbar; Delta klar als Differenzsignal kennzeichnen. Previewsegment mit Start/Dauer, CPU-/VRAM-/Zeitkosten vor Vollrender ersichtlich.

Keine vollständigen langen Tracks in JSON/Base64. Zeitlich begrenzte Previewdateien im ComfyUI-Tempbereich, sichere bestehende Dateiauslieferung, begrenztes Cachebudget und Cleanup. Cacheidentität aus Eingabeprovenienz, Segment, Parametern und Algorithmusversion; wenn Eingabeidentität nicht sicher ist, Cache miss statt falscher Preview. Browser-ObjectURLs/Eventlistener beim Entfernen der Node freigeben. Keine geheimen Previewentscheidungen als Masteringparameter speichern.

## 13. Integration, Validierung und bewusst ausgeschlossene Änderungen

### V01 — Produktdaten, Tests und Auslieferung abschließen

- [ ] **P1 · L · Risiko mittel.** `minimax_json_output.py`, `production_metadata.py`, `metadata_schema.py`, `scripts/build_public_workflow.py`, `scripts/release_common.py`, Dokumentation und Testmatrix.

  **Partial (2026-09-11) — the additive metadata integration is delivered and
  verified; the four new example workflows, the test-matrix extension and the
  real-host open/save/execute pass are not.**

  **Implemented and tested:**

  * **Additive report sections.** `build_generation_metadata()` now accepts
    `eq_report_json`, `auto_eq_analysis_json`, `mastering_json`,
    `resource_profile_json`, `llm_runtime_json`, `model_identity_json` and
    `template_version`, and stores them as new sections - `mastering.eq`,
    `mastering.auto_eq`, `mastering.chain`, `runtime.resource_profile`,
    `runtime.llm`, `models`, and `llm.template_version`. The DSP nodes already
    emit self-describing JSON (`minimax_eq_report_v1`,
    `minimax_auto_eq_report_v1`, `minimax_mastering_v1`), so the record keeps
    them verbatim instead of flattening them into new scalar fields.
  * **No schema bump, no migration.** The sections are plain additions: an
    empty input adds no key, a payload written without them is unchanged, and a
    v6 payload still migrates to v7 with the new sections intact (all three
    asserted). `CURRENT_PRODUCTION_METADATA_SCHEMA` stays `v7` on purpose - a
    structural change, not an addition, is what would need a migration.
  * **Effective and recommended stay separable.** `runtime.resource_profile`
    holds `recommended` and `effective` under separate keys with a test proving
    they cannot be confused; the record must never claim a recommendation was
    the decision.
  * **The node grew only by appended optional sockets.**
    `MiniMaxSaveProductionJSON` gained the seven inputs as `forceInput` sockets
    at the **end** of its optional group - no widget is added, so no stored
    `widgets_values` entry moves. Proven by the frozen contract snapshot: the
    optional list went 36 -> 43 entries with an identical 36-entry prefix (the
    snapshot test reported "First extra element 36: 'eq_report_json'").
  * **The public workflow was updated additively.** Node 99 now carries the
    seven inputs unlinked (the production graph has no EQ/mastering stage),
    inserted directly after `minimax_prompt_md`; `JSON_NEW_INPUT_ORDER` in
    `workflow_schema.py` was **extended**, not replaced, and a helper asserted
    that no other node, link, `last_node_id` or `last_link_id` changed.
  * **Public-example sanitising.** `production_metadata.public_safe_payload()`
    (with `contains_private_path()` / `redact_private_path()`) is a pure,
    conservative helper for any payload that leaves the machine: secret-named
    keys are dropped and absolute paths become `<path>/<file name>` while the
    processing parameters stay intact. The runtime writer deliberately does not
    sanitise - the canonical JSON beside the rendered files is the user's own
    record.
  * **Docs.** `web/docs/MiniMaxSaveProductionJSON.md` documents the seven
    inputs, what belongs in `effective` versus `recommended`, and when to call
    the sanitiser.
  * **The Audio Enhancement Lab workflow now carries the stages.** Its chain is
    `LoadAudio -> Declip -> PRE -> FlashSR -> Hybrid -> HF repair -> Auto-EQ
    (proposal) -> Parametric EQ -> POST lowpass -> Mastering -> Release Prep ->
    Save`. The auto-EQ analyses against an explicit *Warm tilt* (35 % strength,
    max 2 dB, max 4 bands) because `Reference track` without a reference raises,
    and it writes its proposal into the EQ - both nodes are bypassable and the
    EQ keeps its own widget value if the link is removed. The mastering stage
    stays at the working sample rate (`target_sample_rate="keep"`) so Release
    Prep keeps its documented 44.1 kHz / static LUFS guarantee. Verified twice:
    by walking the graph in the JSON (chain order, branch consumers, no dangling
    links) and by executing the stored widget values through the real nodes on
    synthetic audio (4 bands, max 0.97 dB; -10.45 -> -14.04 LUFS, true peak
    -9.23 dBTP, sample rate kept, no NaN/Inf).
    `NODE_MODULE` and `MODULE_NAMES` in `tests/test_node_schema_compat.py` grew
    by the three node types and their owning modules.

  **Tests:** `tests/test_production_metadata.py` grew to 22 tests (two new
  classes: `AdditiveReportTests`, `PublicSafePayloadTests`). Suite: **803 tests,
  OK** (1 skipped: mutagen). `dump_node_contracts.py --check` up to date,
  `validate_release.py` OK, privacy scan CLEAN, installed copy 831/831 files
  identical, 32 nodes, 7 routes.

  **Still open (the reason this is not ticked):**

  * the four **standalone** new workflows - CPU/low-memory text path, balanced
    music production, audio-only EQ/mastering and reference auto-EQ - which are
    also what wire the new report inputs into a saved production record
    (the Audio Enhancement Lab integration above is done);
  * the test matrix (`recommended_test_matrix.json`) and `AUDIO_PIPELINE.md`
    entries for the new nodes and reports;
  * the real-host pass: open an old saved workflow, re-save it and execute it,
    checking named and positional widgets, unknown combo values and missing
    optional dependencies.

Neue optionale Berichte für EQ, Auto-EQ, Mastering und effektives Ressourcen-/LLM-Profil additiv aufnehmen. Alte Felder/Schemata weiter lesbar; Migration nur bei tatsächlich erforderlichem Strukturwechsel. Modellrevision/Hash, Templateversion und tatsächliche Parameter zur Reproduzierbarkeit aufnehmen, keine HF-Tokens oder privaten Absolutpfade in öffentliche Beispiele exportieren.

Neue Workflows zusätzlich liefern: CPU/speichersparender Textpfad, ausgewogene Musikproduktion, Audio-only EQ/Mastering und Referenz-Auto-EQ. Vorhandene Workflows erhalten. Package-Policy und `validate_release` müssen neue Python-/JS-Dateien, optionale Kataloge, Node-Dokumentation und Presets einschließen; Test-Nodezählung bei **additiven** Nodes gezielt erweitern, nicht die alten Vertragsfixtures blind ersetzen.

Verbindliche Tests für jede Lieferung:

- Bestehende Python-Unittests und `tests/test_structured_prompt_frontend.mjs`; reale Import-/Node-Discovery in unterstützter ComfyUI-Umgebung.
- Alte gespeicherte Workflows öffnen, erneut speichern, ausführen; benannte und positionsbasierte Widgets, unbekannte Combowerte und fehlende optionale Abhängigkeiten prüfen.
- DSP unabhängig von UI testen; Signaltests sind wichtiger als Tests, die nur dieselbe Formel kopieren. Blockparität, Nullsignal, kurze Signale, NaN/Inf, extremes erlaubtes Setting und Eingabe-Unveränderlichkeit.
- Lautheits-/TP-Ergebnisse gegen unabhängige Referenz/Testsignale; final exportierte FLAC/WAV und dekodierte MP3 prüfen. Kein Qualitätsurteil allein anhand einer Wellenformgrafik.
- Downloadtests ohne echte große Downloads automatisieren; zusätzlich dokumentierter manueller Download eines ausgewählten realen Modells und Offline-Wiederverwendung.
- Wiederholte Modellwechsel, Abbruch und zehn vollständige Durchläufe; Ressourcen wieder verfügbar und keine steigende Sitzungsspeicherung.
- Neue Module dürfen Node-Discovery ohne CUDA, llama-cpp-python, optionalem Downloader oder JIT nicht blockieren. Fehlende optionale Funktion erst bei Nutzung verständlich melden.

**Nicht ändern:** bestehende kompatible Namen/Pfade, statische Release-Prep-Semantik, bewährte aimdo-Freigabe ohne Nachweis, Vendor-Trainingsteile ohne Bezug zum Inferenzpfad, generierte Musik durch still geänderte Seeds, Bibliotheksinhalt durch massenhaftes Umschreiben, verlustfreie Originalausgaben und kanonische Produktions-JSON-Zuordnung. Keine Hardware-Aufrüstung als Voraussetzung; keine GPU-Pflicht für EQ/Auto-EQ/Kompressor. Kein automatisches globales Leeren fremder Modelle durch UI-Inspektion.

### Zweiter Prüfdurchgang

Beim zweiten Durchgang wurden besonders Workflow-Verbindungen, Bibliotheksrouten, Produktions-JSON, Vertragsfixtures, Release-Policy, vorhandene Promptvarianten sowie der Vendor-VAE/Vocoder-Pfad gegengeprüft. Dabei zusätzlich berücksichtigt: fehlende echte Preflight-Barriere, voreilig angebotene GGUF-Projektoren, statische LUFS-Semantik, falsche Extremwertwahl im Tokenkalibrierskript und bereits vorhandene Streaming-/Cacheverbesserungen. Laufzeitmessung, native Backendunterstützung und Hörqualität bleiben ausdrücklich Implementierungs-/Abnahmeaufgaben.

## 14. Entscheidende Implementierungsskizzen

Die folgenden Ausschnitte sind technische Startpunkte für die genannten Aufgaben, kein bereits integrierter Produktionscode. Fehlergrenzen, Backendadapter und Tests aus den Aufgaben gehören weiterhin dazu. Keine dieser Funktionen verlangt eine GPU.

### E01: ein Peak-Band als normalisierte SOS-Zeile

```python
import math

def peak_sos(sr: int, frequency_hz: float, gain_db: float, q: float):
    values = (float(sr), frequency_hz, gain_db, q)
    if not all(math.isfinite(v) for v in values):
        raise ValueError("EQ parameters must be finite")
    if sr <= 0 or not 20.0 <= frequency_hz <= min(20_000.0, 0.45 * sr):
        raise ValueError("EQ frequency outside supported range")
    if not -12.0 <= gain_db <= 12.0 or not 0.2 <= q <= 10.0:
        raise ValueError("EQ gain or Q outside supported range")
    a = 10.0 ** (gain_db / 40.0)
    w = 2.0 * math.pi * frequency_hz / sr
    alpha = math.sin(w) / (2.0 * q)
    c = math.cos(w)
    a0 = 1.0 + alpha / a
    return [
        (1.0 + alpha * a) / a0, -2.0 * c / a0,
        (1.0 - alpha * a) / a0, 1.0,
        -2.0 * c / a0, (1.0 - alpha / a) / a0,
    ]
```

Shelf/Notch/Passfilter separat ergänzen. Für Q=1/Gain=0 muss die Übertragungsfunktion Unity sein. Nicht in der Oberfläche berechnete Koeffizienten ungeprüft übernehmen: Backend validiert die Parameter und berechnet selbst.

### E01/A03: blockweises SOS ohne Zurücksetzen an Blockgrenzen

```python
def filter_owned_bct(x, sos, block_frames=65_536):
    import numpy as np
    from scipy.signal import sosfilt

    if x.ndim != 3 or x.shape[-1] == 0 or block_frames <= 0:
        raise ValueError("Expected nonempty BCT audio and positive block size")
    sos = np.asarray(sos, dtype=np.float64)
    out = np.empty(x.shape, dtype=np.float32)
    for b in range(x.shape[0]):
        for c in range(x.shape[1]):
            # Zero initial state: defined offline track-start convention.
            state = np.zeros((len(sos), 2), dtype=np.float64)
            for start in range(0, x.shape[-1], block_frames):
                stop = min(start + block_frames, x.shape[-1])
                block, state = sosfilt(sos, x[b, c, start:stop], zi=state)
                out[b, c, start:stop] = block
    return out
```

Der leere Bandfall wird vorher als Bypass behandelt. Ganze Ausgabe bleibt wegen ComfyUI-AUDIO-Vertrag im Speicher; nur Scratch-Speicher ist blockbegrenzt. Nicht behaupten, damit sei der gesamte Graph Streaming. Abbruchcallback zwischen Blöcken ergänzen. Bei später anderer Startzustandspolitik eine neue Algorithmusversion vergeben.

### M01: zustandsbehaftete Gainreduktion

```python
def soft_knee_reduction_db(level_db, threshold_db, ratio, knee_db):
    # Validation is required at the public boundary: ratio >= 1, knee >= 0.
    over = level_db - threshold_db
    slope = 1.0 / ratio - 1.0
    if knee_db == 0.0:
        return slope * max(over, 0.0)
    if over <= -0.5 * knee_db:
        return 0.0
    if over >= 0.5 * knee_db:
        return slope * over
    return slope * (over + 0.5 * knee_db) ** 2 / (2.0 * knee_db)

def smooth_reduction(target_db, previous_db, attack_coefficient,
                     release_coefficient):
    coefficient = (attack_coefficient if target_db < previous_db
                   else release_coefficient)
    return coefficient * previous_db + (1.0 - coefficient) * target_db
```

Koeffizient je Zeitkonstante `exp(-1/(sample_rate * seconds))`; Zeitkonstanten positiv begrenzen. Linearen Gain aus `10**(reduction_db/20)` bilden. `previous_db` über Blöcke weiterreichen. Diese Glättung ist eine Kompressorstufe, **kein** Peak-Sicherheitsbeweis für den Limiter. Die endgültige schnelle Implementierung muss dieselbe Kennlinie/Statefolge wie die Referenz liefern.

### E04: Optimierung auf der tatsächlichen Filterantwort

```python
# Pseudocode: helpers are to be implemented in eq_config/audio_auto_eq.
def residual(parameters):
    bands = unpack_bounded_bands(parameters)  # log-frequency, gain, log-Q
    sos = design_eq_sos(bands, analysis_sample_rate)
    _, response = sosfreqz(sos, worN=frequency_grid_hz,
                          fs=analysis_sample_rate)
    actual_db = 20.0 * np.log10(np.maximum(np.abs(response), 1e-12))
    curve_error = np.sqrt(confidence_weights) * (actual_db - target_delta_db)
    gain_penalty = regularization * np.asarray([b.gain_db for b in bands])
    return np.concatenate((curve_error, gain_penalty))

# least_squares(residual, initial, bounds=(lower, upper), max_nfev=200)
```

Vor Optimierung Nullkorrekturfehler berechnen. Nur Ergebnis übernehmen, wenn der **unregularisierte gewichtete Kurvenfehler** kleiner ist und sämtliche Gain-/Q-/Gesamtkurvengrenzen eingehalten sind. Summierte Bandantwort kann die Einzelbandgrenze überschreiten: Gesamtantwort ebenfalls auf ±Maximalgain prüfen und nötigenfalls Gains reduzieren/erneut optimieren. Frequenzgewichte außerhalb verlässlicher Quellbandbreite auf 0; keine Scheingenauigkeit auf leeren Bändern.

### R01/D03: Zulassung und I/O sind getrennte Entscheidungen

```text
choose_profile(request, detected_resources, catalog):
    preserve explicit model and device selections
    estimate peak RAM + per-device VRAM for each compatible candidate
    account for current free memory, not just installed capacity
    reject candidates exceeding either RAM or any device budget
    rank remaining candidates by selected speed/quality preference
    if estimates are unknown: label uncertainty; do not promise a fit
    return recommendation + reason + effective settings

ensure_artifact(entry):
    resolve existing configured paths first
    acquire lock for canonical destination
    recheck validity after acquiring lock
    if already valid: return existing path
    if downloading is disabled: return an actionable missing-model result
    verify free disk budget and initialize resumable staging
    transfer with bounded retries and cancellation
    validate expected bytes and full SHA256
    atomically promote staging to final path
    invalidate model-list cache; return verified final path
```

Der HF-Adapter darf eigene Cache-/Lockdateien des Hubclients verwenden; die Promotion in das vom Loader sichtbare Ziel bleibt eindeutig. Wenn Windows ein bereits gemapptes Modell sperrt, keinen laufenden Checkpoint ersetzen: neuen Katalogstand daneben bereitstellen oder Aktualisierung bis zum expliziten Unload verschieben.

## 15. Abschließende priorisierte Checkliste

### P0 — notwendig

- [x] B01: verlässliche Baseline und ressourcenübergreifende Testmatrix.
- [ ] R01: hardwareunabhängige Erkennung und begründete Empfehlungen.
- [x] R02: sichere Modellwechsel, begrenzte Sessions, Abbruch/Lifecycle.
- [x] P02: echte Tokenzählung, ehrlicher Fallback und Kalibrierungsbugfix.

### P1 — wesentliche Produktverbesserungen

- [x] D01–D04: korrekter Katalog, Quellen, robuste Downloads, funktionierender Preflight.
- [x] L01–L02: größenabhängige Modellprofile und echte Template-/Thinking-Unterstützung.
- [ ] A01/A03/A04: Batch-/Device-Korrektheit, weniger Audiokopien, echte optionale Zweige.
- [x] E01–E03: selbstgebauter parametrischer EQ mit Messgrundlage und Editor.
- [x] E04: nachvollziehbarer, editierbarer Auto-EQ.
- [x] M01–M03: eigener Kompressor, geprüfter Limiter und gemessenes LUFS-Ziel.
- [ ] P01: kompaktere, konsistente und getestete Promptvarianten.
- [ ] U01/U03: verständliche Profile, Status, Vorschau und lautheitsangepasstes A/B.
- [ ] V01: Metadaten, Workflows, Regressionen und auslieferbares Paket.

### P2 — vertiefende Verbesserungen

- [ ] R03: sichere optionale Residency statt unnötiger Reloads.
- [ ] A02: unnötigen FlashSR-Vocoder-/Ladespeicher reduzieren; Precision nur validiert.
- [ ] A05: begrenzter FFmpeg-Pipetransport.
- [ ] Q01: selektivere Restaurierung und bessere Konfidenzberichte.
- [ ] U02: Bibliotheksindex, nichtblockierende Routen und bessere Suche.

### P3 — nur bei messbarem Nutzen

- [ ] L03: Präfix-/MTP-/Backendexperimente mit dokumentierter Aufwand-Nutzen-Bewertung.
- [ ] Zusätzliche Compilation-/Multi-GPU-Experimente nur nach B01 und ohne neue Pflichtabhängigkeit.
