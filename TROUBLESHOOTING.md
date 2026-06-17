# Troubleshooting
## Bildgenerierung: HTTP 400 `Invalid size ...`

Symptom (Beispiel):

```text
Bildgenerierung fehlgeschlagen (HTTP 400): Invalid size '1536x864'. Supported sizes are 1024x1024, 1024x1536, 1536x1024, and auto.
```

Ursache:

- Das verwendete Bildmodell akzeptiert nur die festen Größen `1024x1024`, `1024x1536`, `1536x1024` oder `auto`.
- Werte wie `1536x864` (echtes 16:9) werden abgelehnt.

Aktuelles Verhalten in CodexCLI:

- `ASPECT: 1:1` -> `size=1024x1024`
- `ASPECT: 4:3` -> `size=auto` (Best-Effort)
- `ASPECT: 16:9` -> `size=auto` (Best-Effort)

Empfehlung:

- Nutze weiter `ASPECT: 16:9` oder `ASPECT: 4:3`; CodexCLI setzt intern `auto` und die API waehlt ein passendes Format.
- Wenn du harte Pixelmaße brauchst, muss das Modell/API diese Größe explizit unterstützen.


## Obsidian meldet „Datei nicht gefunden“

Typische Ursache:

- Du hast im Shell Command das falsche Layout verwendet (`AddOn` vs `.AddOn`).

Fix:

- Prüfe, ob dein tatsächlicher Pfad `<VAULT_ROOT>\<ADDON_DIR>\CodexCLI` ist.
- Standard (Ziel) ist `.AddOn`. `AddOn` ist nur die Dev-Variante.

## `codex`/`codex.cmd` wird nicht gefunden

Prüfen:

```powershell
where.exe codex
where.exe codex.cmd
codex --version
```

Fix:

- Stelle sicher, dass `%APPDATA%\npm` im User-PATH enthalten ist.
- Alternativ setze pro Aufruf `CODEXCLI_CODEX_CMD` auf den vollständigen Pfad zur `codex.cmd` (robust in Obsidian/cmd-Umgebungen).

## CodexCLI läuft in PowerShell, aber nicht aus Obsidian

Typische Ursachen:

- Obsidian startet `cmd`, nicht deine interaktive PowerShell (anderer PATH).
- Falsche Quotes im Shell Command.

Fix:

- Verwende die Beispiele aus `Installation_Codex_CLI_und_Obsidian.md` (sie sind bewusst `cmd /V:ON /C ...`).
- Starte bevorzugt über `run_codexcli.cmd` statt `python.exe ... main.py ...`.

## NAS/UNC: venv im Repo existiert nicht

Symptom:

- Der Vault liegt auf `\\NAS\...` und `.venv` ist nicht vorhanden oder soll nicht auf dem Netzlaufwerk liegen.

Fix:

- `run_codexcli.cmd` nutzt automatisch eine lokale venv unter `%LOCALAPPDATA%\<CODEXCLI_VENV>\CodexCLI\.venv`.
- Wenn die venv noch nicht existiert, wird sie beim ersten Lauf automatisch erstellt und `requirements.txt` installiert (Voraussetzung: `py` oder `python` ist im PATH).
- Wenn du einen anderen Basisordner willst: setze `CODEXCLI_VENV` (z.B. in deinem Shell Command vor dem Aufruf).

## MOC-Steuerliste: Dateien werden nicht (oder falsch) geladen

Symptom:

- Du referenzierst eine MOC-Datei im `## Prompt`, aber es werden nicht die erwarteten Dateien in der gewünschten Reihenfolge geladen.
- Oder CodexCLI schreibt einen Fehler zu „MOC-Eintrag“/„Unterlisten“/„verschachtelte MOC“.

Prüfen:

- Nutze [[MOC_TEMPLATE]] als Ausgangspunkt.
- Stelle sicher, dass die **erste Überschrift** der Datei das Wort `MOC` enthält (z.B. `# Projekt MOC`).
- Stelle sicher, dass die Steuerliste **nur** aus einfachen nummerierten Listeneinträgen besteht (`1. ...`).

Typische Ursachen + Fix:

- **Unterlisten / Einrückungen** → nicht unterstützt.
	- Fix: Keine eingerückten `  1.`-Punkte; alles auf Top-Level.
- **Mehr als eine Referenz pro Listeneintrag** (z.B. `1. [[A]] und [[B]]`) → nicht unterstützt.
	- Fix: Pro Zeile genau eine Referenz; ggf. auf mehrere Zeilen aufteilen.
- **Absolute Windows-Pfade** in der MOC (z.B. `C:\...`) → nicht unterstützt.
	- Fix: WikiLinks oder relative Links verwenden.
- **Verschachtelte MOCs** (eine MOC referenziert eine weitere MOC) → nicht unterstützt.
	- Fix: Nur eine Ebene; MOC darf keine andere MOC einbinden.

Hinweis:

- Relative Pfade in der MOC werden relativ zur **MOC-Datei** aufgelöst.
- Die MOC-Datei selbst wird nicht als Kontext gesendet; nur die aufgelisteten Ziele.
- Details stehen in [[FILE_REFERENCES]].

## OCR liefert leeren Text / `pdftoppm` ist „falsch“

Symptom:

- Scan-PDFs bleiben leer oder OCR bricht ab.

Ursache:

- `pdf2image` nutzt `pdftoppm` aus dem PATH; manchmal ist das Xpdf/MiKTeX statt Poppler.

Fix:

- Installiere Poppler über winget (siehe Installation).
- Setze `CODEXCLI_POPPLER_PATH` explizit auf den Poppler-Ordner `...\Library\bin`.
- Nutze `diag` und prüfe dort `where pdftoppm`.

Wenn OCR wegen Sprache scheitert (z.B. Meldungen zu `deu.traineddata`):

- Prüfe die verfügbaren Tesseract-Sprachen: `tesseract --list-langs`
- Wenn `deu` fehlt: deutsches Sprachpaket nachinstallieren oder `CODEXCLI_OCR_LANG=eng` setzen.

## Diagnose: `diag`

Wenn du nicht weiterkommst:

- Führe `diag` über Obsidian aus.
- Vergleiche die erzeugte Datei `CodexCLI_Connector.md` im Vault-Root zwischen Dev und Zielumgebung.
- Prüfe dort auch den Abschnitt zu `<VAULT_ROOT>\.codexcli\tmp\`; liegengebliebene leere Unterordner nach abgebrochenen Läufen können manuell gelöscht werden.
