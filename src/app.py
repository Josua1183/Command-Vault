import logging
import sys

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from src import __version__
from src.database.connection import get_db_path, init_db
from src.styles.theme import THEMES, apply_theme
from src.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("command-vault")
    app.setApplicationDisplayName("Command Vault")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("CommandVault")
    app.setStyle("Fusion")

    init_db()
    logger.info("Datenbank: %s", get_db_path())

    saved_theme = str(QSettings().value("theme", "dark"))
    apply_theme(saved_theme if saved_theme in THEMES else "dark")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
