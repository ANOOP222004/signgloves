# ui/style.py
#
# Application-wide stylesheet for the Smart Glove Dataset Studio.
#
# How to use:
#   from ui.style import apply_style
#   apply_style(app)   ← call once in main.py after QApplication() is created
#
# Design decisions:
#   - Dark theme: easier on eyes during long dataset collection sessions
#   - Single accent color (teal #00BFA5) for interactive/active elements
#   - Monospace values stay monospace — functional not decorative
#   - Signal plot background is set separately in signal_plot.py (pg background)
#   - All colors defined as constants at the top — change one to retheme

# ── Color palette ──────────────────────────────────────────────────────────────
BG_DARK      = "#1E1E2E"   # main window background
BG_PANEL     = "#2A2A3E"   # group boxes, panels
BG_INPUT     = "#313145"   # inputs, dropdowns, table cells
BG_HOVER     = "#3A3A55"   # hover state for buttons/rows
ACCENT       = "#00BFA5"   # teal — active tab, buttons, progress
ACCENT_DIM   = "#007A6A"   # darker teal — button press, border
TEXT_PRIMARY = "#E8E8F0"   # main text
TEXT_SECONDARY = "#9090A8" # labels, placeholders, secondary info
TEXT_DISABLED  = "#505068" # disabled widgets
BORDER       = "#3D3D56"   # subtle borders
SUCCESS      = "#4CAF50"   # green — calibrated, saved
WARNING      = "#FF9800"   # orange — not calibrated
DANGER       = "#F44336"   # red — errors, drops
TAB_BG       = "#252538"   # inactive tab background

APP_STYLESHEET = f"""
/* ── Global ───────────────────────────────────────────────────────────── */
QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "Ubuntu", "Helvetica Neue", sans-serif;
    font-size: 13px;
}}

QMainWindow {{
    background-color: {BG_DARK};
}}

/* ── Tab bar ──────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background-color: {BG_DARK};
    border-radius: 0px;
}}

QTabBar::tab {{
    background-color: {TAB_BG};
    color: {TEXT_SECONDARY};
    padding: 8px 18px;
    margin-right: 2px;
    border-bottom: 3px solid transparent;
    font-size: 12px;
    font-weight: 500;
}}

QTabBar::tab:selected {{
    background-color: {BG_DARK};
    color: {ACCENT};
    border-bottom: 3px solid {ACCENT};
    font-weight: 700;
}}

QTabBar::tab:hover:!selected {{
    background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}

/* ── Group boxes ──────────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 10px;
    padding: 10px 8px 8px 8px;
    font-weight: 600;
    font-size: 12px;
    color: {TEXT_SECONDARY};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 10px;
    color: {TEXT_SECONDARY};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* ── Buttons ──────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 500;
    min-height: 28px;
}}

QPushButton:hover {{
    background-color: {BG_HOVER};
    border-color: {ACCENT};
    color: {TEXT_PRIMARY};
}}

QPushButton:pressed {{
    background-color: {ACCENT_DIM};
    border-color: {ACCENT};
}}

QPushButton:disabled {{
    background-color: {BG_PANEL};
    color: {TEXT_DISABLED};
    border-color: {BORDER};
}}

/* Record button — primary action, gets accent treatment */
QPushButton#record_btn {{
    background-color: {ACCENT_DIM};
    color: white;
    border: 1px solid {ACCENT};
    font-weight: 700;
    font-size: 13px;
}}

QPushButton#record_btn:hover {{
    background-color: {ACCENT};
}}

QPushButton#record_btn:disabled {{
    background-color: {BG_PANEL};
    color: {TEXT_DISABLED};
    border-color: {BORDER};
}}

/* Save button */
QPushButton#save_btn {{
    background-color: #1B5E20;
    color: #A5D6A7;
    border: 1px solid #2E7D32;
    font-weight: 700;
}}

QPushButton#save_btn:hover {{
    background-color: #2E7D32;
    color: white;
}}

/* Discard button */
QPushButton#discard_btn {{
    background-color: #4E1010;
    color: #EF9A9A;
    border: 1px solid #7B1A1A;
}}

QPushButton#discard_btn:hover {{
    background-color: #7B1A1A;
    color: white;
}}

/* Stop button */
QPushButton#stop_btn {{
    background-color: #4E2A00;
    color: #FFCC80;
    border: 1px solid #7B4400;
}}

QPushButton#stop_btn:hover {{
    background-color: #7B4400;
    color: white;
}}

/* ── Labels ───────────────────────────────────────────────────────────── */
QLabel {{
    color: {TEXT_PRIMARY};
    background-color: transparent;
    font-size: 13px;
}}

/* ── Line edits ───────────────────────────────────────────────────────── */
QLineEdit {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
    selection-background-color: {ACCENT};
}}

QLineEdit:focus {{
    border-color: {ACCENT};
}}

QLineEdit::placeholder {{
    color: {TEXT_DISABLED};
}}

/* ── ComboBox ─────────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
    min-height: 28px;
}}

QComboBox:hover {{
    border-color: {ACCENT};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox::down-arrow {{
    width: 10px;
    height: 10px;
}}

QComboBox QAbstractItemView {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DIM};
    outline: none;
}}

/* ── Table ────────────────────────────────────────────────────────────── */
QTableWidget {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    gridline-color: {BORDER};
    font-size: 12px;
    outline: none;
}}

QTableWidget::item {{
    padding: 4px 8px;
    border: none;
}}

QTableWidget::item:selected {{
    background-color: {ACCENT_DIM};
    color: white;
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
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}}

/* ── Scroll bars ──────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background-color: {BG_PANEL};
    width: 8px;
    margin: 0;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background-color: {BORDER};
    border-radius: 4px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {TEXT_SECONDARY};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background-color: {BG_PANEL};
    height: 8px;
    margin: 0;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background-color: {BORDER};
    border-radius: 4px;
    min-width: 24px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {TEXT_SECONDARY};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Status bar ───────────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {BG_PANEL};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
    font-size: 11px;
    padding: 2px 8px;
}}

QStatusBar QLabel {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
}}

/* ── Message boxes ────────────────────────────────────────────────────── */
QMessageBox {{
    background-color: {BG_PANEL};
    color: {TEXT_PRIMARY};
}}

QMessageBox QPushButton {{
    min-width: 80px;
    padding: 6px 16px;
}}

/* ── Scroll area ──────────────────────────────────────────────────────── */
QScrollArea {{
    background-color: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

/* ── Frame (used for status banner) ──────────────────────────────────── */
QFrame[frameShape="5"] {{
    border: none;
    background-color: transparent;
}}
"""


# Sensor value colors by bend amount — applied programmatically in main_window.py
# Returns a CSS color string for a normalized bend value 0.0–1.0
def bend_color(value: float) -> str:
    """
    Map a normalized bend value (0.0–1.0) to a color string.

    0.0 → gray (finger open, no signal of interest)
    0.5 → yellow (mid-bend)
    1.0 → teal/green (fully bent — maximum signal)

    Used by MainWindow.on_frame_ready() to color the value labels live.
    """
    if value < 0.1:
        return TEXT_SECONDARY      # gray — essentially zero
    elif value < 0.4:
        return "#64B5F6"           # light blue — slight bend
    elif value < 0.7:
        return "#FFD54F"           # amber — mid bend
    else:
        return ACCENT              # teal — strong bend


def apply_style(app):
    """
    Apply the complete application stylesheet.

    Call once in main.py immediately after QApplication() is created:
        app = QApplication(sys.argv)
        apply_style(app)

    The stylesheet cascades to all child widgets automatically.
    Individual widgets can override specific properties using
    setStyleSheet() — their local style takes precedence over the app style.
    """
    app.setStyleSheet(APP_STYLESHEET)
