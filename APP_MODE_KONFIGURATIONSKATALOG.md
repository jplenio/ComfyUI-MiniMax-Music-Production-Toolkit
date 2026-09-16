# App-Mode – Konfigurationskatalog zur Auswahl

**Stand:** 16.09.2026 · Bestandsaufnahme des aktuellen Hauptworkflows, keine implementierte App.

Zum [Konzept und Ausführungsplan](APP_MODE_KONZEPT.md). In **Deine Wahl** bitte H, E, K, A oder G eintragen:
**H** Hauptansicht · **E** Erweitert · **K** Einrichtung · **A** Anzeige/abgeleitet · **G** Graph/Struktur.

Der Vorschlag ist keine Beschränkung. Eine Einstellmöglichkeit darf nur verborgen werden, wenn sie über
„Alle Einstellungen“ oder den vorgesehenen erweiterten Bereich erreichbar bleibt. Verbundene Werte
werden an ihrer Quelle geändert. Rein technische Verkabelung bleibt im Graphen.

Die IDs `N118.model` usw. identifizieren diese konkrete Workflow-Version. Die spätere Implementierung
soll fachliche Rollen auf diese Nodes binden und Feldnamen validieren. Aktuelle Werte sind eine
Momentaufnahme, keine bei jedem App-Start einzuspielenden Defaults.

Native Standardfelder sind **Kandidaten für direkte Bindung**, noch kein Nachweis erfolgreicher
App-Bedienung. Eigene DOM-Widgets und Aktionen benötigen P1-Prüfung beziehungsweise Adapter.
Modell-/Dateilisten sind dynamisch. Längere Texte werden hier verkürzt, nicht im Workflow.

## Produktion und Coverquelle

### N118 – 00 · Song model / Production choices

Node-Typ: `MusicProductionControl`. Vorhandene Werte und vollständige Auswahl erhalten.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N118.model` – Modell | YuE2 | MiniMax Music 3 / YuE2 / YuE2 Cover; Standardfeld; native App-Bindung prüfen | H | — |
| `N118.cover_enabled` – Artwork erstellen | True | Standardfeld; native App-Bindung prüfen | H | — |
| `N118.refinement` – Refinement | Model default | Model default / On / Off; Standardfeld; native App-Bindung prüfen | H | — |
| `N118.mastering_enabled` – Mastering | True | Standardfeld; native App-Bindung prüfen | H | — |
| `N118.artifact_reduction_enabled` – Artefaktreduktion | True | Standardfeld; native App-Bindung prüfen | H | — |

### N121 – Cover song / Source audio

Node-Typ: `MusicCoverSource`. Nur YuE2 Cover; Modus ist auch für die Generierung maßgeblich.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N121.audio` – Quelldatei | &lt;select audio&gt; | Dynamische Audiodateiliste plus native Upload-/Preview-Widgets; App-Kompatibilität prüfen | H | — |
| `N121.mode` – Modus | full | full / melody; Standardfeld; native App-Bindung prüfen | H | — |
| `N121.sheetsage2_model` – sheetsage2 model | sheetsage2_bf16.safetensors | Standardfeld; native App-Bindung prüfen | E | — |

### N37 – Generate song · selected model

Node-Typ: `MusicGeneration`. Dateifelder nach ausgewähltem Songmodell; inaktive Werte erhalten.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N37.yue2_checkpoint` – yue2 checkpoint | yue2_3b_bf16.safetensors | Standardfeld; native App-Bindung prüfen | K | — |
| `N37.minimax_model` – minimax model | minimax_music3_dit_fp16.safetensors | Standardfeld; native App-Bindung prüfen | K | — |
| `N37.minimax_encoder` – minimax encoder | minimax_music3_text_encoder_pruned_int8_convrot.safetensors | Standardfeld; native App-Bindung prüfen | K | — |
| `N37.minimax_vae` – minimax vae | minimax_music3_dav.safetensors | Standardfeld; native App-Bindung prüfen | K | — |
| `N37.tiled_decode` – tiled decode | True | Standardfeld; native App-Bindung prüfen | K | — |

## Songbrief und Prompts

### N80 – Song request · template & fields

Node-Typ: `MiniMaxStructuredPromptV20`. Vorhandene Werte und vollständige Auswahl erhalten.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N80.user_prompt_source` – user prompt source | bundled_library | manual / bundled_library / external_directory; Standardfeld; native App-Bindung prüfen | E | — |
| `N80.user_prompt_directory` – user prompt directory | leer | Standardfeld; native App-Bindung prüfen | E | — |
| `N80.user_prompt_file` – Musikvorlage | electronic/synth-pop-vocal.txt | Vollständige bestehende Liste (241 Einträge im Schema); Standardfeld; native App-Bindung prüfen | H | — |
| `N80.genre` – Genre | Synth-Pop | Vollständige bestehende Liste (265 Einträge im Schema); Standardfeld; native App-Bindung prüfen | E | — |
| `N80.tempo` – Tempo | Dancefloor (120-130 BPM) | custom / Slow (40-70 BPM) / Laid-back (70-100 BPM) / Midtempo (100-120 BPM) / Dancefloor (120-130 BPM) / Uptempo (130-145 BPM) / Fast (145-175 BPM) / Very fast (175-200 BPM); Standardfeld; native App-Bindung prüfen | E | — |
| `N80.meter` – Taktart | 4/4 (common time) | Vollständige bestehende Liste (16 Einträge im Schema); Standardfeld; native App-Bindung prüfen | E | — |
| `N80.key` – Tonart | custom | Vollständige bestehende Liste (25 Einträge im Schema); Standardfeld; native App-Bindung prüfen | E | — |
| `N80.lyrics` – Gesang / Instrumental | yes | custom / yes / sparse / only voice - no words / instrumental; Standardfeld; native App-Bindung prüfen | H | — |
| `N80.language` – Sprache | English | Vollständige bestehende Liste (91 Einträge im Schema); Standardfeld; native App-Bindung prüfen | E | — |
| `N80.voice` – Stimme | female vocal | Vollständige bestehende Liste (47 Einträge im Schema); Standardfeld; native App-Bindung prüfen | E | — |
| `N80.theme` – Thema | night &amp; city lights | Vollständige bestehende Liste (17 Einträge im Schema); Standardfeld; native App-Bindung prüfen | E | — |
| `N80.length` – Gewünschte Länge | 3-4 minutes | custom / 30 seconds / 1 minute / 1-2 minutes / 2-3 minutes / 3-4 minutes / 4-5 minutes; Standardfeld; native App-Bindung prüfen | H | — |
| `N80.description_override` – Beschreibung | Bright, catchy synth-pop: analog synth hooks, punchy drum machines, melodic … (vollständig im Workflow) | Standardfeld; native App-Bindung prüfen | H | — |
| `N80.Save as custom user prompt` – Save as custom user prompt | leer | Frontend-Aktion/Zustand: App-Adapter prüfen; kein eigenständiger DSP-Parameter | E | — |
| `N80.system_prompt_source` – system prompt source | bundled_library | manual / bundled_library / external_directory; Standardfeld; native App-Bindung prüfen | E | — |
| `N80.system_prompt_directory` – system prompt directory | leer | Standardfeld; native App-Bindung prüfen | E | — |
| `N80.system_prompt_file` – Systemvorlage | yue2/production.txt | Vollständige bestehende Liste (25 Einträge im Schema); Standardfeld; native App-Bindung prüfen | E | — |
| `N80.source_name_override` – source name override | leer | Standardfeld; native App-Bindung prüfen | E | — |
| `N80.system_prompt` – System-Prompt | You are a composer, arranger, songwriter and producer preparing a fully dev … (vollständig im Workflow) | Standardfeld; native App-Bindung prüfen | E | — |
| `N80.Save as custom system prompt` – Save as custom system prompt | nicht gespeichert / aus Definition | Frontend-Aktion/Zustand: App-Adapter prüfen; kein eigenständiger DSP-Parameter | E | — |
| `N80.Refresh prompt lists` – Refresh prompt lists | nicht gespeichert / aus Definition | Frontend-Aktion/Zustand: App-Adapter prüfen; kein eigenständiger DSP-Parameter | E | — |

### N53 – Parse song · manual fallback here

Node-Typ: `MiniMaxParseExternalLLMOutputV16`. Manuelle Prompts nur im vorhandenen manuellen Ersatzpfad; Cover-Titel bleibt abgeleitet.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N53.song_count` – Songanzahl | 1 | 1 … 100; Standardfeld; native App-Bindung prüfen | E | — |
| `N53.seed_mode` – Seed-Modus | random_each_song | random_each_song / increment_from_base; Standardfeld; native App-Bindung prüfen | E | — |
| `N53.base_seed` – Basisseed | 1 | 0 … 9223372036854775806; Standardfeld; native App-Bindung prüfen | E | — |
| `N53.user_prompt` – user prompt | Gesteuert durch N80.user_prompt | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |
| `N53.source_name_override` – source name override | Gesteuert durch N80.source_name | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |
| `N53.fallback_title` – fallback title | llm-song | Standardfeld; native App-Bindung prüfen | E | — |
| `N53.manual_caption` – Manueller Style / Caption | leer | Standardfeld; native App-Bindung prüfen | E | — |
| `N53.manual_lyrics` – Manuelle Lyrics | leer | Standardfeld; native App-Bindung prüfen | E | — |
| `N53.manual_title` – Manueller Titel | leer | Standardfeld; native App-Bindung prüfen | E | — |
| `N53.manual_image_prompt` – Manueller Artwork-Prompt | leer | Standardfeld; native App-Bindung prüfen | E | — |
| `N53.model_check_report` – model check report | Gesteuert durch N101.report | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |
| `N53.llm_status` – llm status | Gesteuert durch N81.status | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |
| `N53.max_prompt_tokens` – max prompt tokens | Gesteuert durch N118.prompt_token_budget | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |
| `N53.trim_long_prompt` – trim long prompt | False | Standardfeld; native App-Bindung prüfen | E | — |

## LLM und Modellbeschaffung

### N81 – LLM · In ComfyUI / Local app / Cloud

Node-Typ: `MiniMaxLLMChat`. Betriebsart bestimmt wirksame Parameter; providerabhängige Unterstützung anzeigen.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N81.enabled` – Aktiv | True | Standardfeld; native App-Bindung prüfen | E | — |
| `N81.model` – Modell | Qwen3.8-27B-UD-IQ3_XXS.gguf | Dynamische Modell-/Dateiliste; Standardfeld; native App-Bindung prüfen | K | — |
| `N81.max_tokens` – max tokens | 16384 | 1 … 131072; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.temperature` – temperature | 1 | 0.0 … 2.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.top_p` – top p | 0.95 | 0.0 … 1.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.n_gpu_layers` – n gpu layers | -1 | -1 … 512; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.n_ctx` – n ctx | 32768 | 512 … 262144; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.reset_session` – reset session | True | Standardfeld; native App-Bindung prüfen | E | — |
| `N81.auto_download` – auto download | True | Standardfeld; native App-Bindung prüfen | E | — |
| `N81.chat_format` – chat format | auto | auto / chatml / qwen / gemma / llama-3 / none; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.thinking` – thinking | on | auto / on / off; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.top_k` – top k | 20 | 1 … 1000; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.min_p` – min p | 0 | 0.0 … 1.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.repeat_penalty` – repeat penalty | 1 | 0.0 … 3.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.presence_penalty` – presence penalty | 0 | -2.0 … 2.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.frequency_penalty` – frequency penalty | 0 | -2.0 … 2.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.seed` – seed | -1 | -1 … 2147483647; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.control_after_generate` – control after generate | none | Frontend-Aktion/Zustand: App-Adapter prüfen; kein eigenständiger DSP-Parameter | E | — |
| `N81.split_mode` – split mode | none | none / layer / row; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.tensor_split` – tensor split | leer | Standardfeld; native App-Bindung prüfen | E | — |
| `N81.main_gpu` – main gpu | 0 | 0 … 16; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.tensor_parallel` – tensor parallel | False | Standardfeld; native App-Bindung prüfen | E | — |
| `N81.backend` – LLM-Betriebsart | In ComfyUI (GGUF) | In ComfyUI (GGUF) / Local app / server / Cloud service; Standardfeld; native App-Bindung prüfen | K | — |
| `N81.local_provider` – local provider | LM Studio | LM Studio / Ollama / llama.cpp / Unsloth Studio / vLLM / Other OpenAI-compatible server; Standardfeld; native App-Bindung prüfen | K | — |
| `N81.cloud_provider` – cloud provider | OpenAI | OpenAI / Claude (Anthropic) / Gemini (Google) / DeepSeek / Qwen (Alibaba Cloud) / MiniMax / OpenRouter / Groq / Other OpenAI-compatible cloud; Standardfeld; native App-Bindung prüfen | K | — |
| `N81.server_url` – server url | leer | Standardfeld; native App-Bindung prüfen | K | — |
| `N81.remote_model` – remote model | leer | Standardfeld; native App-Bindung prüfen | K | — |
| `N81.api_key_env` – api key env | Sitzungs-/Verbindungskonfiguration; keine Geheimnisse im Layout | Sitzungs-/Verbindungsadapter; nicht als veröffentlichbaren Parameter behandeln | K | — |
| `N81.credential_id` – credential id | Sitzungs-/Verbindungskonfiguration; keine Geheimnisse im Layout | Sitzungs-/Verbindungsadapter; nicht als veröffentlichbaren Parameter behandeln | K | — |
| `N81.remote_max_tokens` – remote max tokens | 16384 | 1 … 131072; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.request_timeout` – request timeout | 240 | 5 … 600; Standardfeld; native App-Bindung prüfen | E | — |
| `N81.llm_ui_advanced` – llm ui advanced | nicht gespeichert / aus Definition | Frontend-Aktion/Zustand: App-Adapter prüfen; kein eigenständiger DSP-Parameter | E | — |
| `N81.llm_ui_key` – llm ui key | nicht gespeichert / aus Definition | Frontend-Aktion/Zustand: App-Adapter prüfen; kein eigenständiger DSP-Parameter | K | — |
| `N81.llm_ui_clear` – llm ui clear | nicht gespeichert / aus Definition | Frontend-Aktion/Zustand: App-Adapter prüfen; kein eigenständiger DSP-Parameter | K | — |
| `N81.llm_ui_models` – llm ui models | nicht gespeichert / aus Definition | Frontend-Aktion/Zustand: App-Adapter prüfen; kein eigenständiger DSP-Parameter | K | — |
| `N81.llm_ui_help` – llm ui help | nicht gespeichert / aus Definition | Frontend-Aktion/Zustand: App-Adapter prüfen; kein eigenständiger DSP-Parameter | E | — |

### N85 – Free LLM memory → parser

Node-Typ: `MiniMaxLLMUnload`. Vorhandene Werte und vollständige Auswahl erhalten.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N85.unload_now` – unload now | True | Standardfeld; native App-Bindung prüfen | K | — |
| `N85.unload_flashsr` – unload flashsr | False | Standardfeld; native App-Bindung prüfen | K | — |

### N101 – Selected song / artwork / FlashSR model check

Node-Typ: `MiniMaxModelAutodownload`. Vorhandene Werte und vollständige Auswahl erhalten.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N101.minimax_models` – minimax models | True | Standardfeld; native App-Bindung prüfen | K | — |
| `N101.flux2_models` – flux2 models | Gesteuert durch N118.cover_enabled | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |
| `N101.flashsr_models` – flashsr models | Gesteuert durch N118.refinement_enabled | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |
| `N101.llm_model` – llm model | False | Standardfeld; native App-Bindung prüfen | K | — |
| `N101.auto_download` – auto download | True | Standardfeld; native App-Bindung prüfen | K | — |
| `N101.yue2_models` – yue2 models | True | Standardfeld; native App-Bindung prüfen | K | — |
| `N101.sheetsage2_models` – sheetsage2 models | True | Standardfeld; native App-Bindung prüfen | K | — |

## Musikgenerierung

### N55 – Music settings · model aware

Node-Typ: `MiniMaxMusicModelSettings`. MiniMax-/YuE2-Felder nur beim jeweiligen Modell aktiv; getrennte Werte erhalten.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N55.max_duration` – MiniMax technische Maximallänge | 300 | 1.0 … 900.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.ksampler_seed_offset` – ksampler seed offset | 0 | -1000000 … 1000000; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.denoise` – denoise | 1 | 0.0 … 1.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.minimax_steps` – minimax steps | 40 | 1 … 200; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.minimax_cfg` – minimax cfg | 1.7 | 0.0 … 20.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.minimax_sampler_name` – minimax sampler name | euler | euler / dpm_2; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.minimax_scheduler` – minimax scheduler | simple | simple / sgm_uniform; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.minimax_text_cfg_scale` – minimax text cfg scale | 1.7 | 0.0 … 10.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.minimax_text_top_k` – minimax text top k | 50 | 1 … 1000; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.yue2_steps` – yue2 steps | 40 | 1 … 200; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.yue2_cfg` – yue2 cfg | 1 | 0.0 … 20.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.yue2_sampler_name` – yue2 sampler name | dpm_2 | euler / dpm_2; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.yue2_scheduler` – yue2 scheduler | sgm_uniform | simple / sgm_uniform; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.yue2_mode` – yue2 mode | full | full / melody; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.yue2_temperature` – yue2 temperature | 1 | 0.0 … 5.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.yue2_top_p` – yue2 top p | 0.95 | 0.01 … 1.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.yue2_top_k` – yue2 top k | 100 | 1 … 32768; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.yue2_repetition_penalty` – yue2 repetition penalty | 1.2 | 0.01 … 10.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N55.yue2_max_duration` – YuE2 technische Maximallänge | 360 | 1.0 … 900.0; Standardfeld; native App-Bindung prüfen | E | — |

## Artefaktreduktion

### N123 – Artifact reduction · experimental · CHOOSE on/off

Node-Typ: `AudioArtifactReduction`. Unabhängige Artefaktstufe; zentraler Schalter, keine zweite Checkbox.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N123.enabled` – Aktiv | Gesteuert durch N118.artifact_reduction_enabled | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |
| `N123.mode` – Modus | Reduce | Reduce / Analyze only; Standardfeld; native App-Bindung prüfen | E | — |
| `N123.sensitivity` – Empfindlichkeit | Balanced | Gentle / Balanced / Strong; Standardfeld; native App-Bindung prüfen | E | — |
| `N123.min_frequency_hz` – min frequency hz | 3000.0 | 1000.0 … 16000.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N123.max_frequency_hz` – max frequency hz | 18000.0 | 2000.0 … 20000.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N123.max_reduction_db` – max reduction db | 3.0 | 0.0 … 8.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N123.protect_transients` – protect transients | True | Standardfeld; native App-Bindung prüfen | E | — |
| `N123.mix` – mix | 1.0 | 0.0 … 1.0; Standardfeld; native App-Bindung prüfen | E | — |

## Auto-EQ und Manual EQ

### N109 – 1 · Auto-EQ · enabled = on/off

Node-Typ: `MiniMaxAutoEQAnalyze`. Wirkung nur bei aktivem Mastering; gekoppelte Werte an der Quelle ändern.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N109.target_mode` – Internes Auto-EQ-Ziel | Warm tilt | Reference track / Warm tilt / Bright tilt; Intern durch einzigen Preset-Adapter setzen; nicht als zweite Auswahl anzeigen | A | — |
| `N109.strength_percent` – strength percent | 35 | 0 … 100; Standardfeld; native App-Bindung prüfen | E | — |
| `N109.max_gain_db` – max gain db | 2 | 0.1 … 6; Standardfeld; native App-Bindung prüfen | E | — |
| `N109.max_bands` – max bands | 4 | 1 … 6; Standardfeld; native App-Bindung prüfen | E | — |
| `N109.min_frequency_hz` – min frequency hz | 40 | 20 … 1000; Standardfeld; native App-Bindung prüfen | E | — |
| `N109.max_frequency_hz` – max frequency hz | 16000 | 1000 … 20000; Standardfeld; native App-Bindung prüfen | E | — |
| `N109.enabled` – Aktiv | True | Standardfeld; native App-Bindung prüfen | E | — |
| `N109.reference_audio` – Referenzaudio | nicht gespeichert / aus Definition | Audio-Socket: LoadAudio/Upload-Bindung ergänzen, siehe APP-REF; keine bloße Dateipfad-Eingabe | E | — |

### N110 – 2 · Apply Auto-EQ · linked settings

Node-Typ: `MiniMaxParametricEQ`. Wirkung nur bei aktivem Mastering; gekoppelte Werte an der Quelle ändern.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N110.eq_settings_json` – Vollständige EQ-Einstellungen | Gesteuert durch N109.eq_settings_json | Auto-EQ-Anwendung; nicht als zweiten manuellen EQ exponieren | A | — |
| `N110.bypass` – Umgehen | False | Expertenoption: nur automatische EQ-Anwendung umgehen; Analyse und Bericht können aktiv bleiben | E | — |
| `N110.eq_editor` – eq editor | leer | Auto-EQ-Anwendung; nicht als zweiten manuellen EQ exponieren | A | — |

### N112 – 3 · Manual EQ · bypass = off

Node-Typ: `MiniMaxParametricEQ`. Wirkung nur bei aktivem Mastering; gekoppelte Werte an der Quelle ändern.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N112.eq_settings_json` – Vollständige EQ-Einstellungen | {"schema":"minimax_eq_v1","preamp_db":0,"bands":[]} | Standardfeld; native App-Bindung prüfen | E | — |
| `N112.bypass` – Umgehen | False | Standardfeld; native App-Bindung prüfen | E | — |
| `N112.eq_editor` – eq editor | leer | Frontend-Kurveneditor; auf eq_settings_json binden, keinen zweiten Zustand speichern | A | — |

## Mastering und Ausgaberate

### N111 – 5 · Master · compression / LUFS / peak

Node-Typ: `MiniMaxMasteringCompressor`. Wirkung nur bei aktivem Mastering; gekoppelte Werte an der Quelle ändern.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N111.bypass` – Umgehen | False | Standardfeld; native App-Bindung prüfen | E | — |
| `N111.target_lufs` – Ziel-Lautheit (LUFS) | -14 | -30 … -5; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.ceiling_dbtp` – Peak-Obergrenze (dBTP) | -1 | -12 … -0.1; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.target_sample_rate` – Ausgaberate | keep | keep / 44100 / 48000; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.compressor_enabled` – compressor enabled | True | Standardfeld; native App-Bindung prüfen | E | — |
| `N111.threshold_db` – threshold db | -18 | -60 … 0; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.ratio` – ratio | 1.5 | 1 … 10; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.knee_db` – knee db | 6 | 0 … 24; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.attack_ms` – attack ms | 20 | 1 … 200; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.release_ms` – release ms | 150 | 10 … 2000; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.sidechain_hz` – sidechain hz | 80 | 0 … 500; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.detector` – detector | RMS | RMS / Peak; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.input_gain_db` – input gain db | 0 | -24 … 24; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.max_makeup_db` – max makeup db | 18 | 0 … 24; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.max_limiter_reduction_db` – max limiter reduction db | 6 | 1 … 18; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.lookahead_ms` – lookahead ms | 3 | 1 … 5; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.limiter_release_ms` – limiter release ms | 100 | 10 … 1000; Standardfeld; native App-Bindung prüfen | E | — |
| `N111.preset` – Preset | Balanced - gentle glue | Vollständige bestehende Liste (13 Einträge im Schema); Standardfeld; native App-Bindung prüfen | E | — |

### N91 – 4 · Output rate · 44100 / 48000

Node-Typ: `AudioReleasePrep`. Wirkung nur bei aktivem Mastering; gekoppelte Werte an der Quelle ändern.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N91.target_sample_rate` – Ausgaberate | 44100 | 44100 / 48000 / keep; Standardfeld; native App-Bindung prüfen | E | — |
| `N91.processing` – processing | Resample only | Resample only / Streaming Safe -14 LUFS / -1 dBTP / Modern Music -12 LUFS / -2 dBTP / Loud Electronic -10 LUFS / -2 dBTP / Custom / Bypass; Standardfeld; native App-Bindung prüfen | E | — |
| `N91.custom_target_lufs` – custom target lufs | -14 | -24.0 … -5.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N91.custom_true_peak_dbtp` – custom true peak dbtp | -1 | -6.0 … -0.1; Standardfeld; native App-Bindung prüfen | E | — |

## Refinement

### N95 – A · Declip / overload repair

Node-Typ: `AudioDeclipRepair`. Wirkung nur bei aktivem Refinement; Einstellungen trotzdem auffindbar.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N95.mode` – Modus | Auto / conservative | Auto / conservative / Standard / Strong / Custom / Analyze only / Bypass; Standardfeld; native App-Bindung prüfen | E | — |
| `N95.detection_threshold_percent` – detection threshold percent | 98 | 85.0 … 99.99; Standardfeld; native App-Bindung prüfen | E | — |
| `N95.plateau_tolerance_percent` – plateau tolerance percent | 0.001 | 0.0001 … 1.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N95.min_flat_samples` – min flat samples | 3 | 1 … 32; Standardfeld; native App-Bindung prüfen | E | — |
| `N95.slope_context_samples` – slope context samples | 3 | 2 … 64; Standardfeld; native App-Bindung prüfen | E | — |
| `N95.max_repair_ms` – max repair ms | 8 | 0.1 … 50.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N95.max_peak_extension_db` – max peak extension db | 4 | 0.5 … 12.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N95.output_ceiling_dbfs` – output ceiling dbfs | -1 | -12.0 … -0.1; Standardfeld; native App-Bindung prüfen | E | — |
| `N95.mix` – mix | 1 | 0.0 … 1.0; Standardfeld; native App-Bindung prüfen | E | — |

### N49 – B · PRE low-pass · 10 kHz

Node-Typ: `FlashSRLowpassLab`. Wirkung nur bei aktivem Refinement; Einstellungen trotzdem auffindbar.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N49.preset` – Preset | PRE 10 kHz - strong | CUSTOM / PRE 14 kHz - light / PRE 12 kHz - recommended / PRE 10 kHz - strong / PRE 8 kHz - aggressive / POST 20 kHz - recommended gentle / POST 19 kHz - slightly stronger; Standardfeld; native App-Bindung prüfen | E | — |
| `N49.custom_cutoff_hz` – custom cutoff hz | 10000 | 20.0 … 96000.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N49.custom_order` – custom order | 2 | 1 … 12; Standardfeld; native App-Bindung prüfen | E | — |
| `N49.custom_phase_mode` – custom phase mode | zero_phase | zero_phase / causal; Standardfeld; native App-Bindung prüfen | E | — |
| `N49.bypass` – Umgehen | False | Standardfeld; native App-Bindung prüfen | E | — |

### N45 – C · FlashSR · 48 kHz

Node-Typ: `MiniMaxFlashSRAudio`. Wirkung nur bei aktivem Refinement; Einstellungen trotzdem auffindbar.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N45.lowpass_input` – lowpass input | False | Standardfeld; native App-Bindung prüfen | E | — |
| `N45.output_sr` – output sr | 48000 | 48000 / 44100 / 96000; Standardfeld; native App-Bindung prüfen | E | — |
| `N45.auto_download` – auto download | True | Standardfeld; native App-Bindung prüfen | E | — |

### N93 – D · Crossover · FlashSR only

Node-Typ: `FlashSRHybridCrossover`. Wirkung nur bei aktivem Refinement; Einstellungen trotzdem auffindbar.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N93.mode` – Modus | FlashSR only | Original + FlashSR air / Hybrid replace above crossover / Original SRC only / FlashSR only; Standardfeld; native App-Bindung prüfen | E | — |
| `N93.crossover_hz` – crossover hz | 13500 | 7000.0 … 18000.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N93.transition_hz` – transition hz | 2000 | 300.0 … 6000.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N93.flashsr_hf_mix` – flashsr hf mix | 0.45 | 0.0 … 1.5; Standardfeld; native App-Bindung prüfen | E | — |

### N94 – E · HF cymbal repair

Node-Typ: `HFCymbalShimmerRepair`. Wirkung nur bei aktivem Refinement; Einstellungen trotzdem auffindbar.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N94.mode` – Modus | Cymbal clarity | Gentle / Cymbal clarity / Reverb / shimmer control / Custom / Bypass; Standardfeld; native App-Bindung prüfen | E | — |
| `N94.start_frequency_hz` – start frequency hz | 7000 | 3000.0 … 16000.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N94.sustain_reduction_db` – sustain reduction db | 2.25 | 0.0 … 8.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N94.fast_envelope_ms` – fast envelope ms | 5 | 1.0 … 50.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N94.slow_envelope_ms` – slow envelope ms | 180 | 40.0 … 1000.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N94.transient_sensitivity` – transient sensitivity | 0.3 | 0.05 … 1.5; Standardfeld; native App-Bindung prüfen | E | — |
| `N94.side_hf_reduction_db` – side hf reduction db | 1 | 0.0 … 8.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N94.static_hf_trim_db` – static hf trim db | -0.5 | -8.0 … 2.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N94.min_hf_level_dbfs` – min hf level dbfs | -58 | -90.0 … -20.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N94.mix` – mix | 1 | 0.0 … 1.0; Standardfeld; native App-Bindung prüfen | E | — |

### N50 – F · POST low-pass · 19 kHz

Node-Typ: `FlashSRLowpassLab`. Wirkung nur bei aktivem Refinement; Einstellungen trotzdem auffindbar.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N50.preset` – Preset | POST 19 kHz - slightly stronger | CUSTOM / PRE 14 kHz - light / PRE 12 kHz - recommended / PRE 10 kHz - strong / PRE 8 kHz - aggressive / POST 20 kHz - recommended gentle / POST 19 kHz - slightly stronger; Standardfeld; native App-Bindung prüfen | E | — |
| `N50.custom_cutoff_hz` – custom cutoff hz | 19000 | 20.0 … 96000.0; Standardfeld; native App-Bindung prüfen | E | — |
| `N50.custom_order` – custom order | 2 | 1 … 12; Standardfeld; native App-Bindung prüfen | E | — |
| `N50.custom_phase_mode` – custom phase mode | causal | zero_phase / causal; Standardfeld; native App-Bindung prüfen | E | — |
| `N50.bypass` – Umgehen | False | Standardfeld; native App-Bindung prüfen | E | — |

## Artwork

### N64 – Render resolution · GPU workload

Node-Typ: `MiniMaxSquareImageSize`. Artwork-Stufe; bei ausgeschalteter Stufe keine ungewollte Ausführung durch App-Vorschauen.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N64.size_preset` – size preset | 1536x1536 | 256x256 / 512x512 / 1024x1024 / 1536x1536 / 2048x2048 / 3072x3072 / 3096x3096 / custom; Standardfeld; native App-Bindung prüfen | E | — |
| `N64.custom_size` – custom size | 1536 | 64 … 4096; Standardfeld; native App-Bindung prüfen | E | — |

### N65 – FLUX.2 Klein · model

Node-Typ: `UNETLoader`. Artwork-Stufe; bei ausgeschalteter Stufe keine ungewollte Ausführung durch App-Vorschauen.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N65.unet_name` – unet name | flux-2-klein-4b.safetensors | Standardfeld; native App-Bindung prüfen | K | — |
| `N65.weight_dtype` – weight dtype | default | Standardfeld; native App-Bindung prüfen | K | — |

### N66 – FLUX.2 · text encoder

Node-Typ: `CLIPLoader`. Artwork-Stufe; bei ausgeschalteter Stufe keine ungewollte Ausführung durch App-Vorschauen.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N66.clip_name` – clip name | qwen_3_4b.safetensors | Standardfeld; native App-Bindung prüfen | K | — |
| `N66.type` – type | flux2 | Standardfeld; native App-Bindung prüfen | K | — |
| `N66.device` – device | default | Standardfeld; native App-Bindung prüfen | K | — |

### N67 – FLUX.2 · VAE

Node-Typ: `VAELoader`. Artwork-Stufe; bei ausgeschalteter Stufe keine ungewollte Ausführung durch App-Vorschauen.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N67.vae_name` – vae name | flux2-vae.safetensors | Standardfeld; native App-Bindung prüfen | K | — |

### N68 – Image prompt · from parser

Node-Typ: `CLIPTextEncode`. Artwork-Stufe; bei ausgeschalteter Stufe keine ungewollte Ausführung durch App-Vorschauen.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N68.text` – text | Gesteuert durch N53.image_prompt | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |

### N70 – Guidance

Node-Typ: `CFGGuider`. Artwork-Stufe; bei ausgeschalteter Stufe keine ungewollte Ausführung durch App-Vorschauen.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N70.cfg` – cfg | 1 | Standardfeld; native App-Bindung prüfen | E | — |

### N71 – Artwork seed · from song

Node-Typ: `RandomNoise`. Artwork-Stufe; bei ausgeschalteter Stufe keine ungewollte Ausführung durch App-Vorschauen.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N71.noise_seed` – noise seed | Gesteuert durch N53.generation_seed | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |
| `N71.control_after_generate` – control after generate | fixed | Frontend-Aktion/Zustand: App-Adapter prüfen; kein eigenständiger DSP-Parameter | E | — |

### N72 – Sampler

Node-Typ: `KSamplerSelect`. Artwork-Stufe; bei ausgeschalteter Stufe keine ungewollte Ausführung durch App-Vorschauen.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N72.sampler_name` – sampler name | euler | Standardfeld; native App-Bindung prüfen | E | — |

### N73 – Schedule · 4 steps

Node-Typ: `Flux2Scheduler`. Artwork-Stufe; bei ausgeschalteter Stufe keine ungewollte Ausführung durch App-Vorschauen.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N73.steps` – steps | 4 | Standardfeld; native App-Bindung prüfen | E | — |
| `N73.width` – width | Gesteuert durch N64.width | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |
| `N73.height` – height | Gesteuert durch N64.height | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |

### N74 – Square latent · linked render size

Node-Typ: `EmptyFlux2LatentImage`. Artwork-Stufe; bei ausgeschalteter Stufe keine ungewollte Ausführung durch App-Vorschauen.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N74.width` – width | Gesteuert durch N64.width | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |
| `N74.height` – height | Gesteuert durch N64.height | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |
| `N74.batch_size` – batch size | 1 | Standardfeld; native App-Bindung prüfen | E | — |

### N77 – Save cover JPG → audio tags

Node-Typ: `SaveImageSmartPrefix`. Artwork-Stufe; bei ausgeschalteter Stufe keine ungewollte Ausführung durch App-Vorschauen.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N77.collision_mode` – collision mode | auto_increment | auto_increment / overwrite / error_if_exists; Standardfeld; native App-Bindung prüfen | E | — |
| `N77.create_directories` – create directories | True | Standardfeld; native App-Bindung prüfen | E | — |
| `N77.jpeg_quality` – jpeg quality | 95 | 50 … 100; Standardfeld; native App-Bindung prüfen | E | — |
| `N77.filename_mode` – filename mode | album - title | album - title / title only / prefix as provided; Standardfeld; native App-Bindung prüfen | E | — |
| `N77.enabled` – Aktiv | Gesteuert durch N118.cover_enabled | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |

### N96 – Embedded cover resolution · tags

Node-Typ: `MiniMaxSquareImageSize`. Artwork-Stufe; bei ausgeschalteter Stufe keine ungewollte Ausführung durch App-Vorschauen.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N96.size_preset` – size preset | 1024x1024 | 256x256 / 512x512 / 1024x1024 / 1536x1536 / 2048x2048 / 3072x3072 / 3096x3096 / custom; Standardfeld; native App-Bindung prüfen | E | — |
| `N96.custom_size` – custom size | 1536 | 64 … 4096; Standardfeld; native App-Bindung prüfen | E | — |

## Metadaten, Dateipfade und Speichern

### N63 – Release tags · edit artist & album

Node-Typ: `MiniMaxStandardAudioTags`. Vorhandene Werte und vollständige Auswahl erhalten.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N63.artist` – Artist | Example Artist | Standardfeld; native App-Bindung prüfen | H | — |
| `N63.album` – Album | Example Album | Standardfeld; native App-Bindung prüfen | H | — |
| `N63.year` – year | 2026 | Standardfeld; native App-Bindung prüfen | E | — |
| `N63.track` – track | 01 | Standardfeld; native App-Bindung prüfen | E | — |
| `N63.genre` – Genre | custom | Standardfeld; native App-Bindung prüfen | E | — |
| `N63.comment` – comment | Generated with jplenio Music Production Toolkit | Standardfeld; native App-Bindung prüfen | E | — |
| `N63.album_artist` – album artist | Example Artist | Standardfeld; native App-Bindung prüfen | E | — |
| `N63.composer` – composer | Example Composer | Standardfeld; native App-Bindung prüfen | E | — |

### N54 – Output folders

Node-Typ: `MiniMaxOutputPaths`. Vorhandene Werte und vollständige Auswahl erhalten.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N54.base_output` – Basis-Ausgabeverzeichnis | audio/music/%date:yyyy-MM-dd%/Example Album/ | Standardfeld; native App-Bindung prüfen | H | — |
| `N54.original_subdir` – original subdir | original-flac/ | Standardfeld; native App-Bindung prüfen | K | — |
| `N54.sr_flac_subdir` – sr flac subdir | highres-44flac/ | Standardfeld; native App-Bindung prüfen | K | — |
| `N54.sr_mp3_subdir` – sr mp3 subdir | highres-44mp3/ | Standardfeld; native App-Bindung prüfen | K | — |
| `N54.artwork_subdir` – artwork subdir | artwork/ | Standardfeld; native App-Bindung prüfen | K | — |
| `N54.configuration_subdir` – configuration subdir | log/ | Standardfeld; native App-Bindung prüfen | K | — |

### N35 – Original FLAC · native sample rate

Node-Typ: `SaveAudioSmartPrefix`. Vorhandene Werte und vollständige Auswahl erhalten.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N35.format` – format | flac | flac / mp3 / wav; Standardfeld; native App-Bindung prüfen | E | — |
| `N35.collision_mode` – collision mode | auto_increment | auto_increment / overwrite / error_if_exists; Standardfeld; native App-Bindung prüfen | E | — |
| `N35.create_directories` – create directories | True | Standardfeld; native App-Bindung prüfen | E | — |
| `N35.mp3_quality` – mp3 quality | V0 (~245 kbps) | V0 (~245 kbps) / V2 (~190 kbps) / 320 kbps / 256 kbps / 192 kbps; Standardfeld; native App-Bindung prüfen | E | — |
| `N35.flac_bit_depth` – flac bit depth | 24-bit | 24-bit / 16-bit; Standardfeld; native App-Bindung prüfen | E | — |
| `N35.wav_bit_depth` – wav bit depth | 32-bit float | 32-bit float / 24-bit / 16-bit; Standardfeld; native App-Bindung prüfen | E | — |
| `N35.peak_handling` – peak handling | normalize_only_if_clipping | leave_unchanged / normalize_only_if_clipping; Standardfeld; native App-Bindung prüfen | E | — |
| `N35.write_json_sidecar` – write json sidecar | False | Standardfeld; native App-Bindung prüfen | E | — |
| `N35.embed_basic_metadata` – embed basic metadata | True | Standardfeld; native App-Bindung prüfen | E | — |
| `N35.filename_mode` – filename mode | album - title | album - title / title only / prefix as provided; Standardfeld; native App-Bindung prüfen | E | — |
| `N35.embedded_cover_size` – embedded cover size | Gesteuert durch N96.width | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |

### N46 – Release FLAC · final master rate

Node-Typ: `SaveAudioSmartPrefix`. Vorhandene Werte und vollständige Auswahl erhalten.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N46.format` – format | flac | flac / mp3 / wav; Standardfeld; native App-Bindung prüfen | E | — |
| `N46.collision_mode` – collision mode | auto_increment | auto_increment / overwrite / error_if_exists; Standardfeld; native App-Bindung prüfen | E | — |
| `N46.create_directories` – create directories | True | Standardfeld; native App-Bindung prüfen | E | — |
| `N46.mp3_quality` – mp3 quality | V0 (~245 kbps) | V0 (~245 kbps) / V2 (~190 kbps) / 320 kbps / 256 kbps / 192 kbps; Standardfeld; native App-Bindung prüfen | E | — |
| `N46.flac_bit_depth` – flac bit depth | 24-bit | 24-bit / 16-bit; Standardfeld; native App-Bindung prüfen | E | — |
| `N46.wav_bit_depth` – wav bit depth | 32-bit float | 32-bit float / 24-bit / 16-bit; Standardfeld; native App-Bindung prüfen | E | — |
| `N46.peak_handling` – peak handling | normalize_only_if_clipping | leave_unchanged / normalize_only_if_clipping; Standardfeld; native App-Bindung prüfen | E | — |
| `N46.write_json_sidecar` – write json sidecar | False | Standardfeld; native App-Bindung prüfen | E | — |
| `N46.embed_basic_metadata` – embed basic metadata | True | Standardfeld; native App-Bindung prüfen | E | — |
| `N46.filename_mode` – filename mode | album - title | album - title / title only / prefix as provided; Standardfeld; native App-Bindung prüfen | E | — |
| `N46.embedded_cover_size` – embedded cover size | Gesteuert durch N96.width | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |

### N52 – Release MP3 · final master rate

Node-Typ: `SaveAudioSmartPrefix`. Vorhandene Werte und vollständige Auswahl erhalten.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N52.format` – format | mp3 | flac / mp3 / wav; Standardfeld; native App-Bindung prüfen | E | — |
| `N52.collision_mode` – collision mode | auto_increment | auto_increment / overwrite / error_if_exists; Standardfeld; native App-Bindung prüfen | E | — |
| `N52.create_directories` – create directories | True | Standardfeld; native App-Bindung prüfen | E | — |
| `N52.mp3_quality` – mp3 quality | V0 (~245 kbps) | V0 (~245 kbps) / V2 (~190 kbps) / 320 kbps / 256 kbps / 192 kbps; Standardfeld; native App-Bindung prüfen | E | — |
| `N52.flac_bit_depth` – flac bit depth | 24-bit | 24-bit / 16-bit; Standardfeld; native App-Bindung prüfen | E | — |
| `N52.wav_bit_depth` – wav bit depth | 32-bit float | 32-bit float / 24-bit / 16-bit; Standardfeld; native App-Bindung prüfen | E | — |
| `N52.peak_handling` – peak handling | normalize_only_if_clipping | leave_unchanged / normalize_only_if_clipping; Standardfeld; native App-Bindung prüfen | E | — |
| `N52.write_json_sidecar` – write json sidecar | False | Standardfeld; native App-Bindung prüfen | E | — |
| `N52.embed_basic_metadata` – embed basic metadata | True | Standardfeld; native App-Bindung prüfen | E | — |
| `N52.filename_mode` – filename mode | album - title | album - title / title only / prefix as provided; Standardfeld; native App-Bindung prüfen | E | — |
| `N52.embedded_cover_size` – embedded cover size | Gesteuert durch N96.width | Verbundener Eingang: zuständige Quellfunktion anbieten; lokale Voreinstellung nicht als wirksam zeigen | A | — |

### N99 – Production JSON · final artifact record

Node-Typ: `MiniMaxSaveProductionJSON`. Vorhandene Werte und vollständige Auswahl erhalten.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N99.collision_mode` – collision mode | auto_increment | auto_increment / overwrite / error_if_exists; Standardfeld; native App-Bindung prüfen | K | — |
| `N99.filename_mode` – filename mode | album - title | album - title / title only / prefix as provided; Standardfeld; native App-Bindung prüfen | K | — |
| `N99.create_directories` – create directories | True | Standardfeld; native App-Bindung prüfen | K | — |
| `N99.workflow_name` – workflow name | YuE2 Cover / YuE2 / MiniMax Music Production Toolkit 3.0.1 | Standardfeld; native App-Bindung prüfen | K | — |

## Technische Stufenauswahl

### N119 – Refinement · enabled / bypass

Node-Typ: `MusicOptionalStage`. Interne Umschaltung; zentrale Regler sind Node 118.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N119.stage` – stage | Refinement | Technisches Stufenlabel; Benutzer schaltet an Node 118 | G | — |

### N120 – Mastering · enabled / bypass

Node-Typ: `MusicOptionalStage`. Interne Umschaltung; zentrale Regler sind Node 118.

| ID / Einstellung | Aktueller Wert | Möglichkeiten / Bindung | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| `N120.stage` – stage | Mastering | Technisches Stufenlabel; Benutzer schaltet an Node 118 | G | — |

## Zusätzliche zusammengesetzte App-Bedienelemente

Diese Funktionen sind nicht vollständig als einzelne Backend-Widgets vorhanden. Sie benötigen eine
gemeinsame Bindung oder zusätzliche UI-/Ausführungsarbeit; nicht still als bereits verfügbar behandeln.

| ID | Funktion | Bindung / erforderliche Arbeit | Vorschlag | Deine Wahl |
| --- | --- | --- | --- | --- |
| APP-AEQ | Ein Auto-EQ-Preset mit Beschreibung | Zehn Rezepte plus Custom aus web/eq_presets.json → sechs Werte an N109; Hinweis ohne Referenz | E | — |
| APP-MEQ | Manual-EQ-Preset und Kurve | 24 Rezepte plus Custom → N112.eq_settings_json; Preamp und bis zu acht Bänder mit sämtlichen Typ-/Hz-/dB-/Q-/Slope-/Enable-Werten, Undo | E | — |
| APP-REF | Referenzaudio auswählen/anhören | N109.reference_audio ist derzeit unverbunden; nativen LoadAudio und Anschluss hinzufügen. Coverquelle bleibt getrennt | E, bei Referenzpreset sichtbar | — |
| APP-SOURCE | Coverdatei auswählen/anhören | N121.audio, vorhandene Audio-Upload-Anpassung, native App-Kompatibilität prüfen | H bei Cover | — |
| APP-PROMPT | Finalen Prompt prüfen/freigeben | Style/Caption, Lyrics und Bildprompt; zweistufige Ausführung mit eingefrorenem Prompt neu planen | E, optional | — |
| APP-ABC | ABC anzeigen/kopieren | Ausgabe von N122; ein Editor wäre eigene Funktion mit synchroner Prompt-/Generierungsquelle | E, Anzeige | — |
| APP-KEY | Zugangsschlüssel setzen/löschen | Bestehende LLM-Sitzungsrouten nutzen, keine Secrets in Workflow/Layout | K | — |
| APP-RESULT | Ergebnis und Download-Dateien | N116 finaler Player, N115 gegatetes Artwork, tatsächliche Dateien aus Savern/Produktions-JSON | H | — |
| APP-REPORT | Prompt- und Produktionsbericht | N108 / N99; mehrzeilige Lyrics korrekt anzeigen, tatsächlichen Lauf zuordnen | E | — |
| APP-AB | Original/Final/entfernt anhören | Originalquelle, finale Ausgabe, N123.removed_audio; Abhängigkeiten dürfen keine deaktivierte Stufe aktivieren | E, optional | — |
| APP-EXPORT | Ausgabeformate separat aktivieren | Heute feste Saver-Zweige; echte Export-Schalter benötigen zusätzliche Workflow-/Report-Logik | E, optionale Erweiterung | — |
| APP-INSPECT | Alle Einstellungen mit Suche | Jede fachliche Einstellung auffindbar; Status und Quelle verbundener Werte erklären | H als Zugang | — |
| APP-LAYOUT | Eigene Feld-/Gruppenauswahl | Eigenes Layoutprofil; Sichtbarkeit niemals mit Stufenschalter gleichsetzen | K, optional | — |
| APP-PROFILE | Produktionspreset speichern/laden | Echte Parameter separat vom Layout; keine Geheimnisse, Modellwerte erhalten | E, optional | — |
| APP-RESTORE | Aus Produktions-JSON wiederherstellen | Erst Lücken des bestehenden Metadata-Loaders erfassen; vollständiges Restore noch nicht gegeben | E, spätere Erweiterung | — |

Weitere wählbare UI-Funktionen und Priorisierung: UX-01 bis UX-20 im [Konzept](APP_MODE_KONZEPT.md).

## Erfassungsumfang und offene Bestätigung

Erfasst: **271 gespeicherte Eingabe-/Frontend-Felder** in **41 Nodes**, dazu **15 zusammengesetzte App-Funktionen**.
Mehrfach vorkommende Saver-Parameter sind absichtlich getrennt aufgeführt: die drei Ausgabezweige können unterschiedliche Werte haben.
Nicht als frei editierbare App-Eingaben gezählt: Markdown-Notizen, reine Audio-/Bild-/Conditioning-Verbindungen,
Graphpositionen, unkonfigurierte Vorschauausgänge und automatisch erzeugte Modell-/Metadaten-JSONs.
Interne Callbacks, dynamische Dateilisten und hinzugefügte Laufzeit-Widgets sind zusätzlich in P1 zu prüfen.

**Vorläufige Auswahl:** Alle Einträge offen. Die Spalte „Vorschlag“ ist eine Empfehlung, keine bestätigte Benutzerauswahl.
Nach Auswahl muss jeder H/E/K-Eintrag auf eine getestete App-Bedienmöglichkeit abgebildet werden.
