from __future__ import annotations

import json
import math
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QPropertyAnimation,
    QRectF, QSequentialAnimationGroup, QSize, Qt, QTimer, QUrl,
    pyqtSignal, pyqtProperty,
)
from PyQt6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QFontDatabase,
    QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPushButton, QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout,
    QWidget, QProgressBar,
)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

_DEFAULT_W, _DEFAULT_H = 1100, 780
_MIN_W,     _MIN_H     = 900, 600
_LEFT_W  = 180
_RIGHT_W = 380

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

class C:
    """Modern AI color palette — deep void base, single violet-cyan light source,
    calibrated so glow and shadow read as actual light rather than flat fills."""
    BG          = "#060609"   # near-black void, gives glow somewhere to bloom into
    BG_GRAD     = "#0f0f18"   # lifted center for the top-lit dome background
    PANEL       = "#131320"   # panels sit one step above the void
    PANEL_GLASS = "#171726"
    CARD        = "#1b1b2c"   # cards sit one step above panels — visible hierarchy
    BORDER      = "#26263a"
    BORDER_L    = "#3a3a54"
    GLOW        = "#5a5aff"

    # Light source: one violet hue, walked through a tight tint/shade ramp
    # so gradients feel like one material catching light, not three accents.
    PRIMARY     = "#7c5cff"
    PRIMARY_L   = "#a78bfa"
    PRIMARY_D   = "#5b3fd6"
    ACCENT      = "#22d3ee"
    ACCENT_L    = "#67e8f9"
    SUCCESS     = "#2dd4a7"
    SUCCESS_L   = "#5eead4"
    WARNING     = "#f5b756"
    ERROR       = "#ff5c7a"
    ERROR_L     = "#ff8fa3"
    ERROR_D     = "#c23a58"

    # Text colors
    TEXT        = "#eeeef7"
    TEXT_D      = "#a8a8c0"
    TEXT_M      = "#75758f"
    TEXT_DIM    = "#4b4b62"
    WHITE       = "#ffffff"

    # Lighting-specific tokens
    SPECULAR    = "#ffffff"   # highlight glints on orb / glass edges
    RIM         = "#c9b8ff"   # cool rim-light along panel top edges
    SHADOW      = "#000000"

    # Special effects
    GLASS       = "#10f1ccea"
    GLASS_B     = "#5fbe5212"
    GRAD_START  = "#7c5cff"
    GRAD_END    = "#22d3ee"

    # Status colors
    MUTED_C     = "#a90ce7"
    SPEAKING_C  = "#1ce50a"

def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h)
    c.setAlpha(a)
    return c

def _apply_shadow(widget: QWidget, color: str = C.PRIMARY, radius: int = 20, offset: int = 0):
    """Apply a colored glow shadow — for widgets that should look lit from within."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(radius)
    shadow.setColor(qcol(color, 60))
    shadow.setOffset(0, offset)
    widget.setGraphicsEffect(shadow)

def _apply_elevation(widget: QWidget, radius: int = 36, offset: int = 14, alpha: int = 150):
    """Apply a soft black ambient shadow — for panels that should look like they're
    floating a few millimeters above the background, the way real UI chrome does."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(radius)
    shadow.setColor(qcol(C.SHADOW, alpha))
    shadow.setOffset(0, offset)
    widget.setGraphicsEffect(shadow)


class HoverGlowButton(QPushButton):
    """A button whose glow shadow genuinely animates on hover, via QPropertyAnimation
    on the shadow effect's real blurRadius property — not a CSS-transition impression,
    an actual eased animation. Every interactive control in this UI is built from this
    so the whole interface feels like it responds to touch, not just click."""

    def __init__(self, *args, glow_color: str = None, base_radius: int = 16,
                 hover_radius: int = 34, **kwargs):
        super().__init__(*args, **kwargs)
        self._glow_color = glow_color or C.PRIMARY
        self._base_radius = base_radius
        self._hover_radius = hover_radius

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setColor(qcol(self._glow_color, 90))
        self._shadow.setBlurRadius(base_radius)
        self._shadow.setOffset(0, 2)
        self.setGraphicsEffect(self._shadow)

        self._anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def enterEvent(self, e):
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(self._hover_radius)
        self._anim.start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(self._base_radius)
        self._anim.start()
        super().leaveEvent(e)

class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()
        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # NVIDIA
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode == 0:
                vals = [float(v.strip()) for v in r.stdout.strip().split("\n") if v.strip()]
                if vals:
                    return sum(vals) / len(vals)
        except Exception:
            pass

        # AMD (Linux)
        if _OS == "Linux":
            try:
                r = subprocess.run(
                    ["rocm-smi", "--showuse", "--csv"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                return float(parts[1].strip().replace("%", ""))
                            except ValueError:
                                pass
            except Exception:
                pass

            # Intel GPU (Linux)
            try:
                r = subprocess.run(
                    ["intel_gpu_top", "-J", "-s", "500"],
                    capture_output=True, text=True, timeout=1
                )
                if r.returncode == 0 and "Render/3D" in r.stdout:
                    import re
                    m = re.search(r'"busy":\s*([\d.]+)', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        # macOS — powermetrics (GPU Engine)
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["sudo", "-n", "powermetrics", "-n", "1", "-i", "500",
                     "--samplers", "gpu_power"],
                    capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0 and "GPU" in r.stdout:
                    import re
                    m = re.search(r'GPU\s+Active:\s+([\d.]+)%', r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()
            candidates = ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                          "cpu-thermal", "zenpower", "it8688"]
            for name in candidates:
                if name in temps:
                    entries = [e for e in temps[name] if e.current > 0]
                    if entries:
                        return sum(e.current for e in entries) / len(entries)
            for entries in temps.values():
                valid_entries = [e for e in entries if e.current > 0]
                if valid_entries:
                    return sum(e.current for e in valid_entries) / len(valid_entries)
        except Exception:
            pass
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["osx-cpu-temp"], capture_output=True, text=True, timeout=2
                )
                if r.returncode == 0:
                    import re
                    m = re.search(r"([\d.]+)", r.stdout)
                    if m:
                        return float(m.group(1))
            except Exception:
                pass

        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-Command",
                     "(Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace root/wmi).CurrentTemperature"],
                    capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = float(r.stdout.strip().split("\n")[0])
                    return (raw / 10.0) - 273.15
            except Exception:
                pass

        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }

_metrics = _SysMetrics()

class HudCanvas(QWidget):
    """Modern AI Orb visualization — smooth animations, glow, and a state-driven
    light color that eases continuously rather than snapping between two colors."""

    STATE_COLORS = {
        "LISTENING":     C.SUCCESS,
        "THINKING":       C.WARNING,
        "PROCESSING":     C.WARNING,
        "SPEAKING":       C.PRIMARY,
        "MUTED":          C.ERROR,
        "INITIALIZING":   C.PRIMARY_L,
    }

    def __init__(self, face_path: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(350, 350)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted    = False
        self.speaking = False
        self.state    = "INITIALIZING"

        self._tick       = 0
        self._scale      = 1.0
        self._tgt_scale  = 1.0
        self._glow       = 0.5
        self._tgt_glow   = 0.5
        self._last_t     = time.time()
        self._orbit1     = 0.0
        self._orbit2     = 120.0
        self._orbit3     = 240.0
        self._pulse      = 0.0
        self._particles: list[list[float]] = []
        self._face_px: QPixmap | None = None
        self._load_face(face_path)

        # Current displayed light color, eased toward whatever the active
        # state calls for. Kept as float RGB so the lerp is sub-pixel smooth
        # rather than snapping between discrete hex values.
        start = QColor(C.PRIMARY_L)
        self._col_r, self._col_g, self._col_b = start.red(), start.green(), start.blue()

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(16)

    def _active_state_key(self) -> str:
        if self.muted:
            return "MUTED"
        if self.speaking:
            return "SPEAKING"
        return self.state if self.state in self.STATE_COLORS else "LISTENING"

    def _c(self, alpha: int = 255) -> QColor:
        """Current eased light color at the given alpha — the single source of
        truth every glow/ring/gradient in this canvas should pull from."""
        c = QColor(int(self._col_r), int(self._col_g), int(self._col_b))
        c.setAlpha(max(0, min(255, alpha)))
        return c

    def _load_face(self, path: str):
        try:
            from PIL import Image, ImageDraw
            import io
            img = Image.open(path).convert("RGBA")
            sz  = min(img.size)
            img = img.resize((sz, sz), Image.LANCZOS)
            mk  = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(mk).ellipse((2, 2, sz - 2, sz - 2), fill=255)
            img.putalpha(mk)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap()
            px.loadFromData(buf.getvalue())
            self._face_px = px
        except Exception:
            self._face_px = None

    def _step(self):
        self._tick += 1
        now = time.time()

        # Ease the displayed color toward the target state's color. This is
        # what makes a LISTENING → THINKING transition sweep from green to
        # amber through the ramp, instead of jump-cutting.
        target = QColor(self.STATE_COLORS.get(self._active_state_key(), C.PRIMARY))
        col_sp = 0.06
        self._col_r += (target.red()   - self._col_r) * col_sp
        self._col_g += (target.green() - self._col_g) * col_sp
        self._col_b += (target.blue()  - self._col_b) * col_sp

        # Smooth breathing animation
        if now - self._last_t > (0.08 if self.speaking else 0.2):
            if self.speaking:
                self._tgt_scale = random.uniform(1.02, 1.08)
                self._tgt_glow  = random.uniform(0.7, 1.0)
            elif self.muted:
                self._tgt_scale = random.uniform(0.98, 1.0)
                self._tgt_glow  = random.uniform(0.2, 0.35)
            else:
                self._tgt_scale = random.uniform(1.0, 1.02)
                self._tgt_glow  = random.uniform(0.45, 0.65)
            self._last_t = now

        # Smooth transitions
        sp = 0.12
        self._scale += (self._tgt_scale - self._scale) * sp
        self._glow  += (self._tgt_glow  - self._glow)  * sp

        # Orbital rotations
        orb_speed = 0.4 if self.speaking else 0.15
        self._orbit1 = (self._orbit1 + orb_speed) % 360
        self._orbit2 = (self._orbit2 + orb_speed * 0.7) % 360
        self._orbit3 = (self._orbit3 + orb_speed * 0.5) % 360

        # Pulse wave
        pulse_speed = 1.5 if self.speaking else 0.6
        self._pulse = (self._pulse + pulse_speed) % 360

        # Particles for speaking state
        if self.speaking and random.random() < 0.3:
            W, H = self.width(), self.height()
            cx, cy = W / 2, H / 2
            ang = random.uniform(0, 2 * math.pi)
            r_s = min(W, H) * 0.22
            self._particles.append([
                cx + math.cos(ang) * r_s,
                cy + math.sin(ang) * r_s,
                math.cos(ang) * random.uniform(0.5, 1.5),
                math.sin(ang) * random.uniform(0.5, 1.5) - 0.3,
                1.0,
            ])
        
        self._particles = [
            [p[0]+p[2], p[1]+p[3], p[2]*0.98, p[3]*0.98, p[4]-0.02]
            for p in self._particles if p[4] > 0
        ]

        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)

        # Background: soft vignette matching the window's dome light, rather
        # than a flat fill — keeps the orb the brightest thing on screen.
        bg_grad = QRadialGradient(cx, cy * 0.85, fw * 0.95)
        bg_grad.setColorAt(0, qcol(C.BG_GRAD))
        bg_grad.setColorAt(0.6, qcol(C.BG))
        bg_grad.setColorAt(1, qcol("#020203"))
        p.fillRect(self.rect(), bg_grad)

        r_orb = fw * 0.28

        # Faint concentric range rings, like a sensor sweep at rest —
        # replaces the printed dot-grid with something that reads as
        # instrumentation rather than texture.
        for i in range(1, 4):
            rr = r_orb * (2.6 + i * 0.55)
            p.setPen(QPen(qcol(C.GLOW, 10), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - rr, cy - rr, rr * 2, rr * 2))

        # Outer glow rings — squared falloff reads as a soft bloom rather
        # than a stack of visibly discrete rings.
        glow_alpha = int(self._glow * 90)
        steps = 9
        for i in range(steps):
            frac = i / steps
            r = r_orb * (1.5 + frac * 1.1)
            a = max(0, int(glow_alpha * (1 - frac) ** 2))
            p.setPen(QPen(self._c(a), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # Orbiting dots
        orbit_r = [r_orb * 1.4, r_orb * 1.7, r_orb * 2.0]
        orbit_angles = [self._orbit1, self._orbit2, self._orbit3]
        orbit_colors = [C.PRIMARY_L, C.ACCENT, C.SUCCESS]
        
        for r, angle, color in zip(orbit_r, orbit_angles, orbit_colors):
            x = cx + r * math.cos(math.radians(angle))
            y = cy + r * math.sin(math.radians(angle))
            
            # Orbit path (faint)
            p.setPen(QPen(qcol(color, 20), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
            
            # Orbiting dot
            p.setBrush(QBrush(qcol(color, int(self._glow * 200))))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, y), 4, 4)
            
            # Dot glow
            dot_grad = QRadialGradient(x, y, 12)
            dot_grad.setColorAt(0, qcol(color, int(self._glow * 100)))
            dot_grad.setColorAt(1, qcol(color, 0))
            p.setBrush(dot_grad)
            p.drawEllipse(QPointF(x, y), 12, 12)

        # Pulse wave
        pulse_r = r_orb * (1.0 + 0.3 * math.sin(math.radians(self._pulse)))
        pulse_a = int(60 * (0.5 + 0.5 * math.sin(math.radians(self._pulse))))
        p.setPen(QPen(self._c(pulse_a), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(cx - pulse_r, cy - pulse_r, pulse_r * 2, pulse_r * 2))

        # Main orb
        if self._face_px:
            fsz = int(fw * 0.50 * self._scale)
            scaled = self._face_px.scaled(
                fsz, fsz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.drawPixmap(int(cx - fsz / 2), int(cy - fsz / 2), scaled)
        else:
            # Modern orb with gradient
            orb_r = int(r_orb * self._scale)
            
            # Outer glow
            for i in range(6, 0, -1):
                glow_r = orb_r + i * 8
                alpha = int(self._glow * 40 * (1 - i / 6))
                p.setBrush(QBrush(self._c(alpha)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QRectF(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2))
            
            # Main orb gradient — light, mid, and shade stops all pulled from
            # the same eased hue so the sphere reads as one lit material.
            base = QColor(int(self._col_r), int(self._col_g), int(self._col_b))
            light = base.lighter(135)
            dark  = base.darker(150)
            orb_grad = QRadialGradient(cx - orb_r * 0.3, cy - orb_r * 0.3, orb_r * 1.5)
            orb_grad.setColorAt(0,   qcol(light.name(), 200))
            orb_grad.setColorAt(0.5, qcol(base.name(), 150))
            orb_grad.setColorAt(1,   qcol(dark.name(), 100))
            
            p.setBrush(orb_grad)
            p.setPen(QPen(qcol(C.WHITE, 30), 1))
            p.drawEllipse(QRectF(cx - orb_r, cy - orb_r, orb_r * 2, orb_r * 2))

            # Specular highlight — a soft glint offset toward the upper-left,
            # as if a single light source sits above and to one side. This is
            # what separates "lit sphere" from "flat filled circle."
            hl_cx = cx - orb_r * 0.32
            hl_cy = cy - orb_r * 0.38
            hl_r  = orb_r * 0.55
            spec = QRadialGradient(hl_cx, hl_cy, hl_r)
            spec.setColorAt(0, qcol(C.SPECULAR, int(90 * self._glow)))
            spec.setColorAt(0.4, qcol(C.SPECULAR, int(28 * self._glow)))
            spec.setColorAt(1, qcol(C.SPECULAR, 0))
            p.setBrush(spec)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(hl_cx, hl_cy), hl_r, hl_r)

            # Thin rim light along the lower edge — a hint of bounced light,
            # keeps the sphere from looking lit from only one flat angle.
            p.setPen(QPen(light, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            rim_rect = QRectF(cx - orb_r, cy - orb_r, orb_r * 2, orb_r * 2)
            p.drawArc(rim_rect, -50 * 16, 100 * 16)

            # AI label
            p.setPen(QPen(qcol(C.WHITE, 220), 1))
            p.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            p.drawText(QRectF(cx - 80, cy - 12, 160, 24),
                       Qt.AlignmentFlag.AlignCenter, "LESSAN")

        # Particles
        for pt in self._particles:
            a = max(0, min(255, int(pt[4] * 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self._c(a)))
            p.drawEllipse(QPointF(pt[0], pt[1]), 3, 3)

        # Status indicator
        status_y = cy + r_orb * 1.8
        
        # Status pill background
        pill_w, pill_h = 140, 32
        pill_rect = QRectF(cx - pill_w/2, status_y - pill_h/2, pill_w, pill_h)

        state_key = self._active_state_key()
        status_text = {
            "MUTED": "MUTED", "SPEAKING": "SPEAKING", "THINKING": "THINKING",
            "PROCESSING": "PROCESSING", "LISTENING": "LISTENING",
        }.get(state_key, self.state)
        status_color = self.STATE_COLORS.get(state_key, C.PRIMARY)

        # Pill background
        p.setBrush(QBrush(qcol(status_color, 30)))
        p.setPen(QPen(qcol(status_color, 100), 1))
        p.drawRoundedRect(pill_rect, 16, 16)
        
        # Status dot
        dot_x = cx - pill_w/2 + 20
        p.setBrush(QBrush(qcol(status_color, 255)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(dot_x, status_y), 4, 4)
        
        # Status text
        p.setPen(QPen(qcol(status_color), 1))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.drawText(QRectF(cx - pill_w/2 + 30, status_y - 10, pill_w - 40, 20),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, status_text)

class MetricCard(QWidget):
    """Modern metric display card with gradient progress that eases toward
    each new reading rather than snapping — small motion, but it's what makes
    a dashboard feel alive between updates instead of static."""

    def __init__(self, label: str, icon: str, color: str = C.PRIMARY, parent=None):
        super().__init__(parent)
        self._label = label
        self._icon = icon
        self._color = color
        self._value = 0.0          # animated, displayed value
        self._target_value = 0.0   # actual latest reading
        self._text  = "--"
        self.setFixedHeight(48)
        self.setMinimumWidth(90)
        _apply_shadow(self, color, radius=18, offset=4)

        self._anim = QPropertyAnimation(self, b"value", self)
        self._anim.setDuration(480)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def getValue(self):
        return self._value

    def setValue(self, v):
        self._value = v
        self.update()

    value = pyqtProperty(float, getValue, setValue)

    def set_value(self, pct: float, text: str):
        self._target_value = max(0.0, min(100.0, pct))
        self._text  = text
        self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(self._target_value)
        self._anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        # Card background with subtle gradient
        card_grad = QLinearGradient(0, 0, 0, H)
        card_grad.setColorAt(0, qcol(C.CARD, 200))
        card_grad.setColorAt(1, qcol(C.PANEL, 200))
        p.setBrush(card_grad)
        p.setPen(QPen(qcol(C.BORDER_L, 80), 1))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 8, 8)

        # Icon
        p.setFont(QFont("Segoe UI", 12))
        p.setPen(QPen(qcol(self._color), 1))
        p.drawText(QRectF(10, 8, 24, 24), Qt.AlignmentFlag.AlignCenter, self._icon)

        # Label
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QPen(qcol(C.TEXT_M), 1))
        p.drawText(QRectF(36, 6, 50, 14), Qt.AlignmentFlag.AlignLeft, self._label)

        # Value
        p.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT), 1))
        p.drawText(QRectF(36, 20, W - 46, 20), Qt.AlignmentFlag.AlignLeft, self._text)

        # Progress bar
        bar_h = 3
        bar_y = H - bar_h - 6
        bar_w = W - 16
        bar_x = 8

        # Bar background
        p.setBrush(QBrush(qcol(C.BORDER, 100)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        # Bar fill with gradient
        if self._value > 85:
            bar_color = C.ERROR
        elif self._value > 65:
            bar_color = C.WARNING
        else:
            bar_color = self._color

        fill_w = int(bar_w * self._value / 100)
        if fill_w > 0:
            bar_grad = QLinearGradient(bar_x, 0, bar_x + fill_w, 0)
            bar_grad.setColorAt(0, qcol(bar_color))
            bar_grad.setColorAt(1, qcol(bar_color, 180))
            p.setBrush(bar_grad)
            p.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

class ChatWidget(QTextEdit):
    """Modern chat-style log widget"""
    
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Segoe UI", 10))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {C.TEXT};
                border: none;
                padding: 12px;
                selection-background-color: {C.PRIMARY_D};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                border: none;
                margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_L};
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C.GLOW};
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        if   tl.startswith("you:"):    self._tag = "you"
        elif tl.startswith("lessan:"): self._tag = "ai"
        elif tl.startswith("file:"):   self._tag = "file"
        elif "err" in tl:              self._tag = "err"
        else:                          self._tag = "sys"
        self._tmr.start(4)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            
            colors = {
                "you":  C.WHITE,
                "ai":   C.PRIMARY_L,
                "err":  C.ERROR,
                "file": C.SUCCESS,
                "sys":  C.TEXT_D,
            }
            col = colors.get(self._tag, C.TEXT)
            fmt.setForeground(QBrush(qcol(col)))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(15, self._next)

_FILE_ICONS = {
    "image":   ("🖼", C.ACCENT),
    "video":   ("🎬", C.WARNING),
    "audio":   ("🎵", C.PRIMARY),
    "pdf":     ("📄", C.ERROR),
    "word":    ("📝", C.ACCENT),
    "excel":   ("📊", C.SUCCESS),
    "code":    ("💻", C.PRIMARY_L),
    "archive": ("📦", C.WARNING),
    "pptx":    ("📊", C.WARNING),
    "text":    ("📃", C.TEXT_M),
    "data":    ("🔧", C.ACCENT),
    "unknown": ("📎", C.TEXT_DIM),
}

_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"

class FileDropZone(QWidget):
    """Modern file drop zone with glass effect"""
    
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(90)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._pulse = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(30)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._pulse = (self._pulse + 0.05) % (2 * math.pi)
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True
            self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False
        self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True
        self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False
        self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None
        self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for Lessan", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)

class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z = self._z
        W, H = self.width(), self.height()
        pad = 4
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        # Glass background
        if z._drag_over:
            bg_col = qcol(C.PRIMARY, 30)
        elif z._hovering:
            bg_col = qcol(C.CARD, 200)
        else:
            bg_col = qcol(C.PANEL_GLASS, 180)
        
        p.setBrush(bg_col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 12, 12)

        # Animated border
        if z._current_file:
            border_col = qcol(C.SUCCESS, 200)
        elif z._drag_over:
            border_col = qcol(C.PRIMARY, 220)
        elif z._hovering:
            border_col = qcol(C.BORDER_L, 180)
        else:
            pulse_alpha = int(80 + 40 * math.sin(self._z._pulse))
            border_col = qcol(C.BORDER_L, pulse_alpha)

        p.setPen(QPen(border_col, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 12, 12)

        if z._current_file:
            self._paint_file(p, W, H)
        elif z._drag_over:
            self._paint_drag_over(p, W, H)
        else:
            self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = C.PRIMARY if hover else C.TEXT_M
        
        # Upload icon
        p.setFont(QFont("Segoe UI", 18))
        p.setPen(QPen(qcol(col), 1))
        p.drawText(QRectF(0, cy - 28, W, 28), Qt.AlignmentFlag.AlignCenter, "⬆")
        
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QPen(qcol(C.TEXT_D if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 2, W, 18), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here or click to browse")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Segoe UI", 20))
        p.setPen(QPen(qcol(C.PRIMARY), 1))
        p.drawText(QRectF(0, cy - 18, W, 28), Qt.AlignmentFlag.AlignCenter, "Release to upload")

    def _paint_file(self, p, W, H):
        z = self._z
        path = Path(z._current_file)
        cat = _file_category(path)
        icon, col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        
        cx, cy = W / 2, H / 2
        
        # File icon
        p.setFont(QFont("Segoe UI", 24))
        p.setPen(QPen(qcol(col), 1))
        p.drawText(QRectF(0, cy - 32, W, 36), Qt.AlignmentFlag.AlignCenter, icon)
        
        # File name
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT), 1))
        name = path.name
        if len(name) > 30:
            name = name[:27] + "..."
        p.drawText(QRectF(10, cy + 6, W - 20, 18), Qt.AlignmentFlag.AlignCenter, name)
        
        # File size
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QPen(qcol(C.TEXT_M), 1))
        size = _fmt_size(path.stat().st_size)
        p.drawText(QRectF(0, cy + 22, W, 16), Qt.AlignmentFlag.AlignCenter, size)
        
        # Remove button (top right)
        p.setFont(QFont("Segoe UI", 10))
        p.setPen(QPen(qcol(C.ERROR_L, 150), 1))
        p.drawText(QRectF(W - 25, 8, 20, 20), Qt.AlignmentFlag.AlignCenter, "✕")

class SetupOverlay(QFrame):
    """Modern glassmorphism setup overlay"""
    
    setup_complete = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SetupOverlay")
        self.setStyleSheet(f"""
            #SetupOverlay {{
                background: {qcol(C.BG, 220).name(QColor.NameFormat.HexArgb)};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Glass card
        card = QFrame()
        card.setFixedSize(450, 520)
        card.setStyleSheet(f"""
            QFrame {{
                background: {C.PANEL};
                border: 1px solid {C.BORDER};
                border-radius: 24px;
            }}
            QLabel {{
                background: transparent;
                border: none;
                color: {C.TEXT};
            }}
            QLineEdit {{
                background: {C.CARD};
                border: 1px solid {C.BORDER};
                border-radius: 10px;
                padding: 12px;
                color: {C.WHITE};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {C.PRIMARY};
            }}
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {C.GRAD_START}, stop:1 {C.GRAD_END});
                color: {C.WHITE};
                border: none;
                border-radius: 12px;
                padding: 14px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {C.PRIMARY_L}, stop:1 {C.ACCENT_L});
            }}
        """)
        _apply_shadow(card, C.PRIMARY, 40)
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(20)
        
        # Title
        title = QLabel("Welcome to Lessan")
        title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)
        
        subtitle = QLabel("Configure your modern AI assistant")
        subtitle.setFont(QFont("Segoe UI", 10))
        subtitle.setStyleSheet(f"color: {C.TEXT_M};")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(subtitle)
        
        card_layout.addSpacing(20)
        
        # API Key
        card_layout.addWidget(QLabel("OpenRouter API Key"))
        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("sk-or-v1-...")
        self.api_input.setEchoMode(QLineEdit.EchoMode.Password)
        card_layout.addWidget(self.api_input)
        
        # OS Selection
        card_layout.addWidget(QLabel("Target Operating System"))
        os_layout = QHBoxLayout()
        self.os_btns = []
        for os_name in ["Windows", "Darwin", "Linux"]:
            btn = QPushButton(os_name)
            btn.setCheckable(True)
            btn.setFixedWidth(110)
            if os_name == _OS:
                btn.setChecked(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.CARD};
                    border: 1px solid {C.BORDER};
                    color: {C.TEXT_D};
                    padding: 8px;
                }}
                QPushButton:checked {{
                    background: {qcol(C.PRIMARY, 40).name(QColor.NameFormat.HexArgb)};
                    border: 1px solid {C.PRIMARY};
                    color: {C.PRIMARY_L};
                }}
            """)
            os_layout.addWidget(btn)
            self.os_btns.append(btn)
            btn.clicked.connect(lambda _, b=btn: self._select_os(b))
        card_layout.addLayout(os_layout)
        
        card_layout.addStretch()
        
        # Start Button
        start_btn = HoverGlowButton("Initialize Assistant", glow_color=C.PRIMARY, base_radius=10, hover_radius=30)
        start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        start_btn.clicked.connect(self._on_start)
        card_layout.addWidget(start_btn)
        
        layout.addWidget(card)
        
        # Load existing config
        if API_FILE.exists():
            try:
                with open(API_FILE, "r") as f:
                    data = json.load(f)
                    self.api_input.setText(data.get("openrouter_api_key", ""))
            except Exception:
                pass

    def _select_os(self, target):
        for btn in self.os_btns:
            btn.setChecked(btn == target)

    def _on_start(self):
        key = self.api_input.text().strip()
        if not key:
            return
        
        selected_os = _OS
        for btn in self.os_btns:
            if btn.isChecked():
                selected_os = btn.text()
        
        config = {
            "openrouter_api_key": key,
            "os": selected_os
        }
        
        CONFIG_DIR.mkdir(exist_ok=True)
        with open(API_FILE, "w") as f:
            json.dump(config, f, indent=2)
            
        self.setup_complete.emit(config)
        self.hide()

class MainWindow(QMainWindow):
    """Modern AI Dashboard Main Window"""
    
    user_input_submitted = pyqtSignal(str, str) # text, file_path
    mute_toggled = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lessan AI")
        self.resize(_DEFAULT_W, _DEFAULT_H)
        self.setMinimumSize(_MIN_W, _MIN_H)
        
        # Main background — a soft dome of light falling from upper-center,
        # rather than a flat fill. This is what makes panels below look "lit"
        # instead of pasted on top of black.
        self.setStyleSheet(f"""
            QMainWindow {{
                background: qradialgradient(
                    cx:0.5, cy:0.28, radius:1.1, fx:0.5, fy:0.28,
                    stop:0 {C.BG_GRAD}, stop:0.55 {C.BG}, stop:1 #030304
                );
            }}
        """)
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # --- LEFT PANEL: Metrics ---
        left_panel = QFrame()
        left_panel.setFixedWidth(_LEFT_W)
        left_panel.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {C.PANEL_GLASS}, stop:1 {C.PANEL});
                border: 1px solid {C.BORDER};
                border-top: 1px solid {qcol(C.RIM, 70).name(QColor.NameFormat.HexArgb)};
                border-radius: 20px;
            }}
        """)
        _apply_elevation(left_panel)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 25, 15, 25)
        left_layout.setSpacing(15)
        
        # Logo/Title
        logo_label = QLabel("LESSAN")
        logo_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        logo_label.setStyleSheet(f"color: {C.PRIMARY_L}; border: none; background: transparent;")
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(logo_label)
        
        left_layout.addSpacing(20)
        
        # Metrics
        self.m_cpu = MetricCard("CPU", "💻", C.PRIMARY)
        self.m_mem = MetricCard("RAM", "🧠", C.ACCENT)
        self.m_net = MetricCard("NET", "🌐", C.SUCCESS)
        self.m_gpu = MetricCard("GPU", "🎮", C.WARNING)
        self.m_tmp = MetricCard("TMP", "🔥", C.ERROR)
        
        left_layout.addWidget(self.m_cpu)
        left_layout.addWidget(self.m_mem)
        left_layout.addWidget(self.m_net)
        left_layout.addWidget(self.m_gpu)
        left_layout.addWidget(self.m_tmp)
        
        left_layout.addStretch()
        
        # Bottom status
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {C.SUCCESS}; border: none; background: transparent;")
        self.status_text = QLabel("System Ready")
        self.status_text.setStyleSheet(f"color: {C.TEXT_M}; border: none; background: transparent; font-size: 10px;")
        
        status_box = QHBoxLayout()
        status_box.addWidget(self.status_dot)
        status_box.addWidget(self.status_text)
        status_box.addStretch()
        left_layout.addLayout(status_box)
        
        main_layout.addWidget(left_panel)
        
        # --- CENTER PANEL: HUD ---
        center_layout = QVBoxLayout()
        center_layout.setSpacing(20)
        
        self.hud = HudCanvas(str(BASE_DIR / "face.png"))
        center_layout.addWidget(self.hud)
        
        main_layout.addLayout(center_layout, 1)
        
        # --- RIGHT PANEL: Chat & Input ---
        right_panel = QFrame()
        right_panel.setFixedWidth(_RIGHT_W)
        right_panel.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {C.PANEL_GLASS}, stop:1 {C.PANEL});
                border: 1px solid {C.BORDER};
                border-top: 1px solid {qcol(C.RIM, 70).name(QColor.NameFormat.HexArgb)};
                border-radius: 20px;
            }}
        """)
        _apply_elevation(right_panel)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        
        # Chat Area
        chat_container = QFrame()
        chat_container.setStyleSheet("border: none; background: transparent;")
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(10, 10, 10, 10)
        
        self.chat = ChatWidget()
        chat_layout.addWidget(self.chat)
        right_layout.addWidget(chat_container, 1)
        
        # Input Area
        input_container = QFrame()
        input_container.setFixedHeight(220)
        input_container.setStyleSheet(f"""
            QFrame {{
                background: {C.PANEL_GLASS};
                border-top: 1px solid {C.BORDER};
                border-bottom-left-radius: 20px;
                border-bottom-right-radius: 20px;
            }}
        """)
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(15, 15, 15, 15)
        input_layout.setSpacing(12)
        
        # File Drop
        self.drop_zone = FileDropZone()
        input_layout.addWidget(self.drop_zone)
        
        # Text Input Row
        text_row = QHBoxLayout()
        text_row.setSpacing(10)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask Lessan anything...")
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: {C.CARD};
                border: 1px solid {C.BORDER};
                border-radius: 20px;
                padding: 10px 15px;
                color: {C.WHITE};
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {C.PRIMARY};
            }}
        """)
        self.input_field.returnPressed.connect(self._submit)
        text_row.addWidget(self.input_field)
        
        self.send_btn = HoverGlowButton("↑", glow_color=C.PRIMARY, base_radius=14, hover_radius=32)
        self.send_btn.setFixedSize(40, 40)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C.GRAD_START}, stop:1 {C.GRAD_END});
                color: {C.WHITE};
                border: none;
                border-radius: 20px;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C.PRIMARY_L}, stop:1 {C.ACCENT_L});
            }}
        """)
        self.send_btn.clicked.connect(self._submit)
        text_row.addWidget(self.send_btn)
        
        input_layout.addLayout(text_row)
        
        # Control Buttons
        ctrl_row = QHBoxLayout()
        
        self.mic_btn = HoverGlowButton("🎤", glow_color=C.SUCCESS, base_radius=0, hover_radius=26)
        self.mic_btn.setFixedSize(36, 36)
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setCheckable(True)
        self._mic_style_off = f"""
            QPushButton {{
                background: {C.CARD};
                border: 1px solid {C.BORDER};
                border-radius: 18px;
                color: {C.TEXT_D};
            }}
            QPushButton:hover {{
                color: {C.PRIMARY_L};
                border: 1px solid {C.PRIMARY};
            }}
        """
        self._mic_style_on = f"""
            QPushButton {{
                background: {qcol(C.ERROR, 40).name(QColor.NameFormat.HexArgb)};
                border: 1px solid {C.ERROR};
                border-radius: 18px;
                color: {C.ERROR_L};
            }}
        """
        self.mic_btn.setStyleSheet(self._mic_style_off)
        self.mic_btn.toggled.connect(self._on_mic_toggled)
        ctrl_row.addWidget(self.mic_btn)
        
        ctrl_row.addStretch()
        
        self.clear_btn = HoverGlowButton("Clear Chat", glow_color=C.ERROR, base_radius=0, hover_radius=18)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C.TEXT_DIM};
                border: none;
                font-size: 11px;
            }}
            QPushButton:hover {{
                color: {C.ERROR_L};
            }}
        """)
        self.clear_btn.clicked.connect(self.chat.clear)
        ctrl_row.addWidget(self.clear_btn)
        
        input_layout.addLayout(ctrl_row)
        
        right_layout.addWidget(input_container)
        main_layout.addWidget(right_panel)
        
        # Setup Overlay
        self.setup_overlay = SetupOverlay(self)
        self.setup_overlay.hide()
        
        # Metrics Timer
        self.metrics_tmr = QTimer(self)
        self.metrics_tmr.timeout.connect(self._update_metrics)
        self.metrics_tmr.start(2000)
        
        # Shortcuts
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self.chat.clear)
        QShortcut(QKeySequence("Return"), self).activated.connect(self._submit)

    def _update_metrics(self):
        s = _metrics.snapshot()
        self.m_cpu.set_value(s["cpu"], f"{s['cpu']:.1f}%")
        self.m_mem.set_value(s["mem"], f"{s['mem']:.1f}%")
        self.m_net.set_value(min(100, s["net"]*10), f"{s['net']:.2f} MB/s")
        
        if s["gpu"] >= 0:
            self.m_gpu.set_value(s["gpu"], f"{s['gpu']:.1f}%")
            self.m_gpu.show()
        else:
            self.m_gpu.hide()
            
        if s["tmp"] >= 0:
            self.m_tmp.set_value(min(100, s["tmp"]), f"{s['tmp']:.1f}°C")
            self.m_tmp.show()
        else:
            self.m_tmp.hide()

    def _on_mic_toggled(self, checked: bool):
        self.mic_btn.setText("🔇" if checked else "🎤")
        self.mic_btn.setStyleSheet(self._mic_style_on if checked else self._mic_style_off)
        if hasattr(self, 'hud'):
            self.hud.muted = checked
        self.mute_toggled.emit(checked)

    def _submit(self):
        text = self.input_field.text().strip()
        file = self.drop_zone.current_file()
        if text or file:
            self.user_input_submitted.emit(text, file or "")
            if text:
                self.chat.append_log(f"You: {text}")
            if file:
                self.chat.append_log(f"File: {Path(file).name}")
            self.input_field.clear()
            self.drop_zone.clear_file()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.setup_overlay.resize(self.size())

    def showEvent(self, e):
        super().showEvent(e)
        # One-shot fade-in the first time the window appears — a still frame
        # is a poor first impression for something meant to feel "alive."
        if not getattr(self, "_entrance_played", False):
            self._entrance_played = True
            self.setWindowOpacity(0.0)
            self._entrance_anim = QPropertyAnimation(self, b"windowOpacity", self)
            self._entrance_anim.setDuration(520)
            self._entrance_anim.setStartValue(0.0)
            self._entrance_anim.setEndValue(1.0)
            self._entrance_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._entrance_anim.start()

    def show_setup_overlay(self):
        """Fade + slide the setup overlay in, rather than snapping it visible."""
        ov = self.setup_overlay
        ov.resize(self.size())
        effect = QGraphicsOpacityEffect(ov)
        ov.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        ov.show()
        anim = QPropertyAnimation(effect, b"opacity", ov)
        anim.setDuration(380)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        ov._entrance_anim = anim  # keep a reference alive

import random

class LessanUI:
    """Wrapper class for MainWindow that provides the interface expected by main.py"""
    
    def __init__(self, face_image: str = "face.png"):
        self._app = QApplication(sys.argv)
        self._app.setApplicationName("Lessan AI")
        
        self._window = MainWindow()
        self._state = "LISTENING"
        self.muted = False
        self.current_file = None
        self.on_text_command = None  # Callback for text input
        
        # Connect to MainWindow's input signal
        self._window.user_input_submitted.connect(self._on_user_input)
        self._window.mute_toggled.connect(self._on_mute_toggled)
        
        # Show setup overlay if no API key
        if not API_FILE.exists():
            self._window.show_setup_overlay()
        
        self._window.show()
    
    def _on_user_input(self, text: str, file_path: str):
        """Handle user input from MainWindow"""
        self.current_file = file_path if file_path else None
        if self.on_text_command and text:
            self.on_text_command(text)

    def _on_mute_toggled(self, muted: bool):
        """Keep self.muted (read directly by main.py) in sync with the mic button."""
        self.muted = muted
    
    @property
    def root(self):
        """Provide access to the underlying window for main.py compatibility"""
        return self._window
    
    def set_state(self, state: str):
        """Update the assistant state display and drive the orb's animation."""
        self._state = state
        if hasattr(self._window, 'hud'):
            hud = self._window.hud
            hud.state = state
            hud.speaking = (state == "SPEAKING")
            hud.muted = self.muted
        if hasattr(self._window, 'status_text'):
            self._window.status_text.setText(state.title())
    
    def write_log(self, message: str):
        """Write a message to the chat log"""
        if hasattr(self._window, 'chat'):
            self._window.chat.append_log(message)
    
    def wait_for_api_key(self):
        """Block until API key is configured (non-blocking in Qt)"""
        # In Qt, we just ensure the window is shown
        # The actual API key input happens via the setup overlay
        if not API_FILE.exists():
            # Process events until the setup is complete
            while not API_FILE.exists():
                self._app.processEvents()
                time.sleep(0.1)
    
    def run(self):
        """Start the UI event loop"""
        sys.exit(self._app.exec())

def run_ui():
    app = QApplication(sys.argv)
    app.setApplicationName("Lessan AI")
    
    # Set modern font if available
    QFontDatabase.addApplicationFont(":/fonts/inter.ttf")
    
    window = MainWindow()
    
    if not API_FILE.exists():
        window.show_setup_overlay()
    
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_ui()
