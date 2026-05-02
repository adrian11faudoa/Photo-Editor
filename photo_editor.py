#!/usr/bin/env python3
"""
PhotoCrop Studio - A modern desktop photo editor with crop functionality.
Requires: pip install Pillow PyQt5
Optional HEIC support: pip install pillow-heif
"""

import sys
import os
from pathlib import Path
from typing import Optional, List, Tuple

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
        QPushButton, QLabel, QFileDialog, QStatusBar, QSizePolicy,
        QButtonGroup, QToolButton, QFrame, QMessageBox, QProgressDialog,
        QShortcut, QScrollArea, QSplitter, QSlider, QSpacerItem,
        QComboBox
    )
    from PyQt5.QtCore import (
        Qt, QRect, QPoint, QSize, QThread, pyqtSignal, QTimer, QRectF
    )
    from PyQt5.QtGui import (
        QPixmap, QPainter, QColor, QPen, QBrush, QFont, QKeySequence,
        QCursor, QImage, QPalette, QIcon, QFontDatabase, QLinearGradient
    )
except ImportError:
    print("PyQt5 not found. Installing...")
    os.system(f"{sys.executable} -m pip install PyQt5 --quiet")
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
        QPushButton, QLabel, QFileDialog, QStatusBar, QSizePolicy,
        QButtonGroup, QToolButton, QFrame, QMessageBox, QProgressDialog,
        QShortcut, QScrollArea, QSplitter, QSlider, QSpacerItem,
        QComboBox
    )
    from PyQt5.QtCore import (
        Qt, QRect, QPoint, QSize, QThread, pyqtSignal, QTimer, QRectF
    )
    from PyQt5.QtGui import (
        QPixmap, QPainter, QColor, QPen, QBrush, QFont, QKeySequence,
        QCursor, QImage, QPalette, QIcon, QFontDatabase, QLinearGradient
    )

try:
    from PIL import Image
except ImportError:
    os.system(f"{sys.executable} -m pip install Pillow --quiet")
    from PIL import Image

# Try HEIC support
HEIC_SUPPORT = False
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    pass

SUPPORTED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp', '.heic', '.heif']

# ─── Color Palette ────────────────────────────────────────────────────────────
BG_DARK      = "#0f0f10"
BG_PANEL     = "#1a1a1e"
BG_CARD      = "#242428"
BG_HOVER     = "#2e2e34"
ACCENT_BLUE  = "#4a9eff"
ACCENT_CYAN  = "#00d4ff"
TEXT_PRIMARY = "#f0f0f2"
TEXT_MUTED   = "#6e6e7a"
BORDER       = "#2a2a30"
DANGER       = "#ff5555"
SUCCESS      = "#50fa7b"
OVERLAY_CLR  = QColor(0, 0, 0, 140)

HANDLE_SIZE = 10
EDGE_TOLERANCE = 12

# ─── Crop Canvas Widget ────────────────────────────────────────────────────────
class CropCanvas(QWidget):
    crop_changed = pyqtSignal(QRect)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

        self._pixmap: Optional[QPixmap] = None
        self._img_rect = QRect()       # where image is rendered on canvas
        self._crop_rect = QRect()      # crop rect in canvas coords
        self._scale = 1.0
        self._offset = QPoint(0, 0)

        # Interaction state
        self._drag_mode = None         # None | 'create' | 'move' | 'resize'
        self._drag_start = QPoint()
        self._drag_crop_start = QRect()
        self._resize_handle = None     # 'tl','tc','tr','ml','mr','bl','bc','br'

        self._aspect_ratio: Optional[float] = None  # None = free
        self._pan_start = QPoint()
        self._pan_offset = QPoint(0, 0)
        self._panning = False
        self._zoom = 1.0
        self._zoom_center = QPoint()

    # ── Public API ────────────────────────────────────────────────────────────
    def set_image(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self._zoom = 1.0
        self._pan_offset = QPoint(0, 0)
        self._crop_rect = QRect()
        self._fit_image()
        self.update()

    def set_aspect_ratio(self, ratio: Optional[float]):
        self._aspect_ratio = ratio
        self.update()

    def reset_crop(self):
        self._crop_rect = QRect()
        self.update()

    def get_crop_in_image_coords(self) -> Optional[QRect]:
        """Return crop rect in original image pixel coordinates."""
        if self._crop_rect.isNull() or not self._pixmap:
            return None
        ir = self._img_rect
        if ir.width() == 0 or ir.height() == 0:
            return None
        sx = self._pixmap.width() / ir.width()
        sy = self._pixmap.height() / ir.height()
        cr = self._crop_rect.intersected(ir)
        x = int((cr.left() - ir.left()) * sx)
        y = int((cr.top() - ir.top()) * sy)
        w = int(cr.width() * sx)
        h = int(cr.height() * sy)
        return QRect(x, y, max(1, w), max(1, h))

    def has_crop(self) -> bool:
        return not self._crop_rect.isNull() and self._crop_rect.width() > 4

    # ── Layout ────────────────────────────────────────────────────────────────
    def _fit_image(self):
        if not self._pixmap:
            return
        pw, ph = self._pixmap.width(), self._pixmap.height()
        cw, ch = self.width(), self.height()
        if cw <= 0 or ch <= 0:
            return
        scale = min(cw / pw, ch / ph) * 0.9
        self._scale = scale
        iw, ih = int(pw * scale), int(ph * scale)
        x = (cw - iw) // 2
        y = (ch - ih) // 2
        self._img_rect = QRect(x, y, iw, ih)

    def resizeEvent(self, event):
        self._fit_image()
        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor(BG_DARK))

        if not self._pixmap:
            painter.setPen(QColor(TEXT_MUTED))
            painter.setFont(QFont("Arial", 14))
            painter.drawText(self.rect(), Qt.AlignCenter, "Open a folder to begin")
            return

        # Draw image
        painter.drawPixmap(self._img_rect, self._pixmap)

        # Draw overlay + crop
        if not self._crop_rect.isNull() and self._crop_rect.width() > 2:
            cr = self._crop_rect.intersected(self._img_rect)

            # Dark overlay (4 rects around crop)
            painter.fillRect(
                self._img_rect.left(), self._img_rect.top(),
                self._img_rect.width(), cr.top() - self._img_rect.top(),
                OVERLAY_CLR)
            painter.fillRect(
                self._img_rect.left(), cr.bottom(),
                self._img_rect.width(), self._img_rect.bottom() - cr.bottom(),
                OVERLAY_CLR)
            painter.fillRect(
                self._img_rect.left(), cr.top(),
                cr.left() - self._img_rect.left(), cr.height(),
                OVERLAY_CLR)
            painter.fillRect(
                cr.right(), cr.top(),
                self._img_rect.right() - cr.right(), cr.height(),
                OVERLAY_CLR)

            # Crop border
            pen = QPen(QColor(ACCENT_BLUE), 1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(cr)

            # Rule-of-thirds grid lines
            pen2 = QPen(QColor(255, 255, 255, 50), 0.7, Qt.DashLine)
            painter.setPen(pen2)
            for i in (1, 2):
                x = cr.left() + cr.width() * i // 3
                painter.drawLine(x, cr.top(), x, cr.bottom())
                y = cr.top() + cr.height() * i // 3
                painter.drawLine(cr.left(), y, cr.right(), y)

            # Corner & edge handles
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(ACCENT_BLUE))
            for hx, hy in self._handle_positions(cr):
                painter.drawRect(hx - HANDLE_SIZE//2, hy - HANDLE_SIZE//2, HANDLE_SIZE, HANDLE_SIZE)

        elif self._drag_mode == 'create' and not self._crop_rect.isNull():
            pen = QPen(QColor(ACCENT_BLUE), 1.5, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._crop_rect)

        painter.end()

    def _handle_positions(self, r: QRect) -> List[Tuple[int, int]]:
        cx, cy = r.center().x(), r.center().y()
        return [
            (r.left(), r.top()), (cx, r.top()), (r.right(), r.top()),
            (r.left(), cy),                      (r.right(), cy),
            (r.left(), r.bottom()), (cx, r.bottom()), (r.right(), r.bottom()),
        ]

    def _handle_names(self):
        return ['tl', 'tc', 'tr', 'ml', 'mr', 'bl', 'bc', 'br']

    def _hit_handle(self, pos: QPoint, r: QRect) -> Optional[str]:
        positions = self._handle_positions(r)
        names = self._handle_names()
        for (hx, hy), name in zip(positions, names):
            if abs(pos.x() - hx) <= EDGE_TOLERANCE and abs(pos.y() - hy) <= EDGE_TOLERANCE:
                return name
        return None

    def _cursor_for_handle(self, handle: str) -> Qt.CursorShape:
        return {
            'tl': Qt.SizeFDiagCursor, 'br': Qt.SizeFDiagCursor,
            'tr': Qt.SizeBDiagCursor, 'bl': Qt.SizeBDiagCursor,
            'tc': Qt.SizeVerCursor,   'bc': Qt.SizeVerCursor,
            'ml': Qt.SizeHorCursor,   'mr': Qt.SizeHorCursor,
        }.get(handle, Qt.SizeAllCursor)

    # ── Mouse Events ──────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        pos = event.pos()

        # Middle-click or Space+drag = pan (handled via keyboard flag)
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = pos
            self.setCursor(Qt.ClosedHandCursor)
            return

        if event.button() == Qt.LeftButton:
            cr = self._crop_rect.intersected(self._img_rect) if not self._crop_rect.isNull() else QRect()

            handle = self._hit_handle(pos, cr) if not cr.isNull() else None
            if handle:
                self._drag_mode = 'resize'
                self._resize_handle = handle
                self._drag_start = pos
                self._drag_crop_start = QRect(cr)
                return

            if not cr.isNull() and cr.contains(pos):
                self._drag_mode = 'move'
                self._drag_start = pos
                self._drag_crop_start = QRect(self._crop_rect)
                self.setCursor(Qt.ClosedHandCursor)
                return

            if self._img_rect.contains(pos):
                self._drag_mode = 'create'
                self._drag_start = pos
                self._crop_rect = QRect(pos, pos)

    def mouseMoveEvent(self, event):
        pos = event.pos()

        if self._panning:
            delta = pos - self._pan_start
            self._pan_start = pos
            self._img_rect.translate(delta)
            self.update()
            return

        if self._drag_mode == 'create':
            p1, p2 = self._drag_start, pos
            r = QRect(p1, p2).normalized().intersected(self._img_rect)
            if self._aspect_ratio:
                w = r.width()
                h = int(w / self._aspect_ratio)
                if p2.y() < p1.y():
                    r.setTop(r.bottom() - h)
                else:
                    r.setBottom(r.top() + h)
            self._crop_rect = r
            self.update()
            return

        if self._drag_mode == 'move':
            delta = pos - self._drag_start
            new_rect = QRect(
                self._drag_crop_start.left() + delta.x(),
                self._drag_crop_start.top() + delta.y(),
                self._drag_crop_start.width(),
                self._drag_crop_start.height()
            )
            # Clamp to image
            if new_rect.left() < self._img_rect.left():
                new_rect.moveLeft(self._img_rect.left())
            if new_rect.top() < self._img_rect.top():
                new_rect.moveTop(self._img_rect.top())
            if new_rect.right() > self._img_rect.right():
                new_rect.moveRight(self._img_rect.right())
            if new_rect.bottom() > self._img_rect.bottom():
                new_rect.moveBottom(self._img_rect.bottom())
            self._crop_rect = new_rect
            self.update()
            return

        if self._drag_mode == 'resize':
            self._resize_crop(pos)
            self.update()
            return

        # Hover cursor
        cr = self._crop_rect.intersected(self._img_rect) if not self._crop_rect.isNull() else QRect()
        if not cr.isNull():
            handle = self._hit_handle(pos, cr)
            if handle:
                self.setCursor(self._cursor_for_handle(handle))
                return
            if cr.contains(pos):
                self.setCursor(Qt.SizeAllCursor)
                return
        self.setCursor(Qt.CrossCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CrossCursor)
            return
        if event.button() == Qt.LeftButton:
            if self._drag_mode == 'create' and self._crop_rect.width() < 5:
                self._crop_rect = QRect()
            self._drag_mode = None
            self.setCursor(Qt.CrossCursor)
            self.crop_changed.emit(self._crop_rect)
            self.update()

    def wheelEvent(self, event):
        if not self._pixmap:
            return
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        center = event.pos()
        # Scale img_rect around cursor
        old = self._img_rect
        nw = int(old.width() * factor)
        nh = int(old.height() * factor)
        nx = center.x() - int((center.x() - old.left()) * factor)
        ny = center.y() - int((center.y() - old.top()) * factor)
        self._img_rect = QRect(nx, ny, nw, nh)
        # Scale crop rect proportionally
        if not self._crop_rect.isNull():
            fw = nw / old.width() if old.width() else 1
            fh = nh / old.height() if old.height() else 1
            cx = nx + int((self._crop_rect.left() - old.left()) * fw)
            cy = ny + int((self._crop_rect.top() - old.top()) * fh)
            cw = int(self._crop_rect.width() * fw)
            ch = int(self._crop_rect.height() * fh)
            self._crop_rect = QRect(cx, cy, cw, ch)
        self.update()

    def _resize_crop(self, pos: QPoint):
        r = QRect(self._drag_crop_start)
        h = self._resize_handle
        ir = self._img_rect

        if 'l' in h:
            r.setLeft(max(ir.left(), min(pos.x(), r.right() - 4)))
        if 'r' in h:
            r.setRight(min(ir.right(), max(pos.x(), r.left() + 4)))
        if 't' in h:
            r.setTop(max(ir.top(), min(pos.y(), r.bottom() - 4)))
        if 'b' in h:
            r.setBottom(min(ir.bottom(), max(pos.y(), r.top() + 4)))
        if 'c' in h:
            if h == 'tc' or h == 'bc':
                pass  # already handled t/b
            elif h == 'ml' or h == 'mr':
                pass

        if self._aspect_ratio and r.height() > 0:
            if 'l' in h or 'r' in h:
                r.setHeight(int(r.width() / self._aspect_ratio))
            else:
                r.setWidth(int(r.height() * self._aspect_ratio))

        self._crop_rect = r


# ─── Main Window ──────────────────────────────────────────────────────────────
class PhotoEditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Crop Studio")
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)

        self._folder: Optional[Path] = None
        self._images: List[Path] = []
        self._index: int = 0
        self._pil_cache: dict = {}      # path -> PIL.Image (lazy)
        self._rotations: dict = {}      # path -> cumulative rotation degrees (0/90/180/270)

        self._setup_style()
        self._build_ui()
        self._connect_shortcuts()

    # ── Style ─────────────────────────────────────────────────────────────────
    def _setup_style(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {BG_DARK};
                color: {TEXT_PRIMARY};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }}
            QPushButton {{
                background: {BG_CARD};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 7px 18px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {BG_HOVER};
                border-color: {ACCENT_BLUE};
            }}
            QPushButton:pressed {{
                background: {BG_DARK};
            }}
            QPushButton#accent {{
                background: {ACCENT_BLUE};
                color: #000;
                font-weight: 600;
                border: none;
            }}
            QPushButton#accent:hover {{
                background: {ACCENT_CYAN};
            }}
            QPushButton#danger {{
                background: transparent;
                color: {DANGER};
                border-color: {DANGER};
            }}
            QPushButton#danger:hover {{
                background: {DANGER};
                color: #000;
            }}
            QPushButton#nav {{
                background: {BG_PANEL};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 16px;
            }}
            QPushButton#nav:hover {{
                background: {BG_HOVER};
                border-color: {ACCENT_BLUE};
                color: {ACCENT_BLUE};
            }}
            QPushButton#nav:disabled {{
                color: {TEXT_MUTED};
                border-color: {BORDER};
            }}
            QPushButton#toggle {{
                background: transparent;
                border: 1px solid {BORDER};
                border-radius: 5px;
                padding: 5px 14px;
                font-size: 12px;
                color: {TEXT_MUTED};
            }}
            QPushButton#toggle:checked {{
                background: {BG_HOVER};
                border-color: {ACCENT_BLUE};
                color: {ACCENT_BLUE};
            }}
            QLabel#filename {{
                color: {TEXT_PRIMARY};
                font-size: 14px;
                font-weight: 500;
            }}
            QLabel#info {{
                color: {TEXT_MUTED};
                font-size: 12px;
            }}
            QLabel#badge {{
                background: {BG_CARD};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 2px 10px;
                color: {TEXT_MUTED};
                font-size: 12px;
            }}
            QFrame#topbar {{
                background: {BG_PANEL};
                border-bottom: 1px solid {BORDER};
            }}
            QFrame#bottombar {{
                background: {BG_PANEL};
                border-top: 1px solid {BORDER};
            }}
            QStatusBar {{
                background: {BG_PANEL};
                color: {TEXT_MUTED};
                border-top: 1px solid {BORDER};
                font-size: 11px;
            }}
        """)

    # ── UI Construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._build_topbar())
        main_layout.addWidget(self._build_canvas_area(), 1)
        main_layout.addWidget(self._build_bottombar())

        self.statusBar().showMessage("Ready — open a folder to begin")

    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(56)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        # Left: Open
        self._btn_open = QPushButton("📁  Open Folder")
        self._btn_open.clicked.connect(self._open_folder)
        layout.addWidget(self._btn_open)

        layout.addSpacing(16)

        # Aspect ratio toggles
        lbl = QLabel("Ratio:")
        lbl.setObjectName("info")
        layout.addWidget(lbl)

        self._ratio_free = QPushButton("Free")
        self._ratio_free.setObjectName("toggle")
        self._ratio_free.setCheckable(True)
        self._ratio_free.setChecked(True)
        self._ratio_free.clicked.connect(lambda: self._set_ratio(None))

        self._ratio_square = QPushButton("1:1")
        self._ratio_square.setObjectName("toggle")
        self._ratio_square.setCheckable(True)
        self._ratio_square.clicked.connect(lambda: self._set_ratio(1.0))

        self._ratio_169 = QPushButton("16:9")
        self._ratio_169.setObjectName("toggle")
        self._ratio_169.setCheckable(True)
        self._ratio_169.clicked.connect(lambda: self._set_ratio(16/9))

        self._ratio_43 = QPushButton("4:3")
        self._ratio_43.setObjectName("toggle")
        self._ratio_43.setCheckable(True)
        self._ratio_43.clicked.connect(lambda: self._set_ratio(4/3))

        for btn in [self._ratio_free, self._ratio_square, self._ratio_169, self._ratio_43]:
            layout.addWidget(btn)

        layout.addSpacing(16)

        # Rotation buttons
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color: {BORDER};")
        layout.addWidget(sep)

        layout.addSpacing(4)

        rot_lbl = QLabel("Rotate:")
        rot_lbl.setObjectName("info")
        layout.addWidget(rot_lbl)

        self._btn_rot_ccw = QPushButton("↺ −90°")
        self._btn_rot_ccw.setToolTip("Rotate 90° counter-clockwise  [Q]")
        self._btn_rot_ccw.clicked.connect(lambda: self._rotate_current(-90))
        self._btn_rot_ccw.setEnabled(False)
        layout.addWidget(self._btn_rot_ccw)

        self._btn_rot_cw = QPushButton("↻ +90°")
        self._btn_rot_cw.setToolTip("Rotate 90° clockwise  [E]")
        self._btn_rot_cw.clicked.connect(lambda: self._rotate_current(90))
        self._btn_rot_cw.setEnabled(False)
        layout.addWidget(self._btn_rot_cw)

        layout.addStretch()

        # Format selector
        fmt_sep = QFrame()
        fmt_sep.setFrameShape(QFrame.VLine)
        fmt_sep.setStyleSheet(f"color: {BORDER};")
        layout.addWidget(fmt_sep)

        fmt_lbl = QLabel("Save as:")
        fmt_lbl.setObjectName("info")
        layout.addWidget(fmt_lbl)

        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(["Original", "JPG", "PNG", "WEBP", "BMP", "TIFF"])
        self._fmt_combo.setFixedWidth(95)
        self._fmt_combo.setToolTip("Output format when saving")
        self._fmt_combo.setStyleSheet(f"""
            QComboBox {{
                background: {BG_CARD};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QComboBox:hover {{ border-color: {ACCENT_BLUE}; }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {BG_CARD};
                color: {TEXT_PRIMARY};
                selection-background-color: {BG_HOVER};
                border: 1px solid {BORDER};
            }}
        """)
        layout.addWidget(self._fmt_combo)
        layout.addSpacing(8)

        # Right: Reset + Save buttons
        self._btn_reset = QPushButton("↺  Reset")
        self._btn_reset.setObjectName("danger")
        self._btn_reset.clicked.connect(self._reset_crop)
        self._btn_reset.setEnabled(False)

        self._btn_save = QPushButton("💾  Save")
        self._btn_save.setObjectName("accent")
        self._btn_save.clicked.connect(self._save_current)
        self._btn_save.setEnabled(False)

        self._btn_save_all = QPushButton("Save All")
        self._btn_save_all.clicked.connect(self._save_all)
        self._btn_save_all.setEnabled(False)

        layout.addWidget(self._btn_reset)
        layout.addSpacing(8)
        layout.addWidget(self._btn_save)
        layout.addWidget(self._btn_save_all)

        return bar

    def _build_canvas_area(self):
        self._canvas = CropCanvas()
        self._canvas.crop_changed.connect(self._on_crop_changed)
        return self._canvas

    def _build_bottombar(self):
        bar = QFrame()
        bar.setObjectName("bottombar")
        bar.setFixedHeight(60)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(10)

        self._btn_prev = QPushButton("←")
        self._btn_prev.setObjectName("nav")
        self._btn_prev.setFixedWidth(60)
        self._btn_prev.clicked.connect(self._prev_image)
        self._btn_prev.setEnabled(False)

        self._lbl_filename = QLabel("No folder open")
        self._lbl_filename.setObjectName("filename")
        self._lbl_filename.setAlignment(Qt.AlignCenter)

        self._btn_next = QPushButton("→")
        self._btn_next.setObjectName("nav")
        self._btn_next.setFixedWidth(60)
        self._btn_next.clicked.connect(self._next_image)
        self._btn_next.setEnabled(False)

        self._lbl_counter = QLabel("")
        self._lbl_counter.setObjectName("badge")
        self._lbl_counter.setAlignment(Qt.AlignCenter)
        self._lbl_counter.setMinimumWidth(80)

        self._lbl_crop_info = QLabel("")
        self._lbl_crop_info.setObjectName("info")
        self._lbl_crop_info.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._lbl_crop_info.setMinimumWidth(160)

        layout.addWidget(self._btn_prev)
        layout.addWidget(self._lbl_filename, 1)
        layout.addWidget(self._btn_next)
        layout.addSpacing(20)
        layout.addWidget(self._lbl_counter)
        layout.addSpacing(20)
        layout.addWidget(self._lbl_crop_info)

        return bar

    # ── Shortcuts ─────────────────────────────────────────────────────────────
    def _connect_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Left), self, self._prev_image)
        QShortcut(QKeySequence(Qt.Key_Right), self, self._next_image)
        QShortcut(QKeySequence("Ctrl+S"), self, self._save_current)
        QShortcut(QKeySequence("Ctrl+O"), self, self._open_folder)
        QShortcut(QKeySequence("Escape"), self, self._reset_crop)
        QShortcut(QKeySequence("Ctrl+Z"), self, self._reset_crop)
        QShortcut(QKeySequence("Q"), self, lambda: self._rotate_current(-90))
        QShortcut(QKeySequence("E"), self, lambda: self._rotate_current(90))

    # ── Actions ───────────────────────────────────────────────────────────────
    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if not folder:
            return
        self._folder = Path(folder)
        self._images = sorted(
            [p for p in self._folder.iterdir()
             if p.suffix.lower() in SUPPORTED_EXTENSIONS]
        )
        if not self._images:
            QMessageBox.information(self, "No Images",
                "No supported images found in this folder.")
            return
        self._index = 0
        self._pil_cache.clear()
        self._rotations.clear()
        self._load_current()

    def _load_current(self):
        if not self._images:
            return
        path = self._images[self._index]
        pixmap = self._path_to_pixmap(path)
        if pixmap:
            self._canvas.set_image(pixmap)
            self._canvas.reset_crop()
        name = path.name
        if len(name) > 50:
            name = "…" + name[-47:]
        self._lbl_filename.setText(name)
        total = len(self._images)
        self._lbl_counter.setText(f"{self._index + 1} / {total}")
        self._btn_prev.setEnabled(self._index > 0)
        self._btn_next.setEnabled(self._index < total - 1)
        self._btn_save.setEnabled(True)
        self._btn_reset.setEnabled(False)
        self._btn_save_all.setEnabled(True)
        self._btn_rot_ccw.setEnabled(True)
        self._btn_rot_cw.setEnabled(True)
        self._lbl_crop_info.setText("")
        ext = path.suffix.upper().lstrip(".")
        self.statusBar().showMessage(f"{path.name}  ·  {ext}  ·  Use ← → to navigate, drag to crop")

    def _path_to_pixmap(self, path: Path) -> Optional[QPixmap]:
        try:
            if path.suffix.lower() in ('.heic', '.heif') and not HEIC_SUPPORT:
                QMessageBox.warning(self, "HEIC Not Supported",
                    "HEIC/HEIF support requires pillow-heif.\n\n"
                    "Run:  pip install pillow-heif\n\nThen restart the app.")
                return None
            img = Image.open(str(path))
            # Apply any pending rotation for this image
            rot = self._rotations.get(str(path), 0)
            if rot:
                img = img.rotate(-rot, expand=True)  # PIL rotates CCW, so negate
            img = img.convert("RGBA")
            data = img.tobytes("raw", "RGBA")
            qimg = QImage(data, img.width, img.height, QImage.Format_RGBA8888)
            return QPixmap.fromImage(qimg)
        except Exception as e:
            self.statusBar().showMessage(f"Error loading {path.name}: {e}")
            return None

    def _prev_image(self):
        if self._index > 0:
            self._index -= 1
            self._load_current()

    def _next_image(self):
        if self._index < len(self._images) - 1:
            self._index += 1
            self._load_current()

    def _set_ratio(self, ratio: Optional[float]):
        self._canvas.set_aspect_ratio(ratio)
        for btn, r in [
            (self._ratio_free, None),
            (self._ratio_square, 1.0),
            (self._ratio_169, 16/9),
            (self._ratio_43, 4/3),
        ]:
            btn.setChecked(r == ratio)

    def _reset_crop(self):
        self._canvas.reset_crop()
        self._btn_reset.setEnabled(False)
        self._lbl_crop_info.setText("")

    def _rotate_current(self, degrees: int):
        """Rotate the current image by +90 or -90 degrees and refresh view."""
        if not self._images:
            return
        path = str(self._images[self._index])
        current = self._rotations.get(path, 0)
        self._rotations[path] = (current + degrees) % 360
        # Reload canvas with new rotation (reset crop since dims may swap)
        pixmap = self._path_to_pixmap(self._images[self._index])
        if pixmap:
            self._canvas.set_image(pixmap)
            self._canvas.reset_crop()
        rot = self._rotations[path]
        self.statusBar().showMessage(
            f"{self._images[self._index].name}  ·  Rotation: {rot}°  (not saved yet — use Save to apply)"
        )

    def _on_crop_changed(self, rect: QRect):
        has = self._canvas.has_crop()
        self._btn_reset.setEnabled(has)
        if has:
            cr = self._canvas.get_crop_in_image_coords()
            if cr:
                self._lbl_crop_info.setText(f"Crop: {cr.width()} × {cr.height()} px")
        else:
            self._lbl_crop_info.setText("")

    def _save_current(self):
        if not self._images:
            return
        path = self._images[self._index]
        crop = self._canvas.get_crop_in_image_coords()
        self._do_save(path, path, crop, reload_view=True)

    def _do_save(self, src: Path, dst: Path, crop: Optional[QRect], reload_view: bool = False):
        # Format map: combo label -> (extension, PIL format, extra save kwargs)
        FMT_MAP = {
            "JPG":  (".jpg",  "JPEG", {"quality": 92}),
            "PNG":  (".png",  "PNG",  {}),
            "WEBP": (".webp", "WEBP", {"quality": 90, "method": 6}),
            "BMP":  (".bmp",  "BMP",  {}),
            "TIFF": (".tiff", "TIFF", {}),
        }
        chosen = self._fmt_combo.currentText() if hasattr(self, '_fmt_combo') else "Original"
        src_ext = src.suffix.lower()

        try:
            if src_ext in ('.heic', '.heif') and not HEIC_SUPPORT:
                QMessageBox.warning(self, "HEIC Not Supported",
                    "Install pillow-heif to open/save HEIC files:\n  pip install pillow-heif")
                return

            img = Image.open(str(src))

            # Apply rotation
            rot = self._rotations.get(str(src), 0)
            if rot:
                img = img.rotate(-rot, expand=True)

            # Apply crop
            if crop and crop.width() > 0 and crop.height() > 0:
                img = img.crop((crop.left(), crop.top(),
                                crop.left() + crop.width(),
                                crop.top() + crop.height()))

            # Determine output format
            if chosen != "Original":
                ext, pil_fmt, save_kwargs = FMT_MAP[chosen]
            elif src_ext in ('.heic', '.heif'):
                # HEIC can't be written back easily — convert to JPG by default
                ext, pil_fmt, save_kwargs = ".jpg", "JPEG", {"quality": 92}
            else:
                ext      = src_ext
                pil_fmt  = None  # PIL auto-detects from extension
                save_kwargs = {}

            new_dst = dst.with_suffix(ext)

            # Mode conversion for formats that don't support alpha
            if pil_fmt in ("JPEG",) or (pil_fmt is None and ext in ('.jpg', '.jpeg')):
                if img.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    alpha = img.convert("RGBA").split()[-1]
                    bg.paste(img.convert("RGB"), mask=alpha)
                    img = bg
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                if not save_kwargs:
                    save_kwargs = {"quality": 92}
                img.save(str(new_dst), "JPEG", **save_kwargs)
            elif pil_fmt:
                img.save(str(new_dst), pil_fmt, **save_kwargs)
            else:
                img.save(str(new_dst), **save_kwargs)

            # If filename changed (e.g. .heic -> .jpg), update the image list
            if reload_view and new_dst != src:
                # Delete old file if overwriting same folder
                if dst.parent == src.parent and new_dst != src:
                    try:
                        src.unlink()
                    except Exception:
                        pass
                self._images[self._index] = new_dst

            # Clear baked-in rotation
            if reload_view:
                self._rotations.pop(str(src), None)

            self.statusBar().showMessage(f"✓ Saved: {new_dst.name}  [{new_dst.suffix.upper().lstrip('.')}]")

            if reload_view:
                self._load_current()

        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _save_all(self):
        if not self._images:
            return
        out_folder = QFileDialog.getExistingDirectory(self, "Select Output Folder for All Images")
        if not out_folder:
            return
        out_path = Path(out_folder)
        crop = self._canvas.get_crop_in_image_coords()

        prog = QProgressDialog("Saving images…", "Cancel", 0, len(self._images), self)
        prog.setWindowModality(Qt.WindowModal)
        prog.setWindowTitle("Save All")

        for i, img_path in enumerate(self._images):
            prog.setValue(i)
            if prog.wasCanceled():
                break
            dst = out_path / img_path.name
            self._do_save(img_path, dst, crop)

        prog.setValue(len(self._images))
        self.statusBar().showMessage(f"Saved {len(self._images)} images to {out_folder}")


# ─── Entry Point ──────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PhotoCrop Pro")
    app.setStyle("Fusion")

    # Dark palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG_DARK))
    palette.setColor(QPalette.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.Base, QColor(BG_PANEL))
    palette.setColor(QPalette.AlternateBase, QColor(BG_CARD))
    palette.setColor(QPalette.ToolTipBase, QColor(BG_CARD))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.Text, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.Button, QColor(BG_CARD))
    palette.setColor(QPalette.ButtonText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.BrightText, QColor(ACCENT_BLUE))
    palette.setColor(QPalette.Link, QColor(ACCENT_BLUE))
    palette.setColor(QPalette.Highlight, QColor(ACCENT_BLUE))
    palette.setColor(QPalette.HighlightedText, QColor("#000000"))
    app.setPalette(palette)

    window = PhotoEditorWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
