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
# On Windows use forward slashes or raw string — os.path handles both.
VOICE_MODEL_PATH = "voice/vosk-model-small-en-us-0.15"

# The four words the voice listener recognises.
# Vosk is configured with ONLY these words — makes recognition faster and
# more accurate because the model only distinguishes 4 words, not 170,000.
# Must be lowercase — Vosk returns lowercase text.
VOICE_COMMANDS = ["start", "stop", "save", "discard"]

# Audio sample rate for microphone input.
# 16000 Hz is the standard for Vosk models — do not change.
VOICE_SAMPLE_RATE = 16000

# Audio block size fed to Vosk per recognition step.
# 8000 samples at 16000 Hz = 0.5 seconds of audio per chunk.
# Smaller = lower latency, more CPU. Larger = higher latency, less CPU.
# 8000 is a good balance for short command words.
VOICE_BLOCK_SIZE = 8000
