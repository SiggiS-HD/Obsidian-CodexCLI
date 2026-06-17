# Projekt MOC

Diese Datei ist eine Vorlage für eine MOC-Datei im aktuell unterstützten Format.

Wichtig:
- Die Überschrift enthält das Wort `MOC`, damit die Datei als MOC erkannt wird.
- Verarbeitet werden nur einfache nummerierte Listen.
- Pro Listeneintrag ist genau eine Dateireferenz erlaubt.
- Unterstützt sind Obsidian-WikiLinks auf `.md` sowie Markdown-Links auf `.md` und `.txt`.

## Beispiel-Steuerliste

1. [[TASKS]]
2. [[TESTING]]
3. [Hinweise](hinweise.txt)

## Hinweise zur Verwendung

Unterstützt:

```md
1. [[TASKS]]
2. [[Ordner/Projektstand]]
3. [[Projektstand|Alias]]
4. [Hinweise](hinweise.txt)
5. [Dokument](docs/projekt.md)
```

Nicht unterstützt:

```md
- [[TASKS]]
1. [[TASKS]] und [[TESTING]]
1. [Datei](a.md) [Datei](b.md)
1. C:\Pfad\datei.md
1. [[AndereMOC]]
   1. [[Unterpunkt]]
```

## Eigene Liste

1. [[ErsteDatei]]
2. [[ZweiteDatei]]
3. [DritteDatei](pfad/zur/datei.txt)
