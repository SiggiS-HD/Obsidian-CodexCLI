
# Skript codex_log_to_md.py

Das Skript `codex_log_to_md.py` konvertiert Codex-Session-Logs im `JSONL`-Format in lesbare Markdown-Dateien.

Im Kern macht es Folgendes:

1. Es sucht Logdateien.
   Standardmäßig unter `~/.codex/sessions` ( `C:\Users\siggi\.codex\sessions`), alternativ über `--input-file` nur eine einzelne Datei.
   Optional kann es mit `--date YYYY-MM-DD` auf einen bestimmten Tag einschränken.

2. Es liest Codex-/VS-Code-ähnliche Sitzungsdaten ein.
   Dabei unterstützt es zwei Logformen:
   - einfache flache Einträge mit Feldern wie `role` und `content`
   - verschachtelte, zustandsbasierte VS-Code-Session-Logs mit `requests`, `response`, `modelState` und `result`

3. Es rekonstruiert daraus Gesprächsbeiträge.
   Das Skript versucht Benutzertexte und Codex-Antworten robust aus verschiedenen Strukturen herauszuziehen, auch wenn Inhalte verschachtelt in `content`, `items`, `text`, `input_text` oder `output_text` liegen.

4. Es bereinigt und filtert die Inhalte je nach Exportmodus.
   Es gibt drei Modi:
   - `full`: möglichst vollständig, inklusive technischer Inhalte und Metadaten
   - `readable`: besser lesbar, blendet stark technische Blöcke eher aus
   - `text-only`: nur Benutzer- und Assistentenbeiträge, standardmäßig der Modus

5. Es schreibt für jede Session eine Markdown-Datei.
   Die Ausgabe landet standardmäßig im Ordner `codex_chat` neben dem Skript.
   Der Dateiname beginnt mit einem Originator-Präfix, zum Beispiel:
   - `codex_vscode_rollout-....md`
   - `codex_desktop_rollout-....md`
   - `codex_obsidian_rollout-....md`

6. Es erkennt den Originator der Session und baut ihn in den Dateinamen ein.
   Dabei werden Varianten robust normalisiert, damit zum Beispiel `Codex Desktop`,
   `codex-desktop` oder `codex desktop` alle zu `codex_desktop` werden.

**Wichtige Details zum Verhalten**

- `format_unix_ms(...)` wandelt Unix-Zeitstempel in lesbare Datumsangaben um.
- `looks_technical(...)` erkennt eher technische oder rohe Logausgaben, etwa JSON, Tracebacks, Tooldaten oder sehr symbolreiche Zeilen.
- `clean_text_for_readability(...)` entfernt in den lesbaren Modi störende technische Abschnitte oder ausgeblendete Codeblöcke.
- `extract_entries_from_vscode_session(...)` ist der zentrale Teil für komplexe VS-Code-Logs:
  Es baut unvollständige oder verteilte `requests` aus mehreren JSONL-Zeilen wieder zusammen.
- `detect_session_originator_slug(...)` liest Session-Metadaten wie `originator` und `source`
  und mappt sie auf stabile Präfixe für den Markdown-Dateinamen.
- `export_session(...)` erzeugt das eigentliche Markdown mit Überschriften wie `## Benutzer` und `## Codex` sowie Zeitstempeln.

**Kommandozeilenoptionen**

- `--log-root`: Wurzelverzeichnis der Session-Logs
- `--input-file`: genau eine JSONL-Datei exportieren
- `--output`: Zielordner für Markdown-Dateien
- `--mode`: `full`, `readable` oder `text-only`
- `--date`: nur Sessions eines Tages exportieren
- `--force`: Markdown-Dateien immer neu erzeugen, auch wenn sie schon aktuell sind

**Kurz gesagt**

Das Skript ist ein Exporter, der rohe Codex-Session-Logs in menschenlesbare Markdown-Gesprächsprotokolle umwandelt und dabei je nach Modus mehr oder weniger technische Details mitnimmt.

---
### Beispiel-Aufruf

Mit welchem Kommando kann das Skript aus einem beliebigen Verzeichnis aufgerufen die .md Datei(en) für den Tag 13.6.2026 in "D:\Ideas\AddOn\CodexCLI\docs" speichern?


```powershell
python "D:\Ideas\AddOn\CodexCLI\codex_log_to_md.py" --date 2026-06-13 --output "D:\Ideas\AddOn\CodexCLI\docs"
```

Falls du den lesbaren Standard explizit setzen willst:

```powershell
python "D:\Ideas\AddOn\CodexCLI\codex_log_to_md.py" --date 2026-06-13 --output "D:\Ideas\AddOn\CodexCLI\docs" --mode text-only
```

`--date` erwartet das Format `YYYY-MM-DD`, also für `13.6.2026` den Wert `2026-06-13`.

**Dateinamensschema**

Die erzeugten Markdown-Dateien beginnen mit einem aus der Session abgeleiteten Originator:

- `codex_vscode_...md` für VS-Code-Sitzungen
- `codex_desktop_...md` für Codex-Desktop-Sitzungen
- `codex_obsidian_...md` für Obsidian-/`exec`-Sitzungen
- `codex_unknown_...md` falls kein passender Originator erkannt wird

## Laufzeit & Token

Wenn in einer Session verwertbare Laufzeit- oder Token-Metadaten gefunden werden, ergänzt das Skript im Export den Abschnitt `## Laufzeit & Token`.

Typische Kennzahlen sind:

- `Modell`: das in der Session erkannte Modell, zum Beispiel `gpt-5.4`
- `Provider`: der erkannte Modellanbieter
- `Dauer E2E (s)`: die gesamte Laufzeit der Aufgabe in Sekunden
- `Input-Tokens`: alle Eingabe-Tokens der Session
- `Cached Input-Tokens`: der Teil der Eingabe, der als Cache-Treffer gezählt wurde
- `Output-Tokens`: sichtbare Ausgabetokens
- `Reasoning Output-Tokens`: zusätzliche Reasoning-Tokens, sofern im Log enthalten
- `Total Tokens`: Gesamtsumme der Token laut Session-Metadaten
- `Output-Tokens/s (E2E)`: sichtbare Ausgabetokens pro Sekunde über die gesamte Laufzeit
- `Output+Reasoning-Tokens/s (E2E)`: sichtbare Ausgabe plus Reasoning pro Sekunde
- `Total Tokens/s (E2E)`: gesamte Tokenmenge pro Sekunde

Wenn zum Modell ein Preis hinterlegt ist, ergänzt das Skript außerdem eine Kostenschätzung:

- `Kostenbasis Modell`: das Preisprofil, das intern verwendet wurde
- `Geschaetzte Input-Kosten`
- `Geschaetzte Cached-Input-Kosten`
- `Geschaetzte Output-Kosten`
- `Geschaetzte Gesamtkosten`
- `Preisstand`: Stand der hinterlegten Preisdaten

Die Kostenschätzung ist nur so genau wie die im Skript hinterlegten Modellpreise und die im Session-Log vorhandenen Tokenwerte.

## Modellpreise aktualisieren

Die Modellpreise werden nicht automatisch aus dem Web geladen, sondern statisch im Skript gepflegt.

Die relevanten Stellen in [codex_log_to_md.py](d:/Ideas/AddOn/CodexCLI/codex_log_to_md.py) sind:

- `MODEL_PRICING_PER_1M`: enthält die Preise pro 1 Million Tokens je Modell
- `PRICING_LAST_UPDATED`: enthält das Datum der letzten Preisaktualisierung
- `PRICING_SOURCE_URL`: enthält die Referenz auf die Preisquelle

Eine Aktualisierung ist nötig, wenn:

- OpenAI offizielle Preise ändert
- neue Modelle im Export berücksichtigt werden sollen
- sich die Preisstruktur für Cached Input oder Output ändert

So aktualisierst du die Preise konkret:

1. Öffne [codex_log_to_md.py](d:/Ideas/AddOn/CodexCLI/codex_log_to_md.py).
2. Suche den Block `MODEL_PRICING_PER_1M`.
3. Passe beim gewünschten Modell die Werte für `input`, `cached_input` und `output` an.
4. Falls ein neues Modell hinzukommt, ergänze einen neuen Eintrag im selben Format.
5. Aktualisiere `PRICING_LAST_UPDATED` auf das Datum der Änderung.
6. Prüfe, ob `PRICING_SOURCE_URL` noch auf die richtige offizielle Preisquelle zeigt.
7. Erzeuge danach den Markdown-Export neu, damit die neue Kostenschätzung in den `.md`-Dateien erscheint.

Beispiel:

```python
PRICING_LAST_UPDATED = "2026-06-15"

MODEL_PRICING_PER_1M = {
    "gpt-5.4": {"input": 2.50, "cached_input": 0.25, "output": 15.00},
    "gpt-5.4-pro": {"input": 20.00, "cached_input": None, "output": 120.00},
}
```

`cached_input = None` bedeutet, dass im Skript kein separater Rabattpreis hinterlegt ist. In diesem Fall werden Cached-Input-Tokens mit dem normalen Input-Preis bewertet.
