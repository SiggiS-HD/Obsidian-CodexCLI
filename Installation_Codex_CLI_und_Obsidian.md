# Installation: Codex CLI + CodexCLI (Windows 11) + Obsidian

Ziel: Dieses Dokument beschreibt die Schritte, um **CodexCLI** (dieses Repo) in einem Obsidian-Vault zu installieren und über das Obsidian-Plugin **Shell commands** nutzbar zu machen.

## 0) Begriffe & Pfade

Dieses Repo ist dafür gedacht, direkt im Vault zu liegen.

Platzhalter:

- `<VAULT_ROOT>`: Pfad zum Obsidian Vault (z.B. `D:\Ideas` oder `\\NAS\Vault`)
- `<ADDON_DIR>`:
  - Ziel (Standard): `.AddOn`
  - Dev (optional): `AddOn`
- `<CODEXCLI_HOME>`: `<VAULT_ROOT>\<ADDON_DIR>\CodexCLI`

Warum zwei Layouts?

- `.AddOn` ist im Vault „versteckt“ (Standard für Anwender).
- `AddOn` ist während der Entwicklung praktisch, weil Dateien sichtbar/renderbar bleiben.

## 1) Voraussetzungen

- Windows 11
- Python 3.12 (empfohlen)
- Obsidian
- Obsidian Community-Plugin: **Shell commands**
- Node.js (LTS) + npm (für Codex CLI)

## 2) Node.js + npm prüfen/Installieren

Prüfen:

```powershell
node -v
npm -v
```

Wenn `node`/`npm` fehlt: Node.js LTS installieren (Installer setzt PATH i.d.R. korrekt).

## 3) Codex CLI installieren (global)

```powershell
npm install -g @openai/codex
```

Prüfen:

```powershell
where.exe codex
where.exe codex.cmd
codex --version
```

### Wenn `codex` trotz Installation nicht gefunden wird

Unter Windows liegt das globale npm-bin Verzeichnis typischerweise hier:

```text
%APPDATA%\npm
```

PowerShell (User-PATH ergänzen) – ohne Hardcoding eines Usernamens:

```powershell
$npmBin = Join-Path $env:APPDATA "npm"
$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")

if ($userPath -notlike "*${npmBin}*") {
  [System.Environment]::SetEnvironmentVariable(
    "Path",
    ($userPath.TrimEnd(';') + ";" + $npmBin),
    "User"
  )
  "PATH aktualisiert. PowerShell komplett neu starten."
} else {
  "PATH ist bereits ok."
}
```

Danach PowerShell vollständig schließen und neu öffnen.

## 4) CodexCLI in den Vault kopieren

Zielpfad:

```text
<CODEXCLI_HOME>
```

Also z.B.:

- Ziel: `<VAULT_ROOT>\.AddOn\CodexCLI`
- Dev: `<VAULT_ROOT>\AddOn\CodexCLI`

## 5) Python-venv erstellen & Dependencies installieren

Es gibt zwei übliche Setups:

### 5.1 Vault liegt lokal (oder als gemapptes Laufwerk) → venv im Projektordner

Im Ordner `<CODEXCLI_HOME>`:

```powershell
cd "<CODEXCLI_HOME>"
python -m venv .venv

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 5.2 Vault liegt auf einem NAS per UNC-Pfad (`\\SERVER\share\...`) → venv lokal (empfohlen)

Wenn `<CODEXCLI_HOME>` ein UNC-Pfad ist, ist eine venv **im Vault** oft unzuverlässig (Ausführungs-/Rechte-/Performance-Themen). Deshalb nutzt `run_codexcli.cmd` in diesem Fall typischerweise eine **lokale** venv unter:

```text
%LOCALAPPDATA%\%CODEXCLI_VENV%\CodexCLI\.venv
```

Bei der Standardstruktur `\\SERVER\share\<Vault>\.AddOn\CodexCLI` wird `CODEXCLI_VENV` fuer UNC/NAS automatisch aus dem Vault-Namen abgeleitet, also z.B.:

```text
\\CL10NAS\lyt\Test\.AddOn\CodexCLI
-> %LOCALAPPDATA%\Test\CodexCLI\.venv
```

`CODEXCLI_VENV` bleibt fuer UNC/NAS nur noch ein Fallback fuer nicht standardmaessige Layouts. Wenn weder Ableitung noch expliziter Wert greifen, ist der Default `Siggiverse`.

**Option A** (empfohlen, am einfachsten):

- Starte einmal `run_codexcli.cmd` (z.B. via Obsidian Shell Command oder manuell). Wenn die lokale venv fehlt, wird sie automatisch erstellt und `requirements.txt` installiert.
- Voraussetzung: Ein Basis-Python (`py` oder `python`) ist im PATH verfügbar.

**Option B** Einmalig lokale venv erstellen und Requirements aus dem Vault installieren:

```powershell
$codexCliHome = "<CODEXCLI_HOME>"  # UNC-Pfad ist ok
$venvBase = $env:CODEXCLI_VENV
if ([string]::IsNullOrWhiteSpace($venvBase)) {
  $venvBase = Split-Path -Path (Split-Path -Path (Split-Path -Path $codexCliHome -Parent) -Parent) -Leaf
}
if ([string]::IsNullOrWhiteSpace($venvBase)) { $venvBase = "Siggiverse" }

$venvPath = Join-Path $env:LOCALAPPDATA "$venvBase\CodexCLI\.venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $venvPath) | Out-Null
python -m venv $venvPath

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $codexCliHome "requirements.txt")
```

**Nachinstallieren neuer Pakete:**

- Dafür gibt es das Script `<CODEXCLI_HOME>\Neue_Pakete.ps1` (installiert in genau dieselbe lokale venv wie `run_codexcli.cmd`).

```powershell
Get-Help .\Neue_Pakete.ps1
Get-Help .\Neue_Pakete.ps1 -Full
Get-Help .\Neue_Pakete.ps1 -Examples
```

Beispiele:

```powershell
# (optional) nur fuer Sonderfaelle explizit setzen; bei UNC/NAS wird sonst der Vault-Name verwendet
$env:CODEXCLI_VENV = "Siggiverse"

powershell -ExecutionPolicy Bypass -File "<CODEXCLI_HOME>\Neue_Pakete.ps1"
powershell -ExecutionPolicy Bypass -File "<CODEXCLI_HOME>\Neue_Pakete.ps1" -Packages "pypdf"
```

## 6) CodexCLI konfigurieren (wichtig: `CODEXCLI_CODEX_CMD` bei Problemen)

Standardmäßig versucht CodexCLI `codex.cmd` aus dem PATH zu verwenden.

Wenn das in deiner Umgebung (z.B. aus Obsidian heraus) nicht zuverlässig funktioniert, setze pro Aufruf die Env-Var `CODEXCLI_CODEX_CMD` auf den **vollständigen Pfad** zur `codex.cmd` (aus `where.exe codex.cmd`).

Beispiel (für Shell commands / `cmd`):

```bat
cmd /V:ON /C "set ^"CODEXCLI_CODEX_CMD=C:\Users\<USER>\AppData\Roaming\npm\codex.cmd^" && "<CODEXCLI_HOME>\run_codexcli.cmd" append "{{file_path:absolute}}""
```

Hinweis: Das ist robuster als eine Code-Änderung, weil der Pfad je Benutzer unterschiedlich ist.

## 7) Obsidian: Plugin "Shell commands" installieren

In Obsidian:

1. Settings
2. Community plugins
3. Browse
4. **Shell commands** suchen
5. Install + Enable

## 8) Obsidian: Shell Commands anlegen (empfohlen: `run_codexcli.cmd`)

Warum `run_codexcli.cmd`?

- Kein Hardcoding von `python.exe`/`main.py` im Obsidian-Kommando.
- Funktioniert stabil auch bei NAS/UNC, weil es eine lokale venv unter `%LOCALAPPDATA%` nutzen kann.
- Bei Standard-UNC-Layouts `\\...\<Vault>\.AddOn\CodexCLI` wird die lokale venv automatisch unter `%LOCALAPPDATA%\<Vault>\CodexCLI\.venv` ausgewaehlt.
- Für Bildgenerierung (`SAVE_AS: ...png`) übernimmt es API-Key-Fallbacks auf `OPENAI_API_KEY` aus `CODEXCLI_OPENAI_API_KEY` oder `OBSIDIAN_OPENAI_API_KEY`.

### 8.1 Append (Antwort an Note anhängen)

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" append "{{file_path:absolute}}""
```

Modellwahl im Normalfall (Textantworten):

- Die Modellwahl erfolgt in dieser Priorität:
  - `TEXT_MODEL_FORCED` in `app/config.py`
  - danach `CODEXCLI_TEXT_MODEL`
  - sonst Codex-CLI-Default

Wenn du das Modell direkt im Projekt fest erzwingen willst, bearbeite [app/config.py](/d:/Ideas/AddOn/CodexCLI/app/config.py:1) und setze z.B.:

```python
TEXT_MODEL_FORCED: str | None = "gpt-5.4"
```

Wenn du stattdessen das Modell über Windows steuern willst, lasse dort:

```python
TEXT_MODEL_FORCED: str | None = None
```

Optionales Override als User-Umgebungsvariable (PowerShell):

```powershell
setx CODEXCLI_TEXT_MODEL "gpt-5.5"
```

Hinweis:

- Das funktioniert identisch fuer Dev (`AddOn`) und Ziel (`.AddOn`), solange du `<CODEXCLI_HOME>` korrekt aufloest.
- Nach `setx` Obsidian einmal neu starten.
- Wenn `TEXT_MODEL_FORCED` gesetzt ist, uebersteuert es die Umgebungsvariable bewusst.
- Wenn `TEXT_MODEL_FORCED = None` und `CODEXCLI_TEXT_MODEL` nicht gesetzt ist, verwendet CodexCLI den Default der installierten Codex CLI.

Optional für Bildgenerierung (bevorzugt, wenn du im Shell-Commands-Plugin eine versteckte Variable wie `{{_OPENAI_API_KEY}}` definiert hast):

```bat
cmd /V:ON /C "set OPENAI_API_KEY={{_OPENAI_API_KEY}}&& "<CODEXCLI_HOME>\run_codexcli.cmd" append "{{file_path:absolute}}""
```

Hinweis:

- Damit bleibt der API-Key im Obsidian-Plugin hinterlegt und wird nur für diesen einen Aufruf als Umgebungsvariable gesetzt.
- Diese Variante ist oft praktischer als `setx OPENAI_API_KEY ...`, weil der Key dann nicht dauerhaft als Windows-User-Variable gespeichert wird.

### 8.1.1 OpenAI API Key schnell setzen (empfohlen für End-to-End Test)

Variante A (manuell in PowerShell):

```powershell
$env:OPENAI_API_KEY="sk-proj-..."
setx OPENAI_API_KEY "sk-proj-..."
```

Hinweis:

- Die erste Zeile gilt sofort für die aktuelle Session.
- Die zweite Zeile speichert dauerhaft für den aktuellen Benutzer.
- Danach Obsidian/Terminal neu starten.

Variante B (Hilfsskript aus diesem Repo):

```powershell
Get-Help .\Set_OpenAI_Key.ps1
Get-Help .\Set_OpenAI_Key.ps1 -Full
Get-Help .\Set_OpenAI_Key.ps1 -Examples

powershell -ExecutionPolicy Bypass -File "<CODEXCLI_HOME>\Set_OpenAI_Key.ps1"
```

Optional nur für aktuelle Session (ohne `setx`):

```powershell
powershell -ExecutionPolicy Bypass -File "<CODEXCLI_HOME>\Set_OpenAI_Key.ps1" -SessionOnly
```

### 8.2 Summary (laufende Zusammenfassung aktualisieren)

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" update_summary "{{file_path:absolute}}""
```

### 8.2.1 PDF-Index note-basiert per Hotkey verwalten

Für große PDFs wird der Retrieval-Index bewusst vorab aufgebaut. Empfohlene Shell Commands:

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" index_note_pdfs "{{file_path:absolute}}""
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" index_note_status "{{file_path:absolute}}""
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" index_note_clear "{{file_path:absolute}}""
```

Hinweise:

- Diese Kommandos lesen die PDF-Referenzen direkt aus `## Prompt` der aktuellen Note.
- Sie sind deshalb gut für Hotkeys geeignet und benötigen keinen händisch eingetragenen PDF-Vollpfad.
- Standard-Speicherort ist `<VAULT_ROOT>\.codexcli\index\`.
- Optional kann der Index-Root per `CODEXCLI_INDEX_ROOT` überschrieben werden.
- Konzept, Pipeline und Limits sind in [Chat_PDF_RAG.md](/d:/Ideas/AddOn/CodexCLI/Chat_PDF_RAG.md:1) beschrieben.

Technische Alternative mit explizitem PDF-Pfad:

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" index_pdf "C:\Pfad\zur\Datei.pdf""
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" index_status "C:\Pfad\zur\Datei.pdf""
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" index_clear "C:\Pfad\zur\Datei.pdf""
```

Zurueck auf das Konfig-Default:

```powershell
setx CODEXCLI_TEXT_MODEL ""
```

### 8.3 Diagnose (hilft bei DEV vs PROD / OCR / PATH)

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" diag "{{file_path:absolute}}""
```

`diag` schreibt im Vault-Root eine Datei `CodexCLI_Connector.md` (overwrite) und druckt denselben Inhalt auf stdout.

Bei UNC/NAS zeigt `diag` zusaetzlich:

- `CODEXCLI_VENV`
- `CODEXCLI_VENV_SOURCE`
- `CODEXCLI_EXPECTED_PYTHON`
- `CODEXCLI_RELAUNCH_STATUS`

Damit laesst sich direkt pruefen, ob die lokale Vault-venv korrekt erkannt oder per Python-Relaunch erzwungen wurde.

## 9) Optional: OCR für Scan-PDFs (Tesseract + Poppler)

Wenn eine referenzierte PDF keinen Textlayer hat, führt CodexCLI automatisch OCR aus.

### 9.1 Winget aktivieren

Im Microsoft Store **"App Installer"** installieren/aktualisieren, dann:

```powershell
winget --version
```

### 9.2 Tesseract + Poppler installieren

```powershell
winget install --id UB-Mannheim.TesseractOCR -e
winget install --id oschwartz10612.Poppler -e
```

### 9.3 Poppler-Pfad ermitteln

```powershell
where.exe pdftoppm
```

Wenn mehrere Treffer erscheinen (Xpdf/MiKTeX überschattet Poppler): setze `CODEXCLI_POPPLER_PATH` explizit auf den Poppler-Ordner `...\Library\bin`.

### 9.4 OCR-Env-Variablen (pro Aufruf setzen)

Empfohlen ist das Setzen **im Shell Command** (kein dauerhaftes `setx`).

```bat
cmd /V:ON /C "set ^"CODEXCLI_TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe^" && set ^"CODEXCLI_POPPLER_PATH=<POPPLER_BIN>^" && set ^"CODEXCLI_OCR_LANG=deu+eng^" && "<CODEXCLI_HOME>\run_codexcli.cmd" append "{{file_path:absolute}}""
```

Hinweise:

- `CODEXCLI_OCR_LANG` ist standardmäßig `deu+eng`.
- Je nach Tesseract-Installation ist anfangs oft nur `eng` verfügbar. Prüfen:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

Wenn `deu` fehlt: deutsches Sprachpaket nachinstallieren **oder** `CODEXCLI_OCR_LANG=eng` setzen.
- `run_codexcli.cmd` versucht Poppler best-effort zu finden und setzt dann den PATH so, dass Poppler-Tools bevorzugt werden.

## 10. Node.js Kurzcheck (nur falls `node`/`npm` fehlen)

Wenn Abschnitt 2 bei dir nicht geklappt hat, reicht für einen normalen Windows-PC meist:

1. Node.js LTS herunterladen
2. `.msi` installieren
3. Terminal neu öffnen
4. `node -v`
5. `npm -v`

## 11. Alternative über Paketmanager unter Windows

Falls auf dem PC `winget` vorhanden ist, kann Node.js auch per Terminal installiert werden:

```powershell
winget install OpenJS.NodeJS.LTS
```

Danach Terminal neu starten und prüfen:

```powershell
node -v
npm -v
```

## 12. Kurzfassung

`npm` kommt mit `Node.js`. Wenn `npm` fehlt, nutze Abschnitt 10 oder 11, öffne das Terminal neu und prüfe dann mit:

```powershell
node -v
npm -v
```

## Nächster Schritt

Bedienung/Notiz-Struktur und Direktiven (`SAVE_AS`, `EXPORT_CHAT_AS`) stehen in [[BEDIENUNG]].
