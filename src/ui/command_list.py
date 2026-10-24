from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QPoint,
    QPointF,
    QRect,
    QSignalBlocker,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from src.database.models import Command, StatusKind
from src.styles import theme

COMMAND_ROLE = Qt.ItemDataRole.UserRole


class CommandListModel(QAbstractListModel):
    """Listenmodell für Befehle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._commands: list[Command] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self._commands)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._commands):
            return None
        cmd = self._commands[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return cmd.title
        if role == Qt.ItemDataRole.ToolTipRole:
            return cmd.description or cmd.command
        if role == COMMAND_ROLE:
            return cmd
        return None

    def set_commands(self, commands: list[Command]) -> None:
        self.beginResetModel()
        self._commands = list(commands)
        self.endResetModel()

    def get_command(self, index: QModelIndex) -> Command | None:
        if index.isValid() and 0 <= index.row() < len(self._commands):
            return self._commands[index.row()]
        return None

    def row_of(self, command_id: int) -> int:
        for row, cmd in enumerate(self._commands):
            if cmd.id == command_id:
                return row
        return -1


class CommandListDelegate(QStyledItemDelegate):
    """Zeichnet einen Befehl als Karte: Titel, Status, Befehlsvorschau und Tags."""

    ITEM_HEIGHT = 72
    PADDING = 12

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), self.ITEM_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        cmd: Command | None = index.data(COMMAND_ROLE)
        if cmd is None:
            return

        colors = theme.get_theme_colors()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        card = option.rect.adjusted(4, 2, -4, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected:
            painter.setBrush(QColor(colors["bg_selected"]))
            painter.setPen(QColor(colors["accent"]))
        elif hovered:
            painter.setBrush(QColor(colors["bg_hover"]))
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setBrush(QColor(colors["bg_surface"]))
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(card, 8, 8)

        inner = card.adjusted(self.PADDING, 8, -self.PADDING, -8)

        # Status-Punkt rechts oben
        dot_color = self._status_color(cmd.status_kind, colors)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot_color)
        dot_center = QPointF(inner.right() - 5, inner.top() + 9)
        painter.drawEllipse(dot_center, 5, 5)

        # Titel
        title_font = QFont(option.font)
        title_font.setBold(True)
        title_font.setPixelSize(14)
        painter.setFont(title_font)
        painter.setPen(QColor(colors["text_primary"]))
        title_rect = QRect(inner.left(), inner.top(), inner.width() - 20, 20)
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            QFontMetrics(title_font).elidedText(
                cmd.title, Qt.TextElideMode.ElideRight, title_rect.width()
            ),
        )

        # Befehlsvorschau (erste Zeile)
        mono = QFont("monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPixelSize(12)
        painter.setFont(mono)
        painter.setPen(QColor(colors["text_secondary"]))
        first_line = cmd.command.strip().splitlines()[0] if cmd.command.strip() else ""
        cmd_rect = QRect(inner.left(), inner.top() + 22, inner.width(), 16)
        painter.drawText(
            cmd_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            QFontMetrics(mono).elidedText(
                first_line, Qt.TextElideMode.ElideRight, cmd_rect.width()
            ),
        )

        # Tags
        if cmd.tags:
            small = QFont(option.font)
            small.setPixelSize(11)
            painter.setFont(small)
            painter.setPen(QColor(colors["text_muted"]))
            tags_text = "  ".join(f"#{tag}" for tag in cmd.tags)
            tags_rect = QRect(inner.left(), inner.top() + 40, inner.width(), 14)
            painter.drawText(
                tags_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                QFontMetrics(small).elidedText(
                    tags_text, Qt.TextElideMode.ElideRight, tags_rect.width()
                ),
            )

        painter.restore()

    @staticmethod
    def _status_color(kind: StatusKind, colors: dict) -> QColor:
        key = {
            StatusKind.SUCCESS: "success",
            StatusKind.ERROR: "error",
            StatusKind.RUNNING: "warning",
        }.get(kind, "text_muted")
        return QColor(colors[key])


class CommandList(QWidget):
    """Befehlsliste mit Auswahl-, Doppelklick- und Kontextmenü-Signalen."""

    command_selected = Signal(int)  # command_id
    command_activated = Signal(int)  # command_id (Doppelklick / Enter)
    context_menu_requested = Signal(int, QPoint)  # command_id, globale Position

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = CommandListModel(self)
        self._setup_ui()
        theme.notifier.changed.connect(lambda _name: self._list_view.viewport().update())

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._list_view = QListView()
        self._list_view.setModel(self._model)
        self._list_view.setItemDelegate(CommandListDelegate(self._list_view))
        self._list_view.setUniformItemSizes(True)
        self._list_view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._list_view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self._list_view.setMouseTracking(True)
        self._list_view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self._list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self._list_view)

        self._list_view.selectionModel().currentChanged.connect(self._on_current_changed)
        self._list_view.activated.connect(self._on_activated)
        self._list_view.doubleClicked.connect(self._on_activated)
        self._list_view.customContextMenuRequested.connect(self._on_context_menu)

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex):
        cmd = self._model.get_command(current)
        if cmd and cmd.id is not None:
            self.command_selected.emit(cmd.id)

    def _on_activated(self, index: QModelIndex):
        cmd = self._model.get_command(index)
        if cmd and cmd.id is not None:
            self.command_activated.emit(cmd.id)

    def _on_context_menu(self, position: QPoint):
        index = self._list_view.indexAt(position)
        cmd = self._model.get_command(index)
        if cmd and cmd.id is not None:
            self._list_view.setCurrentIndex(index)
            self.context_menu_requested.emit(
                cmd.id, self._list_view.viewport().mapToGlobal(position)
            )

    def set_commands(self, commands: list[Command], keep_selection_id: int | None = None):
        """Ersetzt die Liste und stellt optional die Auswahl ohne Signale wieder her."""
        with QSignalBlocker(self._list_view.selectionModel()):
            self._model.set_commands(commands)
            if keep_selection_id is not None:
                self._select_row(self._model.row_of(keep_selection_id))

    def select_command(self, command_id: int) -> None:
        """Wählt einen Befehl aus (löst ``command_selected`` aus)."""
        self._select_row(self._model.row_of(command_id))

    def clear_selection(self) -> None:
        with QSignalBlocker(self._list_view.selectionModel()):
            self._list_view.clearSelection()
            self._list_view.setCurrentIndex(QModelIndex())

    def _select_row(self, row: int) -> None:
        if row >= 0:
            self._list_view.setCurrentIndex(self._model.index(row))

    def count(self) -> int:
        return self._model.rowCount()
