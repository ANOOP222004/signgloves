# visualization/hand_skeleton.py
# Phase 6 — FINAL VERIFIED VERSION
#
# Fixes applied vs previous version:
#   FIX 1: Left/right hand mirroring corrected.
#           Right hand renders on the RIGHT side of screen (positive X offset).
#           Left hand renders on the LEFT side of screen (negative X offset).
#           mirror=-1 on left hand correctly flips finger spread angles.
#   FIX 2: Manual rotation buttons added (rotate ±15° in azimuth and elevation).
#   FIX 3: QTimer.singleShot(500) GL init — skeleton always visible on startup.
#   FIX 4: _gl_ready guard — no crash if frame arrives before GL initializes.
#   FIX 5: os.environ OpenGL fix is in main.py (not here).
#
# Camera controls:
#   Mouse left drag  = free rotate (360° any direction)
#   Mouse right drag = zoom
#   Mouse middle     = pan
#   Buttons          = precise ±15° azimuth / elevation steps
#   View presets     = FRONT, SIDE, TOP, BACK, 3/4

import json
import os
import numpy as np

import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QGroupBox, QSlider, QLabel, QPushButton,
    QGridLayout,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from config import (
    FINGER_CHANNELS,
    FINGER_COLORS,
    SKELETON_TUNING_PATH,
    SKELETON_DEFAULT_FINGER_MAX_ANGLE,
    SKELETON_DEFAULT_SCALE,
    SKELETON_DEFAULT_IMU_SCALE,
)

# ── Hand geometry constants ───────────────────────────────────────────────────
# Segment lengths [MCP→PIP, PIP→DIP, DIP→TIP] in 3D units
FINGER_SEGMENT_LENGTHS = {
    'thumb':  [0.35, 0.28, 0.22],
    'index':  [0.35, 0.25, 0.20],
    'middle': [0.38, 0.27, 0.21],
    'ring':   [0.35, 0.25, 0.20],
    'little': [0.28, 0.20, 0.16],
}

# X, Y offset of each finger's MCP joint from wrist center
# These are for the RIGHT hand. Left hand mirrors on X via mirror=-1.
FINGER_BASE_OFFSETS = {
    'thumb':  (-0.30,  0.10),
    'index':  (-0.15,  0.50),
    'middle': ( 0.00,  0.55),
    'ring':   ( 0.15,  0.50),
    'little': ( 0.30,  0.42),
}

# Natural splay of each finger at bend=0 (degrees)
FINGER_SPREAD_ANGLES = {
    'thumb':  -35.0,
    'index':  -10.0,
    'middle':   0.0,
    'ring':    10.0,
    'little':  20.0,
}

# Camera preset positions (distance, elevation, azimuth)
CAMERA_PRESETS = {
    '3/4':   (4.5,  20,  45),
    'FRONT': (4.5,   0,   0),
    'SIDE':  (4.5,   0,  90),
    'TOP':   (4.5,  89,   0),
    'BACK':  (4.5,   0, 180),
}

# Manual rotation step per button press (degrees)
ROTATE_STEP = 15.0


def _sphere_mesh_at_origin(radius=0.045):
    """Generate vertex/face arrays for a sphere centered at the origin."""
    rows, cols = 6, 8
    verts, faces = [], []
    for i in range(rows + 1):
        lat = np.pi * (-0.5 + i / rows)
        y   = np.sin(lat)
        r   = np.cos(lat)
        for j in range(cols):
            lon = 2 * np.pi * j / cols
            verts.append([r * np.cos(lon) * radius, y * radius, r * np.sin(lon) * radius])
    for i in range(rows):
        for j in range(cols):
            p1 = i * cols + j
            p2 = i * cols + (j + 1) % cols
            p3 = (i + 1) * cols + j
            p4 = (i + 1) * cols + (j + 1) % cols
            faces += [[p1, p2, p3], [p2, p4, p3]]
    return (np.array(verts, dtype=np.float32),
            np.array(faces,  dtype=np.int32))


class HandSkeletonWidget(QWidget):
    """
    Real-time 3D hand skeleton with 360° interactive camera.

    FIXED: Right hand on right side, left hand on left side.
    FIXED: Manual rotation buttons for precise ±15° steps.

    Public slot:
        on_frame(processed_frame: dict)  ← connect to frame_ready
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._bend = {
            'right': {ch: 0.0 for ch in FINGER_CHANNELS},
            'left':  {ch: 0.0 for ch in FINGER_CHANNELS},
        }
        self._imu = {
            'right': {'pitch': 0.0, 'roll': 0.0, 'yaw': 0.0},
            'left':  {'pitch': 0.0, 'roll': 0.0, 'yaw': 0.0},
        }

        self._max_angles  = dict(SKELETON_DEFAULT_FINGER_MAX_ANGLE)
        self._scale       = SKELETON_DEFAULT_SCALE
        self._imu_scale   = SKELETON_DEFAULT_IMU_SCALE
        self._gl_ready    = False

        # Sphere mesh cache — populated by _precompute_sphere_cache() after GL init.
        # unit_sphere_verts[j] is a (N,3) array at origin for joint radius j.
        # Per-frame update: positioned = unit_sphere_verts[j] + joint_pos (one vectorized add).
        self._unit_sphere_verts: list  = []
        self._sphere_faces             = None
        self._sphere_colors: dict      = {}

        # Render timer — drives _update_skeleton at 25 Hz, decoupled from 30 Hz data rate.
        # on_frame() only stores values; this timer does the GL work.
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(40)
        self._render_timer.timeout.connect(self._update_skeleton)

        # Track camera state for manual buttons
        self._cam_distance  = 4.5
        self._cam_elevation = 20.0
        self._cam_azimuth   = 45.0

        # GL item storage
        self._finger_tubes  = {'right': {}, 'left': {}}
        self._joint_spheres = {'right': {}, 'left': {}}

        self._load_tuning()
        self._build_ui()
        QTimer.singleShot(500, self._init_gl)

    # ── Camera helpers ────────────────────────────────────────────────────────

    def _apply_camera(self):
        """Push current camera state to GLViewWidget."""
        self._view.setCameraPosition(
            distance=self._cam_distance,
            elevation=self._cam_elevation,
            azimuth=self._cam_azimuth,
        )

    def _rotate(self, d_az=0.0, d_el=0.0):
        """Rotate camera by delta azimuth and/or elevation."""
        self._cam_azimuth   = (self._cam_azimuth + d_az) % 360
        self._cam_elevation = max(-89, min(89, self._cam_elevation + d_el))
        self._apply_camera()

    def _preset_camera(self, dist, el, az):
        self._cam_distance  = dist
        self._cam_elevation = el
        self._cam_azimuth   = az
        self._apply_camera()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 4, 0)
        root.setSpacing(6)

        left = QVBoxLayout()
        left.setSpacing(4)

        # ── Camera preset buttons ─────────────────────────────────────
        preset_group = QGroupBox("CAMERA VIEW PRESETS")
        preset_row   = QHBoxLayout(preset_group)
        preset_row.setSpacing(3)
        btn_font = QFont("Courier New", 8)

        for label, (dist, el, az) in CAMERA_PRESETS.items():
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setFont(btn_font)
            btn.clicked.connect(
                (lambda d, e, a: lambda: self._preset_camera(d, e, a))(dist, el, az)
            )
            preset_row.addWidget(btn)

        left.addWidget(preset_group)

        # ── Manual rotation buttons ───────────────────────────────────
        rot_group  = QGroupBox("MANUAL ROTATE  (±15° per click)")
        rot_layout = QGridLayout(rot_group)
        rot_layout.setSpacing(3)

        # Arrow button definitions: (label, row, col, d_az, d_el)
        rot_buttons = [
            ("▲ UP",      0, 1,    0, +ROTATE_STEP),
            ("◀ LEFT",    1, 0, -ROTATE_STEP,    0),
            ("● RESET",   1, 1,    0,    0),   # special: reset to 3/4
            ("▶ RIGHT",   1, 2, +ROTATE_STEP,    0),
            ("▼ DOWN",    2, 1,    0, -ROTATE_STEP),
            ("↺ CCW",     0, 0, -ROTATE_STEP,    0),
            ("↻ CW",      0, 2, +ROTATE_STEP,    0),
            ("⊕ ZOOM IN", 2, 0,    0,    0),   # special
            ("⊖ ZOOM OUT",2, 2,    0,    0),   # special
        ]

        for label, row, col, d_az, d_el in rot_buttons:
            btn = QPushButton(label)
            btn.setFont(QFont("Courier New", 8))
            btn.setFixedHeight(28)

            if label == "● RESET":
                btn.clicked.connect(lambda: self._preset_camera(4.5, 20, 45))
            elif label == "⊕ ZOOM IN":
                def zoom_in():
                    self._cam_distance = max(1.0, self._cam_distance - 0.5)
                    self._apply_camera()
                btn.clicked.connect(zoom_in)
            elif label == "⊖ ZOOM OUT":
                def zoom_out():
                    self._cam_distance = min(12.0, self._cam_distance + 0.5)
                    self._apply_camera()
                btn.clicked.connect(zoom_out)
            else:
                btn.clicked.connect(
                    (lambda da, de: lambda: self._rotate(da, de))(d_az, d_el)
                )

            rot_layout.addWidget(btn, row, col)

        left.addWidget(rot_group)

        # ── 3D OpenGL viewport ────────────────────────────────────────
        pg.setConfigOptions(antialias=True)
        self._view = gl.GLViewWidget()
        self._view.setMinimumSize(460, 340)
        self._apply_camera()
        self._view.setBackgroundColor((8, 10, 8, 255))

        hint = QLabel(
            "🖱  Left drag: free rotate  |  Right drag: zoom  |  Middle: pan"
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #3A5A3A; font-size: 9px;")

        left.addWidget(self._view, stretch=1)
        left.addWidget(hint)

        root.addLayout(left, stretch=3)
        root.addWidget(self._build_tuning_panel(), stretch=1)

    def _build_tuning_panel(self) -> QGroupBox:
        group  = QGroupBox("TUNING")
        layout = QVBoxLayout(group)
        layout.setSpacing(5)
        lf = QFont("Courier New", 9)

        self._angle_sliders = {}
        self._angle_labels  = {}

        # Per-finger sliders
        fg     = QGroupBox("FINGER MAX ANGLE")
        fg_lay = QGridLayout(fg)
        fg_lay.setSpacing(3)

        for row, ch in enumerate(FINGER_CHANNELS):
            r, g, b = FINGER_COLORS[ch]
            nl = QLabel(ch.upper())
            nl.setFont(lf)
            nl.setFixedWidth(52)
            nl.setStyleSheet(f"color: rgb({r},{g},{b}); font-weight: bold;")

            sl = QSlider(Qt.Horizontal)
            sl.setMinimum(10)
            sl.setMaximum(130)
            sl.setValue(int(self._max_angles[ch]))
            sl.setFixedWidth(110)

            vl = QLabel(f"{int(self._max_angles[ch])}°")
            vl.setFont(lf)
            vl.setFixedWidth(32)
            vl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self._angle_sliders[ch] = sl
            self._angle_labels[ch]  = vl

            def make_h(channel, label):
                def h(val):
                    self._max_angles[channel] = float(val)
                    label.setText(f"{val}°")
                    if self._gl_ready:
                        self._update_skeleton()
                return h
            sl.valueChanged.connect(make_h(ch, vl))

            fg_lay.addWidget(nl, row, 0)
            fg_lay.addWidget(sl, row, 1)
            fg_lay.addWidget(vl, row, 2)
        layout.addWidget(fg)

        # Scale
        sg = QGroupBox("HAND SCALE")
        sl = QVBoxLayout(sg)
        self._scale_slider = QSlider(Qt.Horizontal)
        self._scale_slider.setMinimum(50)
        self._scale_slider.setMaximum(200)
        self._scale_slider.setValue(int(self._scale * 100))
        self._scale_label = QLabel(f"{self._scale:.1f}x")
        self._scale_label.setFont(lf)
        self._scale_label.setAlignment(Qt.AlignCenter)

        def on_scale(val):
            self._scale = val / 100.0
            self._scale_label.setText(f"{self._scale:.1f}x")
            if self._gl_ready:
                self._rebuild_gl()
        self._scale_slider.valueChanged.connect(on_scale)
        sl.addWidget(self._scale_slider)
        sl.addWidget(self._scale_label)
        layout.addWidget(sg)

        # IMU sensitivity
        ig = QGroupBox("WRIST SENSITIVITY")
        il = QVBoxLayout(ig)
        self._imu_slider = QSlider(Qt.Horizontal)
        self._imu_slider.setMinimum(0)
        self._imu_slider.setMaximum(300)
        self._imu_slider.setValue(int(self._imu_scale * 100))
        self._imu_label = QLabel(f"{self._imu_scale:.1f}x")
        self._imu_label.setFont(lf)
        self._imu_label.setAlignment(Qt.AlignCenter)

        def on_imu(val):
            self._imu_scale = val / 100.0
            self._imu_label.setText(f"{self._imu_scale:.1f}x")
            if self._gl_ready:
                self._update_skeleton()
        self._imu_slider.valueChanged.connect(on_imu)
        il.addWidget(self._imu_slider)
        il.addWidget(self._imu_label)
        layout.addWidget(ig)

        # Show/Hide toggles
        vh = QGroupBox("SHOW / HIDE")
        vl = QVBoxLayout(vh)

        rb = QPushButton("RIGHT HAND: ON")
        rb.setFont(QFont("Courier New", 8))
        rb.setCheckable(True)
        rb.setChecked(True)

        lb = QPushButton("LEFT HAND: ON")
        lb.setFont(QFont("Courier New", 8))
        lb.setCheckable(True)
        lb.setChecked(True)

        def tog_r(c):
            rb.setText(f"RIGHT HAND: {'ON' if c else 'OFF'}")
            if self._gl_ready:
                self._set_vis('right', c)

        def tog_l(c):
            lb.setText(f"LEFT HAND: {'ON' if c else 'OFF'}")
            if self._gl_ready:
                self._set_vis('left', c)

        rb.toggled.connect(tog_r)
        lb.toggled.connect(tog_l)
        vl.addWidget(rb)
        vl.addWidget(lb)
        layout.addWidget(vh)

        # Save / Reset
        sv = QPushButton("💾  SAVE TUNING")
        sv.setObjectName("save_btn")
        sv.setFont(QFont("Courier New", 9))
        sv.clicked.connect(self._save_tuning)

        rs = QPushButton("RESET DEFAULTS")
        rs.setFont(QFont("Courier New", 9))
        rs.clicked.connect(self._reset_defaults)

        layout.addWidget(sv)
        layout.addWidget(rs)
        layout.addStretch()
        return group

    # ── GL initialization ─────────────────────────────────────────────────────

    def _init_gl(self):
        """500ms delayed GL init — context guaranteed ready."""
        try:
            grid = gl.GLGridItem()
            grid.setSize(6, 6)
            grid.setSpacing(0.5, 0.5)
            grid.setColor((25, 45, 25, 120))
            self._view.addItem(grid)

            axis = gl.GLAxisItem()
            axis.setSize(0.3, 0.3, 0.3)
            self._view.addItem(axis)

            self._build_gl()
            self._gl_ready = True
            self._precompute_sphere_cache()
            self._render_timer.start()
        except Exception as e:
            print(f"[HandSkeleton] GL init failed: {e}")
            print("  Run: pip install PyOpenGL PyOpenGL_accelerate --upgrade")

    def _precompute_sphere_cache(self):
        """
        Pre-compute sphere vertex arrays centered at origin for each of the
        4 joint radii.  Per-frame update is then a single vectorized numpy
        add (unit_verts + joint_pos) instead of re-running Python loops.
        Colors are constant per finger so they are pre-computed here too.
        """
        base_radii = [0.050, 0.042, 0.035, 0.028]
        self._unit_sphere_verts = []
        for r in base_radii:
            verts, faces = _sphere_mesh_at_origin(r * self._scale)
            self._unit_sphere_verts.append(verts)
        _, self._sphere_faces = _sphere_mesh_at_origin(base_radii[0] * self._scale)

        n_verts = len(self._unit_sphere_verts[0])
        self._sphere_colors = {}
        for ch in FINGER_CHANNELS:
            rc, gc, bc = FINGER_COLORS[ch]
            colors = np.ones((n_verts, 4), dtype=np.float32)
            colors[:, 0] = rc / 255.0
            colors[:, 1] = gc / 255.0
            colors[:, 2] = bc / 255.0
            colors[:, 3] = 0.95
            self._sphere_colors[ch] = colors

    def _build_gl(self):
        """Create all GL line and sphere items for both hands."""
        dummy = np.array([[0, 0, 0], [0, 0.01, 0]], dtype=np.float32)
        for hand in ['right', 'left']:
            self._finger_tubes[hand]  = {}
            self._joint_spheres[hand] = {}
            for ch in FINGER_CHANNELS:
                r, g, b = FINGER_COLORS[ch]
                color   = (r/255.0, g/255.0, b/255.0, 1.0)

                # 3 thick segment lines per finger
                segs = []
                for _ in range(3):
                    line = gl.GLLinePlotItem(
                        pos=dummy, color=color,
                        width=5.0, antialias=True, mode='lines'
                    )
                    self._view.addItem(line)
                    segs.append(line)
                self._finger_tubes[hand][ch] = segs

                # 4 joint sphere meshes per finger
                spheres = []
                for j in range(4):
                    radius = (0.050 if j == 0 else
                              0.042 if j == 1 else
                              0.035 if j == 2 else 0.028)
                    verts, faces = _sphere_mesh_at_origin(radius)
                    colors = np.ones((len(verts), 4), dtype=np.float32)
                    colors[:, 0] = r / 255.0
                    colors[:, 1] = g / 255.0
                    colors[:, 2] = b / 255.0
                    colors[:, 3] = 0.95
                    mesh = gl.GLMeshItem(
                        vertexes=verts, faces=faces,
                        vertexColors=colors,
                        smooth=True, drawEdges=False,
                    )
                    self._view.addItem(mesh)
                    spheres.append(mesh)
                self._joint_spheres[hand][ch] = spheres

    def _rebuild_gl(self):
        """Remove and rebuild all GL items (called when scale changes)."""
        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS:
                for item in self._finger_tubes[hand].get(ch, []):
                    self._view.removeItem(item)
                for item in self._joint_spheres[hand].get(ch, []):
                    self._view.removeItem(item)
        self._build_gl()
        self._precompute_sphere_cache()

    def _set_vis(self, hand: str, visible: bool):
        for ch in FINGER_CHANNELS:
            for item in self._finger_tubes[hand].get(ch, []):
                item.setVisible(visible)
            for item in self._joint_spheres[hand].get(ch, []):
                item.setVisible(visible)

    # ── Forward kinematics ────────────────────────────────────────────────────

    def _compute_hand(self, hand: str) -> dict:
        """
        Compute [mcp, pip, dip, tip] for all fingers.

        FIXED MIRRORING:
          Right hand: x_off = +1.2 (renders on RIGHT side of screen)
                      mirror = +1.0 (spread angles unchanged)
          Left hand:  x_off = -1.2 (renders on LEFT side of screen)
                      mirror = -1.0 (spread angles flipped for correct anatomy)

        The base offsets (FINGER_BASE_OFFSETS) are defined for the right hand.
        mirror=-1 on the left hand flips the lateral (bx) component so the
        thumb appears on the correct (outer) side of each hand.
        """
        points = {}
        sc     = self._scale

        # RIGHT hand: positive X side, no mirroring
        # LEFT hand:  negative X side, mirrored
        if hand == 'right':
            x_off  =  1.2 * sc
            mirror =  1.0
        else:
            x_off  = -1.2 * sc
            mirror = -1.0

        for ch in FINGER_CHANNELS:
            bend    = self._bend[hand][ch]
            segs    = FINGER_SEGMENT_LENGTHS[ch]
            bx, by  = FINGER_BASE_OFFSETS[ch]
            spread  = FINGER_SPREAD_ANGLES[ch]
            max_ang = self._max_angles[ch]

            total   = bend * max_ang
            mcp_ang = total * 0.35
            pip_ang = total * 0.40
            dip_ang = total * 0.25

            # mirror flips both the lateral base offset and the spread angle
            spread_rad = np.radians(spread * mirror)
            dx = np.sin(spread_rad)

            mcp = np.array([
                x_off + mirror * bx * sc,
                by * sc,
                0.0
            ], dtype=np.float32)

            dy1 = np.cos(np.radians(mcp_ang))
            dz1 = np.sin(np.radians(mcp_ang))
            pip = mcp + np.array(
                [dx*segs[0]*sc, dy1*segs[0]*sc, dz1*segs[0]*sc],
                dtype=np.float32)

            cum2 = mcp_ang + pip_ang
            dy2, dz2 = np.cos(np.radians(cum2)), np.sin(np.radians(cum2))
            dip = pip + np.array(
                [dx*segs[1]*sc, dy2*segs[1]*sc, dz2*segs[1]*sc],
                dtype=np.float32)

            cum3 = cum2 + dip_ang
            dy3, dz3 = np.cos(np.radians(cum3)), np.sin(np.radians(cum3))
            tip = dip + np.array(
                [dx*segs[2]*sc, dy3*segs[2]*sc, dz3*segs[2]*sc],
                dtype=np.float32)

            points[ch] = [mcp, pip, dip, tip]
        return points

    def _apply_imu(self, points: dict, hand: str) -> dict:
        """Rotate all points by IMU pitch and roll."""
        pitch = np.radians(self._imu[hand]['pitch'] * self._imu_scale)
        roll  = np.radians(self._imu[hand]['roll']  * self._imu_scale)
        cp, sp = np.cos(pitch), np.sin(pitch)
        cr, sr = np.cos(roll),  np.sin(roll)
        Rx = np.array([[1,  0,   0],
                       [0,  cp, -sp],
                       [0,  sp,  cp]], dtype=np.float32)
        Ry = np.array([[ cr, 0, sr],
                       [ 0,  1,  0],
                       [-sr, 0, cr]], dtype=np.float32)
        R = Ry @ Rx
        return {ch: [R @ pt for pt in js] for ch, js in points.items()}

    # ── Skeleton update ───────────────────────────────────────────────────────

    def _update_skeleton(self):
        if not self._gl_ready:
            return

        for hand in ['right', 'left']:
            pts = self._apply_imu(self._compute_hand(hand), hand)

            for ch in FINGER_CHANNELS:
                joints  = pts[ch]
                segs    = self._finger_tubes[hand].get(ch, [])
                spheres = self._joint_spheres[hand].get(ch, [])
                r, g, b = FINGER_COLORS[ch]

                # Update segment lines
                for i, (a, b_pt) in enumerate(zip(joints[:-1], joints[1:])):
                    if i < len(segs):
                        segs[i].setData(
                            pos=np.array([a, b_pt], dtype=np.float32)
                        )

                # Update joint spheres — vectorized: one numpy add per joint,
                # no Python loops, no per-frame array allocation for geometry.
                for j, joint_pos in enumerate(joints):
                    if j < len(spheres) and self._unit_sphere_verts:
                        spheres[j].setMeshData(
                            vertexes=self._unit_sphere_verts[j] + joint_pos,
                            faces=self._sphere_faces,
                            vertexColors=self._sphere_colors[ch],
                        )

    # ── Frame slot ────────────────────────────────────────────────────────────

    def on_frame(self, processed_frame: dict):
        """Store latest sensor values. Rendering is driven by _render_timer at 25 Hz."""
        for hand in ['right', 'left']:
            for ch in FINGER_CHANNELS:
                self._bend[hand][ch] = processed_frame[hand][ch]
            self._imu[hand]['pitch'] = processed_frame[hand]['pitch']
            self._imu[hand]['roll']  = processed_frame[hand]['roll']
            self._imu[hand]['yaw']   = processed_frame[hand]['yaw']

    # ── Tuning persistence ────────────────────────────────────────────────────

    def _save_tuning(self):
        d = os.path.dirname(SKELETON_TUNING_PATH)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(SKELETON_TUNING_PATH, 'w') as f:
            json.dump({'max_angles': self._max_angles,
                       'scale':      self._scale,
                       'imu_scale':  self._imu_scale}, f, indent=2)
        print(f"Tuning saved → {SKELETON_TUNING_PATH}")

    def _load_tuning(self):
        if not os.path.exists(SKELETON_TUNING_PATH):
            return
        try:
            with open(SKELETON_TUNING_PATH) as f:
                d = json.load(f)
            self._max_angles = d.get('max_angles', self._max_angles)
            self._scale      = d.get('scale',      self._scale)
            self._imu_scale  = d.get('imu_scale',  self._imu_scale)
        except Exception:
            pass

    def _reset_defaults(self):
        self._max_angles = dict(SKELETON_DEFAULT_FINGER_MAX_ANGLE)
        self._scale      = SKELETON_DEFAULT_SCALE
        self._imu_scale  = SKELETON_DEFAULT_IMU_SCALE
        for ch in FINGER_CHANNELS:
            self._angle_sliders[ch].setValue(int(self._max_angles[ch]))
        self._scale_slider.setValue(int(self._scale * 100))
        self._imu_slider.setValue(int(self._imu_scale * 100))
        if self._gl_ready:
            self._update_skeleton()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def initialize(self):
        """
        Start GL initialization. Called once when the Visualize tab is first
        selected. Deferring to tab-show time guarantees the GLViewWidget surface
        is fully visible before any GL context or item creation happens, which
        avoids the black-viewport bug on Ubuntu + Mesa software rendering.
        """
        if not self._gl_ready:
            QTimer.singleShot(100, self._init_gl)

    def stop(self):
        """Stop the render timer. Call from MainWindow.closeEvent."""
        self._render_timer.stop()
        self._gl_ready = False
