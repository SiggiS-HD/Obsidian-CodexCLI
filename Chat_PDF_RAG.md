# Chat PDF RAG (Phase 9, v1)

## Ziel
Große PDF-Dateien sollen einmalig lokal indexiert und danach über viele Prompts effizient abgefragt werden, ohne den Volltext in den Prompt zu packen.

Kurz: einmal extrahieren + chunken + indexieren, danach pro Frage nur Top-Treffer als Kontext senden.

## Begriffe in 60 Sekunden
- Chunking: Zerlegung des extrahierten PDF-Texts in kleine, suchbare Textstücke (Chunks).
- Retrieval: Suche nach den relevantesten Chunks für die aktuelle Frage.
- RAG: Kombination aus Retrieval + LLM-Antwort auf Basis der gefundenen Chunks.
- Quellen-Zitation: Jeder Chunk trägt Seite und Dokumentherkunft, damit Antworten "Seite X" referenzieren können.

## v1 Pipeline

### 1) Index-Build (einmalig oder bei PDF-Änderung)
1. PDF öffnen (lokal oder UNC/NAS).
2. Pro Seite Text extrahieren.
3. Text normalisieren (Whitespace, Steuerzeichen, harte Trennartefakte entschärfen).
4. In reproduzierbare Chunks teilen.
5. Chunks und Metadaten im lokalen Index speichern.

### 2) Query-Time (bei jedem append)
1. Query = aktueller Prompttext.
2. Top-N Chunks per FTS5/BM25 aus dem Index abrufen.
3. Treffer auf ein Gesamtzeichenlimit begrenzen.
4. Quellenblock mit Seitenangaben erzeugen.
5. Nur Prompt + Quellenblock an Codex schicken.

## Prompt-Limits (v1)
Die Werte sind bewusst konservativ und können später als Config rausgezogen werden.

- `RAG_TOP_K = 10`
- `RAG_MAX_CONTEXT_CHARS = 18000`
- `RAG_CHUNK_TARGET_CHARS = 1200`
- `RAG_CHUNK_OVERLAP_CHARS = 120`

Verhalten bei Limits:
- Es werden nur so viele Top-Treffer verwendet, wie innerhalb `RAG_MAX_CONTEXT_CHARS` passen.
- Treffer außerhalb des Limits werden verworfen (deterministisch nach Ranking-Reihenfolge).

## Datenmodell (v1)

Empfehlung: SQLite + FTS5.

### Tabelle `documents`
- `doc_id` (TEXT, PK): stabile Dokument-ID.
- `source_path` (TEXT): normalisierter Originalpfad.
- `size_bytes` (INTEGER): Dateigröße.
- `mtime_utc` (TEXT): Last-Modified-Zeit (UTC).
- `hash` (TEXT): Inhalts- oder Signaturhash zur Änderungsprüfung.
- `indexed_at_utc` (TEXT): Zeitpunkt der letzten Indexierung.

### Tabelle `chunks`
- `doc_id` (TEXT, FK -> documents.doc_id)
- `page` (INTEGER): 1-basierte Seitennummer.
- `chunk_index` (INTEGER): Reihenfolge innerhalb des Dokuments.
- `text` (TEXT): Chunk-Inhalt.
- `char_count` (INTEGER): Länge des Chunks.
- `text_hash` (TEXT): optional für Debug/Dedup.

Primärschlüssel-Empfehlung: `(doc_id, chunk_index)`

### FTS5 Index
Virtuelle Tabelle für `chunks.text`, verknüpft mit `doc_id`, `page`, `chunk_index`.

## Dokument-ID und Rebuild-Regel

Stabile ID für lokale + UNC-Pfade:
- `doc_id = sha256(normalized_path + "|" + size_bytes + "|" + mtime_utc)`

Normalisierung für `normalized_path`:
- Pfad vor dem Hashen in eine kanonische Stringform bringen.
- Auf Windows Laufwerksbuchstaben vereinheitlichen und Backslashes konsistent behandeln.
- Für UNC-Pfade den vollständigen `\\server\share\...`-Pfad beibehalten, damit keine Kollision mit lokalen Pfaden entsteht.

Rebuild notwendig, wenn mindestens eines gilt:
- `size_bytes` geändert
- `mtime_utc` geändert
- optional: Inhalts-Hash geändert

## Cache-Root / NAS-Strategie (v1)

### Entscheidung
- Default-Indexpfad: `<vault_root>\.codexcli\index\`
- Konfigurations-Override: `CODEXCLI_INDEX_ROOT`
- Sidecar neben der PDF bleibt vorerst bewusst außen vor.
- Ein lokaler Override ist erlaubt, wenn ein NAS für häufige Rebuilds zu langsam ist.

### Warum dieser Default?
- Der Index bleibt beim Vault und ist damit in derselben Ablagestruktur wie die referenzierten Notizen/PDFs.
- UNC-/NAS-Setups werden nicht durch lokale Benutzerprofile versteckt oder fragmentiert.
- Die Implementierung bleibt v1-seitig einfach: ein Root, darunter dokumentbezogene Indexdaten.

### Verhalten bei NAS-/UNC-Problemen
- Ist PDF oder Index-Root nicht erreichbar, gibt es eine klare Fehlermeldung.
- Es gibt kein stilles Fallback auf einen anderen Speicherort.
- Ein automatischer Rebuild wird in diesem Zustand nicht versucht.

### Locking / parallele Builds
- v1 verwendet ein einfaches Lockfile im Dokument-Indexordner.
- Solange das Lock aktiv ist, startet kein zweiter Build für dasselbe Dokument.
- Verwaiste Locks werden später mit Timestamp-/Ablaufregel behandelt; für Schritt 2 reicht die Festlegung des Konzepts.

## Retrieval-Strategie v1

### Entscheidung
v1 verwendet lexikalisches Retrieval mit SQLite FTS5 (BM25-Style Ranking).

### Warum v1 so?
- Keine zusätzliche API nötig.
- Schnell implementierbar.
- Transparentes, gut debuggbares Ranking.
- Geringe Abhängigkeiten und Kosten.

### v2 Option
Embeddings-Retrieval für bessere semantische Trefferqualität, aber mit zusätzlicher Komplexität/Kosten.

## Quellenformat für den finalen Prompt

Jeder Treffer wird als eindeutiger Quellenblock serialisiert.

Empfohlenes Format:

```text
[PDF-Quelle 1]
Dokument: <basename.pdf>
Pfad: <normalized path>
Seite: 123
Chunk: 45
Score: <optional bm25>
Text:
<chunk text>
```

Zitationsziel in Antworten:
- `Seite <n>` muss direkt aus dem Quellenblock ableitbar sein.
- Optional zusätzlich `Chunk <k>` für interne Nachvollziehbarkeit.

## Fehlerfälle (v1)
- PDF nicht erreichbar (lokal/UNC): klare Fehlermeldung, kein stilles Fallback.
- Index fehlt: Hinweis "Bitte zuerst indexieren" (oder später optional Auto-Build).
- 0 Treffer: Hinweis "Keine relevanten Treffer, Prompt präzisieren".
- FTS/DB-Fehler: technischer Fehlerblock mit kurzem Handlungs-Hinweis.

## Abgrenzung zu bestehenden Flows
- Bestehende Dateireferenzen bleiben unverändert.
- Phase 9 betrifft nur den Umgang mit großen PDFs via Retrieval statt Volltext-Einbettung.
- Beim Index-Build werden neben dem Seitentext auch PDF-Linkannotationen mit `URI` pro Seite übernommen.
- Dadurch koennen z.B. im PDF eingebettete Video-Links, auch wenn sie visuell ueber QR-Codes praesentiert werden, im RAG-Index auffindbar werden.
- OCR/Bild-PDF ist in Phase 9 v1 nicht Kernziel; bestehende OCR-Logik bleibt separat.
- Wenn der bestehende OCR-Fallback anspringt, rendert er Seiten nur temporär in ein Verzeichnis aus dem System-Temp-Ordner.
- Auf Windows ist das typischerweise `%TEMP%`, z.B. `C:\Users\<Name>\AppData\Local\Temp\codexcli-ocr-*`.
- Diese Render-Dateien sind reine Laufzeit-Artefakte und werden nach dem OCR-Lauf automatisch gelöscht.

## Ergebnis von Schritt 1
Mit dieser Notiz sind für Phase 9 Schritt 1 festgelegt:
- Pipeline und Limits
- Datenmodell
- Retrieval-Strategie v1
- Quellen-/Zitationsformat
