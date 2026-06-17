# CodexCLI – Obsidian Codex Connector

Dieser Connector führt aus einer Obsidian-Note heraus Prompts an **Codex CLI** aus und hängt die Antwort strukturiert an dieselbe Note an.

## Motivation

- Du bleibst komplett in Obsidian: Prompt schreiben → Kommando ausführen → Antwort landet in der Note.
- Die Note bleibt die vollständige Unterhaltung (inkl. optionaler laufender Zusammenfassung).
- Du kannst im Prompt zusätzliche Dateien referenzieren (Markdown/TXT/CSV/PDF; PDF bei Bedarf mit OCR).
- Beim PDF-RAG werden auch im PDF eingebettete Linkannotationen (URI-Links) mit indexiert, z.B. klickbare Video-Links hinter QR-Codes.
- Falls OCR für eine PDF nötig ist, werden Render-Dateien nur temporär im System-Temp-Ordner erzeugt und nach dem Lauf wieder gelöscht.
- Agentische Hilfsartefakte von Codex-Läufen werden nach Möglichkeit unter `<VAULT_ROOT>\.codexcli\tmp\` isoliert und nach dem jeweiligen Lauf wieder entfernt.
- Für mehrere Quellen mit fester Reihenfolge kannst du eine MOC-Steuerliste verwenden (siehe `FILE_REFERENCES.md` / `MOC_TEMPLATE.md`).

## Dokumentation (Einstieg)

- Installation (Windows + Obsidian Shell commands): [Installation_Codex_CLI_und_Obsidian.md](Installation_Codex_CLI_und_Obsidian.md)
- Bedienung/Workflows (`append`, `update_summary`, `diag`, Direktiven): [BEDIENUNG.md](BEDIENUNG.md)
- Dateireferenzen (WikiLinks, Pfade, Links): [FILE_REFERENCES.md](FILE_REFERENCES.md)
- PDF-Retrieval / RAG-Konzept und Limits: [Chat_PDF_RAG.md](Chat_PDF_RAG.md)
- How-to: `### Daten` (Anweisungen vs Datenquellen): [HowTo_Prompt_mit_Daten.md](HowTo_Prompt_mit_Daten.md)
- Fehlerbilder & Fixes: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

## Roadmap-Hinweis

- `SAVE_AS` unterstützt jetzt auch Bildausgabe (`.png`) inklusive optionalem Seitenverhältnis (z.B. `ASPECT: 16:9`).
- Für normale Textaufrufe gilt bei der Modellwahl diese Priorität:
  - `TEXT_MODEL_FORCED` in `app/config.py`
  - danach `CODEXCLI_TEXT_MODEL` als Windows-Umgebungsvariable
  - sonst der Default der installierten Codex CLI
- Für die PNG-Generierung wird ein OpenAI API Key benötigt (`OPENAI_API_KEY`).
- Für den geplanten PDF-RAG-Index ist als Default `<VAULT_ROOT>\.codexcli\index\` vorgesehen; optional per `CODEXCLI_INDEX_ROOT` überschreibbar.
- PDF-Dateien im Prompt laufen in Phase 9 über Retrieval aus dem lokalen Index. Für Obsidian ist der empfohlene Workflow note-basiert über `index_note_pdfs`, `index_note_status` und `index_note_clear`; siehe [Chat_PDF_RAG.md](Chat_PDF_RAG.md) und [BEDIENUNG.md](BEDIENUNG.md).
- ASPECT-Hinweis: `1:1` nutzt `1024x1024`; `4:3` und `16:9` werden aktuell als Best-Effort via `size=auto` umgesetzt.
- Für schnelles API-Key-Setup gibt es das Hilfsskript `Set_OpenAI_Key.ps1` (siehe [Installation_Codex_CLI_und_Obsidian.md](Installation_Codex_CLI_und_Obsidian.md)).
- Wenn du im Obsidian-Plugin Shell Commands eine versteckte Variable `{{_OPENAI_API_KEY}}` definiert hast, kannst du damit den Key pro Aufruf an `append` durchreichen, ohne ihn als Windows-Umgebungsvariable zu speichern.

## Schnellstart (Windows 11)

Platzhalter:

- `<VAULT_ROOT>`: Pfad zum Obsidian Vault (z.B. `D:\Ideas` oder `\\NAS\Vault`)
- `<ADDON_DIR>`:
  - Ziel (Standard): `.AddOn` (AddOn im Vault „versteckt“)
  - Dev (optional): `AddOn` (während der Entwicklung sichtbar/renderbar)
- `<CODEXCLI_HOME>`: `<VAULT_ROOT>\<ADDON_DIR>\CodexCLI`

### 1) Repo in den Vault legen

Kopiere/clone diesen Ordner nach:

```text
<VAULT_ROOT>\<ADDON_DIR>\CodexCLI
```

### 2) Python-venv + Dependencies

PowerShell im Projektordner:

```powershell
cd "<CODEXCLI_HOME>"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3) Codex CLI installieren (einmalig)

Siehe [[Installation_Codex_CLI_und_Obsidian]].

Wichtig: Standard ist `codex.cmd` aus dem PATH. Falls das aus Obsidian heraus nicht sauber gefunden wird, setze `CODEXCLI_CODEX_CMD` (siehe Installations-Guide).

### 4) Obsidian: Shell commands anlegen

Im Obsidian Community-Plugin **Shell commands** ein Kommando anlegen (Beispiel für `append`):

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" append "{{file_path:absolute}}""
```

Das Skript `run_codexcli.cmd` nutzt:

- zuerst `<CODEXCLI_HOME>\.venv\Scripts\python.exe`
- sonst eine lokale venv unter `%LOCALAPPDATA%\<CODEXCLI_VENV>\CodexCLI\.venv\Scripts\python.exe` (hilfreich bei NAS/UNC)

Details und weitere Kommandos: siehe [[Installation_Codex_CLI_und_Obsidian]] und [[BEDIENUNG]].

### 5) Textmodell festlegen (optional)

Wenn du das Textmodell fest im Projekt erzwingen willst, öffne [app/config.py](/d:/Ideas/AddOn/CodexCLI/app/config.py:1) und setze zum Beispiel:

```python
TEXT_MODEL_FORCED: str | None = "gpt-5.4"
```

Wenn du stattdessen die Windows-Umgebungsvariable verwenden willst, lasse in `app/config.py`:

```python
TEXT_MODEL_FORCED: str | None = None
```

und setze dann optional:

```powershell
setx CODEXCLI_TEXT_MODEL "gpt-5.5"
```

Wenn beides nicht gesetzt ist, verwendet CodexCLI kein `--model`-Flag und damit den Default der installierten Codex CLI.

## Erwartete Notiz-Struktur

Minimal:

```md
## Prompt
Schreibe eine kurze Zusammenfassung.

## Laufende Zusammenfassung

## Unterhaltung
```

Der Connector schreibt/aktualisiert diese Bereiche (Details: [[BEDIENUNG]]).
