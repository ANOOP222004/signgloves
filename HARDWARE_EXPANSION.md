# Hardware Expansion Plan — 2 Sensors Per Finger
# ============================================================
# PURPOSE OF THIS FILE:
#   This documents a known hardware limitation of the current glove
#   and the complete upgrade path to fix it — if the trained model
#   shows accuracy problems on specific sign pairs.
#
#   Read this BEFORE suggesting any hardware changes to Anoop.
#   The decision to upgrade should be evidence-based (confusion matrix
#   from trained model), not speculative.
#
# STATUS: Deferred — revisit after first model training
# DECISION DATE: March 2026 (Phase 3)
# ============================================================

---

## The Known Limitation

The current glove has **1 Hall effect sensor per finger**, mounted at the
**PIP joint** (middle joint — the proximal interphalangeal joint).

This means the system captures:
- ✅ PIP bend — whether the middle joint is bent or straight
- ✅ Wrist orientation — pitch, roll, yaw via MPU6050 IMU
- ❌ MCP bend — the knuckle (metacarpophalangeal) joint is NOT captured
- ❌ Finger spread — abduction/adduction between fingers is NOT captured

For a one-finger prototype this was correct. For a full 10-sign vocabulary,
certain sign pairs may be indistinguishable from PIP + IMU data alone if
they differ primarily at the MCP joint.

---

## Why This Was Deferred

The decision was made consciously in March 2026 (Phase 3) for these reasons:

1. **No evidence of a problem yet.** No dataset exists, no model has been
   trained, no confusion matrix exists. The limitation is theoretical.

2. **Vocabulary can be chosen to avoid it.** Signs selected to have
   clearly different PIP bend patterns AND wrist orientations may never
   trigger this issue.

3. **The IMU partially compensates.** The BiLSTM sees 60 frames of temporal
   data including wrist motion trajectory — not just final pose. Signs with
   identical finger bend may still be separable by how the wrist moves
   during the gesture.

4. **Hardware is not fully assembled.** Adding more sensors before the
   basic glove works end-to-end adds scope and risk with no proven benefit.

**The correct trigger to revisit this:** Train the model on the initial
dataset. Inspect the confusion matrix. If specific sign pairs show
consistently poor accuracy (< 80% on any pair), identify whether those
pairs differ at the MCP joint. If yes, proceed with the upgrade below.

---

## The Upgrade — 2 Sensors Per Finger

### What Changes Hardware-Side

Add one SS49E Hall sensor per finger at the **MCP joint** (knuckle),
in addition to the existing sensor at the PIP joint.

```
Current:   1 sensor per finger × 5 fingers × 2 hands = 10 sensors total
Upgraded:  2 sensors per finger × 5 fingers × 2 hands = 20 sensors total
```

Each finger now produces 2 independent readings:
- `thumb_pip`, `thumb_mcp`
- `index_pip`, `index_mcp`
- `middle_pip`, `middle_mcp`
- `ring_pip`, `ring_mcp`
- `little_pip`, `little_mcp`

### What Changes in the Packet Format

Current packet (19 fields):
```
F,<frame_id>,<R_T>,<R_I>,<R_M>,<R_R>,<R_L>,<R_P>,<R_RL>,<R_Y>,
<L_T>,<L_I>,<L_M>,<L_R>,<L_L>,<L_P>,<L_RL>,<L_Y>,<checksum>
```

Expanded packet (29 fields):
```
F,<frame_id>,
<R_T_PIP>,<R_T_MCP>,<R_I_PIP>,<R_I_MCP>,<R_M_PIP>,<R_M_MCP>,
<R_R_PIP>,<R_R_MCP>,<R_L_PIP>,<R_L_MCP>,
<R_P>,<R_RL>,<R_Y>,
<L_T_PIP>,<L_T_MCP>,<L_I_PIP>,<L_I_MCP>,<L_M_PIP>,<L_M_MCP>,
<L_R_PIP>,<L_R_MCP>,<L_L_PIP>,<L_L_MCP>,
<L_P>,<L_RL>,<L_Y>,
<checksum>
```

### What Changes in Software

Every change is contained and manageable. No architectural changes needed.

#### config.py
```python
# Change FINGER_CHANNELS to include both joints per finger
FINGER_CHANNELS = [
    'thumb_pip', 'thumb_mcp',
    'index_pip', 'index_mcp',
    'middle_pip', 'middle_mcp',
    'ring_pip', 'ring_mcp',
    'little_pip', 'little_mcp',
]

# Feature count increases: 10 finger channels × 2 hands + 6 IMU = 26
NUM_FEATURES = 26

FEATURE_ORDER = [
    "R_T_PIP", "R_T_MCP", "R_I_PIP", "R_I_MCP",
    "R_M_PIP", "R_M_MCP", "R_R_PIP", "R_R_MCP",
    "R_L_PIP", "R_L_MCP", "R_P", "R_RL", "R_Y",
    "L_T_PIP", "L_T_MCP", "L_I_PIP", "L_I_MCP",
    "L_M_PIP", "L_M_MCP", "L_R_PIP", "L_R_MCP",
    "L_L_PIP", "L_L_MCP", "L_P", "L_RL", "L_Y"
]
```

#### frame.py
Update `make_raw_frame()` and `make_processed_frame()` to include
`thumb_pip`, `thumb_mcp` etc. instead of just `thumb`.

The nested dict structure stays the same:
```python
frame['right']['thumb_pip']   # new key name
frame['right']['thumb_mcp']   # new key
```

#### packet_parser.py
Update field count check from 19 to 29.
Update field index mapping to parse PIP and MCP separately.

#### calibration.py
`FINGER_CHANNELS` is imported from config — update config and
calibration automatically uses the new channel list. No other changes.

#### processing_thread.py
Iterates over `FINGER_CHANNELS` from config — no changes needed.
The loop handles however many channels config defines.

#### filter.py
`EMAFilter` class is channel-agnostic — no changes needed.

#### All UI files (main_window.py, calibration_wizard.py)
Display labels iterate over `FINGER_CHANNELS` — update display names
dict to include `_pip` and `_mcp` variants. Minor cosmetic change only.

#### ML model (BiLSTM)
Input shape changes from `(60, 16)` to `(60, 26)`.
Retrain from scratch on new dataset — the old dataset is incompatible.
This is expected and unavoidable when hardware changes.

#### firmware (.ino)
Add `analogRead()` calls for 10 new MCP sensor GPIO pins.
Update packet construction to include new fields.
Update checksum calculation to include new fields.

---

## Files That Do NOT Change

- `serial_thread.py` — reads bytes, doesn't care about field count
- `filter.py` — per-channel class, channel-agnostic
- `processing_thread.py` — iterates FINGER_CHANNELS from config
- `dataset_manager.py` (Phase 4) — saves whatever columns frame has
- `ml_export.py` (Phase 8) — exports whatever NUM_FEATURES config says
- `main.py` — no changes needed

---

## Impact Summary Table

| Component | Change Required | Effort |
|---|---|---|
| Hardware | Add 10 more SS49E sensors + magnets | Medium |
| Firmware (.ino) | Add analogRead() × 10, update packet | Medium |
| config.py | Update FINGER_CHANNELS, NUM_FEATURES | Small |
| frame.py | Update key names in frame dicts | Small |
| packet_parser.py | Update field count + index mapping | Small |
| calibration.py | No change (uses FINGER_CHANNELS) | None |
| processing_thread.py | No change (iterates FINGER_CHANNELS) | None |
| filter.py | No change | None |
| main_window.py | Update display name labels | Small |
| calibration_wizard.py | No change | None |
| BiLSTM model | Retrain from scratch on new dataset | Large |
| Existing dataset | Incompatible — must re-record | Large |

---

## Decision Checklist for Future Claude Sessions

Before recommending this upgrade, verify ALL of these:

- [ ] Model has been trained on initial dataset
- [ ] Confusion matrix has been inspected
- [ ] At least one sign pair shows < 80% accuracy consistently
- [ ] The confused pairs differ primarily at the MCP joint (not IMU)
- [ ] Anoop has confirmed willingness to re-record the full dataset
- [ ] 3D printed glove assembly can physically accommodate more sensors

If any of these are not met, do NOT recommend the hardware upgrade.
The correct response is: "Let's first see what the confusion matrix shows."

---

## Vocabulary Note

The current planned vocabulary (as of Phase 3):
`HELLO, STOP, YES, NO, THANKYOU, SORRY, HELP, WATER, PLEASE, MORE`

Signs most at risk of confusion with PIP-only sensing:
- HELLO vs STOP — both are open flat hand, differ mainly in motion
- YES vs SORRY — both involve a closed fist, differ in wrist motion
- PLEASE vs STOP — both flat hand, differ in location and motion

The IMU temporal pattern may be sufficient to separate these.
Record the dataset and check before assuming hardware is the bottleneck.
