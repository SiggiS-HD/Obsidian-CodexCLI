# Erstinstallation auf einem neuen Windows-System

Diese Checkliste beschreibt die Erstinstallation von `Obsidian-CodexCLI` auf
einem weiteren Windows-System.

## 1. Voraussetzungen

Empfohlen:

- Windows 11
- Python 3.12
- installierte Codex CLI
- Obsidian
- Obsidian Community-Plugin `Shell commands`

Optional, je nach Nutzung:

- OpenAI API Key fuer `SAVE_AS: *.png`
- Tesseract OCR
- Poppler

## 2. Repository auf das Zielsystem holen

Es gibt drei praktikable Wege.

### Variante A: per Git clone

Empfohlen, wenn auf dem Zielsystem Git installiert ist.

1. Einen Zielordner festlegen, zum Beispiel im Obsidian-Vault:

```text
D:\Ideas\.AddOn\CodexCLI
```

2. PowerShell oeffnen

3. In den uebergeordneten Ordner wechseln:

```powershell
cd "D:\Ideas\.AddOn"
```

4. Repository klonen:

```powershell
git clone git@github.com:SiggiS-HD/Obsidian-CodexCLI.git CodexCLI
```

Falls SSH auf dem Zielsystem nicht eingerichtet ist, alternativ per HTTPS:

```powershell
git clone https://github.com/SiggiS-HD/Obsidian-CodexCLI.git CodexCLI
```

### Variante B: als ZIP von GitHub herunterladen

Sinnvoll, wenn Git auf dem Zielsystem nicht installiert ist.

1. Repository im Browser oeffnen:

```text
https://github.com/SiggiS-HD/Obsidian-CodexCLI
```

2. Auf `Code` klicken

3. `Download ZIP` waehlen

4. ZIP-Datei entpacken

5. Den entpackten Ordner nach:

```text
<VAULT_ROOT>\.AddOn\CodexCLI
```

verschieben oder umbenennen

Wichtig:

- Der finale Ordnername sollte wieder `CodexCLI` sein.
- Nicht mit einem GitHub-Standardnamen wie
  `Obsidian-CodexCLI-main` weiterarbeiten, wenn du spaeter einfache Pfade
  und Dokumentation verwenden willst.

### Variante C: aus einem bestehenden System kopieren

Sinnvoll, wenn du den Projektordner schon lokal auf einem anderen Rechner hast.

1. Den Ordner `CodexCLI` vom bestehenden System kopieren
2. Auf dem Zielsystem in den gewuenschten Vault-Pfad legen:

```text
<VAULT_ROOT>\.AddOn\CodexCLI
```

Hinweis:

- Die vorhandene `.venv` sollte dabei nicht mit uebernommen werden.
- Wenn sie doch mitkopiert wurde, den Ordner `.venv` auf dem Zielsystem loeschen oder umbenennen und lokal neu erstellen.
- Bei einem Vault auf UNC/NAS ist eine Repo-`.venv` besonders problematisch, weil `run_codexcli.cmd` aus Obsidian gestartet wird und eine mitkopierte `.venv` leicht zu Verwirrung fuehrt.

## 3. Zielstruktur im Vault

Empfohlen:

```text
<VAULT_ROOT>\.AddOn\CodexCLI
```

Beispiel:

```text
D:\Ideas\.AddOn\CodexCLI
```

Alternativ waehrend der Entwicklung oder wenn der Ordner sichtbar sein soll:

```text
<VAULT_ROOT>\AddOn\CodexCLI
```

## 4. Python-Umgebung anlegen

Es gibt zwei gueltige Betriebsarten.

### Lokale Arbeitskopie (z.B. `D:\Ideas\...`)

PowerShell im Projektordner:

```powershell
cd "<CODEXCLI_HOME>"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Beispiel:

```powershell
cd "D:\Ideas\.AddOn\CodexCLI"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### UNC/NAS-Vault (z.B. `\\Cl10nas\lyt\Test`)

Wenn `CODEXCLI_HOME` auf einem UNC-/NAS-Pfad liegt, soll die venv nicht im Repo liegen, sondern lokal pro Benutzer unter:

```text
%LOCALAPPDATA%\%CODEXCLI_VENV%\CodexCLI\.venv
```

Beispiel:

```text
C:\Users\siggi\AppData\Local\Test\CodexCLI\.venv
```

Wichtig:

- `run_codexcli.cmd` wird aus Obsidian ueber `cmd.exe` gestartet.
- Beim ersten Aufruf eines Obsidian-Commands wird die lokale venv automatisch erstellt, falls sie noch nicht existiert.
- Eine mitkopierte Repo-`.venv` auf dem NAS sollte entfernt oder umbenannt werden.
- Bei Standard-UNC-Layouts `\\...\<Vault>\.AddOn\CodexCLI` wird `%CODEXCLI_VENV%` automatisch als Vault-Name abgeleitet.
- Fuer UNC-/NAS-Repos bevorzugt `run_codexcli.cmd` damit typischerweise `%LOCALAPPDATA%\<Vault>\CodexCLI\.venv`.
- `main.py` erzwingt diesen UNC-Fall bei Bedarf zusaetzlich per Python-seitigem Relaunch in die erwartete lokale venv.

## 5. Codex CLI auf dem Zielsystem pruefen

Im Terminal testen:

```powershell
codex --version
```

Wenn das nicht funktioniert:

- Codex CLI auf dem Zielsystem installieren
- oder `CODEXCLI_CODEX_CMD` auf den absoluten Pfad von `codex.cmd` setzen

## 6. Obsidian Shell-Command einrichten

In Obsidian das Community-Plugin `Shell commands` aktivieren.

Dann zum Beispiel ein Kommando fuer `append` anlegen:

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" append "{{file_path:absolute}}""
```

Beispiel:

```bat
cmd /V:ON /C ""D:\Ideas\.AddOn\CodexCLI\run_codexcli.cmd" append "{{file_path:absolute}}""
```

Hinweis fuer UNC/NAS:

- Der Einstieg erfolgt ueber `run_codexcli.cmd`, nicht ueber eine manuell aktivierte PowerShell-venv.
- Fuer Standard-UNC-Layouts `\\...\<Vault>\.AddOn\CodexCLI` wird die lokale venv automatisch unter `%LOCALAPPDATA%\<Vault>\CodexCLI\.venv` ausgewaehlt.

## 7. Optional: OpenAI API Key fuer PNG-Ausgabe

Nur erforderlich, wenn du `SAVE_AS: *.png` nutzen willst.

```powershell
powershell -ExecutionPolicy Bypass -File "<CODEXCLI_HOME>\Set_OpenAI_Key.ps1"
```

Beispiel:

```powershell
powershell -ExecutionPolicy Bypass -File "D:\Ideas\.AddOn\CodexCLI\Set_OpenAI_Key.ps1"
```

## 8. Optional: PDF-OCR vorbereiten

Falls du PDF-Dateien mit OCR-Fallback nutzen willst:

- Tesseract installieren
- Poppler installieren

Wenn noetig, die zugehoerigen Pfade ueber Umgebungsvariablen konfigurieren:

- `CODEXCLI_TESSERACT_CMD`
- `CODEXCLI_POPPLER_PATH`
- `CODEXCLI_OCR_LANG`

## 9. Funktionstest

In Obsidian eine Test-Note mit dieser Grundstruktur anlegen:

```md
## Prompt
Schreibe eine kurze Zusammenfassung.

## Laufende Zusammenfassung

## Unterhaltung
```

Danach den Shell-Command fuer `append` ausfuehren.

Wenn alles korrekt eingerichtet ist, sollte Codex die Antwort in die Note zurueckschreiben.

## 10. Troubleshooting: `service_tier`

Wenn beim ersten echten Lauf ein Fehler in dieser Art erscheint:

```text
Error loading config.toml: unknown variant `default`, expected `fast` or `flex`
in `service_tier`
```

dann kommt das Problem in der Regel nicht aus `Obsidian-CodexCLI`, sondern aus der globalen Codex-Konfiguration unter:

```text
C:\Users\<USER>\.codex\config.toml
```

`service_tier` beschreibt die bevorzugte Leistungs- bzw. Betriebsstufe von Codex. Es ist nicht das Modell selbst und auch nicht die Reasoning-Stufe.

Praktisch wichtig:

- `fast`
  schneller, aber mit hoeherem Verbrauch
- `flex`
  gueltiger konservativer Wert
- `default`
  kann in neueren Codex-Versionen ungueltig sein

Fuer ein ChatGPT-Plus-Konto gilt:

- `fast` ist nur sinnvoll, wenn du bewusst den Fast Mode nutzen willst
- `flex` ist ein gueltiger expliziter Wert
- am robustesten ist oft, die `service_tier`-Zeile ganz zu entfernen, damit Codex selbst den passenden Standard waehlt

Empfohlene Loesung bei diesem Fehler:

- `service_tier = "default"` aus `config.toml` entfernen

Alternative:

```toml
service_tier = "flex"
```

## 11. Wichtige Dateien zur Orientierung

- `README.md`
- `Installation_Codex_CLI_und_Obsidian.md`
- `BEDIENUNG.md`
- `Chat_PDF_RAG.md`
- `FILE_REFERENCES.md`
- `TROUBLESHOOTING.md`

## Kurzfassung

1. Repository nach `<VAULT_ROOT>\.AddOn\CodexCLI` holen
2. `.venv` lokal neu anlegen oder bei UNC/NAS automatisch bootstrapen lassen
3. `requirements.txt` installieren
4. `codex --version` pruefen
5. Obsidian `Shell commands` konfigurieren
6. optional API-Key und OCR-Tools einrichten
7. Test-Note ausfuehren
