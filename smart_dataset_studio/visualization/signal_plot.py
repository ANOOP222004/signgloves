# visualization/signal_plot.py
#
# SignalPlotWidget — real-time scrolling graph of finger bend signals.
#
# Fixes in this version:
#   - Y axis tick labels no longer cramped/stacking
#     Root cause: setTicks() overrides any setWidth() called before it.
#     PyQtGraph recalculates axis geometry when ticks change.
#     Fix: call setTicks() first, then setTickFont(), then setWidth() last.
#     Only 3 ticks (0.0, 0.5, 1.0) — more space between labels.
#     Short labels "0.0" not "0.00" — fewer characters, less crowding.
#   - Background updated to #0A0C0A matching new theme
#   - Recording marker changed to yellow matching accent color

from collections import deque

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout

from config import (
    FINGER_CHANNELS,
    FINGER_COLORS,
    PLOT_HISTORY_FRAMES,
    PLOT_TIMER_MS,
    WINDOW_SIZE,
)

_X_AXIS = np.arange(PLOT_HISTORY_FRAMES, dtype=np.float32)


class SignalPlotWidget(QWidget):
    """
    Real-time scrolling signal plot for all 10 finger channels.
    Two PlotItems stacked: Right Hand (top) and Left Hand (bottom).
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._buffers = {
            hand: {
                ch: deque([0.0] * PLOT_HISTORY_FRAMES, maxlen=PLOT_HISTORY_FRAMES)
                for ch in FINGER_CHANNELS
            }
            for hand in ['right', 'left']
        }

        self._recording       = False
        self._frames_captured = 0

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.setInterval(PLOT_TIMER_MS)
        self._timer.timeout.connect(self._redraw)
        self._timer.start()

    # ── UI Construction ───────────────────────────────────────────────

    def _build_ui(self):
        pg.setConfigOptions(antialias=True, useOpenGL=False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._graphics_widget = pg.GraphicsLayoutWidget(parent=self)
        self._graphics_widget.setBackground('#0A0C0A')
        layout.addWidget(self._graphics_widget)

        self._right_plot, self._right_curves = self._make_plot("RIGHT_HAND")
        self._left_plot,  self._left_curves  = self._make_plot("LEFT_HAND")

        self._graphics_widget.addItem(self._right_plot)
        self._graphics_widget.nextRow()
        self._graphics_widget.addItem(self._left_plot)

        marker_pen = pg.mkPen(color='#E8E000', width=2,
                              style=pg.QtCore.Qt.DashLine)
        self._right_marker = pg.InfiniteLine(pos=0, angle=90, pen=marker_pen)
        self._left_marker  = pg.InfiniteLine(pos=0, angle=90, pen=marker_pen)

        self._right_plot.addItem(self._right_marker)
        self._left_plot.addItem(self._left_marker)
        self._right_marker.setVisible(False)
        self._left_marker.setVisible(False)

    def _make_plot(self, title: str):
        """
        Create one configured PlotItem with 5 colored finger curves.

        Y axis fix — correct call order:
            1. setTicks()     first  — PyQtGraph recalcs axis width here
            2. setTickFont()  second — shrink font to 8pt so labels fit
            3. setWidth(42)   last   — explicit width holds because no
                                       more geometry recalcs after this
        Only 3 tick values (0.0, 0.5, 1.0) instead of 5.
        Short labels "0.0" not "0.00" — less horizontal space needed.
        """
        plot = pg.PlotItem(title=title)

        title_style = {'color': '#E8E000', 'size': '10pt', 'bold': True}
        plot.setTitle(title, **title_style)

        axis_pen   = pg.mkPen(color='#1E2A1E', width=1)
        text_color = '#5A6A5A'
        for ax in ['left', 'bottom', 'right', 'top']:
            plot.getAxis(ax).setPen(axis_pen)
            plot.getAxis(ax).setTextPen(text_color)

        plot.setRange(yRange=[-0.05, 1.05], disableAutoRange=True)
        plot.setRange(xRange=[0, PLOT_HISTORY_FRAMES - 1], disableAutoRange=True)

        label_style = {'color': '#5A6A5A', 'font-size': '8pt'}
        plot.setLabel('left',   'BEND',                     **label_style)
        plot.setLabel('bottom', 'FRAMES  (newest → right)', **label_style)

        plot.showGrid(x=False, y=True, alpha=0.4)
        plot.hideButtons()

        # ── Correct order for Y axis labels ──────────────────────────
        # Step 1 — define ticks (3 values, short strings)
        plot.getAxis('left').setTicks([
            [(0.0, '0.0'), (0.5, '0.5'), (1.0, '1.0')]
        ])

        # Step 2 — small font so labels do not stack vertically
        tick_font = pg.QtGui.QFont('Courier New', 8)
        plot.getAxis('left').setTickFont(tick_font)
        plot.getAxis('bottom').setTickFont(tick_font)

        # Step 3 — explicit width AFTER ticks, so this value is final
        plot.getAxis('left').setWidth(42)

        # ── Finger curves ─────────────────────────────────────────────
        curves = {}
        for ch in FINGER_CHANNELS:
            pen   = pg.mkPen(color=FINGER_COLORS[ch], width=2)
            curve = plot.plot(
                x=_X_AXIS,
                y=np.zeros(PLOT_HISTORY_FRAMES, dtype=np.float32),
                pen=pen,
                name=ch.capitalize(),
            )
            curves[ch] = curve

        return plot, curves

    # ── Slots ─────────────────────────────────────────────────────────

    def on_frame(self, processed_frame: dict):
        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS:
                self._buffers[hand][ch].append(processed_frame[hand][ch])

    def on_recording_started(self):
        self._recording       = True
        self._frames_captured = 0
        self._right_marker.setVisible(True)
        self._left_marker.setVisible(True)
        self._right_marker.setPos(0)
        self._left_marker.setPos(0)

    def on_recording_progress(self, captured: int, total: int):
        self._frames_captured = captured
        marker_x = (PLOT_HISTORY_FRAMES - WINDOW_SIZE) + captured
        self._right_marker.setPos(marker_x)
        self._left_marker.setPos(marker_x)

    def on_recording_stopped(self):
        self._recording = False
        self._right_marker.setVisible(False)
        self._left_marker.setVisible(False)

    def _redraw(self):
        for ch in FINGER_CHANNELS:
            y_right = np.array(self._buffers['right'][ch], dtype=np.float32)
            y_left  = np.array(self._buffers['left'][ch],  dtype=np.float32)
            self._right_curves[ch].setData(x=_X_AXIS, y=y_right)
            self._left_curves[ch].setData(x=_X_AXIS, y=y_left)

    def stop(self):
        self._timer.stop()
