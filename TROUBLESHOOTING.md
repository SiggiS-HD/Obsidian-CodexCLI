# Troubleshooting
## Bildgenerierung: HTTP 400 `Invalid size ...`

Symptom (Beispiel):

```text
Bildgenerierung fehlgeschlagen (HTTP 400): Invalid size '1536x864'. Supported sizes are 1024x1024, 1024x1536, 1536x1024, and auto.
```

Ursache:

- Das verwendete Bildmodell akzeptiert nur die festen Groessen `1024x1024`, `1024x1536`, `1536x1024` oder `auto`.
- Werte wie `1536x864` (echtes 16:9) werden abgelehnt.

Aktuelles Verhalten in CodexCLI:

- `ASPECT: 1:1` -> `size=1024x1024`
- `ASPECT: 4:3` -> `size=auto` (Best-Effort)
- `ASPECT: 16:9` -> `size=auto` (Best-Effort)

Empfehlung:

- Nutze weiter `ASPECT: 16:9` oder `ASPECT: 4:3`; CodexCLI setzt intern `auto` und die API waehlt ein passendes Format.
- Wenn du harte Pixelmasse brauchst, muss das Modell/API diese Groesse explizit unterstuetzen.


## Obsidian meldet „Datei nicht gefunden“

Typische Ursache:

- Du hast im Shell Command das falsche Layout verwendet (`AddOn` vs `.AddOn`).

Fix:

- Pruefe, ob dein tatsaechlicher Pfad `<VAULT_ROOT>\<ADDON_DIR>\CodexCLI` ist.
- Standard (Ziel) ist `.AddOn`. `AddOn` ist nur die Dev-Variante.

## `codex`/`codex.cmd` wird nicht gefunden

Pruefen:

```powershell
where.exe codex
where.exe codex.cmd
codex --version
```

Fix:

- Stelle sicher, dass `%APPDATA%\npm` im User-PATH enthalten ist.
- Alternativ setze pro Aufruf `CODEXCLI_CODEX_CMD` auf den vollstaendigen Pfad zur `codex.cmd` (robust in Obsidian/cmd-Umgebungen).

## CodexCLI laeuft in PowerShell, aber nicht aus Obsidian

Typische Ursachen:

- Obsidian startet `cmd`, nicht deine interaktive PowerShell (anderer PATH).
- Falsche Quotes im Shell Command.

Fix:

- Verwende die Beispiele aus `Installation_Codex_CLI_und_Obsidian.md` (sie sind bewusst `cmd /V:ON /C ...`).
- Starte bevorzugt ueber `run_codexcli.cmd` statt `python.exe ... main.py ...`.

## NAS/UNC: Repo-`.venv` wurde mitkopiert

Symptom:

- Der Vault liegt auf `\\NAS\...`.
- Du hast lokal bereits `%LOCALAPPDATA%\%CODEXCLI_VENV%\CodexCLI\.venv` angelegt.
- Trotzdem erscheint ein Fehler wie `No Python at 'C:\...\Python312\python.exe'`.

Ursache:

- Eine alte oder von einem anderen System kopierte Repo-`.venv` liegt noch unter `<CODEXCLI_HOME>\.venv`.
- Solche virtuellen Umgebungen enthalten feste Verweise auf die urspruengliche Python-Installation.
- `run_codexcli.cmd` bevorzugt bei UNC/NAS inzwischen die lokale venv, aber eine mitkopierte Repo-`.venv` bleibt ein klarer Stoerfaktor und sollte entfernt oder umbenannt werden.

Fix:

- Repo-`.venv` auf dem NAS loeschen oder z.B. in `.venv_OFF` umbenennen.
- Danach den Obsidian-Command erneut starten.
- Falls die lokale venv noch nicht existiert, wird sie beim ersten Aufruf automatisch unter `%LOCALAPPDATA%\%CODEXCLI_VENV%\CodexCLI\.venv` erstellt.

## NAS/UNC: venv im Repo existiert nicht

Symptom:

- Der Vault liegt auf `\\NAS\...` und `.venv` ist nicht vorhanden oder soll nicht auf dem Netzlaufwerk liegen.

Fix:

- `run_codexcli.cmd` nutzt automatisch eine lokale venv unter `%LOCALAPPDATA%\<CODEXCLI_VENV>\CodexCLI\.venv`.
- Wenn die venv noch nicht existiert, wird sie beim ersten Lauf automatisch erstellt und `requirements.txt` installiert (Voraussetzung: `py` oder `python` ist im PATH).
- Wenn du einen anderen Basisordner willst: setze `CODEXCLI_VENV` (z.B. in deinem Shell Command vor dem Aufruf).

## MOC-Steuerliste: Dateien werden nicht (oder falsch) geladen

Symptom:

- Du referenzierst eine MOC-Datei im `## Prompt`, aber es werden nicht die erwarteten Dateien in der gewuenschten Reihenfolge geladen.
- Oder CodexCLI schreibt einen Fehler zu „MOC-Eintrag“/„Unterlisten“/„verschachtelte MOC“.

Pruefen:

- Nutze [[MOC_TEMPLATE]] als Ausgangspunkt.
- Stelle sicher, dass die **erste Ueberschrift** der Datei das Wort `MOC` enthaelt (z.B. `# Projekt MOC`).
- Stelle sicher, dass die Steuerliste **nur** aus einfachen nummerierten Listeneintraegen besteht (`1. ...`).

Typische Ursachen + Fix:

- **Unterlisten / Einrueckungen** -> nicht unterstuetzt.
  - Fix: Keine eingerueckten `  1.`-Punkte; alles auf Top-Level.
- **Mehr als eine Referenz pro Listeneintrag** (z.B. `1. [[A]] und [[B]]`) -> nicht unterstuetzt.
  - Fix: Pro Zeile genau eine Referenz; ggf. auf mehrere Zeilen aufteilen.
- **Absolute Windows-Pfade** in der MOC (z.B. `C:\...`) -> nicht unterstuetzt.
  - Fix: WikiLinks oder relative Links verwenden.
- **Verschachtelte MOCs** (eine MOC referenziert eine weitere MOC) -> nicht unterstuetzt.
  - Fix: Nur eine Ebene; MOC darf keine andere MOC einbinden.

Hinweis:

- Relative Pfade in der MOC werden relativ zur **MOC-Datei** aufgeloest.
- Die MOC-Datei selbst wird nicht als Kontext gesendet; nur die aufgelisteten Ziele.
- Details stehen in [[FILE_REFERENCES]].

## OCR liefert leeren Text / `pdftoppm` ist „falsch“

Symptom:

- Scan-PDFs bleiben leer oder OCR bricht ab.

Ursache:

- `pdf2image` nutzt `pdftoppm` aus dem PATH; manchmal ist das Xpdf/MiKTeX statt Poppler.

Fix:

- Installiere Poppler ueber winget (siehe Installation).
- Setze `CODEXCLI_POPPLER_PATH` explizit auf den Poppler-Ordner `...\Library\bin`.
- Nutze `diag` und pruefe dort `where pdftoppm`.

Wenn OCR wegen Sprache scheitert (z.B. Meldungen zu `deu.traineddata`):

- Pruefe die verfuegbaren Tesseract-Sprachen: `tesseract --list-langs`
- Wenn `deu` fehlt: deutsches Sprachpaket nachinstallieren oder `CODEXCLI_OCR_LANG=eng` setzen.

## Diagnose: `diag`

Wenn du nicht weiterkommst:

- Fuehre `diag` ueber Obsidian aus.
- Vergleiche die erzeugte Datei `CodexCLI_Connector.md` im Vault-Root zwischen Dev und Zielumgebung.
- Pruefe dort auch den Abschnitt zu `<VAULT_ROOT>\.codexcli\tmp\`; liegengebliebene leere Unterordner nach abgebrochenen Laeufen koennen manuell geloescht werden.
