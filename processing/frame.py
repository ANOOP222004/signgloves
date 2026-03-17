# =============================================================
# Smart Glove Dataset Studio - processing/frame.py
# Defines the standard Frame data structures used across
# all modules. No logic here, just structure definitions.
# =============================================================


def make_raw_frame(frame_id,
                   r_t, r_i, r_m, r_r, r_l, r_p, r_rl, r_y,
                   l_t, l_i, l_m, l_r, l_l, l_p, l_rl, l_y):
    """
    Raw Frame — created by packet_parser after successful parse.
    Finger values are raw ADC integers (0-4095).
    IMU values are raw floats in degrees (-180 to 180).
    """
    return {
        "frame_id": frame_id,
        "right": {
            "thumb":  r_t,
            "index":  r_i,
            "middle": r_m,
            "ring":   r_r,
            "little": r_l,
            "pitch":  r_p,
            "roll":   r_rl,
            "yaw":    r_y,
        },
        "left": {
            "thumb":  l_t,
            "index":  l_i,
            "middle": l_m,
            "ring":   l_r,
            "little": l_l,
            "pitch":  l_p,
            "roll":   l_rl,
            "yaw":    l_y,
        }
    }


def make_processed_frame(frame_id,
                          r_t, r_i, r_m, r_r, r_l, r_p, r_rl, r_y,
                          l_t, l_i, l_m, l_r, l_l, l_p, l_rl, l_y):
    """
    Processed Frame — created by processing_thread after
    filtering and normalization.
    Finger values are normalized floats (0.0 - 1.0).
    IMU values remain as raw degrees (not normalized).
    """
    return {
        "frame_id": frame_id,
        "right": {
            "thumb":  r_t,
            "index":  r_i,
            "middle": r_m,
            "ring":   r_r,
            "little": r_l,
            "pitch":  r_p,
            "roll":   r_rl,
            "yaw":    r_y,
        },
        "left": {
            "thumb":  l_t,
            "index":  l_i,
            "middle": l_m,
            "ring":   l_r,
            "little": l_l,
            "pitch":  l_p,
            "roll":   l_rl,
            "yaw":    l_y,
        }
    }


def frame_to_feature_vector(processed_frame):
    """
    Converts a Processed Frame into a flat 16-element list.
    Fixed order matches FEATURE_ORDER in config.py:
    [R_T, R_I, R_M, R_R, R_L, R_P, R_RL, R_Y,
     L_T, L_I, L_M, L_R, L_L, L_P, L_RL, L_Y]
    """
    r = processed_frame["right"]
    l = processed_frame["left"]
    return [
        r["thumb"],  r["index"],  r["middle"], r["ring"],  r["little"],
        r["pitch"],  r["roll"],   r["yaw"],
        l["thumb"],  l["index"],  l["middle"], l["ring"],  l["little"],
        l["pitch"],  l["roll"],   l["yaw"],
    ]
