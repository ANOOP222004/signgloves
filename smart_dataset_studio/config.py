# =============================================================
# Smart Glove Dataset Studio - config.py
# Single source of truth for all constants
# Never use magic numbers anywhere else in the codebase
# =============================================================

# --- Serial ---
BAUD_RATE       = 115200
QUEUE_MAX_SIZE  = 100

# --- Sampling ---
SAMPLE_RATE     = 30        # Hz
WINDOW_SIZE     = 60        # frames per gesture sample
FRAME_PERIOD_MS = 33        # milliseconds per frame

# --- Filter ---
EMA_ALPHA       = 0.25

# --- Frame ID ---
FRAME_ID_MAX    = 9999

# --- Paths ---
DATASET_PATH     = "data/dataset/"
CALIBRATION_PATH = "data/calibration/"

# --- Features ---
NUM_FEATURES = 16
FEATURE_ORDER = [
    "R_T", "R_I", "R_M", "R_R", "R_L", "R_P", "R_RL", "R_Y",
    "L_T", "L_I", "L_M", "L_R", "L_L", "L_P", "L_RL", "L_Y"
]

# Calibration
CALIBRATION_DIR = 'data/calibration'

# Channel name lists — used by calibration and processing
FINGER_CHANNELS = ['thumb', 'index', 'middle', 'ring', 'little']
IMU_CHANNELS    = ['pitch', 'roll', 'yaw']

# --- Gesture Vocabulary ---
# The 10 ISL signs targeted for this dataset.
# Used by RecorderPanel (dropdown) and DatasetPanel (display list).
# Stored here so adding/removing a sign only requires editing this one list.
GESTURE_LABELS = [
    'HELLO', 'STOP', 'YES', 'NO', 'THANKYOU',
    'SORRY', 'HELP', 'WATER', 'PLEASE', 'MORE',
]

# --- Voice Commands ---
# Path to the Vosk speech recognition model folder.
# Download: https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
# Extract so this path points to the folder containing 'am/', 'conf/', etc.
VOICE_MODEL_PATH = "voice/vosk-model-small-en-us-0.15"

# The four words the voice listener recognises.
# Fixed vocabulary mode — Vosk only distinguishes these 4 words.
# Must be lowercase — Vosk returns lowercase text.
VOICE_COMMANDS = ["start", "stop", "save", "discard"]

# Audio sample rate for microphone input.
# 16000 Hz is the standard for Vosk models — do not change.
VOICE_SAMPLE_RATE = 16000

# Audio block size fed to Vosk per recognition step.
# 8000 samples at 16000 Hz = 0.5 seconds of audio per chunk.
VOICE_BLOCK_SIZE = 8000

# --- Signal Plot (Phase 5) ---

# How many frames of history the scrolling plot shows.
# 90 frames at 30 Hz = 3 seconds — enough to see one full gesture plus context.
PLOT_HISTORY_FRAMES = 90

# Plot redraw rate in milliseconds.
# 50ms = 20 Hz redraws. Data is still captured at full 30 Hz via on_frame().
# Drawing at 20 Hz instead of 30 Hz reduces GPU/CPU work by 33% with no
# visible difference to the human eye (smooth motion perception starts ~15 Hz).
PLOT_TIMER_MS = 50

# Color for each finger channel in the signal plot.
# Same finger = same color on both Right and Left hand graphs.
# Format: (R, G, B) integers 0-255 — PyQtGraph's native color format.
# Chosen to be visually distinct and readable on both light and dark backgrounds.
FINGER_COLORS = {
    'thumb':  (220,  50,  50),   # red
    'index':  ( 50, 200,  50),   # green
    'middle': ( 50, 130, 255),   # blue
    'ring':   (255, 165,   0),   # orange
    'little': (180,  80, 220),   # purple
}
