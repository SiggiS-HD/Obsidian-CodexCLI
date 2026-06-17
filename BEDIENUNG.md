# Bedienung (Workflows)

Dieses Dokument beschreibt die tägliche Nutzung von CodexCLI aus Obsidian heraus.

Platzhalter (wie in der Installation verwendet):

- `<VAULT_ROOT>`: Pfad zum Obsidian Vault
- `<ADDON_DIR>`: `.AddOn` (Ziel, Standard) oder `AddOn` (Dev)
- `<CODEXCLI_HOME>`: `<VAULT_ROOT>\<ADDON_DIR>\CodexCLI`

## Grundidee

- Du schreibst im Abschnitt `## Prompt` deine aktuelle Anweisung.
- Du führst ein Obsidian Shell Command aus (typisch: `append`).
- CodexCLI baut daraus einen Prompt (inkl. Connector-Regeln + optionalen Dateiquellen) und ruft Codex CLI auf.
- Die Antwort wird in der Note unter `## Unterhaltung` angehängt.

## Notiz-Template

Minimaler Aufbau:

```md
## Prompt
Schreibe eine kurze Zusammenfassung.

## Laufende Zusammenfassung

## Unterhaltung
```

## Workflows

### 1) `append` – Antwort an Note anhängen

Aufruf (typisch über Obsidian Shell commands):

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" append "{{file_path:absolute}}""
```

Verhalten (vereinfacht):

- liest die Note
- nimmt `## Prompt` als aktuelle Aufgabe
- sammelt Dateireferenzen aus `## Prompt` (siehe `FILE_REFERENCES.md`)
- ruft Codex CLI auf
- agentische Laufzeit-Artefakte des Codex-Laufs werden dabei nach Moeglichkeit unter `<VAULT_ROOT>\.codexcli\tmp\` isoliert
- hängt die Antwort in `## Unterhaltung` an
- leert nach Erfolg den Abschnitt `## Prompt`

### 2) `update_summary` – Laufende Zusammenfassung aktualisieren

Aufruf:

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" update_summary "{{file_path:absolute}}""
```

Verhalten:

- nutzt `## Unterhaltung` als Kontext
- nutzt fuer den Codex-Lauf ebenfalls nach Moeglichkeit einen temporaeren Arbeitsordner unter `<VAULT_ROOT>\.codexcli\tmp\`
- aktualisiert `## Laufende Zusammenfassung`

### 3) `diag` – Diagnose schreiben

Aufruf:

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" diag "{{file_path:absolute}}""
```

`diag` ist nützlich bei „funktioniert in Dev, aber nicht in Ziel (NAS/UNC)“ oder bei OCR-/PATH-Problemen.

Es schreibt im Vault-Root eine Datei `CodexCLI_Connector.md` (overwrite) und druckt denselben Inhalt auf stdout.

Zusätzlich zeigt `diag` jetzt auch den isolierten Laufzeitbereich unter `<VAULT_ROOT>\.codexcli\tmp\` an:

- effektiver Pfad des Runtime-Tmp-Roots
- Anzahl Unterordner/Dateien
- Anzahl leerer Unterordner
- kurzer Hinweis, dass liegengebliebene leere Unterordner bei Bedarf manuell gelöscht werden können

### 4) `fix_latex` – Alte LaTeX-Begrenzer normalisieren (einmalig)

Wenn in alten Antworten noch `\(...\)` oder `\[...\]` vorkommen, kannst du die Note nachträglich bereinigen.

Aufruf:

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" fix_latex "{{file_path:absolute}}""
```

Verhalten:

- ersetzt außerhalb von Code (Inline-Code und fenced Codeblocks bleiben unverändert)
	- `\(...\)` → `$...$`
	- `\[...\]` → `$$\n...\n$$`
- überschreibt die Datei in-place

### 5) `index_note_pdfs` – PDFs aus dem Prompt indexieren

Aufruf:

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" index_note_pdfs "{{file_path:absolute}}""
```

Verhalten:

- liest die aktuelle Note
- sucht im Abschnitt `## Prompt` nach PDF-Referenzen wie `[[RAG_Test.pdf]]`
- baut für genau diese PDFs den lokalen Index auf
- schreibt zusätzlich einen sichtbaren `Codex Index`-Block in die Note
- speichert den Index standardmäßig unter `<VAULT_ROOT>\.codexcli\index\<doc_id>\index.sqlite3`

### 6) `index_note_status` – Indexstatus der PDFs aus dem Prompt anzeigen

Aufruf:

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" index_note_status "{{file_path:absolute}}""
```

Verhalten:

- liest die aktuelle Note
- sucht im Abschnitt `## Prompt` nach PDF-Referenzen
- zeigt für jede PDF an, ob ein Index existiert und ob ein Rebuild nötig ist
- schreibt zusätzlich einen sichtbaren `Codex Index Status`-Block in die Note

### 7) `index_note_clear` – Indizes der PDFs aus dem Prompt löschen

Aufruf:

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" index_note_clear "{{file_path:absolute}}""
```

Verhalten:

- liest die aktuelle Note
- sucht im Abschnitt `## Prompt` nach PDF-Referenzen
- löscht für genau diese PDFs die dokumentbezogenen Indexordner
- schreibt zusätzlich einen sichtbaren `Codex Index Clear`-Block in die Note
- die Original-PDFs bleiben unverändert

### 8) Direkte PDF-Kommandos (technische Alternative)

Falls du einmal bewusst mit einem expliziten PDF-Pfad arbeiten willst, gibt es weiterhin die direkten Varianten:

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" index_pdf "C:\Pfad\zur\Datei.pdf""
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" index_status "C:\Pfad\zur\Datei.pdf""
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" index_clear "C:\Pfad\zur\Datei.pdf""
```

## Dateireferenzen im Prompt

Im Abschnitt `## Prompt` kannst du zusätzliche Dateien referenzieren (z.B. `.md`, `.txt`, `.csv`, `.pdf`). CodexCLI liest diese Dateien und gibt ihren Inhalt als Quellenblock an Codex weiter.

Details und Beispiele: siehe `FILE_REFERENCES.md`.

Sonderfall PDF in Phase 9:

- PDF-Dateien werden bei `append` nicht mehr als Volltext-Vorschau in den Prompt kopiert.
- Stattdessen wird aus dem lokalen PDF-Index Retrieval verwendet.
- Wenn noch kein Index existiert, kommt eine klare Meldung wie `Bitte zuerst indexieren`.
- Bei der Indexierung werden auch im PDF vorhandene Linkannotationen mit `URI` uebernommen.
- Dadurch koennen z.B. klickbare Video-Links hinter QR-Codes spaeter ueber den RAG-Index gefunden werden.
- Falls eine PDF keinen extrahierbaren Text enthaelt, nutzt der bestehende OCR-Fallback ein temporäres Render-Verzeichnis im System-Temp-Ordner.
- Auf Windows liegt dieses Verzeichnis typischerweise unter `%TEMP%`, also z.B. `C:\Users\<Name>\AppData\Local\Temp\codexcli-ocr-*`.
- Diese temporären Dateien dienen nur dem aktuellen OCR-Lauf und werden danach automatisch wieder gelöscht.
- Zusaetzliche agentische Hilfsartefakte eines Codex-Laufs werden, wenn moeglich, unter `<VAULT_ROOT>\.codexcli\tmp\` erzeugt und nach dem Lauf wieder entfernt.
- Falls dort nach einem abgebrochenen Lauf leere Unterordner liegen bleiben, koennen diese gefahrlos manuell entfernt werden; `diag` zeigt den aktuellen Zustand an.
- Best Practice fuer Mischaufgaben mit PDF-RAG:
  - Wenn du erst eine inhaltliche Antwort und danach z.B. Lernvideo-Links aus dem gleichen PDF willst, ist ein Zwei-Schritt-Workflow oft robuster als ein einzelner kombinierter Prompt.
  - Beispiel:
    - Schritt 1: `Ich moechte eine Einfuehrung in das Thema Integralrechnung ... Die Seiten sollen zitiert werden.`
    - Schritt 2: `[[Lernvideos]]`
  - Grund: Das Retrieval arbeitet chunk-basiert. Getrennte Prompts fokussieren die Treffer besser als ein einzelner Prompt mit zwei unterschiedlichen Zielen.
- Empfohlener Hotkey-Workflow:
  - zuerst `append`
  - bei fehlendem Index `index_note_pdfs`
  - optional `index_note_status`
  - optional `index_note_clear`
- Hintergrund und Limits: siehe [[Chat_PDF_RAG]].

### Steuerliste (MOC) für eine feste Reihenfolge

Wenn du mehrere Dateien **in einer genau definierten Reihenfolge** als Kontext mit senden willst, kannst du im Prompt statt vieler Links eine **MOC-Datei** referenzieren (nummerierte Steuerliste). Eine Vorlage ist [[MOC_TEMPLATE]].

Details: siehe [[FILE_REFERENCES]].

## Direktiven im Prompt

### `SAVE_AS` – Antwort als Datei speichern

Wenn du die Codex-Antwort als Datei speichern willst, kannst du im `## Prompt` eine Direktive angeben:

```md
## Prompt
Fasse den Inhalt dieses Chats zusammen. SAVE_AS: exports/HD_Herz.md
```

Hinweise:

- Doppelpunkt ist optional: `SAVE_AS exports/x.md` ist ebenfalls gültig.
- Zielpfad muss relativ zum Ordner der aktuellen Note sein (keine absoluten/UNC-Pfade, kein `..`).
- Dateiendung muss `.md` oder `.png` sein.

Verhalten:

- Der Codex-Aufruf nutzt den Prompt ohne `SAVE_AS ...`.
- Bei `.md`: Die Antwort wird als Datei unter `<Ordner der aktuellen Note>\exports\HD_Herz.md` geschrieben (Ordner wird angelegt, Datei überschrieben). In der Note wird im Codex-Block nur ein WikiLink `[[HD_Herz]]` angehängt.
- Bei `.png`: Es wird ein Bild generiert und unter dem Zielpfad gespeichert. In der Note wird nur ein WikiLink auf die Bilddatei angehängt, z.B. `[[Projektstatus.png]]`.

Optionale Direktive für Bildausgabe:

- `ASPECT:` unterstützt aktuell `16:9`, `4:3`, `1:1`.
- Beispiel: `ASPECT: 16:9 SAVE_AS: exports/Projektstatus.png`
- Technischer Hinweis: Die OpenAI-API unterstützt als feste Größen nur `1024x1024`, `1024x1536`, `1536x1024` und `auto`.
- Daher gilt aktuell: `1:1` wird auf `1024x1024` gemappt, `4:3` und `16:9` laufen als Best-Effort über `size=auto`.
- Wenn ein Fehler wie `HTTP 400: Invalid size ...` erscheint, siehe `TROUBLESHOOTING.md`.

Beispiel:

```md
## Prompt
Erzeuge ein klares Überblicksdiagramm für den aktuellen Projektstand. ASPECT: 16:9 SAVE_AS: exports/Projektstatus.png
```

Zusätzliche Konfiguration für PNG:

- `OPENAI_API_KEY` (erforderlich)
- Optional: `CODEXCLI_IMAGE_MODEL`, `CODEXCLI_IMAGE_QUALITY`, `CODEXCLI_IMAGE_TIMEOUT_SECONDS`, `CODEXCLI_OPENAI_BASE_URL`
- Für schnelles Key-Setup siehe `Installation_Codex_CLI_und_Obsidian.md` (Abschnitt "OpenAI API Key schnell setzen").

Zusätzliche Konfiguration für Textaufrufe (append/update_summary):

- Die Modellwahl erfolgt in dieser Priorität:
  - `TEXT_MODEL_FORCED` in `app/config.py`
  - danach `CODEXCLI_TEXT_MODEL`
  - sonst Codex-CLI-Default

Direktes Erzwingen eines Modells im Projekt:

Öffne [app/config.py](/d:/Ideas/AddOn/CodexCLI/app/config.py:1) und setze zum Beispiel:

```python
TEXT_MODEL_FORCED: str | None = "gpt-5.4"
```

Wichtig:

- Mit `"gpt-5.4"` wird dieses Modell immer verwendet, auch wenn `CODEXCLI_TEXT_MODEL` gesetzt ist.
- Mit `None` ist kein Modell im Code erzwungen.
- Wenn `TEXT_MODEL_FORCED = None` und `CODEXCLI_TEXT_MODEL` gesetzt ist, wird die Umgebungsvariable verwendet.
- Wenn `TEXT_MODEL_FORCED = None` und `CODEXCLI_TEXT_MODEL` leer/unset ist, wird kein `--model` an Codex CLI übergeben. Dann greift deren eigener Default.

Beispiele:

Fest im Projekt auf `gpt-5.4` setzen:

```python
TEXT_MODEL_FORCED: str | None = "gpt-5.4"
```

Standard über Codex CLI Default:

```python
TEXT_MODEL_FORCED: str | None = None
```

Keine Zusatzangaben im Shell Command nötig:

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" append "{{file_path:absolute}}""
```

Optionales Override als dauerhafte User-Umgebungsvariable (PowerShell):

```powershell
setx CODEXCLI_TEXT_MODEL "gpt-5.5"
```

Hinweis für Obsidian-Schlüsselbund:

- `run_codexcli.cmd` kann den API-Key nicht direkt aus dem Obsidian-Keyring lesen.
- Es übernimmt aber automatisch in dieser Reihenfolge:
	- `OPENAI_API_KEY`
	- `CODEXCLI_OPENAI_API_KEY`
	- `OBSIDIAN_OPENAI_API_KEY`
- Wenn du im Shell-Commands-Plugin eine versteckte Variable wie `{{_OPENAI_API_KEY}}` definiert hast, ist die bevorzugte Lösung: den Wert im `cmd`-Aufruf direkt auf `OPENAI_API_KEY` setzen.

Beispiel (Shell Command), falls dein Plugin den Secret-Wert in eine Variable einsetzen kann:

```bat
cmd /V:ON /C "set OPENAI_API_KEY={{_OPENAI_API_KEY}}&& "<CODEXCLI_HOME>\run_codexcli.cmd" append "{{file_path:absolute}}""
```

Vorteil dieser Variante:

- Der API-Key bleibt im Obsidian-Plugin hinterlegt und muss nicht als Windows-Umgebungsvariable gespeichert werden.

### `EXPORT_CHAT_AS` – Unterhaltung exportieren (ohne LLM)

Wenn du den kompletten Abschnitt `## Unterhaltung` in eine Datei exportieren willst (ohne Context-Limits), nutze `EXPORT_CHAT_AS`:

```md
## Prompt
EXPORT_CHAT_AS: exports/Cholesterin-Chat.md
```

Verhalten:

- Es wird **kein** Codex/LLM aufgerufen.
- Exportiert wird der komplette Inhalt von `## Unterhaltung`.
- Zielpfad-Regeln wie bei `SAVE_AS`.
