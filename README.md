# MiniMax Music Production Toolkit für ComfyUI

**Ein paar Felder ausfüllen – fertigen Song bekommen.**

Beschreibe einfach, was du hören willst. Ein Genre, eine Stimmung, ein paar
Worte zum Thema. Den Rest übernimmt der Workflow: Er schreibt daraus einen
ausgereiften Produktionsplan, erzeugt den Song mit **MiniMax Music 3**, repariert
und verfeinert den Klang, gestaltet ein passendes Cover und legt alles sauber
benannt, getaggt und release-fertig in deinen Ausgabeordner.

Du musst kein Audio-Ingenieur sein und keine Kette aus zwanzig Knoten verstehen.
Dieses Toolkit bündelt genau dieses Wissen in **einem** Workflow – so, dass am
Ende ein Ergebnis herauskommt, das du direkt veröffentlichen kannst.

Autor: [Johannes Plenio](https://github.com/jplenio)

> Unabhängiges Community-Projekt. Es werden keine MiniMax-, FLUX-, LLM- oder
> FlashSR-Modellgewichte mitgeliefert – sie werden separat heruntergeladen oder
> bereitgestellt (siehe [Installation](INSTALLATION.md)).

## 🎧 Erst hören, dann ausprobieren

Die Musik auf dieser Seite wurde komplett mit diesem Workflow erzeugt:

👉 [Demo-Galerie öffnen](https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/)

Wenn dir gefällt, was du hörst: Genau dafür ist dieses Projekt da.

## Warum es sich so einfach anfühlt

Der Workflow ist so aufgebaut, dass **du kreativ bleibst und er die Technik
macht**:

- **Wenige Felder.** Genre, Tempo, Tonart, Stimme, Sprache, Stimmung, Länge –
  mehr braucht es nicht. Jedes Feld hat außerdem eine „custom“-Option, wenn du
  etwas offen lassen willst.
- **Ein Textfeld für alles Weitere.** Was nicht in die Felder passt, schreibst du
  einfach als Beschreibung dazu – so frei, wie du möchtest.
- **Das Modell denkt mit.** Ein lokales Sprachmodell formt aus deinen Angaben den
  präzisen Plan, den MiniMax Music 3 braucht, inklusive passendem Songtitel und
  Cover-Idee.
- **Der Klang wird aufgeräumt.** Clipping wird repariert, die Höhen werden
  erweitert (FlashSR), störende Zisch- und Schimmer-Anteile werden gezähmt und
  die Lautstärke streaming-tauglich gemacht.
- **Alles ist am Ende benannt und getaggt.** `Album - Titel`, FLAC + MP3,
  Cover-JPG und eine zentrale Produktions-JSON – ein Song, ein sauberer Ordner.

## So läuft ein Song durch

```text
Du füllst ein paar Felder aus
        ↓
Lokales LLM schreibt Caption, Lyrics, Titel & Cover-Idee
        ↓
MiniMax Music 3 erzeugt den Song
        ↓
Klang wird repariert & verfeinert (Declip → FlashSR → HF-Repair → Release-Prep)
        ↓
FLUX.2 erzeugt das Cover
        ↓
FLAC + MP3 + Cover + Produktions-JSON werden gespeichert
```

Den genauen technischen Ablauf findest du in [AUDIO_PIPELINE.md](AUDIO_PIPELINE.md)
und [WORKFLOW.md](WORKFLOW.md).

## Das Beste daran: der Custom Mode

Beim Prompt kannst du ganz am Anfang **`custom`** wählen. Dann lädt der Workflow
keinerlei Vorlage – er lässt deine Felder exakt so, wie du sie ausgefüllt hast,
und nutzt nur das, was du selbst hineingeschrieben hast.

Warum ist das so großartig?

- **Volle Freiheit, null Überraschungen.** Kein Prompt, der heimlich Felder
  überschreibt. Was du einträgst, ist genau das, was ankommt.
- **Trotzdem kein leeres Blatt.** Die Auswahllisten für Genre, Tempo, Key und
  Co. bleiben erhalten – du kannst dich von Vorschlägen inspirieren lassen,
  ohne sie benutzen zu müssen.
- **Schnellstmöglich starten.** Du musst keine Bibliothek durchsuchen. Einfach
  `custom` wählen, ein paar Felder füllen, eine Beschreibung schreiben – fertig.
- **Beste aus beiden Welten.** Du kannst jederzeit wieder eine Vorlage wählen,
  die dir die Felder vorausfüllt, und danach trotzdem alles überarbeiten.

So wird aus einem „vorgefertigten Werkzeug“ ein echtes Instrument: dein
Geschmack bestimmt den Song, die Maschine sorgt fürs Handwerk.

## Das Toolkit im Überblick

- **Structured Song Prompt** – strukturierte Felder für Genre, Tempo, Tonart,
  Lyrics, Sprache, Stimme, Thema und Länge plus freie Beschreibung. Prompt-Dateien
  können die Felder vorausfüllen; jedes Feld lässt sich überschreiben und
  `custom` lässt es ganz weg.
- **Integrierter LLM-Chat (llama.cpp)** – lokales GGUF-Sprachmodell, kein
  externer LLM-Knoten nötig. Die LLM-Stufe lässt sich auch komplett abschalten.
- **Strukturiertes Parsing** – extrahiert `[Caption]`, `[Lyrics]`, `[Title]` und
  `[Image_Prompt]` aus der Antwort, mit manuellen Fallbacks.
- **Produktions-Systemprompt** – auf MiniMax Music 3 abgestimmt: lange
  Instrumentalstrukturen, einfallsreiche Lyrics und Vermeidung matschiger
  Höhen.
- **Prompt-Bibliothek** – über 60 fertige Genre-Vorlagen mit Metadaten.
- **Reproduzierbare Einstellungen** – konsistente Seeds und Sampling-Werte.
- **Integriertes Audio Super Resolution (FlashSR)** – der Inferenz-Code ist
  gebündelt; nur die Gewichte werden beim ersten Lauf geladen.
- **Modell-Auto-Download / Prüfung** – `models_config.json` plus Prüf-Knoten mit
  Fortschrittsanzeige.
- **Declip / Overload-Repair** – rekonstruiert kurzzeitig hart beschnittene Peaks.
- **FlashSR-Werkzeuge** – Pre-/Post-Filter und kontrollierte Höhen-Mischung.
- **HF Cymbal / Shimmer Repair** – reduziert verwaschene obere Frequenzen, ohne
  die Transienten zu zerstören.
- **Statische LUFS / True-Peak Release-Prep** – konstante Lautheit ohne AGC,
  Kompressor oder zeitabhängiges Lautheits-Riding.
- **Release-Dateien** – FLAC/MP3/WAV, `Album - Titel`-Benennung, Standard-Tags,
  einstellbare Cover-Auflösung.
- **Zentrale Produktions-JSON** – ein kanonisches JSON pro Song nach allen
  Ausgaben.
- **FLUX.2-Cover-Zweig** – quadratisches Artwork und JPEG-Speicherung.
- **Komplette UI-Hilfe** – Tooltips für jeden Eingang und Markdown-Hilfe für
  jeden Knoten.

## Installation

Installiere das Paket in das `custom_nodes`-Verzeichnis deiner ComfyUI-
Installation und installiere die Abhängigkeiten mit dem Python-Interpreter, der
zu deiner ComfyUI-Installation gehört. Danach ComfyUI neu starten und den
Browser einmal hart neu laden (`Ctrl+F5`).

Für den integrierten LLM-Chat zusätzlich in derselben Umgebung installieren:

```bash
python -m pip install llama-cpp-python
```

und eine llama.cpp-kompatible GGUF nach `models/llm` legen (oder eine
Download-URL in `models_config.json` konfigurieren).

Die vollständige Anleitung: [INSTALLATION.md](INSTALLATION.md).

## Beispiel-Workflow

Lade:

`example_workflows/MiniMax_Music3_Production_Toolkit.json`

Der öffentliche Workflow enthält nur generische Metadaten und keine
maschinenbezogenen Pfade. Er ist als vollständiger Referenz-Workflow gedacht;
jeder einzelne Knoten lässt sich auch unabhängig verwenden.

## Demo & SoundCloud

Die eingebaute **35-Track**-GitHub-Pages-Demo wird aus den erzeugten
Produktionsdaten gespeist und zeigt Cover, SoundCloud-Player, Suche/Filter,
musikalische Kurzbeschreibungen und aufklappbare Generierungsdetails.

- Player-Seite: `docs/index.html`
- Track-/SoundCloud-Konfiguration: `docs/demo-tracks.js`
- Cover: `docs/assets/demo-covers/`
- Anleitung: [AUDIO_EXAMPLES.md](AUDIO_EXAMPLES.md)
- Öffentliche Seite: `https://jplenio.github.io/ComfyUI-MiniMax-Music-Production-Toolkit/`

## Dokumentation

- [Installation & Abhängigkeiten](INSTALLATION.md)
- [Komplette Workflow-Anleitung](WORKFLOW.md)
- [Prompt-Bibliothek](PROMPT_LIBRARY.md)
- [Audio-Verarbeitung](AUDIO_PIPELINE.md)
- [Artwork-Workflow](ARTWORK_WORKFLOW.md)
- [Audio-Beispiele / SoundCloud](AUDIO_EXAMPLES.md)
- [Fehlerbehebung](TROUBLESHOOTING.md)
- [Publishing / Maintainer-Guide](PUBLISHING.md)
- [Entwicklungs-Guide](DEVELOPMENT.md)
- [Changelog](CHANGELOG.md)

## Einschränkungen

- De-Clipping kann plausible Peak-Krümmung rekonstruieren, aber keine
  Information wiederherstellen, die durch Clipping zerstört wurde.
- FlashSR kann Hochfrequenz-Inhalte „erfinden“. Hybrid-Crossover und HF-Repair
  sind Sicherheitsnetze, keine Garantien.
- Statische LUFS-Normalisierung erhält die Dynamik und kann bewusst unter einem
  angefragten Ziel bleiben, wenn das True-Peak-Limit keine weitere Anhebung
  zulässt.
- Die LLM-Qualität hängt vom gewählten lokalen Modell ab.
- GitHub-README-Seiten können keinen nativen SoundCloud-Player zuverlässig
  einbetten; dafür ist die GitHub-Pages-Demo gedacht.

## Lizenz

MIT. Siehe [LICENSE](LICENSE) und [NOTICE.md](NOTICE.md).
