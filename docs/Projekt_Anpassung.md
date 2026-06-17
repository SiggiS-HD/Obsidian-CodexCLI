
Ich denke, dass ich bei der Definition des Leistungsumfangs für das Projekt **Codex CLI Anbindung an das OpenAI LLM** nicht genau genug war.

Aktuell realisieren wir das jeder Prompt-Kontext um die Inhalte der angefügten Dateien erweitert wird und die angefügten Dateien können ebenfalls Arbeitsanweisungen für das LLM enthalten.

Die meisten meiner Anwendungsfälle sind jedoch viel einfacher. Die angefügten Dateien enthalten keine weitere Arbeitsanweisungen, sondern sollen einfach nur vom LLM, auch durch Tools die dem LLM zur Verfügung stehen, verarbeitet werden.

Beispiel:
> Lies das angefügte PDF Dokument, erstelle eine Zusammenfassung und schlage die nächsten sinnvollen Arbeitsschritte vor.

oder
> Das angefügte PDF Dokument wurde gescannt und soll nun in editierbaren Text in ein Markdown Dokument umgewandelt werden. Dabei sollen Formatierungen, wie Überschriften, Zeilenumbrüche, Tabellen und Hervorhebungen (fett) beibehalten werden.

Wenn ich so eine Anforderung an ChatGPT stelle, dann nutzt das LLM die notwendigen Tools (Scan/OCR), bearbeitet den Prompt und liefert das Ergebnis.

Können wir diese einfache Verarbeitung nicht auch über Codex CLI zur Verfügung stellen?

Die bis jetzt implementierte Aufbereitung der Quellen und die Erweiterung des Prompt-Kontext sollte als komplexere Anwendung erhalten bleiben. 

Bitte noch nichts ändern, sondern nur erläutern / diskutieren ob diese Anpassung möglich ist und wie man dies realisieren könnte.