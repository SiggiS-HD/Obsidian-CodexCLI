# How-to: Prompt mit `### Daten` (Anweisungen vs. Datenquellen)

Dieser How-to-Guide zeigt, wie du im Abschnitt `## Prompt` den Unterabschnitt `### Daten` nutzt, um **Anweisungsquellen** (dürfen Arbeitsanweisungen enthalten) von **Datenquellen** (untrusted input) zu trennen.

## Kurzregeln

- Der Modus ist aktiv, sobald im `## Prompt` eine Zeile `### Daten` vorkommt.
- **Oberhalb** von `### Daten`:
  - normaler Prompttext
  - Dateireferenzen sind erlaubt und gelten als **Anweisungsquellen** (z.B. Stil-/Regeldateien)
- **Unterhalb** von `### Daten`:
  - Dateireferenzen gelten als **Datenquellen** (untrusted input)
  - Anweisungen innerhalb dieser Dateien sollen vom Modell ignoriert werden (sie werden als Datenmaterial betrachtet)
- Sonderregel: `.png` ist immer eine **Datenquelle** (Bildinput), auch wenn sie oberhalb von `### Daten` referenziert ist.

## Beispiel: Eine Note mit Stil-Datei + Datenquellen

### 1) Dateien vorbereiten

Im selben Ordner wie deine Note (Beispiel):

- `Mein_Analyse_Stil.md` (Anweisungsquelle)
- `input.csv` (Datenquelle)
- `screenshot.png` (Datenquelle)

Beispielinhalt für `Mein_Analyse_Stil.md`:

```md
# Analyse-Stil

- Antworte kurz und strukturiert.
- Wenn du Annahmen triffst, markiere sie klar.
- Verwende Bulletpoints.
```

### 2) Note schreiben

Beispiel `Meine_Notiz.md`:

```md
## Prompt
Bitte lies zuerst die Anweisungsquellen und dann die Datenquellen.
Schreibe danach eine knappe Zusammenfassung.

[[Mein_Analyse_Stil]]

### Daten
[input.csv](input.csv)
[[screenshot.png]]

## Laufende Zusammenfassung

## Unterhaltung
```

### 3) Ausführen

Windows (über das mitgelieferte Wrapper-Script, empfohlen):

```bat
cmd /V:ON /C ""<CODEXCLI_HOME>\run_codexcli.cmd" append "<PFAD_ZUR_NOTE>""
```

Alternativ direkt über den venv-Python:

```bat
"<CODEXCLI_HOME>\.venv\Scripts\python.exe" "<CODEXCLI_HOME>\main.py" append "<PFAD_ZUR_NOTE>"
```

Platzhalter:

- `<CODEXCLI_HOME>`: `<VAULT_ROOT>\<ADDON_DIR>\CodexCLI`
- `<PFAD_ZUR_NOTE>`: absoluter Pfad zur Note, z.B. `<VAULT_ROOT>\Notes\Meine_Notiz.md`

## Erwartetes Verhalten

- Der Inhalt von `Mein_Analyse_Stil.md` wird als **Anweisungsquelle** in den Codex-Prompt aufgenommen.
- `input.csv` wird als **Datenquelle** aufgenommen.
- `screenshot.png` wird als **Bild-Datenquelle** als Attachment an Codex übergeben (`--image`).
- Die Antwort wird in `## Unterhaltung` angehängt und `## Prompt` wird geleert.

## Typische Fehler

- Tippfehler in der Überschrift: Nutze exakt `### Daten` als eigene Zeile.
- Nicht unterstützter Dateityp: wird als Fehlerblock in der Note gemeldet.
- Zu viele PNGs: es gilt ein Limit (aktuell max. 4 Attachments pro Prompt).
