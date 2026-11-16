import json
import logging
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .domain import Cancelled, Settings, file_size, timestamp
from .engine import Transcriber

logger = logging.getLogger(__name__)

FILE_FILTER = (
    "Аудио и видео (*.mkv *.mp4 *.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.webm "
    "*.mov *.avi *.wma *.wmv *.m4v *.mpeg *.mpg *.ts *.mts *.m2ts *.aiff *.amr);;Все файлы (*)"
)

STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 13px; color: #243247; }
QMainWindow, QWidget#content { background: #f4f6f9; }
QFrame#sidebar { background: #182333; border: none; }
QLabel#brand { color: #ffffff; font-size: 19px; font-weight: 700; }
QLabel#sideTitle { color: #f0f4fa; font-weight: 600; }
QLabel#sideNote { color: #a8b6ca; font-size: 12px; }
QLabel#title { font-size: 30px; font-weight: 700; color: #172333; }
QLabel#subtitle, QLabel#muted { color: #68768a; }
QLabel#eyebrow { color: #4a7b6a; font-size: 11px; font-weight: 700; }
QFrame#card { background: white; border: 1px solid #e1e6ee; border-radius: 12px; }
QFrame#drop { background: #fcfdff; border: 2px dashed #c1ccdb; border-radius: 12px; }
QFrame#drop[hover="true"] { background: #fff3e9; border-color: #db7837; }
QLabel#dropTitle { font-size: 18px; font-weight: 600; }
QLabel#sectionTitle { font-size: 14px; font-weight: 700; }
QLabel#fieldLabel { color: #68768a; font-size: 12px; }
QPushButton { background: white; border: 1px solid #d4dce7; border-radius: 7px; padding: 8px 15px; font-weight: 600; }
QPushButton:hover { background: #edf1f7; border-color: #b6c3d4; }
QPushButton:disabled { color: #9da8b6; background: #f0f2f6; border-color: #e2e6ed; }
QPushButton#primary { background: #c86a2d; color: white; border: 1px solid #c86a2d; padding: 11px 25px; }
QPushButton#primary:hover { background: #ad5722; }
QPushButton#primary:disabled { background: #d9b69d; border-color: #d9b69d; }
QPushButton#textButton { background: transparent; border: none; color: #52647a; padding: 4px; }
QComboBox, QLineEdit { background: #f9fafc; border: 1px solid #dce2eb; border-radius: 6px; padding: 7px; min-height: 18px; }
QComboBox:disabled, QLineEdit:disabled { color: #9da8b6; }
QComboBox QAbstractItemView { background: white; selection-background-color: #f8e8dc; }
QComboBox::drop-down { border: none; width: 22px; }
QCheckBox { spacing: 8px; }
QTableWidget { background: white; border: none; gridline-color: #edf0f4; selection-background-color: #eef3f9; selection-color: #243247; }
QTableWidget::item { padding: 6px; border-bottom: 1px solid #edf0f4; }
QHeaderView::section { background: #f8f9fc; color: #68768a; border: none; padding: 7px; font-size: 11px; font-weight: 600; }
QPlainTextEdit { background: white; border: none; font-size: 13px; padding: 5px; selection-background-color: #f8e8dc; }
QProgressBar { border: none; border-radius: 4px; background: #e7ecf3; min-height: 7px; max-height: 7px; }
QProgressBar::chunk { background: #c86a2d; border-radius: 4px; }
QToolTip { background: #182333; color: white; border: none; padding: 7px; }
"""


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


class WaveMark(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(44, 42)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#e9985c"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for x, height in zip((5, 13, 21, 29, 37), (9, 20, 32, 20, 9)):
            painter.drawLine(x, (42 - height) // 2, x, (42 + height) // 2)


class DropZone(QFrame):
    files_dropped = Signal(list)
    browse_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        self.setMinimumHeight(150)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for text, name in (
            ("Перетащите аудио или видео", "dropTitle"),
            ("MKV, MP4, MP3, WAV и другие форматы", "muted"),
        ):
            item = label(text, name)
            item.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(item)
        button = QPushButton("Выбрать файлы")
        button.setFixedWidth(165)
        button.clicked.connect(self.browse_clicked)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignHCenter)

    def set_hover(self, hover):
        self.setProperty("hover", hover)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event):
        if self.isEnabled() and event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
            self.set_hover(True)

    def dragLeaveEvent(self, event):
        self.set_hover(False)

    def dropEvent(self, event):
        self.set_hover(False)
        if self.isEnabled():
            self.files_dropped.emit([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()


class BatchWorker(QThread):
    state = Signal(int, str)
    status = Signal(str)
    progress = Signal(float, object)
    preview = Signal(str)
    result = Signal(int, str)
    failure = Signal(int, str)
    current_file = Signal(int, str)

    def __init__(self, jobs, output_dir, data_dir, settings):
        super().__init__()
        self.jobs, self.output_dir, self.data_dir, self.settings = jobs, output_dir, data_dir, settings
        self.cancel_event = threading.Event()
        self.was_cancelled = False
        self.error_count = 0

    def run(self):
        engine = Transcriber(self.data_dir, self.settings, self.cancel_event.is_set, self.status.emit)
        try:
            self.run_jobs(engine)
        finally:
            engine.close()

    def run_jobs(self, engine):
        for row, path in self.jobs:
            if self.cancel_event.is_set():
                self.was_cancelled = True
                break
            self.current_file.emit(row, path.name)
            self.state.emit(row, "Обработка")
            try:
                target = engine.run_file(
                    path, self.output_dir, self.progress.emit,
                    lambda segment: self.preview.emit(f"[{timestamp(segment.start)}]  {segment.text}"),
                )
                self.result.emit(row, str(target))
                self.state.emit(row, "Готово")
            except Cancelled:
                self.was_cancelled = True
                self.state.emit(row, "Остановлено")
                break
            except Exception as exc:
                logger.exception("Transcription failed: %s", path)
                self.error_count += 1
                self.state.emit(row, "Ошибка")
                self.failure.emit(row, friendly_error(exc))
        self.was_cancelled = self.was_cancelled or self.cancel_event.is_set()


class GpuProbeSignals(QObject):
    ready = Signal(list, str)


class GpuProbe(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = GpuProbeSignals()

    def run(self):
        from .vulkan import list_devices
        try:
            self.signals.ready.emit(list_devices(), "")
        except Exception as exc:
            self.signals.ready.emit([], str(exc))


def friendly_error(exc: Exception) -> str:
    details = str(exc)
    lowered = details.lower()
    if "vulkan" in lowered:
        return "Не удалось использовать AMD / Intel GPU. Обновите драйвер видеокарты или выберите процессор (CPU).\n\n" + details
    if "cuda" in lowered or "cudnn" in lowered or "cublas" in lowered:
        return "Не удалось использовать NVIDIA GPU. Выберите процессор (CPU) и повторите.\n\n" + details
    if any(word in lowered for word in ("huggingface", "connection", "network", "connecterror", "couldn't connect")):
        return "Не удалось загрузить модель. Проверьте интернет и доступ к huggingface.co, затем повторите.\n\n" + details
    if isinstance(exc, PermissionError):
        return "Нет доступа к файлу или папке. Закройте документ в Word и выберите доступную папку.\n\n" + details
    return details or type(exc).__name__


class MainWindow(QMainWindow):
    def __init__(self, app_dir: Path, data_dir: Path):
        super().__init__()
        self.app_dir, self.data_dir = app_dir, data_dir
        self.paths: list[Path] = []
        self.results: dict[int, Path] = {}
        self.errors: dict[int, str] = {}
        self.worker = None
        self.close_when_done = False
        self.preferences = self.read_preferences()
        self.output_dir = Path(self.preferences.get("output_dir", str(app_dir / "results")))
        self.setWindowTitle("Транскрибер · аудио и видео в Word")
        self.resize(1190, 860)
        self.setMinimumSize(1020, 740)
        self.setAcceptDrops(True)
        self.build_ui()
        self.restore_preferences()
        self.update_buttons()
        self.gpu_probe = GpuProbe()
        self.gpu_probe.signals.ready.connect(self.show_gpu_devices)
        QThreadPool.globalInstance().start(self.gpu_probe)

    def show_gpu_devices(self, devices, error):
        if self.is_busy():
            return
        selected = self.device.currentData()
        preferred = self.preferences.get("device", selected)
        for index in reversed(range(self.device.count())):
            if str(self.device.itemData(index)).startswith("vulkan:"):
                self.device.removeItem(index)
        if devices:
            for device in devices:
                self.device.addItem(f"{device['name']} · Vulkan", f"vulkan:{device['index']}")
        else:
            self.device.addItem("AMD / Intel GPU · Vulkan", "vulkan:0")
            self.device.setItemData(self.device.count() - 1, error or "Совместимые Vulkan GPU не найдены", Qt.ItemDataRole.ToolTipRole)
        index = self.device.findData(preferred if str(preferred).startswith("vulkan:") else selected)
        if index >= 0:
            self.device.setCurrentIndex(index)

    def read_preferences(self):
        try:
            value = json.loads((self.data_dir / "settings.json").read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_preferences(self):
        preferences = {
            "output_dir": str(self.output_dir), "model": self.quality.currentData(),
            "device": self.device.currentData(), "audio_track": self.track.currentData(),
            "timestamps": self.timestamps.isChecked(),
        }
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            (self.data_dir / "settings.json").write_text(json.dumps(preferences, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            logger.exception("Could not save preferences")

    def restore_preferences(self):
        for widget, key in ((self.quality, "model"), (self.device, "device"), (self.track, "audio_track")):
            index = widget.findData(self.preferences.get(key))
            if index >= 0:
                widget.setCurrentIndex(index)
        self.timestamps.setChecked(self.preferences.get("timestamps", True))

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(174)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 27, 18, 24)
        side.setSpacing(13)
        side.addWidget(WaveMark())
        side.addWidget(label("Транскрибер", "brand"))
        side.addWidget(label("ИЗ ЗВУКА В ТЕКСТ", "sideNote"))
        side.addSpacing(38)
        for title, note in (("01   Добавьте запись", "Аудио или видео"), ("02   Распознайте", "Русская речь"), ("03   Откройте Word", "Готовый .docx")):
            side.addWidget(label(title, "sideTitle"))
            side.addWidget(label(note, "sideNote"))
            side.addSpacing(15)
        side.addStretch()
        side.addWidget(label("Локальная\nобработка", "sideTitle", True))
        side.addWidget(label("Записи остаются\nна вашем компьютере.", "sideNote", True))
        side.addSpacing(10)
        side.addWidget(label("WINDOWS  ·  v1.1", "sideNote"))
        outer.addWidget(sidebar)
        content = QWidget()
        content.setObjectName("content")
        main = QVBoxLayout(content)
        main.setContentsMargins(28, 23, 28, 23)
        main.setSpacing(15)
        main.addWidget(label("АУДИО И ВИДЕО → WORD", "eyebrow"))
        main.addWidget(label("Пусть запись станет текстом", "title"))
        main.addWidget(label("Расшифровка русской речи. Большие файлы — небольшими фрагментами.", "subtitle"))
        body = QHBoxLayout()
        body.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(13)
        self.drop = DropZone()
        self.drop.files_dropped.connect(self.add_files)
        self.drop.browse_clicked.connect(self.browse)
        left.addWidget(self.drop)
        queue_card = QFrame()
        queue_card.setObjectName("card")
        queue_layout = QVBoxLayout(queue_card)
        queue_layout.setContentsMargins(13, 13, 13, 9)
        queue_heading = QHBoxLayout()
        queue_heading.addWidget(label("Очередь файлов", "sectionTitle"))
        queue_heading.addStretch()
        self.queue_count = label("0 файлов", "muted")
        queue_heading.addWidget(self.queue_count)
        queue_layout.addLayout(queue_heading)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ФАЙЛ", "ОБЪЁМ", "СТАТУС"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(115)
        self.table.setShowGrid(False)
        self.table.itemDoubleClicked.connect(self.open_row)
        queue_layout.addWidget(self.table)
        self.empty_hint = label("Добавьте одну запись или несколько сразу.", "muted")
        queue_layout.addWidget(self.empty_hint)
        left.addWidget(queue_card, 1)
        body.addLayout(left, 6)
        options_card = QFrame()
        options_card.setObjectName("card")
        options_card.setFixedWidth(290)
        options = QVBoxLayout(options_card)
        options.setContentsMargins(18, 17, 18, 17)
        options.setSpacing(8)
        options.addWidget(label("Настройки расшифровки", "sectionTitle"))
        self.quality = QComboBox()
        for title, value in (("Быстро · base", "base"), ("Баланс · small", "small"), ("Точнее · medium", "medium"), ("Максимум · large-v3", "large-v3")):
            self.quality.addItem(title, value)
        self.quality.setCurrentIndex(1)
        self.device = QComboBox()
        self.device.addItem("Процессор (CPU)", "cpu")
        self.device.addItem("Видеокарта NVIDIA (CUDA)", "cuda")
        self.device.addItem("AMD / Intel GPU · Vulkan", "vulkan:0")
        self.device.setToolTip("AMD и Intel: Vulkan и актуальный драйвер видеокарты. NVIDIA: CUDA/cuDNN. CPU работает без GPU.")
        self.track = QComboBox()
        self.track.addItem("Русская, иначе первая", None)
        for number in range(1, 17):
            self.track.addItem(f"Аудиодорожка № {number}", number - 1)
        self.track.setToolTip("Для MKV с несколькими озвучками. Если метки языка нет, укажите номер дорожки.")
        for title, widget in (("Качество", self.quality), ("Обработка", self.device), ("Аудиодорожка", self.track)):
            options.addWidget(label(title, "fieldLabel"))
            options.addWidget(widget)
        self.timestamps = QCheckBox("Таймкоды в документе Word")
        self.timestamps.setChecked(True)
        options.addWidget(self.timestamps)
        options.addWidget(label("Папка с результатами", "fieldLabel"))
        folder_row = QHBoxLayout()
        self.folder = QLineEdit(str(self.output_dir))
        self.folder.setReadOnly(True)
        self.folder.setToolTip(str(self.output_dir))
        self.choose_folder_button = QPushButton("…")
        self.choose_folder_button.setFixedWidth(37)
        self.choose_folder_button.setAccessibleName("Выбрать папку с результатами")
        self.choose_folder_button.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(self.choose_folder_button)
        options.addLayout(folder_row)
        options.addWidget(label("Модель загрузится один раз. Затем распознавание работает без интернета.", "muted", True))
        options.addStretch()
        body.addWidget(options_card)
        main.addLayout(body, 4)
        progress_row = QHBoxLayout()
        self.status_label = label("Готов к работе", "sectionTitle")
        self.status_label.setWordWrap(True)
        self.time_label = label("", "muted")
        progress_row.addWidget(self.status_label, 1)
        progress_row.addWidget(self.time_label)
        main.addLayout(progress_row)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        main.addWidget(self.progress_bar)
        preview_card = QFrame()
        preview_card.setObjectName("card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(15, 12, 15, 7)
        preview_heading = QHBoxLayout()
        preview_heading.addWidget(label("Текст записи", "sectionTitle"))
        preview_heading.addStretch()
        preview_heading.addWidget(label("ПРЕДПРОСМОТР", "fieldLabel"))
        preview_layout.addLayout(preview_heading)
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumBlockCount(700)
        self.preview_text.setMinimumHeight(85)
        self.preview_text.setPlaceholderText("Здесь появится распознанный текст. Полная расшифровка сохранится в Word.")
        preview_layout.addWidget(self.preview_text)
        main.addWidget(preview_card, 2)
        actions = QHBoxLayout()
        self.remove_button = QPushButton("Убрать выбранные")
        self.remove_button.setObjectName("textButton")
        self.remove_button.clicked.connect(self.remove_selected)
        self.open_folder_button = QPushButton("Открыть папку")
        self.open_folder_button.clicked.connect(self.open_folder)
        self.stop_button = QPushButton("Остановить")
        self.stop_button.clicked.connect(self.stop)
        self.start_button = QPushButton("Распознать в Word")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.start)
        actions.addWidget(self.remove_button)
        actions.addStretch()
        actions.addWidget(self.open_folder_button)
        actions.addWidget(self.stop_button)
        actions.addWidget(self.start_button)
        main.addLayout(actions)
        outer.addWidget(content, 1)

    def dragEnterEvent(self, event):
        if not self.is_busy() and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.is_busy():
            self.add_files([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()

    def browse(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Выберите аудио или видео", "", FILE_FILTER)
        self.add_files(paths)

    def add_files(self, paths):
        if self.is_busy():
            return
        added = 0
        for raw in paths:
            path = Path(raw).resolve()
            if not path.is_file() or path in self.paths:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            row = len(self.paths)
            self.paths.append(path)
            self.table.insertRow(row)
            for column, value in enumerate((path.name, file_size(size), "В очереди")):
                item = QTableWidgetItem(value)
                item.setToolTip(str(path) if column == 0 else value)
                self.table.setItem(row, column, item)
            added += 1
        self.queue_count.setText(f"Файлов: {len(self.paths)}")
        self.empty_hint.setVisible(not self.paths)
        if added:
            self.status_label.setText("Файлы добавлены. Можно начинать.")
        self.update_buttons()

    def remove_selected(self):
        if self.is_busy():
            return
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
            self.paths.pop(row)
            self.results = {key - (key > row): value for key, value in self.results.items() if key != row}
            self.errors = {key - (key > row): value for key, value in self.errors.items() if key != row}
        self.queue_count.setText(f"Файлов: {len(self.paths)}")
        self.empty_hint.setVisible(not self.paths)
        self.update_buttons()

    def choose_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Куда сохранить документы Word?", str(self.output_dir))
        if directory:
            self.output_dir = Path(directory)
            self.folder.setText(directory)
            self.folder.setToolTip(directory)
            self.save_preferences()

    def is_busy(self):
        return self.worker is not None and self.worker.isRunning()

    def update_buttons(self):
        busy = self.is_busy()
        for widget in (self.drop, self.quality, self.device, self.track, self.timestamps, self.choose_folder_button, self.remove_button):
            widget.setEnabled(not busy)
        self.start_button.setEnabled(bool(self.paths) and not busy)
        self.stop_button.setEnabled(busy)

    def start(self):
        if self.is_busy() or not self.paths:
            return
        jobs = [(row, path) for row, path in enumerate(self.paths) if self.table.item(row, 2).text() != "Готово"]
        if not jobs:
            # A deliberate second run can export different quality/track/timestamp settings.
            jobs = list(enumerate(self.paths))
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=self.output_dir):
                pass
        except OSError as exc:
            QMessageBox.warning(self, "Папка недоступна", friendly_error(exc))
            return
        self.save_preferences()
        settings = Settings(
            model=self.quality.currentData(), device=self.device.currentData(),
            audio_track=self.track.currentData(), timestamps=self.timestamps.isChecked(),
        )
        for row, _ in jobs:
            self.results.pop(row, None)
            self.errors.pop(row, None)
            self.set_state(row, "В очереди")
        self.worker = BatchWorker(jobs, self.output_dir, self.data_dir, settings)
        self.worker.state.connect(self.set_state)
        self.worker.status.connect(self.status_label.setText)
        self.worker.progress.connect(self.show_progress)
        self.worker.preview.connect(self.preview_text.appendPlainText)
        self.worker.current_file.connect(self.show_current)
        self.worker.result.connect(self.store_result)
        self.worker.failure.connect(self.show_failure)
        self.worker.finished.connect(self.batch_finished)
        self.progress_bar.setRange(0, 0)
        self.worker.start()
        self.update_buttons()

    def show_current(self, row, name):
        self.preview_text.clear()
        self.preview_text.setPlaceholderText(f"Распознаётся: {name}")
        self.table.selectRow(row)
        self.status_label.setText(f"Подготовка: {name}")
        self.time_label.setText("")
        self.progress_bar.setRange(0, 0)

    def set_state(self, row, state):
        item = self.table.item(row, 2)
        item.setText(state)
        item.setForeground(QColor({"Готово": "#28775d", "Ошибка": "#b34736", "Обработка": "#b66a32"}.get(state, "#68768a")))

    def show_progress(self, seconds, duration):
        if duration and duration > 0:
            self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(min(999, int(seconds / duration * 1000)))
            self.time_label.setText(f"{timestamp(seconds)} / {timestamp(duration)}")
        else:
            self.progress_bar.setRange(0, 0)
            self.time_label.setText(timestamp(seconds))

    def store_result(self, row, path):
        self.results[row] = Path(path)
        self.table.item(row, 2).setToolTip(f"Дважды нажмите, чтобы открыть Word:\n{path}")

    def show_failure(self, row, message):
        self.errors[row] = message
        self.table.item(row, 2).setToolTip(message)
        self.preview_text.appendPlainText(f"\nОшибка: {message}\nДважды нажмите на файл, чтобы увидеть подробности.")

    def stop(self):
        if self.is_busy():
            self.worker.cancel_event.set()
            self.stop_button.setEnabled(False)
            self.status_label.setText("Остановка… Завершённые фрагменты сохранены. Ожидаем завершения текущей операции.")

    def batch_finished(self):
        worker = self.worker
        if worker.was_cancelled:
            self.status_label.setText("Остановлено. При повторном запуске продолжим с сохранённого фрагмента.")
        elif worker.error_count:
            self.status_label.setText("Есть ошибки. Дважды нажмите на строку с ошибкой для подробностей.")
        else:
            self.status_label.setText("Готово! Документы Word сохранены. Двойной щелчок по файлу откроет результат.")
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(1000 if not worker.was_cancelled and not worker.error_count else 0)
        self.update_buttons()
        worker.deleteLater()
        self.worker = None
        if self.close_when_done:
            self.close()

    def open_row(self, item):
        row = item.row()
        if row in self.results:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.results[row])))
        elif row in self.errors:
            QMessageBox.warning(self, "Не удалось распознать запись", self.errors[row])

    def open_folder(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_dir)))

    def closeEvent(self, event):
        self.save_preferences()
        if self.is_busy():
            self.close_when_done = True
            self.stop()
            event.ignore()
        else:
            event.accept()


def run_gui(app_dir: Path, data_dir: Path, files: list[str]) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Транскрибер")
    app.setOrganizationName("LocalTranscriber")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    window = MainWindow(app_dir, data_dir)
    window.show()
    if files:
        window.add_files(files)
    return app.exec()
