# Testing Notes

## Aktueller Testaufruf

Das minimale Testgerüst für den bestehenden Append-Workflow wird aktuell so ausgeführt:

```bash
python -m unittest tests.test_append_workflow
```

Dabei lädt Python das eingebaute Modul `unittest`, sucht in `tests/test_append_workflow.py` nach `TestCase`-Klassen und führt alle Methoden aus, deren Name mit `test_` beginnt.

## Was aktuell getestet wird

Die Datei `tests/test_append_workflow.py` sichert derzeit vier zentrale Fälle ab:

1. Ein leerer Abschnitt `## Prompt` erzeugt einen Fehlerblock in der Note.
2. Eine erfolgreiche Codex-Antwort wird an `## Unterhaltung` angehängt.
3. Der Abschnitt `## Prompt` wird nach erfolgreichem Append geleert.
4. Codex-Startfehler und Codex-Rückgabefehler werden in die Note geschrieben.

## Aufbau der Testdatei

Die Tests bestehen aus drei Bausteinen:

- `build_note(prompt, chat="")`
  Erzeugt eine vollständige Markdown-Testnote mit den Abschnitten `## Laufende Zusammenfassung`, `## Prompt` und `## Unterhaltung`.
- `create_note(content)`
  Erstellt eine temporäre Datei `note.md` in einem temporären Ordner und schreibt den Testinhalt hinein.
- Testmethoden `test_*`
  Rufen `append_response()` auf und prüfen Rückgabewert sowie den veränderten Dateiinhalt.

## Warum `run_codex()` gemockt wird

Die Tests sollen nicht die echte Codex-CLI starten. Deshalb wird in mehreren Tests `run_codex()` ersetzt:

```python
@patch("app.append_workflow.run_codex")
```

Wichtig ist, dass die Funktion dort gepatcht wird, wo sie im Workflow verwendet wird, also in `app.append_workflow`, nicht in `app.codex_client`.

Dadurch können die Tests kontrollierte Ergebnisse simulieren:

- erfolgreicher Lauf
- Fehler-Rückgabecode
- Startfehler

Das macht die Tests schnell, stabil und unabhängig von externer Umgebung.

## Temporäre Dateien

Die Testnote wird in einem temporären Ordner angelegt, typischerweise unter dem Windows-Temp-Verzeichnis des Benutzers.

Aktuell wird der Ordner nach jedem Test automatisch gelöscht:

```python
self.addCleanup(temp_dir.cleanup)
```

Dadurch bleiben die Tests sauber und hinterlassen keine Artefakte.

## Kleine Debug-Variante des Testhelpers

Für Debugging kann der Helper so erweitert werden, dass temporäre Dateien optional erhalten bleiben.

Beispielidee:

```python
import os
import tempfile
from pathlib import Path

KEEP_TEST_FILES = os.getenv("KEEP_TEST_FILES") == "1"

def create_note(self, content: str) -> Path:
    temp_dir = tempfile.TemporaryDirectory()

    if not KEEP_TEST_FILES:
        self.addCleanup(temp_dir.cleanup)
    else:
        print(f"Keeping test files in: {temp_dir.name}")

    note_path = Path(temp_dir.name) / "note.md"
    note_path.write_text(content, encoding="utf-8")
    return note_path
```

Dann gibt es zwei Modi:

- Standard:
  Temp-Dateien werden automatisch gelöscht.
- Debug:
  Mit gesetzter Umgebungsvariable bleiben die Dateien erhalten.

Beispiel unter PowerShell:

```powershell
$env:KEEP_TEST_FILES="1"
python -m unittest tests.test_append_workflow
```

So kann der erzeugte Ordnerpfad aus der Ausgabe direkt geöffnet und geprüft werden.

## Empfehlung

Für normale Testläufe sollte das automatische Cleanup aktiv bleiben. Die Debug-Variante ist nur für gezielte Fehlersuche sinnvoll.
