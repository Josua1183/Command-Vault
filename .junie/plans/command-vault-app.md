---
sessionId: session-261021-110435-rwk4
---

### ✓ Step 1: Projektstruktur & Datenbank-Setup
### ✓ Step 2: Service-Layer Implementierung
### ✓ Step 3: Styling & Theme-System
### ✓ Step 4: Hauptfenster & Befehlsliste
### ✓ Step 5: Befehlsdetail & Editor
### ✓ Step 6: Integration & Feinschliff
### ✓ Step 7: Kategorien & Filterung
### ✓ Step 8: Automatisierte Ausführung (Scheduler)
### ✓ Step 9: UI für Kategorien & Schedule
### ✓ Step 10: Tests & Validierung

# Requirements

### Overview & Goals
Eine moderne Desktop-App für Linux, die als zentraler Speicher für alle Ihre Befehle dient. Sie können Befehle speichern, mit Titel und Beschreibung versehen, kategorisieren, suchen und direkt ausführen – optional mit oder ohne Terminal-Fenster.

### User Stories
- Als Benutzer möchte ich Befehle mit Titel, Beschreibung und Tags speichern, um sie später schnell wiederzufinden
- Als Benutzer möchte ich Befehle nach Titel, Beschreibung oder Tags durchsuchen können
- Als Benutzer möchte ich gespeicherte Befehle direkt ausführen können
- Als Benutzer möchte ich einstellen können, ob ein Terminal-Fenster geöffnet wird oder nicht
- Als Benutzer möchte ich Befehle bearbeiten und löschen können
- Als Benutzer möchte ich den Ausführungsstatus und Ausgabe der Befehle sehen

### Functional Requirements
- **Befehlsverwaltung**: CRUD-Operationen (Create, Read, Update, Delete) für Befehle
- **Befehlsattribute**: Titel, Befehl, Beschreibung, Tags, Ausführungsverzeichnis, Terminal-Option
- **Suche & Filterung**: Echtzeit-Suche über alle Felder
- **Befehlsausführung**: Ausführung mit/ohne Terminal, Ausgabe-Anzeige, Status-Tracking
- **Kategorisierung**: Tags für Befehle, Filterung nach Tags
- **Modernes UI**: Dark/Light Mode, responsive Layout, intuitive Navigation

### Non-Functional Requirements
- **Plattform**: Linux (primär), potenziell cross-platform
- **Performance**: Schnelle Suche auch bei hunderten Befehlen
- **Persistenz**: SQLite-Datenbank für alle Daten
- **Design**: Modernes, sauberes Design mit konsistentem Styling


# Technical Design

### Current Implementation
- `pyproject.toml`: PySide6 ≥6.12.0, Python ≥3.14
- `commands.db`: SQLite mit Schema (`id`, `title`, `command`, `last_status`)
- `main.py`, `main.qml`: Leere Dateien

### Key Decisions
- **PySide6 mit QWidgets** (nicht QML): Bessere Kontrolle über komplexe UI-Elemente, etablierte Patterns, einfachere Integration von Custom Widgets
- **Model-View-Architektur**: Trennung von Daten (Model), Darstellung (View) und Logik (Controller/ViewModel)
- **QSS Styling**: CSS-ähnliches Styling für konsistentes, modernes Design
- **SQLite mit sqlite3**: Keine zusätzlichen Dependencies, eingebaut in Python
- **Projektstruktur**: Modularer Aufbau mit klarer Trennung von concerns

### Proposed Changes

#### Projektstruktur
```
command-vault/
├── main.py                      # Entry point
├── pyproject.toml               # Dependencies
├── commands.db                  # SQLite database
├── src/
│   ├── __init__.py
│   ├── app.py                   # QApplication setup
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py        # DB-Verbindung, Migration
│   │   └── models.py            # Command-Modell
│   ├── services/
│   │   ├── __init__.py
│   │   ├── command_service.py   # CRUD-Logik für Befehle
│   │   └── executor_service.py  # Befehlsausführung
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py       # Hauptfenster
│   │   ├── command_list.py      # Befehlsliste (ListView)
│   │   ├── command_detail.py    # Befehlsdetail-Panel
│   │   ├── command_editor.py    # Editor-Dialog
│   │   ├── search_bar.py        # Suchleiste
│   │   └── output_panel.py      # Ausgabe-Panel
│   └── styles/
│       ├── __init__.py
│       ├── theme.py             # Theme-Management
│       └── styles.qss           # QSS-Stylesheet
└── resources/
    └── icons/                   # Icons, wenn benötigt
```

#### Datenbank-Schema (erweitert)
```
commands (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    command TEXT NOT NULL,
    description TEXT,
    working_directory TEXT,
    tags TEXT,                  # JSON-Array als String
    open_terminal BOOLEAN DEFAULT 1,
    last_status TEXT,
    last_output TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
```

#### Architektur
- **Database Layer**: `connection.py` verwaltet die Verbindung und Migrationen, `models.py` definiert das Command-Objekt
- **Service Layer**: `command_service.py` für CRUD, `executor_service.py` für Befehlsausführung (mit QProcess)
- **UI Layer**: MainWindow als Container, CommandList für die Liste, CommandDetail für Details, CommandEditor für Bearbeitung
- **Styling**: Zentrales QSS-Stylesheet mit Dark/Light Theme Support

### Components

#### MainWindow
- Splitter-Layout: Links Befehlsliste, rechts Detail/Editor
- Toolbar mit Suchleiste und Aktionen
- Statusbar

#### CommandList
- QListView mit Custom Delegate für modernes Rendering
- Filterung nach Suche und Tags
- Sortierung (alphabetisch, nach Datum)

#### CommandDetail
- Anzeige von Titel, Beschreibung, Tags
- Befehls-Preview (Code-Block)
- Ausführungs-Button
- Ausgabe-Panel (wenn kein Terminal)

#### CommandEditor
- Dialog für Erstellen/Bearbeiten
- Felder: Titel, Befehl, Beschreibung, Working Directory, Tags, Terminal-Option
- Validierung

#### ExecutorService
- QProcess für Befehlsausführung
- Optional: Terminal öffnen (xdg-open, x-terminal-emulator)
- Ausgabe erfassen und zurückgeben
- Timeout-Handling

### Risks
- **Terminal-Integration**: Verschiedene Terminals auf Linux haben unterschiedliche CLI-Optionen → Fallback-Mechanismus nötig
- **Lange Befehle**: Ausgabe-Panel muss mit großer Ausgabe umgehen → Scrollen, Limitierung
- **Sicherheit**: Ausführung von Befehlen mit potenziell gefährlichen Kommandos → Bestätigung bei gefährlichen Patterns (sudo, rm -rf, etc.)


# Testing

### Validation Approach
Manuelle Validierung der Kernfunktionen nach Implementierung.

### Key Scenarios
- **Befehl erstellen**: Neuer Befehl mit allen Attributen wird gespeichert und in der Liste angezeigt
- **Befehl bearbeiten**: Änderungen werden persistiert
- **Befehl löschen**: Befehl wird entfernt, Datenbank aktualisiert
- **Suche**: Filterung funktioniert in Echtzeit, Ergebnisse sind korrekt
- **Ausführung mit Terminal**: Terminal öffnet sich, Befehl wird ausgeführt
- **Ausführung ohne Terminal**: Ausgabe wird im Panel angezeigt, Status aktualisiert
- **Theme-Wechsel**: Dark/Light Mode funktioniert konsistent

### Edge Cases
- Leere Befehle oder Titel
- Sehr lange Befehle oder Ausgabe
- Befehle mit Sonderzeichen
- Datenbank-Migration von altem Schema
- Gleichzeitige Suche während der Ausführung
