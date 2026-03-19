# visualization/signal_plot.py
#
# SignalPlotWidget — real-time scrolling graph of finger bend signals.
#
# What this does:
#   Displays two stacked scrolling graphs — Right Hand and Left Hand.
#   Each graph shows 5 colored lines, one per finger.
#   The X axis shows the last PLOT_HISTORY_FRAMES frames (3 seconds at 30 Hz).
#   The Y axis is fixed at 0.0–1.0 (normalized bend values).
#
# How it connects to the pipeline:
#   ProcessingThread emits frame_ready at 30 Hz.
#   on_frame() is connected to that signal — it just appends to deques. No drawing.
#   A QTimer fires every PLOT_TIMER_MS (50ms = 20 Hz) and calls _redraw().
#   _redraw() reads all 10 deques and updates all 10 PlotDataItems in one batch.
#
# Why separate data capture (30 Hz) from drawing (20 Hz)?
#   Drawing is expensive relative to appending to a deque.
#   Capturing at 30 Hz ensures no data is lost.
#   Drawing at 20 Hz reduces GPU work by 33% with no visible difference —
#   the human eye perceives smooth motion above ~15 Hz.
#
# Why PyQtGraph instead of Matplotlib?
#   Matplotlib redraws the entire figure on every update — axes, ticks, labels,
#   all lines. At 20 Hz that causes visible stutter.
#   PyQtGraph updates only the line data, leaving axes and labels in place.
#   It's built on Qt's own graphics system, so it integrates natively with PyQt5.
#
# Why deque with maxlen?
#   A deque(maxlen=N) automatically drops the oldest item when you append to a
#   full deque. No manual slicing, no shifting. O(1) per append.
#   When the graph starts, the deque fills with zeros — the lines start flat at 0.0
#   and rise to real values as real data arrives. This is correct and expected.

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

# X axis tick values — frame indices 0 to PLOT_HISTORY_FRAMES-1.
# Computed once at module load, reused every redraw.
# Using numpy arange gives a C array under the hood — faster than a Python list
# when PyQtGraph converts it for rendering.
_X_AXIS = np.arange(PLOT_HISTORY_FRAMES, dtype=np.float32)


class SignalPlotWidget(QWidget):
    """
    Real-time scrolling signal plot for all 10 finger channels.

    Contains two PlotItems stacked vertically:
        Top:    Right Hand — 5 colored lines
        Bottom: Left Hand  — 5 colored lines

    Usage (from main_window.py):
        plot_widget = SignalPlotWidget()
        processing_thread.frame_ready.connect(plot_widget.on_frame)
        layout.addWidget(plot_widget)

    The widget manages its own QTimer internally — no external timer needed.
    Call start() after adding to layout to begin the redraw timer.
    The timer starts automatically on construction — stop() is available
    if you ever need to pause (e.g. during a calibration step).
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── Data buffers ──────────────────────────────────────────────
        # One deque per finger per hand — 10 deques total.
        # Each deque holds PLOT_HISTORY_FRAMES floats (0.0–1.0).
        # Initialised with zeros — lines start flat until real data arrives.
        # Structure mirrors the frame dict: self._buffers['right']['thumb']
        self._buffers = {
            hand: {
                ch: deque([0.0] * PLOT_HISTORY_FRAMES, maxlen=PLOT_HISTORY_FRAMES)
                for ch in FINGER_CHANNELS
            }
            for hand in ['right', 'left']
        }

        # Flag set during active recording — used to draw a vertical
        # progress marker showing how far through the 60-frame window we are.
        self._recording        = False
        self._frames_captured  = 0   # updated by on_recording_progress()

        # ── Build UI ──────────────────────────────────────────────────
        self._build_ui()

        # ── Redraw timer ──────────────────────────────────────────────
        # Fires every PLOT_TIMER_MS milliseconds.
        # Calls _redraw() which reads all deques and updates all line data.
        # The timer is started here — it runs continuously while the app is open.
        # Data capture (on_frame) and drawing (_redraw) are intentionally decoupled:
        #   on_frame  → 30 Hz  → append to deque  (no drawing)
        #   _redraw   → 20 Hz  → read deque, setData() on all lines
        self._timer = QTimer(self)
        self._timer.setInterval(PLOT_TIMER_MS)
        self._timer.timeout.connect(self._redraw)
        self._timer.start()

    # ── UI Construction ───────────────────────────────────────────────

    def _build_ui(self):
        """
        Build the two-graph layout using PyQtGraph.

        PyQtGraph's GraphicsLayoutWidget is a QWidget that holds a grid of
        PlotItems. We add two rows — one for each hand.

        pg.setConfigOptions() sets global PyQtGraph rendering preferences.
        These must be called before creating any PlotItem — they affect how
        all subsequent plots are rendered.
        """
        # antialias=True: smooth diagonal lines (no jagged edges on curves).
        # useOpenGL=False: software rendering — more compatible across GPUs.
        #   OpenGL mode is faster but occasionally crashes on some Linux setups.
        #   For 20 Hz with 10 lines this is more than fast enough without OpenGL.
        pg.setConfigOptions(antialias=True, useOpenGL=False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # GraphicsLayoutWidget: PyQtGraph's container for multiple plots.
        # background='w' sets white background.
        # 'k' would be black — white is easier to read in a bright lab environment.
        self._graphics_widget = pg.GraphicsLayoutWidget(parent=self)
        self._graphics_widget.setBackground('#1E1E2E')   # matches BG_DARK in style.py
        layout.addWidget(self._graphics_widget)

        # ── Create the two PlotItems ──────────────────────────────────
        # _make_plot() returns a configured PlotItem and a dict of PlotDataItems.
        # The PlotDataItems are stored so _redraw() can call setData() on them.
        self._right_plot, self._right_curves = self._make_plot("Right Hand")
        self._left_plot,  self._left_curves  = self._make_plot("Left Hand")

        # addItem() places each PlotItem into the GraphicsLayoutWidget.
        # nextRow() moves to the next row in the grid — stacks them vertically.
        self._graphics_widget.addItem(self._right_plot)
        self._graphics_widget.nextRow()
        self._graphics_widget.addItem(self._left_plot)

        # Recording progress marker — a vertical line showing current frame
        # position during a recording. Invisible until recording starts.
        # One marker per plot — both updated simultaneously.
        self._right_marker = pg.InfiniteLine(
            pos=0, angle=90,
            pen=pg.mkPen(color=(200, 0, 0), width=2, style=pg.QtCore.Qt.DashLine)
        )
        self._left_marker = pg.InfiniteLine(
            pos=0, angle=90,
            pen=pg.mkPen(color=(200, 0, 0), width=2, style=pg.QtCore.Qt.DashLine)
        )
        self._right_plot.addItem(self._right_marker)
        self._left_plot.addItem(self._left_marker)
        self._right_marker.setVisible(False)
        self._left_marker.setVisible(False)

    def _make_plot(self, title: str):
        """
        Create one configured PlotItem with 5 colored finger curves.

        Returns:
            plot:   pg.PlotItem — the plot container (axes, title, grid)
            curves: dict mapping finger channel name → pg.PlotDataItem

        Why PlotItem and not just plot()?
            pg.plot() creates a standalone window. PlotItem is the component
            that goes inside a GraphicsLayoutWidget — it's the plot without
            its own window frame.

        Why setRange() with disableAutoRange?
            By default PyQtGraph auto-scales the Y axis to fit the data.
            For bend values (0.0–1.0) we always want Y fixed at [-0.05, 1.05].
            The small padding (-0.05, 1.05) prevents lines at exactly 0.0 or 1.0
            from being clipped at the axis edge.
            disableAutoRange=True locks this range permanently — incoming data
            never causes the axis to rescale, which would cause the graph to
            jump around visually.
        """
        plot = pg.PlotItem(title=title)

        # Title and axis label colors — light text on dark background
        title_style = {'color': '#9090A8', 'size': '11pt', 'bold': False}
        plot.setTitle(title, **title_style)

        axis_pen   = pg.mkPen(color='#3D3D56', width=1)
        text_color = '#9090A8'
        for ax in ['left', 'bottom', 'right', 'top']:
            plot.getAxis(ax).setPen(axis_pen)
            plot.getAxis(ax).setTextPen(text_color)

        # Y axis: normalized bend 0.0–1.0, fixed range with small padding.
        plot.setRange(yRange=[-0.05, 1.05], disableAutoRange=True)

        # X axis: frame index 0 to PLOT_HISTORY_FRAMES-1.
        # Also fixed — the scrolling effect comes from updating the DATA,
        # not from moving the axis. The axis always shows 0 to 89.
        plot.setRange(xRange=[0, PLOT_HISTORY_FRAMES - 1], disableAutoRange=True)

        # Axis labels
        plot.setLabel('left', 'Bend', units='')
        plot.setLabel('bottom', 'Frames (newest → right)')

        # Grid lines — subtle horizontal guides at 0.25, 0.5, 0.75
        plot.showGrid(x=False, y=True, alpha=0.3)

        # Remove the default auto-scale button (the 'A' button in the corner).
        # We fixed the range — the auto-scale button would undo our fixed range
        # if clicked accidentally.
        plot.hideButtons()

        # Y axis ticks: 0.0, 0.25, 0.5, 0.75, 1.0
        # Custom ticks prevent PyQtGraph from choosing awkward values like 0.333.
        plot.getAxis('left').setTicks([
            [(0.0, '0.0'), (0.25, '0.25'), (0.5, '0.5'), (0.75, '0.75'), (1.0, '1.0')]
        ])

        # ── Create one curve per finger ───────────────────────────────
        curves = {}
        for ch in FINGER_CHANNELS:
            color = FINGER_COLORS[ch]   # (R, G, B) from config.py

            # mkPen creates a QPen — the line style for this curve.
            # width=2: thick enough to see clearly, thin enough not to overlap.
            pen = pg.mkPen(color=color, width=2)

            # PlotDataItem: the actual line on the graph.
            # name= sets the legend entry text.
            # We're not showing a legend (too much space) but name= is useful
            # for debugging — hovering over a line in some PyQtGraph modes
            # shows the name.
            curve = plot.plot(
                x=_X_AXIS,
                y=np.zeros(PLOT_HISTORY_FRAMES, dtype=np.float32),
                pen=pen,
                name=ch.capitalize(),
            )
            curves[ch] = curve

        return plot, curves

    # ── Data intake slot ──────────────────────────────────────────────

    def on_frame(self, processed_frame: dict):
        """
        Slot connected to ProcessingThread.frame_ready signal.

        Called 30 times per second on the main thread.
        ONLY appends data to deques — no drawing happens here.
        Drawing is handled by _redraw() via QTimer at 20 Hz.

        Why no drawing here?
            If we called setData() here, we'd be drawing 30 times per second.
            The QTimer approach draws 20 times per second — same visual result,
            33% less rendering work. At this scale it's a minor saving, but it's
            the correct pattern: decouple data ingestion rate from render rate.

        Args:
            processed_frame: Processed Frame dict from processing_thread:
                {
                    'frame_id': int,
                    'right': {'thumb': float, 'index': float, ..., 'pitch': float, ...},
                    'left':  {'thumb': float, 'index': float, ..., 'pitch': float, ...}
                }
        """
        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS:
                self._buffers[hand][ch].append(
                    processed_frame[hand][ch]   # float 0.0–1.0
                )

    # ── Recording state slots ─────────────────────────────────────────

    def on_recording_started(self):
        """
        Slot connected to RecorderPanel.recording_started signal.

        Shows the vertical progress marker on both graphs.
        The marker starts at x=0 (left edge) and moves right as frames are captured.
        """
        self._recording       = True
        self._frames_captured = 0
        self._right_marker.setVisible(True)
        self._left_marker.setVisible(True)
        self._right_marker.setPos(0)
        self._left_marker.setPos(0)

    def on_recording_progress(self, captured: int, total: int):
        """
        Slot connected to GestureRecorder.progress_updated signal.

        Moves the vertical marker to show how far through the 60-frame
        window the current recording has progressed.

        The marker position is in X-axis units (frame index 0–89).
        We map the captured count into the rightmost WINDOW_SIZE frames
        of the history buffer:
            marker_x = (PLOT_HISTORY_FRAMES - WINDOW_SIZE) + captured

        Why that formula?
            The plot always shows the last 90 frames.
            A 60-frame recording occupies the rightmost 60 of those 90 slots.
            When captured=0, the marker is at x=30 (start of the recording region).
            When captured=60, the marker is at x=90 (right edge = complete).

        Args:
            captured: frames collected so far (0–60)
            total:    total frames needed (always WINDOW_SIZE = 60)
        """
        self._frames_captured = captured
        marker_x = (PLOT_HISTORY_FRAMES - WINDOW_SIZE) + captured
        self._right_marker.setPos(marker_x)
        self._left_marker.setPos(marker_x)

    def on_recording_stopped(self):
        """
        Slot connected to RecorderPanel.recording_stopped signal.

        Hides the vertical progress marker.
        Called on save, discard, or frame drop abort.
        """
        self._recording = False
        self._right_marker.setVisible(False)
        self._left_marker.setVisible(False)

    # ── Redraw ────────────────────────────────────────────────────────

    def _redraw(self):
        """
        Called every PLOT_TIMER_MS milliseconds by the QTimer.

        Reads all 10 deques and calls setData() on all 10 PlotDataItems.

        setData(y=array) updates the line without recreating the PlotDataItem.
        PyQtGraph only repaints the lines — axes, labels, grid stay unchanged.
        This is why PyQtGraph is fast: it does the minimum work needed.

        np.array(deque) converts the deque to a NumPy array in one call.
        PyQtGraph's setData() accepts NumPy arrays natively — no list conversion.
        dtype=np.float32 saves memory vs float64 and is what the GPU prefers.
        """
        for ch in FINGER_CHANNELS:
            y_right = np.array(self._buffers['right'][ch], dtype=np.float32)
            y_left  = np.array(self._buffers['left'][ch],  dtype=np.float32)

            self._right_curves[ch].setData(x=_X_AXIS, y=y_right)
            self._left_curves[ch].setData(x=_X_AXIS, y=y_left)

    # ── Timer control ─────────────────────────────────────────────────

    def stop(self):
        """Stop the redraw timer. Call when the window is closing."""
        self._timer.stop()
