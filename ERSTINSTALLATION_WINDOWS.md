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
- Wenn sie doch mitkopiert wurde, den Ordner `.venv` auf dem Zielsystem loeschen
  und lokal neu erstellen.

## 3. Zielstruktur im Vault

Empfohlen:

```text
<VAULT_ROOT>\.AddOn\CodexCLI
```

Beispiel:

```text
D:\Ideas\.AddOn\CodexCLI
```

Alternativ waehrend Entwicklung oder wenn der Ordner sichtbar sein soll:

```text
<VAULT_ROOT>\AddOn\CodexCLI
```

## 4. Python-Umgebung anlegen

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

Wenn alles korrekt eingerichtet ist, sollte Codex die Antwort in die Note
zurueckschreiben.

## 10. Wichtige Dateien zur Orientierung

- `README.md`
- `Installation_Codex_CLI_und_Obsidian.md`
- `BEDIENUNG.md`
- `Chat_PDF_RAG.md`
- `FILE_REFERENCES.md`
- `TROUBLESHOOTING.md`

## Kurzfassung

1. Repository nach `<VAULT_ROOT>\.AddOn\CodexCLI` holen
2. `.venv` lokal neu anlegen
3. `requirements.txt` installieren
4. `codex --version` pruefen
5. Obsidian `Shell commands` konfigurieren
6. optional API-Key und OCR-Tools einrichten
7. Test-Note ausfuehren
