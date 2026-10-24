"""Öffnet Befehle in einem externen Terminal-Emulator (Linux)."""

import logging
import os
import shlex
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Das Skript bekommt den eigentlichen Befehl als $1 übergeben. Dadurch sind
# keinerlei Quoting-Tricks nötig und beliebige Sonderzeichen funktionieren.
# Nach der Ausführung bleibt das Terminal offen, bis eine Taste gedrückt wird.
_WRAPPER_SCRIPT = (
    'bash -c "$1"; status=$?; '
    'printf "\\n\\033[2m[Beendet mit Exit-Code %s]\\033[0m\\n" "$status"; '
    'read -r -n 1 -s -p "Beliebige Taste drücken, um das Fenster zu schließen ..."; '
    "echo"
)


class TerminalError(Exception):
    """Wird geworfen, wenn kein Terminal gestartet werden konnte."""


@dataclass(frozen=True)
class TerminalSpec:
    """Beschreibt, wie ein bestimmtes Terminal aufgerufen wird."""

    binary: str
    build_args: Callable[[str, list[str]], list[str]]
    """(Arbeitsverzeichnis, Programm + Argumente) -> vollständige argv-Liste."""


def _spec(binary: str, builder: Callable[[str, list[str]], list[str]]) -> TerminalSpec:
    return TerminalSpec(binary, builder)


TERMINALS: list[TerminalSpec] = [
    _spec("konsole", lambda wd, argv: ["konsole", "--workdir", wd, "-e", *argv]),
    _spec(
        "gnome-terminal",
        lambda wd, argv: ["gnome-terminal", f"--working-directory={wd}", "--", *argv],
    ),
    _spec(
        "ptyxis",
        lambda wd, argv: ["ptyxis", "--new-window", "--working-directory", wd, "--", *argv],
    ),
    _spec(
        "xfce4-terminal",
        lambda wd, argv: ["xfce4-terminal", f"--working-directory={wd}", "-x", *argv],
    ),
    _spec(
        "terminator",
        lambda wd, argv: ["terminator", f"--working-directory={wd}", "-x", *argv],
    ),
    _spec(
        "tilix",
        lambda wd, argv: ["tilix", f"--working-directory={wd}", "-e", shlex.join(argv)],
    ),
    _spec("alacritty", lambda wd, argv: ["alacritty", "--working-directory", wd, "-e", *argv]),
    _spec("kitty", lambda wd, argv: ["kitty", "--directory", wd, *argv]),
    _spec("foot", lambda wd, argv: ["foot", "--working-directory", wd, *argv]),
    _spec("wezterm", lambda wd, argv: ["wezterm", "start", "--cwd", wd, "--", *argv]),
    _spec("xterm", lambda wd, argv: ["xterm", "-e", *argv]),
    _spec("x-terminal-emulator", lambda wd, argv: ["x-terminal-emulator", "-e", *argv]),
]

# Bevorzugtes Terminal je Desktop-Umgebung.
_DESKTOP_PREFERENCE = {
    "kde": "konsole",
    "gnome": "gnome-terminal",
    "xfce": "xfce4-terminal",
}


def build_wrapped_argv(command: str) -> list[str]:
    """Baut die argv-Liste, die den Befehl ausführt und das Terminal offen hält."""
    return ["bash", "-c", _WRAPPER_SCRIPT, "command-vault", command]


def _ordered_terminals() -> list[TerminalSpec]:
    """Terminals in Prioritätsreihenfolge ($TERMINAL, Desktop, Rest)."""
    by_binary = {spec.binary: spec for spec in TERMINALS}
    preferred: list[str] = []

    env_terminal = os.environ.get("TERMINAL", "").strip()
    if env_terminal:
        preferred.append(os.path.basename(shlex.split(env_terminal)[0]))

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    for key, binary in _DESKTOP_PREFERENCE.items():
        if key in desktop:
            preferred.append(binary)

    ordered = [by_binary[b] for b in preferred if b in by_binary]
    ordered.extend(spec for spec in TERMINALS if spec not in ordered)
    return ordered


def find_terminal() -> TerminalSpec | None:
    """Liefert das erste auf dem System verfügbare Terminal."""
    for spec in _ordered_terminals():
        if shutil.which(spec.binary):
            return spec
    return None


def launch_in_terminal(command: str, working_directory: str = "") -> str:
    """Startet ``command`` in einem neuen Terminal-Fenster.

    Gibt den Namen des verwendeten Terminals zurück.
    Wirft ``TerminalError``, wenn nichts gestartet werden konnte.
    """
    work_dir = os.path.expanduser(working_directory) if working_directory else os.getcwd()
    if not os.path.isdir(work_dir):
        raise TerminalError(f"Arbeitsverzeichnis existiert nicht: {work_dir}")

    spec = find_terminal()
    if spec is None:
        raise TerminalError(
            "Kein Terminal-Emulator gefunden (z. B. konsole, gnome-terminal, xterm)."
        )

    argv = spec.build_args(work_dir, build_wrapped_argv(command))
    env = {**os.environ, "PWD": work_dir}
    logger.info("Starte Terminal: %s", shlex.join(argv))
    try:
        subprocess.Popen(
            argv,
            cwd=work_dir,
            env=env,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise TerminalError(f"Terminal konnte nicht gestartet werden: {exc}") from exc
    return spec.binary
