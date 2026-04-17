# ui/style.py
#
# Application-wide stylesheet for the Smart Glove Dataset Studio.
#
# Theme: Terminal Instrument — inspired by professional signal analysis hardware.
# Near-black background, yellow primary accent, green secondary accent.
# Monospace font throughout for a scientific data instrument aesthetic.
#
# How to use:
#   from ui.style import apply_style
#   apply_style(app)   ← call once in main.py after QApplication() is created
#
# ALSO UPDATE signal_plot.py:
#   self._graphics_widget.setBackground('#0A0C0A')   ← matches BG_DARK below
#
# All colors defined as constants — change one to retheme the entire app.

# ── Color palette ──────────────────────────────────────────────────────────────

BG_DARK        = "#0A0C0A"    # main window — near black with faint green tint
BG_PANEL       = "#0F140F"    # group boxes, panels — dark green-black
BG_INPUT       = "#141A14"    # inputs, dropdowns, table cells — slightly lighter
BG_HOVER       = "#1C251C"    # hover state — slightly lighter than panel
BG_SELECTED    = "#1E2A1A"    # selected row/item background

ACCENT         = "#E8E000"    # yellow — active tab underline, Record button, headings
ACCENT_DIM     = "#A0A000"    # darker yellow — button press state, borders
ACCENT_HOVER   = "#F5F020"    # brighter yellow — button hover

SUCCESS        = "#39FF14"    # bright green — calibrated banner, OPTIMAL badges
SUCCESS_DIM    = "#1A7A08"    # dark green — success button fill
SUCCESS_BORDER = "#28B006"    # medium green — success button border

WARNING        = "#E8E000"    # yellow — not calibrated banner (reuses accent)
WARNING_BG     = "#1A1A00"    # very dark yellow background for warning banner

DANGER         = "#FF2A2A"    # red — errors, frame drops, discard
DANGER_DIM     = "#4A0808"    # dark red — discard button fill
DANGER_BORDER  = "#8A1010"    # medium red — discard button border

STOP_COLOR     = "#FF8C00"    # amber — stop button
STOP_DIM       = "#3A2000"    # dark amber — stop button fill
STOP_BORDER    = "#7A4400"    # medium amber — stop button border

TEXT_PRIMARY   = "#D0D0C0"    # main readable text — warm off-white
TEXT_SECONDARY = "#5A6A5A"    # labels, placeholders — muted green-gray
TEXT_ACCENT    = "#E8E000"    # yellow text — for important values, active state
TEXT_DISABLED  = "#2A3A2A"    # disabled widgets — very dark

BORDER         = "#1E2A1E"    # subtle panel borders — dark green
BORDER_ACCENT  = "#3A4A00"    # yellow-tinted border — focused inputs

TAB_BG         = "#0A0C0A"    # inactive tab background — same as window

# ── Stylesheet ─────────────────────────────────────────────────────────────────

APP_STYLESHEET = f"""

/* ── Global ───────────────────────────────────────────────────────────────── */
QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: "Courier New", "Courier", "DejaVu Sans Mono", monospace;
    font-size: 12px;
}}

QMainWindow {{
    background-color: {BG_DARK};
}}

/* ── Tab bar ──────────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-top: none;
    background-color: {BG_DARK};
}}

QTabBar {{
    background-color: {BG_DARK};
}}

QTabBar::tab {{
    background-color: {TAB_BG};
    color: {TEXT_SECONDARY};
    padding: 8px 20px;
    margin-right: 0px;
    border: none;
    border-bottom: 2px solid transparent;
    font-family: "Courier New", "Courier", monospace;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    min-width: 80px;
}}

QTabBar::tab:selected {{
    background-color: {BG_DARK};
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
    font-weight: 700;
}}

QTabBar::tab:hover:!selected {{
    background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
    border-bottom: 2px solid {ACCENT_DIM};
}}

/* ── Group boxes ──────────────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 0px;
    margin-top: 14px;
    padding: 12px 8px 8px 8px;
    font-family: "Courier New", "Courier", monospace;
    font-size: 10px;
    font-weight: 700;
    color: {TEXT_SECONDARY};
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    left: 8px;
    background-color: {BG_PANEL};
    color: {TEXT_SECONDARY};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}

/* ── Buttons — base style ─────────────────────────────────────────────────── */
QPushButton {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 0px;
    padding: 7px 16px;
    font-family: "Courier New", "Courier", monospace;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    min-height: 30px;
}}

QPushButton:hover {{
    background-color: {BG_HOVER};
    border-color: {ACCENT_DIM};
    color: {TEXT_PRIMARY};
}}

QPushButton:pressed {{
    background-color: {BG_SELECTED};
    border-color: {ACCENT};
}}

QPushButton:disabled {{
    background-color: {BG_PANEL};
    color: {TEXT_DISABLED};
    border-color: {BORDER};
}}

/* ── Record button — yellow filled, primary action ────────────────────────── */
QPushButton#record_btn {{
    background-color: {ACCENT};
    color: #000000;
    border: 1px solid {ACCENT};
    font-weight: 700;
    font-size: 12px;
    letter-spacing: 2px;
}}

QPushButton#record_btn:hover {{
    background-color: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
    color: #000000;
}}

QPushButton#record_btn:pressed {{
    background-color: {ACCENT_DIM};
    border-color: {ACCENT_DIM};
    color: #000000;
}}

QPushButton#record_btn:disabled {{
    background-color: {BG_PANEL};
    color: {TEXT_DISABLED};
    border-color: {BORDER};
}}

/* ── Save button — green ──────────────────────────────────────────────────── */
QPushButton#save_btn {{
    background-color: {SUCCESS_DIM};
    color: {SUCCESS};
    border: 1px solid {SUCCESS_BORDER};
    font-weight: 700;
    letter-spacing: 1px;
}}

QPushButton#save_btn:hover {{
    background-color: {SUCCESS_BORDER};
    color: #000000;
    border-color: {SUCCESS};
}}

QPushButton#save_btn:pressed {{
    background-color: {SUCCESS};
    color: #000000;
}}

/* ── Discard button — red ─────────────────────────────────────────────────── */
QPushButton#discard_btn {{
    background-color: {DANGER_DIM};
    color: {DANGER};
    border: 1px solid {DANGER_BORDER};
    font-weight: 700;
    letter-spacing: 1px;
}}

QPushButton#discard_btn:hover {{
    background-color: {DANGER_BORDER};
    color: white;
    border-color: {DANGER};
}}

QPushButton#discard_btn:pressed {{
    background-color: {DANGER};
    color: white;
}}

/* ── Stop button — amber ──────────────────────────────────────────────────── */
QPushButton#stop_btn {{
    background-color: {STOP_DIM};
    color: {STOP_COLOR};
    border: 1px solid {STOP_BORDER};
    font-weight: 700;
    letter-spacing: 1px;
}}

QPushButton#stop_btn:hover {{
    background-color: {STOP_BORDER};
    color: white;
    border-color: {STOP_COLOR};
}}

QPushButton#stop_btn:pressed {{
    background-color: {STOP_COLOR};
    color: black;
}}

/* ── Labels ───────────────────────────────────────────────────────────────── */
QLabel {{
    color: {TEXT_PRIMARY};
    background-color: transparent;
    font-family: "Courier New", "Courier", monospace;
    font-size: 12px;
}}

/* ── Line edits ───────────────────────────────────────────────────────────── */
QLineEdit {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 0px;
    padding: 6px 8px;
    font-family: "Courier New", "Courier", monospace;
    font-size: 12px;
    selection-background-color: {ACCENT_DIM};
    selection-color: #000000;
}}

QLineEdit:focus {{
    border-color: {ACCENT};
    color: {TEXT_ACCENT};
}}

QLineEdit::placeholder {{
    color: {TEXT_DISABLED};
}}

/* ── ComboBox ─────────────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 0px;
    padding: 6px 8px;
    font-family: "Courier New", "Courier", monospace;
    font-size: 12px;
    min-height: 30px;
}}

QComboBox:hover {{
    border-color: {ACCENT_DIM};
    color: {TEXT_ACCENT};
}}

QComboBox:focus {{
    border-color: {ACCENT};
}}

QComboBox::drop-down {{
    /* The drop-down button area on the right side of the combobox.
       subcontrol-origin: padding keeps it inside the combobox border.
       We remove all borders and background — the arrow will be the only indicator. */
    subcontrol-origin: padding;
    subcontrol-position: top right;
    border: none;
    border-left: 1px solid {BORDER};
    width: 28px;
    background-color: {BG_INPUT};
}}

QComboBox::down-arrow {{
    /* image: none removes the default OS-drawn arrow icon (the square).
       We replace it by setting a fixed-size area and letting Qt draw nothing —
       the actual visible indicator is the ▼ character appended via the
       drop-down area background. This is the only reliable way in Qt CSS
       to remove the default platform arrow without providing an image file. */
    image: none;
    width: 0px;
    height: 0px;
    border-left:   5px solid transparent;
    border-right:  5px solid transparent;
    border-top:    6px solid {TEXT_SECONDARY};
}}

QComboBox QAbstractItemView {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    selection-background-color: {BG_SELECTED};
    selection-color: {ACCENT};
    outline: none;
    font-family: "Courier New", "Courier", monospace;
}}

/* ── Table ────────────────────────────────────────────────────────────────── */
QTableWidget {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 0px;
    gridline-color: {BORDER};
    font-family: "Courier New", "Courier", monospace;
    font-size: 11px;
    outline: none;
}}

QTableWidget::item {{
    padding: 5px 8px;
    border: none;
    border-bottom: 1px solid {BORDER};
}}

QTableWidget::item:selected {{
    background-color: {BG_SELECTED};
    color: {ACCENT};
}}

QTableWidget::item:alternate {{
    background-color: {BG_PANEL};
}}

QHeaderView::section {{
    background-color: {BG_PANEL};
    color: {TEXT_SECONDARY};
    border: none;
    border-bottom: 1px solid {BORDER};
    border-right: 1px solid {BORDER};
    padding: 6px 8px;
    font-family: "Courier New", "Courier", monospace;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

/* ── Scroll bars ──────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background-color: {BG_PANEL};
    width: 6px;
    margin: 0;
    border-radius: 0px;
}}

QScrollBar::handle:vertical {{
    background-color: {BORDER};
    border-radius: 0px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {ACCENT_DIM};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background-color: {BG_PANEL};
    height: 6px;
    margin: 0;
    border-radius: 0px;
}}

QScrollBar::handle:horizontal {{
    background-color: {BORDER};
    border-radius: 0px;
    min-width: 20px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {ACCENT_DIM};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Status bar ───────────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {BG_PANEL};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
    font-family: "Courier New", "Courier", monospace;
    font-size: 10px;
    letter-spacing: 0.5px;
    padding: 2px 8px;
}}

QStatusBar QLabel {{
    color: {TEXT_SECONDARY};
    font-family: "Courier New", "Courier", monospace;
    font-size: 10px;
    letter-spacing: 0.5px;
}}

/* ── Message boxes ────────────────────────────────────────────────────────── */
QMessageBox {{
    background-color: {BG_PANEL};
    color: {TEXT_PRIMARY};
    font-family: "Courier New", "Courier", monospace;
}}

QMessageBox QLabel {{
    color: {TEXT_PRIMARY};
    font-family: "Courier New", "Courier", monospace;
    font-size: 12px;
}}

QMessageBox QPushButton {{
    min-width: 80px;
    padding: 6px 16px;
}}

/* ── Scroll area ──────────────────────────────────────────────────────────── */
QScrollArea {{
    background-color: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

/* ── Frame (used for status banner) ──────────────────────────────────────── */
QFrame[frameShape="5"] {{
    border: none;
    background-color: transparent;
}}

/* ── Toolbar / menu bar (if ever added) ──────────────────────────────────── */
QMenuBar {{
    background-color: {BG_DARK};
    color: {TEXT_SECONDARY};
    border-bottom: 1px solid {BORDER};
    font-family: "Courier New", "Courier", monospace;
    font-size: 11px;
}}

QMenuBar::item:selected {{
    background-color: {BG_HOVER};
    color: {ACCENT};
}}

QMenu {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    font-family: "Courier New", "Courier", monospace;
}}

QMenu::item:selected {{
    background-color: {BG_SELECTED};
    color: {ACCENT};
}}

/* ── Tooltip ──────────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {ACCENT_DIM};
    font-family: "Courier New", "Courier", monospace;
    font-size: 11px;
    padding: 4px 8px;
}}

"""


# ── bend_color() ───────────────────────────────────────────────────────────────
# Maps a normalized bend value (0.0–1.0) to a color string.
# Used by MainWindow.on_frame_ready() to color sensor value labels live.
#
# Theme-matched color progression:
#   0.0       → muted green-gray (finger open, no signal)
#   0.1–0.4   → dim yellow (slight bend — activity starting)
#   0.4–0.7   → bright yellow accent (mid bend — clear signal)
#   0.7–1.0   → bright green (strong bend — maximum signal)
#
# This mirrors the Stitch design language:
#   yellow = active/measuring, green = maximum/optimal

def bend_color(value: float) -> str:
    if value < 0.1:
        return TEXT_SECONDARY    # muted — finger essentially open
    elif value < 0.4:
        return ACCENT_DIM        # dim yellow — slight bend
    elif value < 0.7:
        return ACCENT            # bright yellow — mid bend
    else:
        return SUCCESS           # bright green — strong bend / fully active


# ── apply_style() ──────────────────────────────────────────────────────────────
def apply_style(app):
    """
    Apply the complete application stylesheet.

    Call once in main.py immediately after QApplication() is created:

        app = QApplication(sys.argv)
        apply_style(app)    ← MUST be before any widget is created

    The stylesheet cascades to all child widgets automatically.
    Individual widgets can override with setStyleSheet() — local style
    takes precedence over the app-level style.

    REMINDER: also update signal_plot.py background line:
        self._graphics_widget.setBackground('#0A0C0A')
    """
    app.setStyleSheet(APP_STYLESHEET)
