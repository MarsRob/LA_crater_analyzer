from __future__ import annotations

import copy
import csv
import sys
from pathlib import Path

import cv2
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from crater_analyzer.models import CraterRecord
from crater_analyzer.video import VideoReader, adjusted_frame, detect_crater_candidate


class VideoCanvas(QWidget):
    clicked_image = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(640, 420)
        self.setMouseTracking(True)
        self._pixmap: QPixmap | None = None
        self._image_size: tuple[int, int] | None = None
        self._expected: tuple[float, float] | None = None
        self._center: tuple[float, float] | None = None
        self._inner: tuple[tuple[float, float], tuple[float, float]] | None = None
        self._outer: tuple[tuple[float, float], tuple[float, float]] | None = None
        self._pending: tuple[float, float] | None = None
        self._label: str = ""
        self._instruction: str = ""
        self._zoom_enabled = False
        self._zoom_focus: tuple[float, float] | None = None
        self._zoom_size = 260

    def set_frame(self, frame_bgr) -> None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        bytes_per_line = channels * width
        image = QImage(rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).copy()
        self._pixmap = QPixmap.fromImage(image)
        self._image_size = (width, height)
        self.update()

    def set_overlay(
        self,
        expected: tuple[float, float] | None,
        center: tuple[float, float] | None,
        inner: tuple[tuple[float, float], tuple[float, float]] | None,
        outer: tuple[tuple[float, float], tuple[float, float]] | None,
        pending: tuple[float, float] | None,
        label: str = "",
        instruction: str = "",
    ) -> None:
        self._expected = expected
        self._center = center
        self._inner = inner
        self._outer = outer
        self._pending = pending
        self._label = label
        self._instruction = instruction
        self.update()

    def set_zoom(
        self,
        enabled: bool,
        focus: tuple[float, float] | None,
        size: int,
    ) -> None:
        self._zoom_enabled = enabled
        self._zoom_focus = focus
        self._zoom_size = size
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111318"))
        if self._pixmap is None or self._image_size is None:
            painter.setPen(QColor("#8a93a3"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Open an MP4 video to begin")
            return

        image_rect = self._image_rect()
        source_rect = self._source_rect()
        painter.drawPixmap(image_rect.toRect(), self._pixmap, source_rect.toRect())
        self._draw_overlays(painter, image_rect)
        self._draw_instruction(painter, image_rect)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        image_point = self._widget_to_image(event.position())
        if image_point is not None:
            self.clicked_image.emit(image_point[0], image_point[1])

    def _image_rect(self) -> QRectF:
        if self._image_size is None:
            return QRectF()
        source = self._source_rect()
        scale = min(self.width() / source.width(), self.height() / source.height())
        draw_w = source.width() * scale
        draw_h = source.height() * scale
        x = (self.width() - draw_w) / 2
        y = (self.height() - draw_h) / 2
        return QRectF(x, y, draw_w, draw_h)

    def _source_rect(self) -> QRectF:
        if self._image_size is None:
            return QRectF()
        image_w, image_h = self._image_size
        if not self._zoom_enabled or self._zoom_focus is None:
            return QRectF(0, 0, image_w, image_h)

        size = min(max(80, self._zoom_size), image_w, image_h)
        half = size / 2
        cx, cy = self._zoom_focus
        left = min(max(0.0, cx - half), max(0.0, image_w - size))
        top = min(max(0.0, cy - half), max(0.0, image_h - size))
        return QRectF(left, top, size, size)

    def _image_to_widget(self, point: tuple[float, float], image_rect: QRectF) -> QPointF:
        if self._image_size is None:
            return QPointF()
        source = self._source_rect()
        return QPointF(
            image_rect.left() + ((point[0] - source.left()) / source.width()) * image_rect.width(),
            image_rect.top() + ((point[1] - source.top()) / source.height()) * image_rect.height(),
        )

    def _widget_to_image(self, point: QPointF) -> tuple[float, float] | None:
        if self._image_size is None:
            return None
        rect = self._image_rect()
        if not rect.contains(point):
            return None
        source = self._source_rect()
        x = source.left() + ((point.x() - rect.left()) / rect.width()) * source.width()
        y = source.top() + ((point.y() - rect.top()) / rect.height()) * source.height()
        return x, y

    def _draw_cross(
        self,
        painter: QPainter,
        point: tuple[float, float],
        rect: QRectF,
        color: str,
        radius: int,
    ) -> None:
        mapped = self._image_to_widget(point, rect)
        painter.setPen(QPen(QColor(color), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(mapped.x() - radius, mapped.y()), QPointF(mapped.x() + radius, mapped.y()))
        painter.drawLine(QPointF(mapped.x(), mapped.y() - radius), QPointF(mapped.x(), mapped.y() + radius))
        painter.drawEllipse(mapped, radius, radius)

    def _draw_measurement(
        self,
        painter: QPainter,
        measurement: tuple[tuple[float, float], tuple[float, float]] | None,
        rect: QRectF,
        color: str,
    ) -> None:
        if measurement is None:
            return
        a = self._image_to_widget(measurement[0], rect)
        b = self._image_to_widget(measurement[1], rect)
        center = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
        radius = ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5 / 2.0
        painter.setPen(QPen(QColor(color), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(center, radius, radius)
        painter.drawLine(a, b)
        painter.drawEllipse(a, 4, 4)
        painter.drawEllipse(b, 4, 4)

    def _draw_overlays(self, painter: QPainter, rect: QRectF) -> None:
        if self._expected is not None:
            self._draw_cross(painter, self._expected, rect, "#f0c54a", 12)
            self._draw_label(painter, self._expected, rect, self._label, "#f0c54a")
        if self._center is not None:
            self._draw_cross(painter, self._center, rect, "#5cc8ff", 9)
            if self._expected is None:
                self._draw_label(painter, self._center, rect, self._label, "#5cc8ff")
        if self._pending is not None:
            self._draw_cross(painter, self._pending, rect, "#ff6b6b", 7)
        self._draw_measurement(painter, self._inner, rect, "#62d26f")
        self._draw_measurement(painter, self._outer, rect, "#c084fc")

    def _draw_label(
        self,
        painter: QPainter,
        point: tuple[float, float],
        rect: QRectF,
        text: str,
        color: str,
    ) -> None:
        if not text:
            return
        mapped = self._image_to_widget(point, rect)
        label_rect = QRectF(mapped.x() + 15, mapped.y() - 28, 54, 24)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#111318"))
        painter.drawRoundedRect(label_rect, 4, 4)
        painter.setPen(QPen(QColor(color), 2))
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_instruction(self, painter: QPainter, rect: QRectF) -> None:
        if not self._instruction:
            return
        width = min(rect.width() - 24, 760)
        label_rect = QRectF(rect.left() + 12, rect.top() + 12, width, 34)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(17, 19, 24, 220))
        painter.drawRoundedRect(label_rect, 5, 5)
        painter.setPen(QPen(QColor("#e6e8ee"), 1))
        painter.drawText(label_rect.adjusted(12, 0, -12, 0), Qt.AlignmentFlag.AlignVCenter, self._instruction)
        painter.setBrush(Qt.BrushStyle.NoBrush)


class AnalysisResultsDialog(QDialog):
    def __init__(self, csv_path: Path, output_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.csv_path = csv_path
        self.output_dir = output_dir
        self.current_pixmap: QPixmap | None = None
        self.files = [
            path
            for path in sorted(output_dir.iterdir())
            if path.suffix.lower() in {".png", ".csv"}
        ]

        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setWindowTitle("CSV Analysis Results")
        self.resize(980, 700)

        layout = QVBoxLayout(self)
        title = QLabel(f"Analysis: {csv_path.name}")
        title.setObjectName("workflowTitle")
        layout.addWidget(title)

        body = QHBoxLayout()
        self.file_list = QListWidget()
        self.file_list.setMinimumWidth(290)
        for path in self.files:
            self.file_list.addItem(path.name)
        body.addWidget(self.file_list)

        self.preview_stack = QStackedWidget()
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_scroll = QScrollArea()
        self.image_scroll.setWidget(self.image_label)
        self.image_scroll.setWidgetResizable(True)
        self.text_preview = QPlainTextEdit()
        self.text_preview.setReadOnly(True)
        self.preview_stack.addWidget(self.image_scroll)
        self.preview_stack.addWidget(self.text_preview)
        body.addWidget(self.preview_stack, 1)
        layout.addLayout(body, 1)

        footer = QHBoxLayout()
        self.output_label = QLabel(f"Output folder: {output_dir}")
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.output_label, 1)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

        self.file_list.currentRowChanged.connect(self.show_file)
        if self.files:
            self.file_list.setCurrentRow(0)
        else:
            self.text_preview.setPlainText("No analysis output files were found.")
            self.preview_stack.setCurrentWidget(self.text_preview)

    def show_file(self, row: int) -> None:
        if row < 0 or row >= len(self.files):
            return
        path = self.files[row]
        if path.suffix.lower() == ".png":
            self.current_pixmap = QPixmap(str(path))
            self.preview_stack.setCurrentWidget(self.image_scroll)
            self._update_scaled_image()
            return

        self.current_pixmap = None
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            text = str(exc)
        self.text_preview.setPlainText(text)
        self.preview_stack.setCurrentWidget(self.text_preview)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.preview_stack.currentWidget() == self.image_scroll:
            self._update_scaled_image()

    def _update_scaled_image(self) -> None:
        if self.current_pixmap is None or self.current_pixmap.isNull():
            self.image_label.clear()
            return
        available = self.image_scroll.viewport().size()
        if available.width() <= 1 or available.height() <= 1:
            return
        scaled = self.current_pixmap.scaled(
            available,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LA Crater Analyzer")
        self.resize(1360, 820)

        self.reader = VideoReader()
        self.records: list[CraterRecord] = []
        self.frame_index = 0
        self.current_index = 1
        self.pending_point: tuple[float, float] | None = None
        self.last_click: tuple[float, float] | None = None
        self.last_click_frame: int | None = None
        self.scan_position_override: tuple[float, float] | None = None
        self.armed_target: str | None = None
        self.shortcuts: list[QShortcut] = []
        self.undo_stack: list[dict[str, object]] = []
        self.redo_stack: list[dict[str, object]] = []
        self.last_csv_path: Path | None = None
        self.csv_needs_export = False
        self.review_pause_ms = 1200
        self.review_pause_record_index: int | None = None
        self.review_pause_timer = QTimer(self)
        self.review_pause_timer.setSingleShot(True)
        self.review_pause_timer.timeout.connect(self.finish_review_pause)
        self.workflow_step = "presence"
        self._updating_controls = False

        self.canvas = VideoCanvas()
        self.canvas.clicked_image.connect(self.on_canvas_clicked)

        self._build_actions()
        self._build_layout()
        self._connect_signals()
        self._ensure_records(self.total_spin.value())
        self.current_spin.setRange(1, self.total_spin.value())
        self._sync_all()

    def _build_actions(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.open_action = QAction("Open MP4", self)
        self.open_action.triggered.connect(self.open_video)
        toolbar.addAction(self.open_action)

        self.export_action = QAction("Export CSV / Save Progress", self)
        self.export_action.triggered.connect(self.export_csv)
        toolbar.addAction(self.export_action)

        self.import_action = QAction("Import CSV", self)
        self.import_action.triggered.connect(self.import_csv)
        toolbar.addAction(self.import_action)

        self.analyze_action = QAction("Analyze Last CSV", self)
        self.analyze_action.triggered.connect(self.analyze_latest_csv)
        toolbar.addAction(self.analyze_action)

        toolbar.addSeparator()
        self.unsaved_label = QLabel("Saved")
        self.unsaved_label.setObjectName("unsavedLabel")
        toolbar.addWidget(self.unsaved_label)

    def _build_layout(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.canvas, 1)
        left_layout.addLayout(self._build_timeline())
        splitter.addWidget(left)

        right_content = QWidget()
        right_content.setMinimumWidth(430)
        right_layout = QVBoxLayout(right_content)
        right_layout.addWidget(self._build_project_panel())
        right_layout.addWidget(self._build_workflow_panel())
        right_layout.addWidget(self._build_display_panel())
        right_layout.addWidget(self._build_annotation_panel())
        right_layout.addWidget(self._build_assist_panel())
        right_layout.addWidget(self._build_table())
        right_layout.addStretch(1)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setMinimumWidth(460)
        right_scroll.setWidget(right_content)
        splitter.addWidget(right_scroll)
        splitter.setSizes([880, 480])

        self.status = QLabel("No video loaded")
        self.status.setObjectName("statusLabel")
        main_layout.addWidget(self.status)

    def _build_timeline(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        row = QHBoxLayout()
        self.prev_button = QPushButton("Prev")
        self.next_button = QPushButton("Next")
        row.addWidget(self.prev_button)
        row.addWidget(self.next_button)
        row.addStretch(1)
        layout.addLayout(row)

        slider_row = QHBoxLayout()
        self.frame_label = QLabel("Frame 0 / 0")
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setRange(0, 0)
        slider_row.addWidget(self.frame_label)
        slider_row.addWidget(self.frame_slider, 1)
        layout.addLayout(slider_row)

        fine_row = QHBoxLayout()
        self.back_100_button = QPushButton("-100")
        self.back_10_button = QPushButton("-10")
        self.back_1_button = QPushButton("-1")
        self.forward_1_button = QPushButton("+1")
        self.forward_10_button = QPushButton("+10")
        self.forward_100_button = QPushButton("+100")
        self.frame_spin = QSpinBox()
        self.frame_spin.setRange(1, 1)
        fine_row.addWidget(QLabel("Exact frame"))
        fine_row.addWidget(self.frame_spin)
        fine_row.addWidget(self.back_100_button)
        fine_row.addWidget(self.back_10_button)
        fine_row.addWidget(self.back_1_button)
        fine_row.addWidget(self.forward_1_button)
        fine_row.addWidget(self.forward_10_button)
        fine_row.addWidget(self.forward_100_button)
        layout.addLayout(fine_row)
        return layout

    def _build_project_panel(self) -> QGroupBox:
        box = QGroupBox("Session")
        layout = QGridLayout(box)

        self.total_spin = QSpinBox()
        self.total_spin.setRange(1, 100000)
        self.total_spin.setValue(400)
        self.current_spin = QSpinBox()
        self.current_spin.setRange(1, 400)
        self.current_spin.setValue(1)

        layout.addWidget(QLabel("Known total"), 0, 0)
        layout.addWidget(self.total_spin, 0, 1)
        self.apply_total_button = QPushButton("Apply Total")
        layout.addWidget(self.apply_total_button, 0, 2)
        layout.addWidget(QLabel("Current crater"), 1, 0)
        layout.addWidget(self.current_spin, 1, 1, 1, 2)

        self.go_expected_button = QPushButton("Go Expected Frame")
        self.go_expected_button.setText("Go Suggested Frame")
        layout.addWidget(self.go_expected_button, 2, 0, 1, 3)
        self.summary_label = QLabel("Visible 0 | Missing 0 | Unreviewed 1")
        layout.addWidget(self.summary_label, 3, 0, 1, 3)
        self.calibration_label = QLabel("Prediction starts after 3 visible centers")
        layout.addWidget(self.calibration_label, 4, 0, 1, 3)
        self.scan_position_label = QLabel("Scan position: not calibrated")
        layout.addWidget(self.scan_position_label, 5, 0, 1, 3)
        self.set_scan_position_button = QPushButton("Use Current Center as Scan Position")
        layout.addWidget(self.set_scan_position_button, 6, 0, 1, 3)
        self.follow_predictions_check = QCheckBox("Follow predicted crater while scrubbing")
        self.show_suggestions_check = QCheckBox("Show prediction overlays")
        self.show_suggestions_check.setChecked(True)
        layout.addWidget(self.follow_predictions_check, 7, 0, 1, 3)
        layout.addWidget(self.show_suggestions_check, 8, 0, 1, 3)
        return box

    def _build_workflow_panel(self) -> QGroupBox:
        box = QGroupBox("Guided Review")
        layout = QVBoxLayout(box)

        self.workflow_title = QLabel("Crater 1: presence")
        self.workflow_title.setObjectName("workflowTitle")
        self.workflow_instruction = QLabel("Confirm whether the current crater is visible.")
        self.workflow_instruction.setWordWrap(True)
        self.workflow_instruction.setMinimumHeight(54)
        layout.addWidget(self.workflow_title)
        layout.addWidget(self.workflow_instruction)

        steps_row = QHBoxLayout()
        self.step_blocks: dict[str, QLabel] = {}
        for key, label in (
            ("presence", "1 Inner"),
            ("rim", "2 Rim?"),
            ("inner", "3 Finish inner"),
            ("outer", "4 Outer if rim"),
        ):
            block = QLabel(label)
            block.setAlignment(Qt.AlignmentFlag.AlignCenter)
            block.setMinimumHeight(34)
            block.setObjectName("workflowStepBlock")
            self.step_blocks[key] = block
            steps_row.addWidget(block, 1)
        layout.addLayout(steps_row)

        self.presence_actions_label = QLabel("Presence")
        presence_row = QHBoxLayout()
        self.present_button = QPushButton("Use Existing Center")
        self.absent_button = QPushButton("Mark Missing")
        layout.addWidget(self.presence_actions_label)
        presence_row.addWidget(self.present_button)
        presence_row.addWidget(self.absent_button)
        layout.addLayout(presence_row)

        self.rim_actions_label = QLabel("Rim exception")
        rim_row = QHBoxLayout()
        self.no_rim_button = QPushButton("Clear Rim")
        self.yes_rim_button = QPushButton("Rim Present")
        layout.addWidget(self.rim_actions_label)
        rim_row.addWidget(self.no_rim_button)
        rim_row.addWidget(self.yes_rim_button)
        layout.addLayout(rim_row)

        self.history_actions_label = QLabel("History")
        history_row = QHBoxLayout()
        self.workflow_undo_button = QPushButton("Undo Last")
        self.workflow_redo_button = QPushButton("Redo")
        self.cancel_measure_button = QPushButton("Cancel Current Measurement")
        layout.addWidget(self.history_actions_label)
        history_row.addWidget(self.workflow_undo_button)
        history_row.addWidget(self.workflow_redo_button)
        layout.addLayout(history_row)
        layout.addWidget(self.cancel_measure_button)

        self.tool_actions_label = QLabel("Manual override")
        self.unlock_tools_check = QCheckBox("Unlock manual override tools")
        tool_row = QHBoxLayout()
        self.arm_center_button = QPushButton("Center")
        self.arm_inner_button = QPushButton("Inner Circle")
        self.arm_outer_button = QPushButton("Outer Circle")
        layout.addWidget(self.tool_actions_label)
        layout.addWidget(self.unlock_tools_check)
        tool_row.addWidget(self.arm_center_button)
        tool_row.addWidget(self.arm_inner_button)
        tool_row.addWidget(self.arm_outer_button)
        layout.addLayout(tool_row)
        return box

    def _build_annotation_panel(self) -> QGroupBox:
        box = QGroupBox("Measurement Tools")
        layout = QGridLayout(box)

        self.mode_center = QRadioButton("Center")
        self.mode_inner = QRadioButton("Inner diameter")
        self.mode_outer = QRadioButton("Outer diameter")
        self.mode_center.setChecked(True)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_center)
        mode_row.addWidget(self.mode_inner)
        mode_row.addWidget(self.mode_outer)
        layout.addWidget(QLabel("Manual click target"), 0, 0, 1, 2)
        layout.addLayout(mode_row, 1, 0, 1, 2)

        self.visible_check = QCheckBox("Visible")
        self.missing_check = QCheckBox("Missing")
        layout.addWidget(self.visible_check, 3, 0)
        layout.addWidget(self.missing_check, 3, 1)

        self.rim_combo = QComboBox()
        self.rim_combo.addItems(["Unknown rim", "No rim", "Rim present"])
        layout.addWidget(QLabel("Rim"), 4, 0)
        layout.addWidget(self.rim_combo, 4, 1)

        self.center_label = QLabel("Center: -")
        self.inner_label = QLabel("Inner: -")
        self.outer_label = QLabel("Outer: -")
        layout.addWidget(self.center_label, 5, 0, 1, 2)
        layout.addWidget(self.inner_label, 6, 0, 1, 2)
        layout.addWidget(self.outer_label, 7, 0, 1, 2)

        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Notes")
        self.notes_edit.setFixedHeight(70)
        layout.addWidget(self.notes_edit, 8, 0, 1, 2)
        return box

    def _build_display_panel(self) -> QGroupBox:
        box = QGroupBox("Display")
        layout = QGridLayout(box)

        self.brightness_slider = self._slider(-100, 100, 0)
        self.contrast_slider = self._slider(20, 300, 100)
        self.gamma_slider = self._slider(30, 300, 100)
        self.clahe_check = QCheckBox("CLAHE")
        self.sharpen_check = QCheckBox("Sharpen")
        self.zoom_check = QCheckBox("Zoom crater area")
        self.zoom_check.setChecked(True)
        self.zoom_size_spin = QSpinBox()
        self.zoom_size_spin.setRange(80, 900)
        self.zoom_size_spin.setSingleStep(20)
        self.zoom_size_spin.setValue(500)

        layout.addWidget(QLabel("Brightness"), 0, 0)
        layout.addWidget(self.brightness_slider, 0, 1)
        layout.addWidget(QLabel("Contrast"), 1, 0)
        layout.addWidget(self.contrast_slider, 1, 1)
        layout.addWidget(QLabel("Gamma"), 2, 0)
        layout.addWidget(self.gamma_slider, 2, 1)
        layout.addWidget(self.clahe_check, 3, 0)
        layout.addWidget(self.sharpen_check, 3, 1)
        layout.addWidget(self.zoom_check, 4, 0)
        layout.addWidget(self.zoom_size_spin, 4, 1)
        return box

    def _build_assist_panel(self) -> QGroupBox:
        box = QGroupBox("Assist")
        layout = QGridLayout(box)

        self.detect_current_button = QPushButton("Suggest Current Crater")
        self.detect_all_button = QPushButton("Scan Unreviewed Suggestions")
        self.assist_note = QLabel("Automatic detection is optional and may be unreliable on doubled or low-contrast frames.")
        self.assist_note.setWordWrap(True)
        layout.addWidget(self.assist_note, 0, 0, 1, 2)
        layout.addWidget(self.detect_current_button, 1, 0)
        layout.addWidget(self.detect_all_button, 1, 1)
        return box

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["#", "Status", "Frame", "Rim", "Inner px", "Outer px"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        return self.table

    def _slider(self, low: int, high: int, value: int) -> QSlider:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setValue(value)
        return slider

    def _connect_signals(self) -> None:
        self.frame_slider.valueChanged.connect(self.set_frame_index)
        self.total_spin.valueChanged.connect(self._sync_total_apply_button)
        self.apply_total_button.clicked.connect(self.apply_total_changed)
        self.current_spin.valueChanged.connect(self.set_current_index)
        self.prev_button.clicked.connect(lambda: self.step_crater(-1))
        self.next_button.clicked.connect(lambda: self.step_crater(1))
        self.go_expected_button.clicked.connect(self.go_expected_frame)
        self.set_scan_position_button.clicked.connect(self.set_scan_position_from_current)
        self.follow_predictions_check.toggled.connect(self._sync_all)
        self.show_suggestions_check.toggled.connect(self._sync_all)
        self.frame_spin.valueChanged.connect(self.set_frame_from_spin)
        self.back_100_button.clicked.connect(lambda: self.nudge_frame(-100))
        self.back_10_button.clicked.connect(lambda: self.nudge_frame(-10))
        self.back_1_button.clicked.connect(lambda: self.nudge_frame(-1))
        self.forward_1_button.clicked.connect(lambda: self.nudge_frame(1))
        self.forward_10_button.clicked.connect(lambda: self.nudge_frame(10))
        self.forward_100_button.clicked.connect(lambda: self.nudge_frame(100))
        self.present_button.clicked.connect(self.mark_present_from_workflow)
        self.absent_button.clicked.connect(self.mark_missing_from_workflow)
        self.workflow_undo_button.clicked.connect(self.undo_last)
        self.workflow_redo_button.clicked.connect(self.redo_last)
        self.cancel_measure_button.clicked.connect(self.cancel_current_measurement)
        self.arm_center_button.clicked.connect(lambda: self.arm_click_target("center"))
        self.arm_inner_button.clicked.connect(lambda: self.arm_click_target("inner"))
        self.arm_outer_button.clicked.connect(lambda: self.arm_click_target("outer"))
        self.no_rim_button.clicked.connect(lambda: self.set_rim_from_workflow(False))
        self.yes_rim_button.clicked.connect(lambda: self.set_rim_from_workflow(True))
        self.detect_current_button.clicked.connect(self.detect_current)
        self.detect_all_button.clicked.connect(self.detect_unreviewed)
        self.unlock_tools_check.toggled.connect(self._sync_all)
        self.visible_check.toggled.connect(self.on_visibility_changed)
        self.missing_check.toggled.connect(self.on_missing_changed)
        self.rim_combo.currentIndexChanged.connect(self.on_rim_changed)
        self.notes_edit.textChanged.connect(self.on_notes_changed)
        self.table.itemSelectionChanged.connect(self.on_table_selection)

        for slider in (self.brightness_slider, self.contrast_slider, self.gamma_slider):
            slider.valueChanged.connect(self.refresh_frame)
        self.clahe_check.toggled.connect(self.refresh_frame)
        self.sharpen_check.toggled.connect(self.refresh_frame)
        self.zoom_check.toggled.connect(self._update_overlay)
        self.zoom_size_spin.valueChanged.connect(self._update_overlay)

        previous_shortcut = QShortcut(QKeySequence("Left"), self)
        previous_shortcut.activated.connect(lambda: self.step_crater(-1))
        next_shortcut = QShortcut(QKeySequence("Right"), self)
        next_shortcut.activated.connect(lambda: self.step_crater(1))
        visible_shortcut = QShortcut(QKeySequence("Space"), self)
        visible_shortcut.activated.connect(self.toggle_visible)
        undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        undo_shortcut.activated.connect(self.undo_last)
        redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self)
        redo_shortcut.activated.connect(self.redo_last)
        missing_shortcut = QShortcut(QKeySequence("M"), self)
        missing_shortcut.activated.connect(self.shortcut_mark_missing)
        rim_shortcut = QShortcut(QKeySequence("R"), self)
        rim_shortcut.activated.connect(self.shortcut_toggle_rim)
        undo_key_shortcut = QShortcut(QKeySequence("U"), self)
        undo_key_shortcut.activated.connect(self.shortcut_undo)
        redo_key_shortcut = QShortcut(QKeySequence("Y"), self)
        redo_key_shortcut.activated.connect(self.shortcut_redo)
        cancel_shortcut = QShortcut(QKeySequence("Esc"), self)
        cancel_shortcut.activated.connect(self.cancel_current_measurement)
        self.shortcuts.extend(
            [
                previous_shortcut,
                next_shortcut,
                visible_shortcut,
                undo_shortcut,
                redo_shortcut,
                missing_shortcut,
                rim_shortcut,
                undo_key_shortcut,
                redo_key_shortcut,
                cancel_shortcut,
            ]
        )

    def open_video(self) -> None:
        if not self._confirm_continue_with_unsaved_changes("Open a new video?"):
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open crater scan video",
            "",
            "Videos (*.mp4 *.avi *.mov *.mkv);;All files (*.*)",
        )
        if not path:
            return
        self._load_video(path, reset_records=True)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._confirm_continue_with_unsaved_changes("Close LA Crater Analyzer?"):
            event.accept()
        else:
            event.ignore()

    def _confirm_continue_with_unsaved_changes(self, title: str) -> bool:
        if not self.csv_needs_export:
            return True
        answer = QMessageBox.question(
            self,
            title,
            "There are unsaved crater edits. Export the current CSV before continuing?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.No:
            return True
        return self.export_csv() is not None

    def _load_video(self, path: str | Path, reset_records: bool) -> bool:
        try:
            info = self.reader.open(path)
        except RuntimeError as exc:
            QMessageBox.critical(self, "Video error", str(exc))
            return False

        self.frame_slider.setRange(0, max(0, info.frame_count - 1))
        self.frame_spin.setRange(1, max(1, info.frame_count))
        self.frame_index = 0
        if reset_records:
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.last_csv_path = None
            self.csv_needs_export = False
            self.records = [CraterRecord(index=index) for index in range(1, self.total_spin.value() + 1)]
            self.current_index = 1
            self.current_spin.blockSignals(True)
            self.current_spin.setValue(1)
            self.current_spin.blockSignals(False)
            self.workflow_step = "presence"
        self.last_click = None
        self.last_click_frame = None
        self.armed_target = None
        if reset_records:
            self.scan_position_override = None
        if reset_records:
            self._clear_predictions()
        self.refresh_frame()
        self._sync_all()
        self.status.setText(
            f"Loaded {info.path.name}: {info.frame_count} frames, {info.width}x{info.height}, {info.fps:.2f} fps"
        )
        return True

    def set_frame_index(self, index: int) -> None:
        self.frame_index = index
        if self.follow_predictions_check.isChecked():
            self._select_nearest_crater_for_frame()
        self.refresh_frame()
        self._sync_all()

    def set_frame_from_spin(self, frame_number: int) -> None:
        self.set_frame_index(frame_number - 1)

    def nudge_frame(self, delta: int) -> None:
        maximum = self.frame_slider.maximum()
        self.set_frame_index(max(0, min(maximum, self.frame_index + delta)))

    def _select_nearest_crater_for_frame(self) -> None:
        if self.pending_point is not None or self.prediction_count() < 3:
            return
        candidates = [record for record in self.records if record.expected_frame is not None]
        if not candidates:
            return
        nearest = min(candidates, key=lambda record: abs((record.expected_frame or 0) - self.frame_index))
        if nearest.index == self.current_index:
            return
        self.current_index = nearest.index
        self.armed_target = None
        self.current_spin.blockSignals(True)
        self.current_spin.setValue(nearest.index)
        self.current_spin.blockSignals(False)
        self._infer_workflow_step_for_current()

    def refresh_frame(self) -> None:
        if self.reader.info is None:
            self._update_overlay()
            return
        try:
            raw = self.reader.read(self.frame_index)
        except RuntimeError as exc:
            self.status.setText(str(exc))
            return

        shown = adjusted_frame(
            raw,
            self.brightness_slider.value(),
            self.contrast_slider.value() / 100.0,
            self.gamma_slider.value() / 100.0,
            self.clahe_check.isChecked(),
            self.sharpen_check.isChecked(),
        )
        self.canvas.set_frame(shown)
        frame_count = self.reader.info.frame_count
        self.frame_label.setText(f"Frame {self.frame_index + 1} / {frame_count}")
        if self.frame_slider.value() != self.frame_index:
            self.frame_slider.blockSignals(True)
            self.frame_slider.setValue(self.frame_index)
            self.frame_slider.blockSignals(False)
        if self.frame_spin.value() != self.frame_index + 1:
            self.frame_spin.blockSignals(True)
            self.frame_spin.setValue(self.frame_index + 1)
            self.frame_spin.blockSignals(False)
        self._update_overlay()

    def _sync_total_apply_button(self) -> None:
        pending_total = self.total_spin.value()
        applied_total = len(self.records)
        self.apply_total_button.setEnabled(pending_total != applied_total)
        if pending_total == applied_total:
            self.apply_total_button.setText("Apply Total")
        elif pending_total > applied_total:
            self.apply_total_button.setText(f"Add {pending_total - applied_total}")
        else:
            self.apply_total_button.setText(f"Remove {applied_total - pending_total}")

    def apply_total_changed(self) -> None:
        total = self.total_spin.value()
        old_total = len(self.records)
        if total == old_total:
            self._sync_total_apply_button()
            return
        if total < old_total and self._total_change_would_discard_data(total):
            answer = QMessageBox.warning(
                self,
                "Reduce known total?",
                (
                    f"Reducing the known total from {old_total} to {total} will remove "
                    f"{old_total - total} crater record(s). Some of those records contain "
                    "review data or measurements.\n\nContinue?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.total_spin.blockSignals(True)
                self.total_spin.setValue(old_total)
                self.total_spin.blockSignals(False)
                self._sync_total_apply_button()
                return
        self._push_undo()
        self._ensure_records(total)
        self.current_spin.setRange(1, total)
        self.current_index = min(self.current_index, total)
        self.current_spin.setValue(self.current_index)
        self.recalculate_expected_positions()
        self._sync_total_apply_button()
        self._sync_all()

    def _ensure_records(self, total: int) -> None:
        existing = {record.index: record for record in self.records}
        self.records = [existing.get(index, CraterRecord(index=index)) for index in range(1, total + 1)]

    def _total_change_would_discard_data(self, total: int) -> bool:
        return any(self._record_has_review_data(record) for record in self.records[total:])

    def _record_has_review_data(self, record: CraterRecord) -> bool:
        return (
            record.visible
            or record.missing
            or record.center_point() is not None
            or record.inner_a is not None
            or record.inner_b is not None
            or record.outer_a is not None
            or record.outer_b is not None
            or record.rim_present is not None
            or record.measurement_frame is not None
            or record.auto_score is not None
            or bool(record.flags)
            or bool(record.notes.strip())
        )

    def set_current_index(self, index: int) -> None:
        self._cancel_review_pause_timer()
        self.current_index = index
        self.pending_point = None
        self.armed_target = None
        self._infer_workflow_step_for_current()
        self._sync_all()

    def current_record(self) -> CraterRecord:
        return self.records[self.current_index - 1]

    def _derive_center_from_inner(self, record: CraterRecord) -> None:
        if record.center_point() is not None or record.inner_a is None or record.inner_b is None:
            return
        frame = record.measurement_frame if record.measurement_frame is not None else self.frame_index
        record.set_center(
            (
                (record.inner_a[0] + record.inner_b[0]) / 2.0,
                (record.inner_a[1] + record.inner_b[1]) / 2.0,
            ),
            frame,
        )

    def _snapshot(self) -> dict[str, object]:
        return {
            "records": copy.deepcopy(self.records),
            "current_index": self.current_index,
            "frame_index": self.frame_index,
            "pending_point": self.pending_point,
            "last_click": self.last_click,
            "last_click_frame": self.last_click_frame,
            "scan_position_override": self.scan_position_override,
            "armed_target": self.armed_target,
            "workflow_step": self.workflow_step,
        }

    def _restore_snapshot(self, snapshot: dict[str, object]) -> None:
        self.records = copy.deepcopy(snapshot["records"])
        self.current_index = int(snapshot["current_index"])
        self.frame_index = int(snapshot["frame_index"])
        self.pending_point = snapshot["pending_point"]  # type: ignore[assignment]
        self.last_click = snapshot["last_click"]  # type: ignore[assignment]
        self.last_click_frame = snapshot["last_click_frame"]  # type: ignore[assignment]
        self.scan_position_override = snapshot["scan_position_override"]  # type: ignore[assignment]
        self.armed_target = snapshot["armed_target"]  # type: ignore[assignment]
        self.workflow_step = str(snapshot["workflow_step"])
        self.total_spin.blockSignals(True)
        self.total_spin.setValue(len(self.records))
        self.total_spin.blockSignals(False)
        self.current_spin.setRange(1, len(self.records))
        self.current_spin.blockSignals(True)
        self.current_spin.setValue(self.current_index)
        self.current_spin.blockSignals(False)
        self.refresh_frame()
        self._sync_all()

    def _push_undo(self) -> None:
        self.csv_needs_export = True
        self.undo_stack.append(self._snapshot())
        if len(self.undo_stack) > 200:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self._sync_undo_redo_actions()

    def undo_last(self) -> None:
        if not self.undo_stack:
            return
        self._cancel_review_pause_timer()
        self.redo_stack.append(self._snapshot())
        self._restore_snapshot(self.undo_stack.pop())
        self.csv_needs_export = True
        self.status.setText("Undid last crater edit")

    def redo_last(self) -> None:
        if not self.redo_stack:
            return
        self._cancel_review_pause_timer()
        self.undo_stack.append(self._snapshot())
        self._restore_snapshot(self.redo_stack.pop())
        self.csv_needs_export = True
        self.status.setText("Redid crater edit")

    def cancel_current_measurement(self) -> None:
        if self.pending_point is None:
            self.status.setText("No in-progress measurement to cancel")
            return
        self.pending_point = None
        self.status.setText("Current measurement cancelled")
        self._sync_all()

    def _sync_undo_redo_actions(self) -> None:
        can_undo = bool(self.undo_stack)
        can_redo = bool(self.redo_stack)
        if hasattr(self, "workflow_undo_button"):
            self.workflow_undo_button.setEnabled(can_undo)
        if hasattr(self, "workflow_redo_button"):
            self.workflow_redo_button.setEnabled(can_redo)
        if hasattr(self, "cancel_measure_button"):
            self.cancel_measure_button.setEnabled(self.pending_point is not None)

    def step_crater(self, direction: int) -> None:
        target = max(1, min(len(self.records), self.current_index + direction))
        self.current_spin.setValue(target)
        self.go_expected_frame()

    def go_expected_frame(self) -> None:
        record = self.current_record()
        if record.expected_frame is not None:
            self.frame_index = max(0, min(record.expected_frame, self.frame_slider.maximum()))
            self.refresh_frame()

    def on_canvas_clicked(self, x: float, y: float) -> None:
        if not self._click_target_matches_step():
            self.status.setText("The current guided step does not use an image click.")
            return
        point = (x, y)
        self._push_undo()
        self.last_click = point
        self.last_click_frame = self.frame_index
        record = self.current_record()
        if self.mode_center.isChecked():
            record.set_center(point, self.frame_index)
            record.rim_present = False
            record.outer_a = None
            record.outer_b = None
            self.pending_point = None
            self.armed_target = None
            self.recalculate_expected_positions()
            if self.workflow_step in {"presence", "center"}:
                self.workflow_step = "inner"
            self.status.setText(f"Crater {record.index}: center set at {x:.1f}, {y:.1f}")
        elif self.mode_inner.isChecked():
            saved = self._capture_measurement(record, point, "inner")
            if saved and self.workflow_step in {"presence", "center", "inner"}:
                self.armed_target = None
                if record.rim_present:
                    self.workflow_step = "outer"
                else:
                    self._begin_review_pause()
                    return
        elif self.mode_outer.isChecked():
            saved = self._capture_measurement(record, point, "outer")
            if saved and self.workflow_step == "outer":
                self.armed_target = None
                self._begin_review_pause()
                return
        self._sync_all()

    def _click_target_matches_step(self) -> bool:
        if self.unlock_tools_check.isChecked():
            return True
        if self.workflow_step in {"presence", "center", "inner"}:
            return self.mode_inner.isChecked()
        if self.workflow_step == "outer":
            return self.mode_outer.isChecked()
        return False

    def _capture_measurement(
        self, record: CraterRecord, point: tuple[float, float], kind: str
    ) -> bool:
        if self.pending_point is None:
            self.pending_point = point
            self.status.setText(f"Crater {record.index}: click opposite {kind} diameter edge")
            return False

        if kind == "inner":
            record.inner_a = self.pending_point
            record.inner_b = point
            if record.rim_present is None:
                record.rim_present = False
        else:
            record.outer_a = self.pending_point
            record.outer_b = point
            record.rim_present = True
        record.measurement_frame = self.frame_index
        if record.center_point() is None:
            record.set_center(
                ((self.pending_point[0] + point[0]) / 2.0, (self.pending_point[1] + point[1]) / 2.0),
                self.frame_index,
            )
        record.visible = True
        record.missing = False
        self.pending_point = None
        self.recalculate_expected_positions()
        self.status.setText(f"Crater {record.index}: {kind} diameter saved")
        return True

    def recalculate_expected_positions(self) -> None:
        visible = [
            record
            for record in self.records
            if record.visible
            and not record.missing
            and record.center_x is not None
            and record.center_y is not None
            and record.measurement_frame is not None
        ]
        for record in self.records:
            if record.center_x is not None and record.center_y is not None:
                record.expected_frame = record.measurement_frame
                record.expected_x = record.center_x
                record.expected_y = record.center_y
            elif len(visible) < 3:
                record.expected_frame = None
                record.expected_x = None
                record.expected_y = None

        if len(visible) < 3:
            return

        frame_slope, frame_intercept = self._linear_fit(
            [(record.index, float(record.measurement_frame)) for record in visible]
        )
        scan_x, scan_y = self.scan_position()
        for record in self.records:
            if record.center_x is not None and record.center_y is not None:
                continue
            record.expected_frame = round(frame_slope * record.index + frame_intercept)
            record.expected_x = scan_x
            record.expected_y = scan_y

    def _clear_predictions(self) -> None:
        for record in self.records:
            record.expected_frame = record.measurement_frame
            record.expected_x = record.center_x
            record.expected_y = record.center_y

    def prediction_count(self) -> int:
        return sum(
            1
            for record in self.records
            if record.visible
            and not record.missing
            and record.center_x is not None
            and record.center_y is not None
            and record.measurement_frame is not None
        )

    def scan_position(self) -> tuple[float, float]:
        if self.scan_position_override is not None:
            return self.scan_position_override
        visible = [
            record
            for record in self.records
            if record.visible
            and not record.missing
            and record.center_x is not None
            and record.center_y is not None
        ]
        if not visible:
            return 0.0, 0.0
        return (
            sum(float(record.center_x) for record in visible) / len(visible),
            sum(float(record.center_y) for record in visible) / len(visible),
        )

    def set_scan_position_from_current(self) -> None:
        record = self.current_record()
        point = record.center_point()
        if point is None and self.last_click_frame == self.frame_index:
            point = self.last_click
        if point is None:
            QMessageBox.information(
                self,
                "Scan position needed",
                "Click or measure the crater center before setting the scan position.",
            )
            return
        self._push_undo()
        self.scan_position_override = point
        self.recalculate_expected_positions()
        self._sync_all()
        self.status.setText(f"Scan position set to {point[0]:.1f}, {point[1]:.1f}")

    def _linear_fit(self, points: list[tuple[int, float]]) -> tuple[float, float]:
        count = len(points)
        x_mean = sum(point[0] for point in points) / count
        y_mean = sum(point[1] for point in points) / count
        denominator = sum((point[0] - x_mean) ** 2 for point in points)
        if denominator == 0:
            return 0.0, y_mean
        slope = sum((point[0] - x_mean) * (point[1] - y_mean) for point in points) / denominator
        intercept = y_mean - slope * x_mean
        return slope, intercept

    def on_visibility_changed(self, checked: bool) -> None:
        if self._updating_controls:
            return
        record = self.current_record()
        self._push_undo()
        record.visible = checked
        if checked:
            record.missing = False
        self._sync_all()

    def on_missing_changed(self, checked: bool) -> None:
        if self._updating_controls:
            return
        record = self.current_record()
        self._push_undo()
        if checked:
            record.set_missing()
        else:
            record.missing = False
        self._sync_all()

    def on_rim_changed(self, index: int) -> None:
        if self._updating_controls:
            return
        record = self.current_record()
        self._push_undo()
        record.rim_present = None if index == 0 else index == 2
        self._sync_all()

    def on_notes_changed(self) -> None:
        if self._updating_controls:
            return
        self.current_record().notes = self.notes_edit.toPlainText()
        self.csv_needs_export = True

    def toggle_visible(self) -> None:
        self.visible_check.setChecked(not self.visible_check.isChecked())

    def _shortcut_blocked_by_text_focus(self) -> bool:
        focused = QApplication.focusWidget()
        if focused is None:
            return False
        return focused == self.notes_edit or self.notes_edit.isAncestorOf(focused)

    def shortcut_mark_missing(self) -> None:
        if self._shortcut_blocked_by_text_focus():
            return
        self.mark_missing_from_workflow()

    def shortcut_toggle_rim(self) -> None:
        if self._shortcut_blocked_by_text_focus():
            return
        record = self.current_record()
        self.set_rim_from_workflow(record.rim_present is not True)

    def shortcut_undo(self) -> None:
        if self._shortcut_blocked_by_text_focus():
            return
        self.undo_last()

    def shortcut_redo(self) -> None:
        if self._shortcut_blocked_by_text_focus():
            return
        self.redo_last()

    def arm_click_target(self, target: str) -> None:
        self.pending_point = None
        if target == "center":
            self.armed_target = "center"
            self.mode_center.setChecked(True)
            self.status.setText("Center click target armed. Click the crater center in the image.")
        elif target == "inner":
            self.armed_target = "inner"
            self.mode_inner.setChecked(True)
            self.status.setText("Inner circle target armed. Click two opposite inner crater edges.")
        elif target == "outer":
            self.armed_target = "outer"
            self.mode_outer.setChecked(True)
            self.status.setText("Outer circle target armed. Click two opposite outer rim edges.")
        self._update_overlay()

    def _set_guided_click_target(self) -> None:
        if self.unlock_tools_check.isChecked():
            return
        if self.workflow_step in {"presence", "center", "inner"}:
            self.armed_target = "inner"
            self.mode_inner.setChecked(True)
        elif self.workflow_step == "outer":
            self.armed_target = "outer"
            self.mode_outer.setChecked(True)
        else:
            self.armed_target = None

    def mark_present_from_workflow(self) -> None:
        record = self.current_record()
        self._push_undo()
        record.visible = True
        record.missing = False
        if record.rim_present is None:
            record.rim_present = False
            record.outer_a = None
            record.outer_b = None
        self.pending_point = None
        self.armed_target = None
        self.workflow_step = "inner"
        self._sync_all()

    def mark_missing_from_workflow(self) -> None:
        self._push_undo()
        self.current_record().set_missing()
        self.pending_point = None
        self.armed_target = None
        self._advance_to_next_crater()

    def set_rim_from_workflow(self, rim_present: bool) -> None:
        record = self.current_record()
        self._push_undo()
        record.rim_present = rim_present
        record.visible = True
        record.missing = False
        if not rim_present:
            record.outer_a = None
            record.outer_b = None
        self.pending_point = None
        self.armed_target = None
        self.workflow_step = "inner"
        self._sync_all()

    def _begin_review_pause(self) -> None:
        self.workflow_step = "review_pause"
        self.review_pause_record_index = self.current_index
        self.review_pause_timer.start(self.review_pause_ms)
        self.status.setText(
            f"Crater {self.current_index}: measurement saved. Brief review pause before next crater."
        )
        self._sync_all()

    def finish_review_pause(self) -> None:
        if self.workflow_step != "review_pause":
            return
        if self.review_pause_record_index != self.current_index:
            return
        self.review_pause_record_index = None
        self._advance_to_next_crater()

    def _cancel_review_pause_timer(self) -> None:
        if self.review_pause_timer.isActive():
            self.review_pause_timer.stop()
        self.review_pause_record_index = None

    def _advance_to_next_crater(self) -> None:
        self._cancel_review_pause_timer()
        self.pending_point = None
        self.armed_target = None
        if self.current_index >= len(self.records):
            self.workflow_step = "complete"
            self._sync_all()
            return
        self.current_index += 1
        self.current_spin.blockSignals(True)
        self.current_spin.setValue(self.current_index)
        self.current_spin.blockSignals(False)
        self.workflow_step = "presence"
        self.go_expected_frame()
        self._sync_all()

    def _infer_workflow_step_for_current(self) -> None:
        if self.workflow_step in {"complete", "review_pause"}:
            return
        record = self.current_record()
        self._derive_center_from_inner(record)
        if record.missing or not record.visible:
            self.workflow_step = "presence"
        elif record.inner_diameter_px is None:
            self.workflow_step = "inner"
        elif record.rim_present is None:
            self.workflow_step = "inner"
        elif record.center_point() is None:
            self.workflow_step = "inner"
        elif record.rim_present and record.outer_diameter_px is None:
            self.workflow_step = "outer"
        else:
            self.workflow_step = "complete" if self._all_records_finished() else "presence"

    def _all_records_finished(self) -> bool:
        for record in self.records:
            self._derive_center_from_inner(record)
            if record.missing:
                continue
            if not record.visible:
                return False
            if record.center_point() is None:
                return False
            if record.rim_present is None:
                return False
            if record.inner_diameter_px is None:
                return False
            if record.rim_present and record.outer_diameter_px is None:
                return False
        return True

    def detect_current(self) -> None:
        if self.reader.info is None:
            return
        record = self.current_record()
        try:
            raw = self.reader.read(self.frame_index)
        except RuntimeError as exc:
            QMessageBox.warning(self, "Detection failed", str(exc))
            return
        frame = adjusted_frame(
            raw,
            self.brightness_slider.value(),
            self.contrast_slider.value() / 100.0,
            self.gamma_slider.value() / 100.0,
            self.clahe_check.isChecked(),
            self.sharpen_check.isChecked(),
        )
        candidate = detect_crater_candidate(frame, record.expected_point())
        if candidate is None:
            self.status.setText(f"Crater {record.index}: no automatic candidate found")
            return

        cx, cy, radius, score = candidate
        answer = QMessageBox.question(
            self,
            "Apply automatic suggestion?",
            f"Candidate center: {cx:.1f}, {cy:.1f}\nCandidate diameter: {radius * 2:.1f} px\n\nApply to crater {record.index}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._push_undo()
        record.set_center((cx, cy), self.frame_index)
        record.inner_a = (cx - radius, cy)
        record.inner_b = (cx + radius, cy)
        record.auto_score = score
        if "auto_detected" not in record.flags:
            record.flags.append("auto_detected")
        self.recalculate_expected_positions()
        self.status.setText(f"Crater {record.index}: automatic candidate applied")
        self._sync_all()

    def detect_unreviewed(self) -> None:
        if self.reader.info is None:
            return
        if self.prediction_count() < 3:
            QMessageBox.information(
                self,
                "Calibration needed",
                "Review at least three visible crater centers before scanning unreviewed positions.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Apply automatic suggestions?",
            "This will scan all unreviewed predicted positions and may mark craters found or missing. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._push_undo()
        found = 0
        missed = 0
        for record in self.records:
            if record.visible or record.missing or record.expected_frame is None:
                continue
            raw = self.reader.read(record.expected_frame)
            frame = adjusted_frame(
                raw,
                self.brightness_slider.value(),
                self.contrast_slider.value() / 100.0,
                self.gamma_slider.value() / 100.0,
                self.clahe_check.isChecked(),
                self.sharpen_check.isChecked(),
            )
            candidate = detect_crater_candidate(frame, record.expected_point())
            if candidate is None:
                record.missing = True
                if "auto_not_found" not in record.flags:
                    record.flags.append("auto_not_found")
                missed += 1
                continue
            cx, cy, radius, score = candidate
            record.set_center((cx, cy), record.expected_frame)
            record.inner_a = (cx - radius, cy)
            record.inner_b = (cx + radius, cy)
            record.auto_score = score
            if "auto_detected" not in record.flags:
                record.flags.append("auto_detected")
            found += 1

        self.recalculate_expected_positions()
        self.status.setText(f"Detection pass complete: {found} found, {missed} marked missing")
        self._sync_all()

    def export_csv(self) -> Path | None:
        if not self.records:
            return None
        default_name = "crater_measurements.csv"
        if self.reader.info is not None:
            default_name = self.reader.info.path.with_suffix(".csv").name
        path, _ = QFileDialog.getSaveFileName(self, "Export crater table", default_name, "CSV (*.csv)")
        if not path:
            return None

        csv_path = Path(path)
        fields = [
            "app_csv_version",
            "source_video_path",
            "index",
            "status",
            "expected_frame_index",
            "expected_frame_number",
            "expected_x",
            "expected_y",
            "measurement_frame_index",
            "measurement_frame_number",
            "center_x",
            "center_y",
            "rim_present",
            "inner_diameter_px",
            "outer_diameter_px",
            "inner_x1",
            "inner_y1",
            "inner_x2",
            "inner_y2",
            "outer_x1",
            "outer_y1",
            "outer_x2",
            "outer_y2",
            "auto_score",
            "flags",
            "notes",
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for record in self.records:
                writer.writerow(self._record_to_row(record))
        self.last_csv_path = csv_path
        self.csv_needs_export = False
        self.status.setText(f"Exported {len(self.records)} crater records to {csv_path}")
        return csv_path

    def analyze_latest_csv(self) -> None:
        csv_path = self._csv_path_for_analysis()
        if csv_path is None:
            return

        output_dir = self._analysis_output_dir_for_csv(csv_path)
        try:
            from scripts.analyze_crater_csv import DEFAULT_UM_PER_PIXEL, analyze

            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            analyze(csv_path, output_dir, rolling_window=15, bins=12, um_per_pixel=DEFAULT_UM_PER_PIXEL)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Analysis failed", str(exc))
            self.status.setText(f"Analysis failed: {exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.status.setText(f"Analyzed {csv_path.name}; outputs written to {output_dir}")
        AnalysisResultsDialog(csv_path, output_dir, self).exec()

    def _analysis_output_dir_for_csv(self, csv_path: Path) -> Path:
        if csv_path.parent.name == "csv" and csv_path.parent.parent.name == "data":
            return csv_path.parent.parent / "analysis" / f"{csv_path.stem}_analysis"
        return csv_path.with_name(f"{csv_path.stem}_analysis")

    def _csv_path_for_analysis(self) -> Path | None:
        if self.last_csv_path is not None and self.last_csv_path.exists() and not self.csv_needs_export:
            return self.last_csv_path

        if self.last_csv_path is not None and self.last_csv_path.exists() and self.csv_needs_export:
            answer = QMessageBox.question(
                self,
                "Export current progress?",
                "There are unsaved crater edits. Export the current CSV before running analysis?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return None
            if answer == QMessageBox.StandardButton.No:
                return self.last_csv_path
            return self.export_csv()

        answer = QMessageBox.question(
            self,
            "CSV needed",
            "No exported CSV is available for this session. Export a CSV now and analyze it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return None
        return self.export_csv()

    def import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import crater progress CSV",
            "",
            "CSV (*.csv);;All files (*.*)",
        )
        if not path:
            return

        try:
            with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
        except OSError as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return

        records = [self._record_from_row(row) for row in rows if row.get("index")]
        if not records:
            QMessageBox.warning(self, "Import failed", "The CSV did not contain crater records.")
            return

        records.sort(key=lambda record: record.index)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.last_csv_path = Path(path)
        self.csv_needs_export = False
        self.records = records
        self.current_index = self._resume_index()
        self.total_spin.blockSignals(True)
        self.total_spin.setValue(len(records))
        self.total_spin.blockSignals(False)
        self.current_spin.setRange(1, len(records))
        self.current_spin.blockSignals(True)
        self.current_spin.setValue(self.current_index)
        self.current_spin.blockSignals(False)
        self.pending_point = None
        self.last_click = None
        self.last_click_frame = None
        self.armed_target = None
        self.scan_position_override = None
        self.recalculate_expected_positions()
        self.workflow_step = "presence"
        self._infer_workflow_step_for_current()
        self._load_source_video_from_csv(rows)
        self.go_expected_frame()
        self._sync_all()
        self.status.setText(f"Imported {len(records)} crater records from {path}")

    def _load_source_video_from_csv(self, rows: list[dict[str, str]]) -> None:
        source = ""
        for row in rows:
            source = (row.get("source_video_path") or "").strip()
            if source:
                break
        if not source:
            if self.reader.info is None:
                QMessageBox.information(
                    self,
                    "Video needed",
                    "CSV progress imported. Open the matching MP4 before continuing measurements.",
                )
            return

        source_path = Path(source)
        current_path = self.reader.info.path if self.reader.info is not None else None
        if current_path is not None and current_path.resolve() == source_path.resolve():
            return
        if not source_path.exists():
            QMessageBox.warning(
                self,
                "Source video not found",
                f"CSV progress references this video, but it was not found:\n{source_path}",
            )
            return

        answer = QMessageBox.question(
            self,
            "Open source video?",
            f"The CSV references this video:\n{source_path}\n\nOpen it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._load_video(source_path, reset_records=False)

    def _record_to_row(self, record: CraterRecord) -> dict[str, object]:
        return {
            "app_csv_version": "2",
            "source_video_path": "" if self.reader.info is None else str(self.reader.info.path),
            "index": record.index,
            "status": record.status_text(),
            "expected_frame_index": record.expected_frame,
            "expected_frame_number": None if record.expected_frame is None else record.expected_frame + 1,
            "expected_x": self._fmt(record.expected_x),
            "expected_y": self._fmt(record.expected_y),
            "measurement_frame_index": record.measurement_frame,
            "measurement_frame_number": None
            if record.measurement_frame is None
            else record.measurement_frame + 1,
            "center_x": self._fmt(record.center_x),
            "center_y": self._fmt(record.center_y),
            "rim_present": "" if record.rim_present is None else record.rim_present,
            "inner_diameter_px": self._fmt(record.inner_diameter_px),
            "outer_diameter_px": self._fmt(record.outer_diameter_px),
            "inner_x1": self._fmt_point(record.inner_a, 0),
            "inner_y1": self._fmt_point(record.inner_a, 1),
            "inner_x2": self._fmt_point(record.inner_b, 0),
            "inner_y2": self._fmt_point(record.inner_b, 1),
            "outer_x1": self._fmt_point(record.outer_a, 0),
            "outer_y1": self._fmt_point(record.outer_a, 1),
            "outer_x2": self._fmt_point(record.outer_b, 0),
            "outer_y2": self._fmt_point(record.outer_b, 1),
            "auto_score": self._fmt(record.auto_score),
            "flags": ";".join(record.flags),
            "notes": record.notes,
        }

    def _record_from_row(self, row: dict[str, str]) -> CraterRecord:
        record = CraterRecord(index=self._parse_int(row.get("index")) or 1)
        status = (row.get("status") or "").strip().lower()
        record.visible = status == "visible"
        record.missing = status == "missing"
        if status not in {"visible", "missing", "unreviewed"}:
            record.visible = self._parse_bool(row.get("visible")) is True
            record.missing = self._parse_bool(row.get("missing")) is True

        record.expected_frame = self._parse_int(row.get("expected_frame_index"))
        if record.expected_frame is None:
            expected_number = self._parse_int(row.get("expected_frame_number"))
            record.expected_frame = None if expected_number is None else expected_number - 1
        record.expected_x = self._parse_float(row.get("expected_x"))
        record.expected_y = self._parse_float(row.get("expected_y"))
        record.measurement_frame = self._parse_int(row.get("measurement_frame_index"))
        if record.measurement_frame is None:
            measurement_number = self._parse_int(row.get("measurement_frame_number"))
            record.measurement_frame = None if measurement_number is None else measurement_number - 1
        record.center_x = self._parse_float(row.get("center_x"))
        record.center_y = self._parse_float(row.get("center_y"))
        record.rim_present = self._parse_bool(row.get("rim_present"))
        record.inner_a = self._parse_point(row.get("inner_x1"), row.get("inner_y1"))
        record.inner_b = self._parse_point(row.get("inner_x2"), row.get("inner_y2"))
        record.outer_a = self._parse_point(row.get("outer_x1"), row.get("outer_y1"))
        record.outer_b = self._parse_point(row.get("outer_x2"), row.get("outer_y2"))
        record.auto_score = self._parse_float(row.get("auto_score"))
        record.flags = [
            flag.strip()
            for flag in (row.get("flags") or "").split(";")
            if flag.strip()
        ]
        record.notes = row.get("notes") or ""
        return record

    def _resume_index(self) -> int:
        for record in self.records:
            if record.missing:
                continue
            if not record.visible:
                return record.index
            if record.center_point() is None:
                return record.index
            if record.rim_present is None:
                return record.index
            if record.inner_diameter_px is None:
                return record.index
            if record.rim_present and record.outer_diameter_px is None:
                return record.index
        return self.records[-1].index

    def _parse_int(self, value: str | None) -> int | None:
        number = self._parse_float(value)
        return None if number is None else int(round(number))

    def _parse_float(self, value: str | None) -> float | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _parse_bool(self, value: str | None) -> bool | None:
        if value is None or str(value).strip() == "":
            return None
        normalized = str(value).strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
        return None

    def _parse_point(self, x_value: str | None, y_value: str | None) -> tuple[float, float] | None:
        x = self._parse_float(x_value)
        y = self._parse_float(y_value)
        if x is None or y is None:
            return None
        return x, y

    def on_table_selection(self) -> None:
        if self._updating_controls:
            return
        selected = self.table.selectedItems()
        if not selected:
            return
        row = selected[0].row()
        self.current_spin.setValue(row + 1)

    def _sync_all(self) -> None:
        self._set_guided_click_target()
        self._sync_controls()
        self._sync_summary()
        self._sync_workflow_panel()
        self._populate_table()
        self._update_overlay()
        self._sync_undo_redo_actions()
        self._sync_total_apply_button()
        self._sync_unsaved_indicator()

    def _sync_controls(self) -> None:
        record = self.current_record()
        self._updating_controls = True
        unlocked = self.unlock_tools_check.isChecked()
        self.visible_check.setChecked(record.visible)
        self.missing_check.setChecked(record.missing)
        if record.rim_present is None:
            self.rim_combo.setCurrentIndex(0)
        elif record.rim_present:
            self.rim_combo.setCurrentIndex(2)
        else:
            self.rim_combo.setCurrentIndex(1)
        self.notes_edit.setPlainText(record.notes)
        self.center_label.setText(
            "Center: -" if record.center_point() is None else f"Center: {record.center_x:.1f}, {record.center_y:.1f}"
        )
        self.inner_label.setText(
            "Inner: -" if record.inner_diameter_px is None else f"Inner: {record.inner_diameter_px:.1f} px"
        )
        self.outer_label.setText(
            "Outer: -" if record.outer_diameter_px is None else f"Outer: {record.outer_diameter_px:.1f} px"
        )
        self.mode_center.setEnabled(unlocked)
        self.mode_inner.setEnabled(unlocked)
        self.mode_outer.setEnabled(unlocked)
        self.visible_check.setEnabled(unlocked)
        self.missing_check.setEnabled(unlocked)
        self.rim_combo.setEnabled(unlocked)
        self._updating_controls = False

    def _sync_summary(self) -> None:
        visible = sum(1 for record in self.records if record.visible)
        missing = sum(1 for record in self.records if record.missing)
        unreviewed = len(self.records) - visible - missing
        self.summary_label.setText(
            f"Visible {visible} | Missing {missing} | Unreviewed {unreviewed}"
        )
        calibration = self.prediction_count()
        if calibration < 3:
            self.calibration_label.setText(f"Prediction calibration: {calibration}/3 visible centers")
            self.scan_position_label.setText("Scan position: not calibrated")
        else:
            self.calibration_label.setText("Prediction active from reviewed centers")
            scan_x, scan_y = self.scan_position()
            source = "manual" if self.scan_position_override is not None else "average"
            self.scan_position_label.setText(f"Scan position ({source}): {scan_x:.1f}, {scan_y:.1f}")
        record = self.current_record()
        has_suggestion = record.expected_frame is not None
        self.go_expected_button.setEnabled(has_suggestion)
        self.follow_predictions_check.setEnabled(calibration >= 3)
        self.show_suggestions_check.setEnabled(calibration >= 3 or has_suggestion)
        self.detect_current_button.setEnabled(self.reader.info is not None)
        self.detect_all_button.setEnabled(self.reader.info is not None and calibration >= 3)

    def _sync_unsaved_indicator(self) -> None:
        if self.csv_needs_export:
            self.unsaved_label.setText("Unsaved changes")
            self.unsaved_label.setStyleSheet("color: #f0c54a; padding-left: 8px;")
        else:
            self.unsaved_label.setText("Saved")
            self.unsaved_label.setStyleSheet("color: #8a93a3; padding-left: 8px;")

    def _sync_workflow_panel(self) -> None:
        record = self.current_record()
        titles = {
            "presence": f"Crater {record.index}: inner diameter",
            "center": f"Crater {record.index}: inner diameter",
            "rim": f"Crater {record.index}: rim",
            "inner": f"Crater {record.index}: inner diameter",
            "outer": f"Crater {record.index}: outer diameter",
            "review_pause": f"Crater {record.index}: quick review",
            "complete": "Review complete",
        }
        calibration = self.prediction_count()
        manual_prefix = "" if calibration >= 3 else f"Manual calibration {calibration}/3. "
        instructions = {
            "presence": manual_prefix + "Click two opposite inner crater edges. The midpoint becomes the measured center. Use Mark Missing only if the crater is not visible.",
            "center": "Click two opposite inner crater edges. The midpoint becomes the measured center.",
            "rim": "Rim defaults to no. Click Rim Present only if a rim is visible.",
            "inner": "No rim is assumed. Click Rim Present only if needed, otherwise click two opposite inner crater edges.",
            "outer": "Click two opposite outer rim edges.",
            "review_pause": "Measurement saved. Check the overlay briefly; use Undo Last if it looks wrong.",
            "complete": "All crater positions have been reviewed. Use Export CSV / Save Progress in the toolbar.",
        }
        self.workflow_title.setText(titles.get(self.workflow_step, "Guided review"))
        self.workflow_instruction.setText(instructions.get(self.workflow_step, ""))

        active_block = "inner" if self.workflow_step == "review_pause" else "presence" if self.workflow_step == "center" else self.workflow_step
        completed = self._completed_workflow_blocks(record)
        for key, block in self.step_blocks.items():
            if key == active_block:
                block.setStyleSheet(
                    "background: #1f657d; border: 1px solid #5cc8ff; border-radius: 5px; font-weight: 600;"
                )
            elif key in completed:
                block.setStyleSheet(
                    "background: #244733; border: 1px solid #4b8a5c; border-radius: 5px; color: #d8f6dd;"
                )
            elif key == "outer" and record.rim_present is False:
                block.setStyleSheet(
                    "background: #1b1f27; border: 1px solid #2b303a; border-radius: 5px; color: #6d7480;"
                )
            else:
                block.setStyleSheet(
                    "background: #242a35; border: 1px solid #343a46; border-radius: 5px; color: #b8c0cc;"
                )

        is_presence = self.workflow_step in {"presence", "center"}
        is_rim = self.workflow_step in {"presence", "center", "rim", "inner"}
        unlocked = self.unlock_tools_check.isChecked()
        self.presence_actions_label.setEnabled(is_presence)
        self.present_button.setEnabled(is_presence and record.center_point() is not None)
        self.absent_button.setEnabled(is_presence)
        self.tool_actions_label.setEnabled(self.workflow_step in {"presence", "center", "inner", "outer"})
        self.arm_center_button.setEnabled(unlocked)
        self.arm_inner_button.setEnabled(unlocked)
        self.arm_outer_button.setEnabled(unlocked)
        self.rim_actions_label.setEnabled(is_rim)
        self.no_rim_button.setEnabled(is_rim and record.rim_present is True)
        self.yes_rim_button.setEnabled(is_rim and record.rim_present is not True)

    def _completed_workflow_blocks(self, record: CraterRecord) -> set[str]:
        completed: set[str] = set()
        if record.visible or record.missing or record.center_point() is not None:
            completed.add("presence")
        if record.rim_present is not None:
            completed.add("rim")
        if record.inner_diameter_px is not None:
            completed.add("inner")
        if record.rim_present is False or record.outer_diameter_px is not None:
            completed.add("outer")
        return completed

    def _populate_table(self) -> None:
        self._updating_controls = True
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            rim = "unknown" if record.rim_present is None else ("yes" if record.rim_present else "no")
            values = [
                str(record.index),
                record.status_text(),
                "" if record.expected_frame is None else str(record.expected_frame + 1),
                rim,
                self._fmt(record.inner_diameter_px),
                self._fmt(record.outer_diameter_px),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))
        self.table.selectRow(self.current_index - 1)
        self._updating_controls = False

    def _update_overlay(self) -> None:
        if not self.records:
            return
        record = self.current_record()
        inner = None
        outer = None
        if record.inner_a is not None and record.inner_b is not None:
            inner = (record.inner_a, record.inner_b)
        if record.outer_a is not None and record.outer_b is not None:
            outer = (record.outer_a, record.outer_b)
        expected = self._overlay_expected_point(record)
        zoom_focus = record.center_point() or expected or self.last_click
        self.canvas.set_zoom(
            self.zoom_check.isChecked(),
            zoom_focus,
            self.zoom_size_spin.value(),
        )
        self.canvas.set_overlay(
            expected,
            record.center_point(),
            inner,
            outer,
            self.pending_point,
            f"#{record.index}",
            self._video_instruction(record),
        )

    def _video_instruction(self, record: CraterRecord) -> str:
        if self.workflow_step == "complete":
            return "Review complete. Export or analyze the CSV from the toolbar."
        if self.workflow_step == "review_pause":
            return f"Crater {record.index}: measurement saved. Quick final check; Undo Last if needed."
        if self.pending_point is not None:
            return f"Crater {record.index}: first edge set. Click the opposite edge, or press Esc to cancel."
        if self.workflow_step in {"presence", "center", "inner"}:
            return f"Crater {record.index}: click two opposite inner edges. M = missing, R = rim present."
        if self.workflow_step == "outer":
            return f"Crater {record.index}: click two opposite outer rim edges. Esc cancels current measurement."
        if self.workflow_step == "rim":
            return f"Crater {record.index}: R toggles rim present. M marks missing."
        return f"Crater {record.index}: follow Guided Review."

    def _overlay_expected_point(self, record: CraterRecord) -> tuple[float, float] | None:
        if not self.show_suggestions_check.isChecked():
            return None
        expected = record.expected_point()
        if expected is None or record.expected_frame is None:
            return expected
        if self.prediction_count() < 3:
            return expected
        visible_frames = [
            record.measurement_frame
            for record in self.records
            if record.measurement_frame is not None and record.center_point() is not None
        ]
        if len(visible_frames) < 2:
            tolerance = 2
        else:
            visible_frames.sort()
            gaps = [
                abs(visible_frames[index + 1] - visible_frames[index])
                for index in range(len(visible_frames) - 1)
                if visible_frames[index + 1] != visible_frames[index]
            ]
            tolerance = max(2, round((sum(gaps) / len(gaps)) / 2)) if gaps else 2
        if abs(self.frame_index - record.expected_frame) > tolerance:
            return None
        return expected

    def _fmt(self, value: float | int | None) -> str:
        if value is None:
            return ""
        return f"{float(value):.3f}".rstrip("0").rstrip(".")

    def _fmt_point(self, point: tuple[float, float] | None, offset: int) -> str:
        if point is None:
            return ""
        return self._fmt(point[offset])


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(
        """
        QWidget {
            background: #151820;
            color: #e6e8ee;
            font-size: 13px;
        }
        QMainWindow, QToolBar {
            background: #151820;
        }
        QGroupBox {
            border: 1px solid #343a46;
            border-radius: 6px;
            margin-top: 10px;
            padding: 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
            color: #b8c0cc;
        }
        QPushButton, QToolButton {
            background: #242a35;
            border: 1px solid #3a4352;
            border-radius: 5px;
            padding: 6px 10px;
        }
        QPushButton:hover, QToolButton:hover {
            background: #2d3442;
        }
        QPushButton:pressed, QToolButton:pressed {
            background: #1f657d;
        }
        QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTableWidget {
            background: #10131a;
            border: 1px solid #343a46;
            border-radius: 4px;
            selection-background-color: #1f657d;
        }
        QHeaderView::section {
            background: #242a35;
            color: #e6e8ee;
            border: 1px solid #343a46;
            padding: 4px;
        }
        QSlider::groove:horizontal {
            height: 6px;
            background: #343a46;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #5cc8ff;
            width: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }
        #statusLabel {
            color: #aeb7c5;
            padding: 4px;
        }
        """
    )


def main() -> None:
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())
