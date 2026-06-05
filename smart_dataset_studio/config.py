# =============================================================
# Smart Glove Dataset Studio - config.py
# Single source of truth for ALL constants — Phases 1 through 6
# NEVER use magic numbers anywhere else in the codebase
# Replace your entire existing config.py with this file
# =============================================================

# --- Serial ---
BAUD_RATE       = 115200
QUEUE_MAX_SIZE  = 100          # DO NOT rename — used as QUEUE_MAX_SIZE everywhere

# --- Sampling ---
SAMPLE_RATE     = 30           # Hz
WINDOW_SIZE     = 60           # frames per gesture sample
FRAME_PERIOD_MS = 33           # milliseconds per frame (1000 / 30)

# --- Filter ---
EMA_ALPHA       = 0.25         # Exponential Moving Average smoothing factor

# --- Frame ID ---
FRAME_ID_MAX    = 9999         # max frame ID value — rollover modulo = 10000

# --- Paths ---
DATASET_PATH     = "data/dataset/"
CALIBRATION_PATH = "data/calibration/"

# --- Features ---
NUM_FEATURES = 16
FEATURE_ORDER = [
    "R_T", "R_I", "R_M", "R_R", "R_L", "R_P", "R_RL", "R_Y",
    "L_T", "L_I", "L_M", "L_R", "L_L", "L_P", "L_RL", "L_Y"
]

# --- Calibration ---
CALIBRATION_DIR = 'data/calibration'

# Channel name lists — used by calibration and processing
FINGER_CHANNELS = ['thumb', 'index', 'middle', 'ring', 'little']
IMU_CHANNELS    = ['pitch', 'roll', 'yaw']

# --- Gesture Vocabulary ---
# The 10 ISL signs targeted for this dataset.
# Used by RecorderPanel (dropdown) and DatasetPanel (display list).
# To add a sign: append to this list only — nothing else needs changing.
GESTURE_LABELS = [
    'HELLO', 'STUDY', 'YES', 'NO', 'THANKYOU',
    'SORRY', 'HELP', 'WATER', 'PLEASE', 'FRIENDS'
]

# --- Voice Commands ---
# Path to the Vosk speech recognition model folder.
# Download: https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
# Extract so this path points to the folder containing 'am/', 'conf/', etc.
VOICE_MODEL_PATH = "voice/vosk-model-small-en-us-0.15"

# Words the voice listener recognises.
# Fixed vocabulary mode — Vosk only distinguishes these words.
# Must be lowercase — Vosk returns lowercase text.
# First four are recorder controls (handled by RecorderPanel.on_voice_command).
# Remaining six are tab navigation (handled by MainWindow.on_voice_command).
# All entries MUST be single words — Vosk fixed-grammar mode silently
# fails to build the recogniser if any entry contains whitespace, which
# breaks every other command too (the whole recogniser stops emitting).
VOICE_COMMANDS = ["start", "stop", "save", "discard",
                  "dashboard", "record", "visualize",
                  "calibration", "dataset", "export", "predict",
                  "open", "closed", "calibrate"]

# Tab navigation map: spoken word → QTabWidget index.
# Indices must match the addTab() order in MainWindow._build_ui().
VOICE_TAB_COMMANDS = {
    "dashboard":   0,
    "record":      1,
    "visualize":   2,
    "calibration": 3,
    "dataset":     4,
    "export":      5,
    "predict":     6,
}

# Audio sample rate for microphone input.
# 16000 Hz is the standard for Vosk models — do not change.
VOICE_SAMPLE_RATE = 16000

# Audio block size fed to Vosk per recognition step.
# 8000 samples at 16000 Hz = 0.5 seconds of audio per chunk.
VOICE_BLOCK_SIZE = 8000

# --- Signal Plot (Phase 5) ---

# How many frames of history the scrolling plot shows.
# 90 frames at 30 Hz = 3 seconds of history.
PLOT_HISTORY_FRAMES = 90

# Plot redraw timer interval in milliseconds.
# 50ms = 20 Hz redraws. Data captured at full 30 Hz, drawn at 20 Hz.
# Decouples ingestion rate from render rate — reduces GPU work.
PLOT_TIMER_MS = 50

# Color for each finger channel in the signal plot and 3D skeleton.
# Same finger = same color on both Right and Left hand graphs.
# Format: (R, G, B) integers 0-255 — PyQtGraph's native color format.
FINGER_COLORS = {
    'thumb':  (220,  50,  50),   # red
    'index':  ( 50, 200,  50),   # green
    'middle': ( 50, 130, 255),   # blue
    'ring':   (255, 165,   0),   # orange
    'little': (180,  80, 220),   # purple
}

# --- Phase 6: Hand Skeleton ---

# Where skeleton tuning values are saved between sessions.
# Stores per-finger max rotation angles, scale, and IMU sensitivity.
SKELETON_TUNING_PATH = "data/skeleton_tuning.json"

# Default max rotation angle per finger in degrees.
# How far the virtual finger bends when bend value = 1.0
# These are starting estimates — tune with sliders in the Visualize tab.
# Correct values depend on your exact magnet placement and finger length.
SKELETON_DEFAULT_FINGER_MAX_ANGLE = {
    'thumb':  70.0,
    'index':  90.0,
    'middle': 90.0,
    'ring':   85.0,
    'little': 80.0,
}

# Default global hand scale in the 3D viewport (1.0 = normal size)
SKELETON_DEFAULT_SCALE = 1.0

# Default IMU rotation sensitivity multiplier.
# 1.0 = actual IMU degrees map 1:1 to virtual hand rotation.
# Increase if wrist rotation looks too subtle on screen.
# Decrease if virtual hand rotates too aggressively.
SKELETON_DEFAULT_IMU_SCALE = 1.0

# ── Speed tagging (Phase 7) ───────────────────────────────────────────────────
# Frame zones per recording speed. Used to label which part of the 60-frame
# window captures the start, transition, and end of the gesture motion.
# These ranges are inclusive start, exclusive end (Python slice convention).
SLOW_ZONES   = {'start': (0, 10),  'transition': (10, 50), 'end': (50, 60)}
MEDIUM_ZONES = {'start': (0, 8),   'transition': (8,  45), 'end': (45, 60)}
FAST_ZONES   = {'start': (0, 5),   'transition': (5,  30), 'end': (30, 60)}

# Keyed by speed tag string for easy lookup.
SPEED_ZONES  = {'slow': SLOW_ZONES, 'medium': MEDIUM_ZONES, 'fast': FAST_ZONES}

# Valid speed tag values.
SPEED_TAGS   = ['slow', 'medium', 'fast']

# Default speed used when the user hasn't changed the selector.
DEFAULT_SPEED = 'medium'

# ── ML Export (Phase 8) ───────────────────────────────────────────────────────
# Root folder for all ML export packages.
EXPORT_PATH        = "data/exports/"

# Stratified split ratios — must sum to 1.0.
EXPORT_TRAIN_RATIO = 0.8
EXPORT_VAL_RATIO   = 0.1
EXPORT_TEST_RATIO  = 0.1
