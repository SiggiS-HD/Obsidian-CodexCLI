# Codex Chat Exporter

Diese Version verarbeitet jetzt auch das reale Codex-JSONL-Format mit:

- `type`
- `payload`
- `payload.role`
- `payload.content[].text`

## Wichtigste Verbesserungen

- korrektes Auslesen von `payload.role`
- korrektes Extrahieren von Text aus `payload.content`
- Standard-Output jetzt stabil relativ zum Script: `codex_chat/`
- `--input-file` zum Testen einzelner Dateien
- `text-only` funktioniert jetzt auch mit payload-basierten Logs

## Beispiele

Eine einzelne Datei testen:

```bash
python codex_log_to_md.py --input-file "/pfad/zur/datei.jsonl" --mode text-only --force
```

Nur einen bestimmten Tag exportieren:

```bash
python codex_log_to_md.py --mode text-only --date 2026-03-09 --force
```

Etwas ausführlicher:

```bash
python codex_log_to_md.py --mode readable --date 2026-03-09 --force
```

## Codex Chats - z.B. über Osidian
Die Session-JSONL-Dateien liegen auf deinem Windows-System standardmäßig hier:
```
C:\Users\siggi\.codex\sessions\
```

Die Struktur ist nach Datum verschachtelt, also typischerweise:
`C:\Users\siggi\.codex\sessions\YYYY\MM\DD\rollout-...jsonl`

Beispiel:
`C:\Users\siggi\.codex\sessions\2026\04\22\rollout-2026-04-22T10-19-34-019db445-ebb3-7971-a195-e8ae94bdad31.jsonl`

Zusätzlich liegen im Wurzelordner `C:\Users\siggi\.codex\` noch weitere JSONL-Dateien wie:
- `history.jsonl`
- `session_index.jsonl`

Wenn du sie im Explorer öffnen willst, ist der Hauptpfad:
```
%USERPROFILE%\.codex\sessions
```

## Codex Chats - in VS Code

```
C:\Users\siggi\AppData\Roaming\Code\User\workspaceStorage\
```

Beispiel:
```

C:\Users\siggi\AppData\Roaming\Code\User\workspaceStorage\3efaf13857c6561be9d8c531957e4d6f\chatSessions\b5dafbae-db52-43cf-9b03-747e33440377.jsonl
```
