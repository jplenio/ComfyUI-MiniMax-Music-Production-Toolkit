# App-Mode für das Music Production Toolkit – Konzept und Ausführungsplan

**Stand:** 16.09.2026 · **Status:** Konzept, noch keine App-Mode-Implementierung.

**Entscheidungsvorlage:** Welche Einstellungen sollen sofort sichtbar sein, welche
unter „Erweitert“ und welche unter „Einrichtung“? Der vollständige
[Konfigurationskatalog](APP_MODE_KONFIGURATIONSKATALOG.md) enthält die aktuellen
Felder sowie zusätzliche Vorschläge. Seine Auswahlspalte bleibt bewusst offen.
Alle Empfehlungen sind Vorschläge; keine bisherige Einstellung wird entfernt.

## 1. Ziel und Umfang

Der App-Mode soll einen Song ohne Kenntnis des Node-Graphen erstellbar machen.
Dabei bleiben YuE2, YuE2 Cover und MiniMax Music 3, alle Audio-Stufen, die
Prompt-Kontrolle, sämtliche Modellparameter und die Ausgabeoptionen verfügbar.
Die Oberfläche ordnet diese Möglichkeiten nach der Aufgabe des Benutzers.

Primärer Gegenstand ist `example_workflows/Music_Production_Toolkit.json`.
Der klassische MiniMax-Workflow und das Audio Enhancement Lab bleiben bestehen;
eigene App-Ansichten dafür sind eine anschließende Ausbaustufe. Diese Planung
ändert weder den laufenden Workflow noch die installierte ComfyUI-Instanz.

„Ohne Einschränkung“ bedeutet:

- Jede bisher direkt bedienbare fachliche Einstellung erhält einen erreichbaren
  Platz in Hauptansicht, erweitertem Bereich oder Einrichtung.
- Alle vorhandenen Auswahllisten und zulässigen Werte bleiben erhalten.
  Vereinfachte Beschriftungen dürfen Werte weder zusammenlegen noch begrenzen.
- Benutzerwerte bleiben beim Wechsel von Modell, Ansicht und Preset erhalten.
- Verkabelte, abgeleitete Werte werden an ihrer zuständigen Quelle eingestellt.
  Die App zeigt nicht mehrere widersprüchliche Regler für denselben Wert.
- Der Graph bleibt für freie Verkabelung, neue Nodes und Strukturänderungen
  erreichbar. Ein Graph-Rücksprung allein ersetzt jedoch keinen noch fehlenden
  App-Regler für eine als App-Funktion zugesagte Einstellung.

## 2. Technische Ausgangslage und Grenzen

### 2.1 Belegte native Funktionen

Der offizielle Guide nennt App-Mode ab Frontend 1.41.13, Auswahl von Ein- und
Ausgaben, eine Vorschau, die Wahl der Startansicht, Ausführung/Abbruch und
schmale Bildschirmansichten. Die Dokumentation beschränkt Share-Links auf
Comfy Cloud. Eine lokale App benötigt für dieses Konzept keine Veröffentlichung.
[Quelle: offizieller App-Mode-Guide](https://docs.comfy.org/interface/app-mode).

Comfy beschreibt App-Mode als andere Ansicht desselben Workflows mit demselben
Backend und derselben Queue. Der App Builder erlaubt nach der Ankündigung
Beschriftung, Reihenfolge und Gruppierung der ausgewählten Eingaben.
[Quelle: Comfy-Ankündigung vom 10.03.2026](https://blog.comfy.org/p/from-workflow-to-app-introducing).

Die ältere Ankündigung formuliert die Verfügbarkeit von Share-Links weiter als
der aktuelle Guide. Für dieses lokale Projekt wird daraus keine lokale
Freigabefunktion abgeleitet; Teilen/Hosting gehört nicht zum ersten Umfang.

### 2.2 Lokal überprüfter Bestand

- Das installierte Frontend-Paket meldet **1.52.7**; auch die lokale
  ComfyUI-Anforderung nennt diese Version. Das ist ein Paketbefund, kein Beleg,
  welche Version der derzeit geöffnete Browser tatsächlich geladen hat.
- Der Hauptworkflow speichert `extra.frontendVersion = 1.48.7`. Dieser historische
  Speicherwert darf nicht als aktive Frontend-Version verwendet werden.
- Es gibt noch keine App-Mode-Konfiguration im geprüften Hauptworkflow.
- Auto-EQ besitzt einen eigenen DOM-Presetselektor; `target_mode` ist intern
  weiterhin gespeichert und im Graphen ausgeblendet.
- Manual EQ besitzt einen DOM-Kurveneditor mit Presetauswahl und Undo.
- LLM-Auswahl, Modellabfrage und Zugangsdaten sowie Prompt-Speicherbuttons
  verwenden zusätzliche Frontend-Logik und zum Teil eigene Server-Routen.
- Cover-Upload verwendet native Audio-Widgets mit einer gezielten
  Toolkit-Anpassung. Deren bisherigen Initialisierungsfehler nicht wiederholen.

### 2.3 Was vor der Umsetzung ausdrücklich zu prüfen ist

| Frage | Warum sie relevant ist | Vorgehen bei fehlender Unterstützung |
| --- | --- | --- |
| Werden unsere DOM-Widgets in der App dargestellt und bedienbar? | Auto-EQ, Manual EQ, Prompt-Report | Gemeinsame Bedienlogik mit App-Adapter verwenden; keinen zweiten unabhängigen Zustand schaffen. |
| Lösen App-Änderungen dieselben Callbacks aus? | Presetwerte, Promptdatei-Prefill, Modellwechsel, LLM-Felder | Gemeinsame Änderungsfunktion aus beiden Ansichten aufrufen. |
| Sind Gruppen, Ein-/Ausklappen und bedingte Sichtbarkeit ausreichend steuerbar? | Kurze Hauptansicht trotz großer Auswahl | Kleine Toolkit-Erweiterung prüfen; im ersten Prototyp ehrliche statische Gruppen. |
| Funktionieren Audio-Upload und alle benötigten Audio-/Bild-/Textausgaben? | Coverquelle, Referenz, Ergebnis, Berichte | Native Upload-/Preview-Nodes beziehungsweise gezielte Adapter; keine bloßen Textpfade als Ersatz für einen Audioplayer. |
| Wie werden App-Bindings gespeichert und nach Änderungen wiederhergestellt? | Stabile Workflow-Dateien | Erst reale Builder-Datei erzeugen und Schema prüfen; keine App-JSON-Schlüssel erfinden. |
| Können einzelne Frontend-Aktionen angeboten werden? | API-Key-Eingabe, Listen aktualisieren, Prompt speichern | Dedizierte Buttons mit bestehenden Funktionen verbinden. |

Suchfelder, Favoriten, persönliche Layoutprofile, ein App-Experteninspektor,
flexible Abhängigkeiten und A/B-Player sind **gewünschte Erweiterungen**, keine
hier bereits nachgewiesenen nativen App-Mode-Funktionen.

## 3. Aufbau der Benutzeroberfläche

Die native App-Aufteilung wird genutzt: Ergebnisbereich und Eingabebereich,
auf schmalen Displays entsprechend erreichbare Tabs. Keine feste Zusage einer
eigenen links/rechts-Anordnung, bevor der Builder-Prototyp geprüft ist.

**Empfohlene Hauptansicht:**

1. **Song erstellen:** Modell, Musikvorlage, Beschreibung, Instrumental/Gesang,
   gewünschte Länge. Bei YuE2 Cover direkt die Quelldatei und den Cover-Modus.
2. **Klang und Produktion:** Artwork, Refinement, Artefaktreduktion und Mastering
   als vier unabhängige Schalter; aufklappbare Einstellungen darunter.
3. **Veröffentlichen:** Artist, Album, Ausgabeverzeichnis; weitere Tags/Dateioptionen
   unter „Erweitert“.
4. **Erstellen und Ergebnis:** Start/Abbruch, tatsächliche aktive Verarbeitung,
   Audioplayer, Artwork und Links zu den erzeugten Dateien.

Skizze des Inhalts, nicht einer bereits vorhandenen App-Implementierung:

```text
Music Production Toolkit                    [Einrichtung] [Alle Einstellungen]

Song erstellen
  Modell: YuE2 | YuE2 Cover | MiniMax Music 3
  Vorlage [Auswahl]     Instrumental / Gesang [vollständige Auswahl]
  Beschreibung [mehrzeilig]        Gewünschte Länge [Auswahl / individuell]
  Bei Cover: Quelldatei [Auswählen] [Anhören]   Begleitung [full / melody]
  [Musikalische Details] [Prompts prüfen / selbst bearbeiten]

Klang und Produktion
  Artwork [an]  Refinement [modellabhängig]  Artefaktreduktion [an]  Mastering [an]
  [Artefaktreduktion: Balanced] [EQ] [Kompression und Lautheit]
  Hinweis: Referenz-EQ ausgewählt – Referenzaudio fehlt, Korrektur wird übersprungen.

Artist [       ]  Album [       ]  Ausgabeverzeichnis [                  ]
  [Weitere Ausgabeoptionen]

[Song erstellen]       Tatsächlich aktiv: YuE2 · Balanced · Mastering
Ergebnis: [Audioplayer] [Artwork] [FLAC] [MP3] [Original] [Berichte]
```

Die Hauptansicht soll gewöhnlich ohne mehr als etwa 10–15 gleichzeitig
geöffnete Eingabefelder auskommen. Das ist ein Gestaltungsziel, keine Begrenzung
der insgesamt erreichbaren Einstellungen.

## 4. Ebenen und Auswahl der sichtbaren Funktionen

| Kennzeichen | Ebene | Regel |
| --- | --- | --- |
| H | Hauptansicht | Häufige kreative Entscheidungen, direkt sichtbar. |
| E | Erweitert | Voll bedienbar in derselben App, zunächst eingeklappt. |
| K | Einrichtung | Wiederverwendbare Modell-/LLM-/Dateieinstellungen. |
| A | Anzeige / abgeleitet | Nicht doppelt editieren; Verweis auf zuständige Quelle. |
| G | Graph / technische Struktur | Node-Verbindungen, Hilfswerte und reine Darstellung. |

Der Katalog schlägt pro Feld eine Ebene vor. In **„Deine Wahl“** kann die
gewünschte Ebene eingetragen werden. Bei einem verbundenen Feld zuerst die
zuständige Quelle bestimmen; eine Umstufung von A zu H macht einen berechneten
Wert nicht automatisch beschreibbar.

Ein späterer Befehl **„Ansicht anpassen“** könnte Felder anheften, Gruppen
umordnen und Layoutprofile speichern. Ausblenden ändert ausschließlich die
Ansicht, niemals Parameterwerte oder die Ausführung einer Stufe. Die alternative
Ansicht „Alle Einstellungen“ muss ausgeblendete bedienbare Felder wiederfinden.

## 5. Fachlicher Auswahlkatalog – empfohlene Gruppen

Die Detaildatei enthält jeden erfassten Parameter einzeln. Diese Tabelle ist die
inhaltliche Vorauswahl für die Konzeption:

| Bereich | Denkbare App-Einstellungen | Empfehlung |
| --- | --- | --- |
| Modell | YuE2, YuE2 Cover, MiniMax Music 3 | H |
| Coverquelle | Datei/Upload, Abspielen, full/melody, abgeleiteter Titel | H, nur bei Cover |
| Musikvorlage | Bibliotheks-/eigene Vorlage, Dateiquelle, Speichern, Aktualisieren | H; Speicherort K |
| Musikbeschreibung | Freitext; Genre, Tempo/BPM, Taktart, Tonart, Thema | Freitext H; Details E oder anheftbar |
| Stimme | Lyrics-Modus, Sprache, Stimme, Instrumental, nur Stimme ohne Worte | Modus H; Details kontextabhängig |
| Länge | Musikalische Ziellänge, technische Maximallänge je Modell | Ziel H; Maximum E, klar getrennt |
| Prompts | Systemvorlage, eigene System-Prompts, finaler Style/Caption, Lyrics, Artwork-Prompt | Vorlagen E; vollständiger Editor E |
| Manuelle Produktion | LLM aus, manuelle Style/Lyrics/Titel/Bild-Prompt-Felder | E; dann erforderliche Felder aufklappen |
| Varianten | Songanzahl, Seed-Modus, Basisseed, Seed-Offset | H/E; alle bestehenden Modi erhalten |
| LLM | In ComfyUI / lokale App / Cloud, Anbieter, Modell, Verbindung | Modus/Modell H oder K; Verbindung K |
| LLM-Details | Tokenlimits, Sampling, Kontext, GPU-Schichten, Gerätesplitting, Timeout, Thinking | E/K vollständig |
| Musikmodell-Details | Checkpoints/Encoder/VAE, Schritte, CFG, Sampler/Scheduler, Text-/ABC-Sampling | E/K, getrennte Werte pro Modell |
| Modellbeschaffung | Auto-Download, ausgewählter Song, SheetSage2, LLM, Artwork, FlashSR | K; relevante Statusanzeige H |
| Produktionsstufen | Artwork, Refinement, Artefaktreduktion, Mastering | H; kein verstecktes globales Qualitäts-Preset |
| Artefaktreduktion | An/Aus, Analyse/Reduce, Sensitivity, Frequenzbereich, maximale Reduktion, Anschlagschutz, Mix | Schalter H; Rest E |
| Refinement | Declip, PRE/POST-Filter, FlashSR, Crossover, HF-Reparatur, sämtliche Custom-Werte | E, nur aktive Stufe hervorheben |
| Auto-EQ | Ein/Aus, ein Preset, Referenzdatei, Stärke/Gain/Bänder/Frequenzbereich | E; Referenzbedarf sofort sichtbar |
| Manual EQ | Preset, Bypass, Kurve, acht Bänder, Typ/Frequenz/Gain/Q/Slope/Enable, Preamp, Undo | E; keine zweite Auto-EQ-Anwendung anzeigen |
| Mastering | Kompressionspreset/Custom, Kompression an/aus, LUFS/Peak, Dynamik-/Limiterparameter | Preset H/E; sämtliche Details E |
| Artwork | Auflösung, eigener Prompt, Seed, Sampler/Steps/CFG, Modelle, JPG-Qualität, eingebettete Covergröße | E; Modelle K |
| Veröffentlichung | Artist, Album, Jahr, Track, Genre, Kommentar, Album-Artist, Komponist | Artist/Album H; übrige E |
| Dateien | Basisordner, Unterordner, Format-/Bit-Tiefen-/MP3-Optionen je Saver, Kollisionen, Namensschema, Tags/Sidecars | H/E/K nach persönlicher Wahl |
| Ergebnisse | Finales Audio, Original, Artwork, FLAC/MP3, Prompt-Markdown, Produktions-JSON | H; technische Details E |

## 6. Verbindliche Interaktionsregeln

### Modelle, Quellen und Namen

- Modellwechsel verändert die Auswahl der relevanten Felder und der tatsächlich
  ausgeführten Nodes, löscht aber keine gespeicherten Einstellungen des anderen
  Modells. Das gilt auch beim Wechsel zurück von Cover zu neuer Komposition.
- Bei YuE2 Cover bleibt der Titel aus Quelldateiname plus `-cover` abgeleitet.
  Keine frei editierbare App-Titelbox anbieten, deren Wert später ignoriert wird.
  Der Dateiname und die Quelle werden vor dem Lauf sichtbar bestätigt.
- Quelldatei für Cover und Auto-EQ-Referenz sind getrennte Aufgaben mit getrennten
  Dateifeldern. Keine automatische Gleichsetzung dieser Audiodateien.
- SheetSage2-ABC bleibt die gemeinsame Quelle für Cover-Konditionierung und
  angepassten Prompt. ABC anzeigen/kopieren ist möglich; ein ABC-Editor wäre eine
  gesonderte Erweiterung mit durchgängiger Verdrahtung, kein bloßes Textfeld.

### Aktuelle Defaults, die die App unverändert übernehmen muss

| Einstellung | Aktueller Hauptworkflow |
| --- | --- |
| Modell | YuE2 |
| Artwork | An |
| Refinement | Model default: YuE2/Cover aus, MiniMax an |
| Artefaktreduktion | An, Balanced, maximal 3 dB |
| Mastering | An |
| Auto-EQ | Warm - gentle (workflow default); Warm tilt, 35 %, maximal 2 dB, vier Bänder |
| Auto-EQ ohne Referenz | Hinweis und neutrale Durchleitung; übrige Verarbeitung läuft |
| Manual EQ | Flat |
| YuE2 Schritte / Obergrenze | 40 / 360 Sekunden |
| YuE2 Checkpoint | yue2_3b_bf16.safetensors |
| Release-Ausgaberate | 44,1 kHz, 48 kHz wählbar |
| Release-Kommentar | Generated with jplenio Music Production Toolkit |

Bestehende Benutzer-Workflows dürfen durch Öffnen der App nicht auf diese Werte
zurückgesetzt werden. Die tatsächlich geladenen Werte haben Vorrang.

### Keine widersprüchlichen Regler

- Auto-EQ hat genau einen Presetselektor. `target_mode` bleibt intern. Die
  verknüpfte Apply-Auto-EQ-Instanz wird nicht als zweiter EQ angeboten; eine
  dort gespeicherte lokale Flat-Voreinstellung darf nicht als Ergebnis erscheinen.
- Manual EQ bleibt die eigenständige, editierbare Instanz. Bei Custom zeigt die
  App die reale Kurve und Werte, nicht nur einen veralteten Presetnamen.
- Mastering aus und Kompression aus sind verschieden: ersteres überspringt
  auch EQ/Rate/Lautheit, letzteres lässt Lautheit/Peak-Kontrolle aktiv.
- Zentraler Stufenschalter und darunter sichtbarer Status verweisen auf dieselbe
  Quelle. Keine zweite unverbundene Checkbox am Unterpanel.
- Eine gesperrte verbundene Einstellung erklärt „gesteuert durch …“ und bietet
  den Weg zum Quellregler. Kein deaktiviertes Feld ohne Erklärung.

### Länge, Instrumental und Prompt-Übernahme

- „Gewünschte Songlänge“ bleibt ein musikalisches Ziel. Die technische Obergrenze
  ist separat. Keine automatische Kürzung, kein Cut bei Erreichen des Ziels.
- Instrumental setzt die bestehenden modellabhängigen Promptregeln fort;
  versteckte Vocal-Felder dürfen ihnen nicht entgegenwirken. Humming bleibt eine
  ausdrückliche kreative Wahl, falls vom Benutzer gewünscht.
- Vorlagen laden und Modellwechsel dürfen manuell bearbeitete Prompts nicht
  unbemerkt überschreiben. Entwurf je Vorlage/Modell erhalten; „Vorlage erneut
  übernehmen“ als bewusste Aktion, mit Rückgängig-Möglichkeit.
- Ein Modus „erst Prompt erstellen, danach freigeben und Audio erzeugen“ ist
  attraktiv, aber **zusätzliche Ausführungslogik**: finalen Prompt snapshotten,
  beim zweiten Schritt keine erneute zufällige LLM-Ausgabe erzeugen. Nicht als
  bloßer zusätzlicher Startbutton umsetzen.

## 7. Weitere konfigurierbare App-Funktionen zur Auswahl

Alle folgenden Punkte sind optionale Konzeptbausteine, noch nicht umgesetzt:

| ID | Möglichkeit | Nutzen / Umfang | Vorschlag |
| --- | --- | --- | --- |
| UX-01 | Deutsch/Englisch | Labels/Hilfe übersetzen, Modell-/Preset-IDs stabil halten | Erste Version |
| UX-02 | Kompakt / Komfort / Experte | Unterschiedliche Sichtbarkeit, identische Parameter | Erste Version: Haupt + Erweitert; weitere Profile später |
| UX-03 | Felder anheften und Gruppen sortieren | Eigene häufige Einstellungen vorn | Nach Kernfunktion |
| UX-04 | Suche über alle Einstellungen | Auch verborgene/inaktive Werte auffindbar | Hohe Priorität |
| UX-05 | Layoutprofile je Aufgabe | Neues Lied, Cover, reine Nachbearbeitung | Nach Kernfunktion |
| UX-06 | Hilfe kurz / ausführlich | Wenig Text im Alltag, Erklärung bei Bedarf | Erste Version |
| UX-07 | Aktive Verarbeitung zusammenfassen | Erwartung mit realer Ausführung abgleichen | Erste Version |
| UX-08 | Änderungen gegenüber geladenem Profil | Eigene Anpassungen erkennen; gezielt zurücksetzen | Nach Kernfunktion |
| UX-09 | Produktionspreset speichern | Parameterzustand getrennt vom Layout speichern | Nach Kernfunktion |
| UX-10 | Prompt-Vorschau vor Audio | Bewusste Prüfung; braucht zweistufigen Ablauf | Gesondertes Arbeitspaket |
| UX-11 | A/B-Player Original / Final / entfernt | Reparatur und Mastering beurteilen | Nach sicherer Vorschauintegration |
| UX-12 | Lautheitsangepasstes A/B | Fairer Vergleich, ausschließlich Wiedergabepegel | Später; Export unverändert |
| UX-13 | Variantenübersicht mit Favoriten | Mehrere Ergebnisse übersichtlich bewerten | Nach Kernfunktion |
| UX-14 | Aus Produktions-JSON wiederherstellen | Reproduzierbarkeit | Erst Loader-Lücken analysieren; kein heutiges Vollrestore versprechen |
| UX-15 | Nur Artwork / nur Nachbearbeitung erneut ausführen | Keine unnötige Neugenerierung | Eigene Teil-Ausführungsplanung und Cache-Regeln nötig |
| UX-16 | Bestimmte Download-/Verbindungsdetails anzeigen | Einfache Oberfläche, bei Problemen Diagnose | Erste Version in Einrichtung |
| UX-17 | Automatische Ergebniswiedergabe | Komfortoption | Optional, standardmäßig aus |
| UX-18 | Tastaturbedienung, größere Schrift, Kontrast | Barrierearme Bedienung | Erste Version |
| UX-19 | Validierung vor dem Queue-Start | Fehlende Coverquelle/Modelle früh erklären | Erste Version |
| UX-20 | Persönliche Startansicht App/Graph | Bestehende Arbeitsweise respektieren | Erste Version |

Keine Oberfläche soll automatisch Dateien löschen, hochladen oder veröffentlichen.
Bestehende lokale und Cloud-LLM-Optionen bleiben mit ihrer tatsächlichen
Datenübertragung erkennbar. API-Schlüssel bleiben in der bestehenden sicheren
Sitzungsverwaltung; sie gehören weder in App-Layouts noch in Workflow-Dateien.

## 8. Empfohlene Architektur

### Ein Workflow und eine maßgebliche Quelle für jeden Wert

Die App ist eine Ansicht desselben Graphen. Keine zweite Generation-Pipeline und
kein dauerhafter Fork der Audio-Logik. App-Bindings identifizieren fachliche Rollen
wie `production`, `song_request`, `music_settings`, `auto_eq`, `manual_eq` und
`artifact_reduction`; beim Binden werden Node-Typ und Feldname geprüft. Die
aktuellen Node-IDs stehen im Katalog, sind aber nicht als einzige dauerhafte
Identität ausreichend, wenn Benutzer Nodes duplizieren oder ersetzen.

Eine vorgeschlagene Toolkit-Manifestdatei könnte pro Feld führen:
`id`, Rolle, Node-Typ, Eingabename, Label, Gruppe, Ebene, Sichtbarkeitsbedingung,
Hilfe, Darstellungsart und Nur-Lesen-Verweis. Das ist ein **eigenes geplantes
Schema**, kein behauptetes ComfyUI-App-Schema. Es speichert keine zweite Kopie
der Audio-Parameter. Layoutprofil und Produktionspreset sind getrennte Objekte.

### Gemeinsame Adapter statt doppelter Logik

- Presets lesen `web/eq_presets.json` und `web/mastering_presets.json` gemeinsam.
  Presetwechsel setzt alle zugehörigen Werte zusammen; numerische Änderungen
  aktualisieren Custom. Auch App-Änderungen müssen diese Logik auslösen.
- Promptauswahl nutzt bestehende Bibliotheks-/Metadatenfunktionen und ihre
  Aktualitätsprüfung bei asynchronen Antworten. Alte Antworten dürfen einen
  inzwischen bearbeiteten Prompt nicht überschreiben.
- LLM-Verbindungsaktionen verwenden die vorhandenen Konfigurationsrouten und
  Sitzungsdaten. Keine Zugangsdaten als frei serialisierbares Widget ergänzen.
- Manual-EQ-Editor und Reports müssen entweder nativ nachweislich funktionieren
  oder gezielt an die App-Ansicht angepasst werden. Darstellungslogik darf geteilt
  werden, die eigentliche Signalverarbeitung bleibt im bestehenden Backend.
- Die App darf keine Wiederherstellung nur anhand von Presetnamen durchführen;
  gespeicherte reale Werte und Custom-Einstellungen haben Vorrang.

### Ergebnis- und Laufmodell

Jeder Lauf erhält einen eingefrorenen Satz angeforderter Werte und einen Bezug
zu den wirklichen Ergebnisdateien/Berichten. UI-Änderungen während des Laufs
gelten für den nächsten Auftrag. Ergebnisansicht und Warteschlange dürfen nicht
alte Dateien als neues Ergebnis darstellen.

Audio-Preview muss aus der finalen Ausgabe hinter den Stufenschaltern kommen.
Zusätzliche Vorschauen dürfen deaktiviertes Refinement, Artwork oder Mastering
nicht durch neue Abhängigkeiten aktivieren. Für A/B gegebenenfalls einen
separat gegateten Vergleichsausgang planen und testen. Fortschritt aus echten
Ereignissen ableiten; keine erfundenen Restzeiten für LLM/Generierung.

## 9. Ausführungsplan und Abnahmepunkte

Aufwände sind grobe aktive Entwicklungstage, keine Terminzusage. Die technische
Vorprüfung bestimmt vor allem den Adapteraufwand. Ein kleiner nativer Prototyp
ist ausdrücklich noch keine fertige Oberfläche mit vollständiger Auswahl.

| Paket | Arbeit | Konkretes Ergebnis / Abnahme | Abhängigkeit | Aufwand |
| --- | --- | --- | --- | --- |
| P0 | Katalog durchgehen, H/E/K/A/G festlegen, optionale UX-Funktionen priorisieren | Ausgefüllte Auswahl, dokumentierte erste Version | Dieses Konzept | 0,5–1 |
| P1 | Isolierter Builder-Prototyp auf verifizierter Frontend-Version; App-Speicherschema, Audio, Custom-Widgets, Callbacks prüfen | Kompatibilitätsmatrix mit bestanden/offen, gespeicherter Prototyp | P0 | 1–2 |
| P2 | Rollenbindungen, gemeinsame Änderungsfunktionen, Zustandserhalt, Layoutschema planen/implementieren | App ↔ Graph ↔ Datei rundlaufend ohne Werteverlust | P1 | 1–2 |
| P3 | Hauptansicht und Einrichtung aufbauen: Modell, Coverquelle, Brief, LLM, Stufen, Dateien | Song-/Cover-Kernablauf bedienbar | P2 | 2–3 |
| P4 | Erweiterte Einstellungen, Presets/EQ-Editor, Promptaktionen und vollständigen Feldzugang integrieren | Jeder ausgewählte Katalogeintrag erreichbar; keine doppelten Quellen | P2/P3 | 2–5 |
| P5 | Vorabhinweise, Laufstatus, Audio/Bild/Berichte und Dateizugriff anbinden | Richtiger Lauf, richtige Dateien, saubere Abbrüche | P3 | 1–2 |
| P6 | Persistenz-, Schalter-, Browser-, Tastatur- und reale Audio-Abnahme | Prüfkatalog unten bestanden; Grenzen dokumentiert | P4/P5 | 2–3 |
| P7 | App-Workflow/Ansicht paketieren, Anleitung, Migration, Release-Vorbereitung | Installierbares geprüftes Ergebnis; Graph weiterhin nutzbar | P6 | 0,5–1 |

**Grobe Größenordnung:** 10–19 aktive Tage für die umfassende erste Version,
je nach App-Unterstützung der Custom-Widgets. Optionale Funktionen wie Prompt-
Freigabe, Teil-Ausführung oder vollständiges JSON-Restore werden nach P1/P0
separat geschätzt. Eine reduzierte native Ansicht kann früher entstehen, erfüllt
aber noch nicht automatisch den Anspruch vollständiger Einstellmöglichkeiten.

### Vorgesehene Dateien / Arbeitsbereiche bei späterer Umsetzung

- Hauptworkflow: native App-Konfiguration ergänzen, Struktur und Defaults erhalten.
- Geplantes Manifest, zum Beispiel `web/app_mode/fields.json`: erst nach P1
  festlegen; Rollen-/Feldmetadaten und Ebenen, keine Geheimnisse/Parameterduplikate.
- Gemeinsame UI-Adapter für `eq_presets`, `audio_eq`, `mastering_presets`,
  `structured_prompt`, `song_model` und `llm_provider` prüfen und bei Bedarf
  aus den bisherigen Node-Hooks lösen. Vorhandene Graph-Funktionalität erhalten.
- Backend nur ändern, wenn eine ausgewählte zusätzliche Funktion es benötigt;
  additive Schnittstellen und unveränderte bestehende Widget-Reihenfolge.
- Neue Tests für App-Bindings und Browserbedienung; bestehende Workflow-,
  Schema-, Metadaten- und Audio-Tests weiterhin laufen lassen.
- README, App-Anleitung, Node-Hilfe, Kompatibilitätsmatrix und Release-Notes
  aktualisieren. Heute wird ausschließlich dieses Konzept erstellt.

## 10. Prüfkatalog für die Umsetzung

| Prüfung | Erfolgskriterium |
| --- | --- |
| Vollständigkeit | Jeder fachliche Katalogeintrag ist einer realen Bedienmöglichkeit zugeordnet; keine still verschwundenen Auswahlwerte. |
| Roundtrip | Graph → App → Speichern → Laden → Graph erhält Werte, Links, Custom-Presets und manuelle Prompts. |
| Modelle | Alle drei Modelle, Wechsel hin/zurück, getrennte Modellparameter und Cover-Namensregel korrekt. |
| Schalter | 3 Modelle × 2 Artwork × 3 Refinement-Wahlen × 2 Artefaktreduktion × 2 Mastering = 72 zentrale Kombinationen; unerwünschte Zweige laufen nicht. |
| Referenz-EQ | Mit/ohne Referenz, Presetwechsel und Custom: verständlicher Hinweis; ohne Referenz kein Abbruch und keine behauptete Korrektur. |
| EQ-Bedienung | Nur ein Auto-Preset, separate Manual-Kurve, Undo, acht Bänder; keine lokale Flat-Anzeige als angebliches Auto-Ergebnis. |
| LLM | Alle drei Betriebsarten, Modellabfrage, Schlüssel setzen/löschen, Verbindungsausfall; keine Schlüssel in gespeicherten Dateien. |
| Prompt-Bibliothek | Vorlage, eigenes Verzeichnis, manuelle Änderungen, asynchrone Wechsel und Speichern ohne unbeabsichtigtes Überschreiben. |
| Cover-Audio | Upload, bestehende Datei, Preview, Wiederöffnen, full/melody, SheetSage2; keine UNKNOWN-Widgets. |
| Ausführung | Queue, Abbruch, Fehler und erneuter Start; Ergebnis gehört zum richtigen Auftrag. |
| Ergebnisse | Audio/Artwork und Dateilinks vorhanden; Original bleibt Original; Artefakt-Differenz und Reports stimmen. |
| Dauer | Ziel und Obergrenze verständlich getrennt; kein neuer Cut durch App-Logik. |
| Bedienbarkeit | Tastatur, Fokus, Beschriftungen, mehrzeilige Lyrics unter Windows, schmale Ansicht ohne abgeschnittene Regler. |
| Versionen | Getestete lokale Frontend-Version und Mindestversion dokumentiert; nicht unterstützte Adapter mit klarer Diagnose. |

Die 72 Kombinationen werden zunächst über Graph-/Abhängigkeitsprüfungen
abgedeckt. Nicht 72 teure GPU-Generierungen verlangen: pro Modell ein echter
End-to-End-Lauf plus gezielte reale Gegenprüfungen der kritischen Schalter,
Audioausgaben und Custom-Widgets. Automatisierte Attrappen ersetzen diese
Browser-/Hörabnahme nicht.

## 11. Entscheidungen vor dem Bau

1. Im Katalog pro Feld H/E/K/A/G auswählen; vorgeschlagene Gruppen bei Bedarf ändern.
2. Erste Version: nur native App-Ansicht oder zusätzlich Suchfunktion,
   „Alle Einstellungen“ und erforderliche Widget-Adapter? Empfehlung: Letzteres,
   sobald P1 den konkreten Bedarf bestätigt.
3. Persönliche Startansicht App oder Graph? Empfehlung: App optional anbieten,
   bestehende gespeicherte Workflows nicht ungefragt umstellen.
4. Zusätzliche UX-Funktionen priorisieren: Prompt-Freigabe, A/B, Varianten,
   Teil-Ausführung und Produktionspreset-/Layoutverwaltung sind getrennte Aufgaben.
5. Nach P1 die offenen technischen Punkte schließen und Aufwand präzisieren.

**Fertig ist die erste Version erst**, wenn die gewählten Einstellungen tatsächlich
bedienbar sind, der Graph-Wechsel keine Werte verändert und der vollständige
Song-/Cover-Export mit den bisherigen Möglichkeiten funktioniert.
