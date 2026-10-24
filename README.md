# Command Vault

Moderne Desktop-App (PySide6) zum Speichern, Durchsuchen und Ausführen von Shell-Befehlen –
wahlweise in einem Terminal-Fenster oder direkt in der App mit Live-Ausgabe.

## Starten

```bash
uv sync
uv run python main.py
```

## Tests & Linting

```bash
uv run pytest
uv run ruff check .
```

## Projektstruktur

```
main.py                     Einstiegspunkt
src/app.py                  QApplication-Setup (Theme, Logging, DB)
src/database/               SQLite-Verbindung, Migration, Datenmodell
src/services/               CommandService (CRUD/Suche), ExecutorService (QProcess),
                            terminal_launcher (Terminal-Emulatoren)
src/ui/                     Hauptfenster, Liste, Detail, Editor, Ausgabe, Suche
src/styles/                 Theme-Verwaltung + styles.qss (Template)
tests/                      pytest (läuft headless mit QT_QPA_PLATFORM=offscreen)
```

## Daten

Die Datenbank liegt in `~/.local/share/command-vault/commands.db`
(überschreibbar mit `COMMAND_VAULT_DB=/pfad/zur.db`). Eine vorhandene `commands.db` im
Projektordner wird beim ersten Start dorthin übernommen (Kopie).

## Terminal-Unterstützung

konsole, gnome-terminal, ptyxis, xfce4-terminal, terminator, tilix, alacritty, kitty, foot,
wezterm, xterm, x-terminal-emulator. Über `$TERMINAL` lässt sich ein bevorzugtes Terminal wählen.
