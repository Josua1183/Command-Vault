import shlex
import subprocess
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CommandVault - Prototyp")
        self.resize(500, 200)

        # Zentrales Widget & Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Titel / Beschreibung
        self.label = QLabel("Gib einen Bash-Befehl ein:")
        layout.addWidget(self.label)

        # Eingabefeld für Befehle
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("z.B. notify-send 'Erfolg' 'Der Befehl lief!'")
        layout.addWidget(self.cmd_input)

        # Start-Button
        self.run_button = QPushButton("Befehl ausführen")
        self.run_button.clicked.connect(self.run_command)
        layout.addWidget(self.run_button)

        # Statusanzeige
        self.status_label = QLabel("Bereit.")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

    def run_command(self):
        command = self.cmd_input.text()
        if not command:
            self.status_label.setText("Bitte zuerst einen Befehl eingeben!")
            return

        try:
            # Sicher: Befehl wird als Argument-Liste ausgeführt, keine Shell-Injection
            args = shlex.split(command)
            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                self.status_label.setText("Erfolgreich ausgeführt! ✓")
            else:
                self.status_label.setText(f"Fehler: {result.stderr.strip()}")
        except Exception as e:
            self.status_label.setText(f"Ausnahmefehler: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
