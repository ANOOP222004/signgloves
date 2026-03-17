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
