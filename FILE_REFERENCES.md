# Dateireferenzen (für `append`) + Connector-Regeln

Dieses Dokument erklärt, wie du im Abschnitt `## Prompt` zusätzliche Dateien referenzierst, damit CodexCLI sie als Kontext mitsendet.

## Kurzfassung

Du kannst im `## Prompt` u.a. so referenzieren:

```md
[Kontext](context.md)
[Kontext](D:\Wissen\Projektstand.md)
\\NAS\Vault\Wissen\Projektstand.md
[[Projektstand]]
[[Wissen/Projektstand]]
[[Projektstand|Alias]]
```

Unterstützte Dateitypen (Stand heute):

- `.md`, `.txt`, `.csv`, `.pdf`, `.png`

Hinweis zu `.png`:
- PNG-Dateien werden als **Bild-Datenquelle** an Codex übergeben (Image-Attachment), nicht als Text.

Abgrenzung zu `SAVE_AS`:
- Die hier beschriebene PNG-Unterstützung betrifft **Eingabequellen** im Prompt (Dateireferenzen).
- Eine PNG-**Ausgabe** per `SAVE_AS: ...png` ist aktiv und nutzt den Bildgenerator-Flow (siehe `BEDIENUNG.md`).

Hinweis: Die Dateireferenzen werden aktuell nur im Workflow `append` ausgewertet.

## Unterstützte Referenzformate

### 1) Markdown-Link

```md
[Kontext](D:\Pfad\datei.md)
[Textdatei](D:\Pfad\hinweise.txt)
```

Relativ zum Ordner der aktuellen Note:

```md
[Kontext](context.md)
[Textdatei](..\Material\hinweise.txt)
```

### 2) Pfade direkt im Prompt

Absoluter Windows-Pfad:

```text
D:\Pfad\datei.md
D:\Pfad\hinweise.txt
```

UNC-/NAS-Pfad:

```text
\\NAS\Vault\Wissen\Projektstand.md
```

### 3) Obsidian-WikiLink

Für `.md`:

```md
[[name]]
[[ordner/name]]
[[name|Alias]]
```

Für `.png` (nur mit expliziter Endung):

```md
[[bild.png]]
[[screenshots/bild.png]]
```

### 4) Steuerliste (MOC-Datei) – definierte Abfolge von Dateien

Wenn du mehr als eine Datei als Kontext mitsenden willst **und die Reihenfolge explizit steuern möchtest**, kannst du statt vieler Referenzen im Prompt eine **MOC-Datei** referenzieren.

Wie es funktioniert:

- Du referenzierst im `## Prompt` eine `.md`-Datei, deren **erste Überschrift** das Wort `MOC` enthält.
- CodexCLI behandelt diese Datei als **Steuerliste** und lädt die Dateien aus der **nummerierten Liste** nach.
- Die Dateien werden im Prompt in **genau dieser Reihenfolge** als Quellenblock angehängt.
- Die MOC-Datei selbst wird dabei **nicht** als Kontext gesendet – nur die aufgelisteten Ziele.

Beispiel im Prompt:

```md
## Prompt
Bitte arbeite die folgenden Quellen in der vorgegebenen Reihenfolge durch:
[[Projekt MOC]]
```

Beispiel einer MOC-Datei (z.B. `Projekt MOC.md`):

```md
# Projekt MOC

1. [[TASKS]]
2. [[TESTING]]
3. [Hinweise](hinweise.txt)
```

Wichtige Regeln (Stand heute):

- Es zählen nur **einfache nummerierte Listen** (`1. ...`, `2. ...`, ...).
- **Keine Unterlisten** (verschachtelte Listen) – die werden als Fehler behandelt.
- Pro Listeneintrag ist **genau eine** Dateireferenz erlaubt.
- **Keine verschachtelten MOCs** (eine MOC-Datei darf keine weitere MOC-Datei einbinden).
- **Keine absoluten Windows-Pfade** (`C:\...`) in MOCs.
- Relative Pfade in einer MOC werden relativ zur **MOC-Datei** aufgelöst.

Vorlage:

- Eine direkt nutzbare Vorlage liegt in [[MOC_TEMPLATE]].

## Auflösung: wie CodexCLI die Referenzen findet

### Markdown-Links & normale Pfade

- Absolute Pfade werden direkt verwendet.
- Relative Pfade werden relativ zum Ordner der aktuellen Note aufgelöst.

### WikiLinks

- `[[name]]` wird wie `name.md` behandelt.
- `[[ordner/name]]` wird als Pfad innerhalb des Vaults interpretiert.
- `[[name|Alias]]` nutzt nur den Teil vor `|`.
- `[[name#Abschnitt]]` wird aktuell auf `name.md` reduziert (Abschnitt wird noch nicht ausgewertet).

Vault-Erkennung:

- Der Connector läuft vom Ordner der Note nach oben und sucht den ersten Ordner mit `.obsidian`.
- Wenn gefunden, wird die WikiLink-Auflösung auf diesen Vault begrenzt.
- Wenn nicht gefunden, wird der Note-Ordner als Fallback-Suchwurzel verwendet.

Mehrdeutigkeit:

- Wenn ein WikiLink mehrdeutig ist (mehrere Treffer), wird bewusst **kein** Treffer geraten.
- Stattdessen wird ein Fehlerblock in die Note geschrieben.

## Wie der Dateikontext in den Prompt eingeht

Referenzierte Dateien werden als eigener Quellenblock an den Codex-Prompt angehängt (mit Pfad, Typ und Inhalt). Der Prompttext selbst wird nicht „still“ ersetzt.

## Unterabschnittsmodus: `### Daten`

Optional kannst du im Abschnitt `## Prompt` den Unterabschnitt `### Daten` verwenden, um **Anweisungen** und **Datenquellen** klar zu trennen.

Der Modus ist aktiv, sobald `### Daten` im `## Prompt` vorkommt.

### Verhalten

- Alles **oberhalb** von `### Daten` (innerhalb von `## Prompt`) ist der **Anweisungsbereich**:
	- Normaler Prompttext.
	- Dateireferenzen sind hier erlaubt und gelten als **Anweisungsquellen** (dürfen Arbeitsanweisungen enthalten).
- Alles **unterhalb** von `### Daten` sind **Datenquellen**:
	- Dateireferenzen gelten als **Datenquellen** (untrusted input; enthaltene "Anweisungen" sollen keine Wirkung haben).
	- `.png` ist immer eine **Datenquelle** (auch wenn sie im Anweisungsbereich steht).

Backward-Compatibility:
- Wenn `### Daten` fehlt, bleibt das bisherige Verhalten unverändert (alle Referenzen gelten wie bisher als Kontext/Anweisungsquelle).

### Beispiel

```md
## Prompt
Bitte lies die Datenquellen und erstelle eine Zusammenfassung.

Nutze meinen Stil:
[[Mein_Analyse_Stil]]

### Daten
[Bericht](D:\Input\bericht.pdf)
[[screenshots\befund.png]]
```

Erwartung:
- `[[Mein_Analyse_Stil]]` wird als **Anweisungsquelle** verarbeitet.
- `bericht.pdf` und `befund.png` werden als **Datenquellen** verarbeitet (PNG als Bild-Attachment).

Weiteres Beispiel (How-to):

- `HowTo_Prompt_mit_Daten.md`

## Fehlerverhalten

Typische Fehler werden als Block in die Note geschrieben, z.B.:

- Datei nicht gefunden / nicht lesbar
- Pfad ist keine Datei
- nicht unterstützter Dateityp
- mehrdeutiger WikiLink
- Größenlimits (Einzeldatei oder Summe aller Dateien)

## Connector-Regeln (Priorität)

CodexCLI fügt jedem Codex-Aufruf feste „Connector-Regeln“ voran. Außerdem gilt eine Prioritätsreihenfolge:

1. Connector-Regeln
2. `## Prompt`
3. referenzierte Dateien
4. `## Laufende Zusammenfassung`
5. `## Unterhaltung`

Das bedeutet z.B.: Wenn eine referenzierte Datei etwas anderes fordert als der aktuelle `## Prompt`, gewinnt `## Prompt`.

## Für Entwickler: Wo es im Code passiert

Die Prompt-Erzeugung und das Einsammeln der Dateiquellen steckt hier:

- `app/markdown_sections.py` (`build_codex_prompt(...)`)
- `app/append_workflow.py` (`append_response(...)`)
- `app/file_context.py` (Extraktion/Auflösung/Validierung/Formatierung)
