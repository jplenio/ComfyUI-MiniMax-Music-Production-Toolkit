# YuE2 Cover: Bestandsaufnahme und Korrekturplan

Stand: 2026-09-16. Geltungsbereich: ausschließlich Song model **YuE2 Cover**.
Normale YuE2- und MiniMax-Generierung behalten ihre bisherigen Regeln.

**Aktuelle Nachprüfung vom 17.09.2026:** Die folgenden Notizen sind historisch.
Leere native Lyrics und umbenannte ABC-Header wurden durch feste native Header,
geprüfte ABC-Zeitachsen und musikalische Tags mit leeren Lyrics-Abschnitten
ersetzt. Originalworte werden jetzt deterministisch aus dem Transkript eingesetzt.
Siehe [Fehleranalyse und echter Audiotest](YUE2_COVER_DIAGNOSTICS.md): Prompt-Vorlesen
ist im neuen ASR-Vergleich nicht nachweisbar, völlige Gesangsfreiheit jedoch
weiterhin nicht belegt. Der Nutzer hat ausdrücklich die Prompt-/ABC-Korrekturen
ohne zusätzliche Gesangstrennung gewählt.

## Nachprüfung der gemeldeten Audioläufe

Die Berichte `_001`/`_002` und das ComfyUI-Protokoll vom 16.09.2026 zeigen:

- Instrumental: Die tatsächlich generierte ABC enthält bereits **null Vocal-Noten**.
  Die Lyrics enthielten nur Abschnittstags. Restgesang ist deshalb kein Beleg
  für eine unvollständige Notenbearbeitung. Als zusätzliche Konditionierung
  bekommt der native Generator jetzt ein vollständig leeres Lyrics-Feld;
  Abschnittsplanung bleibt in Style und Bericht. `generation.cover_conditioning`
  hält den Unterschied fest. Keine Garantie gegen akustische Stimmreste.
- Original: VAD behielt nur 7,296 von 207,133 Sekunden (3,52 %); Whisper lieferte
  zwei Segmente mit 40 Zeichen. Das LLM erhielt also bereits unvollständige Worte.
  VAD ist nun standardmäßig aus; alte gespeicherte Einstellungen erhalten bei
  weniger als 50 % Restdauer oder keinem Segment einen vollständigen zweiten
  Durchlauf ohne VAD. Offensichtliche reine Anfangsfragmente stoppen die Generierung.
- Neue Lyrics: Der letzte Fortschritt lag innerhalb Whisper, vor SheetSage/LLM;
  der vorherige Lauf meldete fehlendes `cublas64_12.dll`. Die genaue native
  Blockierstelle ist nicht protokolliert. Ein separater Worker begrenzt und
  isoliert solche Fehler, meldet Fortschritt und wird beim Abbruch beendet.
  Installierte Windows-DLL-Verzeichnisse werden bekannt gemacht; bei GPU-Fehler
  folgt CPU/int8. Weitere Auto-Läufe meiden die fehlgeschlagene GPU bis Neustart.

Nachprüfung: 1.001 Tests erfolgreich durchgelaufen, davon einer übersprungen.
Echte Unterprozesse mit simuliertem Whisper prüfen Transport, Fehler und Timeout;
Transkript-/Graph-Tests prüfen VAD-Wiederholung und leere Instrumental-Lyrics.
Release-Prüfung und Dokumentationslinks bestehen. Keine neue echte Whisper-
Transkription oder YuE2-Audiogenerierung ausgeführt; Hörqualität bleibt zu prüfen.
Die folgenden Abschnitte dokumentieren die vorausgegangene Bestandsaufnahme.

## Verständnis der Bedienung

- `mode=full` bindet Melodie und Harmonie an die Quelle; `melody` lässt eine
  neue Begleitung zu. Dieselbe Auswahl steuert Transkription und Generierung.
- `new lyrics`: Das LLM schreibt neue Worte zum gewählten Template. Es erhält
  die Originalphrasen mit Zeitinformationen sowie die musikalischen Abschnitte,
  Noten und Pausen als Orientierung für ähnliche Silbenzahl und Betonung.
  Neue Worte stehen ausschließlich unter passenden Tags in `[Lyrics]`.
- `original lyrics`: Whisper transkribiert. Das LLM ordnet diese Worte den
  Abschnitten zu. Wortfolge und Wiederholungen müssen vollständig erhalten
  bleiben; ein verändertes Ergebnis darf nicht unbemerkt generiert werden.
- `instrumental`: Die Auswahl überstimmt das Template und alle Gesangswünsche.
  Keine Lyrics und keine gesummten Stimmen. Python bearbeitet die Partitur;
  Prompt, Parser und Generator sichern die Entscheidung zusätzlich ab.

## Befunde vor der Korrektur

1. Die Grundverkabelung ist vorhanden: Quelle, SheetSage2, Score-Node, Whisper,
   Structured Prompt, Parser, MusicGeneration und Produktionsbericht.
2. Der Instrumental-Umbau ändert nur den Anzeigenamen von `Vocal`. Noten bleiben
   in dieser Stimme. Die Neu-Serialisierung fasst Musikzeilen zusammen und kann
   Felder/Kommentare falsch behandeln. Reine Umbenennung ist kein zuverlässiger
   Ersatz der Gesangspartie.
3. Die sogenannte Silbenkarte zählt Notenanschläge, nicht Silben. Die Anweisung
   verbietet sogar Melismen. Instrumentalnoten werden als Ersatz gezählt, wenn
   die Vocal-Stimme fehlt. Damit entsteht ein falscher Schreibauftrag.
4. Bei neuen Lyrics läuft Whisper nicht: Originalphrasierung und tatsächliche
   Worte fehlen. Bei Original-Lyrics gehen die vorhandenen Zeitinformationen
   auf dem Weg zum LLM verloren.
5. Der Parser misst nur eine Wortmengen-Überdeckung. Reihenfolge, kurze Wörter
   und Wiederholungen sind nicht abgesichert. Instrumental wird am Generator
   bislang nicht gegenüber widersprüchlichen Lyrics erzwungen.
6. Whisper führt die eigentliche Transkription beim Iterieren aus. Der bisherige
   CPU-Fallback umschließt nur den Aufruf, nicht diese verzögerte Ausführung.
   Ein leeres Ergebnis wird als erfolgreiche Transkription zurückgegeben.

## Ausführungsplan

1. Regressionen mit realistischem nativen ABC schreiben: mehrere Blöcke pro
   Abschnitt, gebundene Noten, Pausen, Tonart-/Taktwechsel und Harmony-Symbole.
2. Native zwei Stimmen erhalten. Für Instrumental Vocal-Noten in gleich lange
   Pausen umwandeln, Harmonie erhalten, die frühere Gesangsmelodie in `Ins`
   übernehmen. In Blöcken mit Gesang übernimmt diese Melodie die führende
   Instrumentalpartie; vorhandene Instrumentalthemen in gesangsfreien Blöcken
   bleiben. Überlappende ursprüngliche Instrumentalnoten werden dabei ersetzt
   und im Bericht ausgewiesen. „Remove vocal line“ behält die alte Ins-Partie.
   Keine zusätzlichen, undokumentierten Stimmen erfinden. Bearbeitung muss
   wiederholbar sein und Notendauern, Grenzen und Struktur erhalten.
3. Notenkarte ehrlich als Phrasierungshilfe kennzeichnen, mit Pausen und
   Notenlängen statt behaupteter exakter Silben. Keine Ins-Ersatzsilben.
4. Whisper für beide texttragenden Cover-Modi nutzen, mit Wortzeitmarken;
   Originaltext in new lyrics nur als Phrasierungsvorlage kennzeichnen.
   Instrumental und andere Songmodelle bleiben ohne Whisper. Verzögerte Fehler,
   leere Ergebnisse und Modellfreigabe behandeln.
5. Modus-Priorität im System-/User-Prompt, Parser und Generator absichern.
   Originalworte mit ihrer vollständigen Reihenfolge prüfen. Keine automatische
   Kürzung von Cover-Lyrics. Abweichungen mit konkreter Korrekturmeldung stoppen.
6. Workflow-Beschriftungen, Autoload, Berichte, Hilfe und YUE2.md angleichen.
   Vorhandene Socket-Positionen und individuelle Einstellungen erhalten.
7. Gezielte Regressionen, gesamte Testsuite, Node-Verträge, Frontend- und
   Release-Validierung ausführen. Keine neuen Release-Assets oder Veröffentlichung
   im Rahmen dieses Reviews.

## Quellen und Grenzen

- [Offizieller Cover-Ablauf](https://github.com/multimodal-art-projection/YuE/blob/main/docs/covers.md):
  Quelle transkribieren, Lyrics/Style passend zur Partitur erstellen, full/melody.
- [Native ABC- und Lyrics-Regeln](https://github.com/multimodal-art-projection/YuE/blob/main/skills/yue2-music/references/abc-editing.md):
  zwei monophone Stimmen, Harmonie in Vocal auch bei Pausen; Silben können sich
  über Melismen erstrecken. Es gibt keinen erzwungenen Phonem-zu-Note-Kanal.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper): Wortzeitmarken und
  verzögerte Transkription über den Segment-Generator.

Die Instrumentalübertragung ist eine bewusst begrenzte Bearbeitung der nativen
Partitur, keine Garantie für das Audioverhalten des Modells. Whisper-Zeitmarken
und Text sind Schätzungen. Exakte Silbensynchronität oder vollständig gesangsfreie
Ausgabe lassen sich erst am erzeugten Audio beurteilen.

## Umsetzung und Prüfergebnis

Die oben beschriebenen Korrekturen sind im vorhandenen Workflow umgesetzt.
Die Whisper-Verbindungen zu Prompt und Parser verwenden jetzt den Berichtsausgang
mit Text und Zeitinformationen. Neue Lyrics werden zusätzlich abgewiesen, wenn
das LLM einfach den gesamten Originaltext kopiert; nummerierte Style-Abschnitte
müssen mit den Lyrics-Tags übereinstimmen. Unbekannte explizite Lyrics-Modi
führen zu einer Fehlermeldung statt zum stillen Wechsel auf new lyrics.

Gesamte Testsuite: 991 Tests, erfolgreich, einer übersprungen. Nach der letzten
kleinen ABC-Korrektur zusätzlich 63 Cover-Tests erfolgreich. Die symbolischen
Tests prüfen die übertragenen Tonhöhen, Bindungen, Dauern, Pausen, mehrere
Blöcke pro Abschnitt sowie Takt-/Tonartfelder und Idempotenz. Weitere Tests
prüfen Modus-Isolation, beide Quellenmodi, Originalwortfolge, Prompt-Verbindungen,
Whisper-Zeitmarken, verzögerte CUDA-Fehler und die unveränderte Längenbehandlung.
Node-Verträge und Release-Validierung bestehen; 133 Dokumentationslinks wurden
geprüft. Whisper und LLM sind in den Tests simuliert. Es wurde kein Modell
heruntergeladen und keine echte Audio-Qualitätsmessung durchgeführt.

Die von Deepseek vorbereitete Version 3.1.0 bleibt bestehen. Für dieses Review
wurde kein Release veröffentlicht und kein vorhandenes Release-Archiv ersetzt.
