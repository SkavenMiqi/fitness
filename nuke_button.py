from kivy.uix.button import Button
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle, Triangle
from kivy.properties import BooleanProperty, NumericProperty
from kivy.metrics import dp
import math
from datetime import date
from utils import fx
from utils.appearance import state as appearance
import theme
import database as db
import sounds

_BG_NORMAL = theme.PANEL
_BG_NUKED = (0.16, 0.035, 0.018, 1)
_ICON_NORMAL = theme.VFD_ORANGE
_ICON_NUKED = theme.LED_RED
_METAL = theme.METAL
_METAL_DARK = theme.METAL_DARK

class NukeButton(Button):
    nuked_today = BooleanProperty(False)
    _glow = NumericProperty(0.15)

    def __init__(self, **kwargs):
        super().__init__(background_normal="", background_color=(0,0,0,0), **kwargs)
        self._bg = _BG_NORMAL
        self._icon = _ICON_NORMAL
        self.bind(pos=self._draw, size=self._draw, _glow=self._draw)
        self.bind(nuked_today=self._on_nuked_changed)
        appearance.bind(enhanced=self._draw)
        self.nuked_today = db.is_date_nuked(date.today().isoformat())
        Clock.schedule_once(lambda dt: self._start_glow(), 0.5)

    def _start_glow(self):
        anim = (Animation(_glow=0.32, duration=2.0, transition="linear") +
                Animation(_glow=0.05, duration=2.0, transition="linear"))
        anim.repeat = True
        anim.start(self)

    def _on_nuked_changed(self, *_):
        if self.nuked_today:
            self._bg = _BG_NUKED
            self._icon = _ICON_NUKED
        else:
            self._bg = _BG_NORMAL
            self._icon = _ICON_NORMAL
        self._draw()

    def on_press(self):
        sounds.play_explosion()
        if self.nuked_today:
            self._bg = sounds.lighten(_BG_NUKED)
            self._icon = sounds.lighten(_ICON_NUKED)
        else:
            self._bg = sounds.lighten(_BG_NORMAL)
            self._icon = sounds.lighten(_ICON_NORMAL)
        self._draw()

    def on_release(self):
        self._on_nuked_changed()

    def _draw(self, *args):
        self.canvas.before.clear()
        self.canvas.after.clear()
        x, y = self.x, self.y
        w, h = self.width, self.height
        cx, cy = self.center_x, self.center_y
        bg, icon = self._bg, self._icon
        unit = min(w, h)
        outer_r = unit * 0.38
        face_r = outer_r * 0.78
        hub_r = face_r * 0.26
        with self.canvas.before:
            Color(*bg)
            Rectangle(pos=(x, y), size=(w, h))
            # Soft status glow stays inside the rectangular control panel.
            # Concentric low-opacity rings, not a flat translucent glow disk.
            if not appearance.enhanced:
                Color(*icon[:3], self._glow * 0.45)
                glow_r = outer_r * 1.18
                Ellipse(pos=(cx - glow_r, cy - glow_r), size=(glow_r * 2, glow_r * 2))
            for radius_scale, alpha in (((1.15, 0.08), (1.10, 0.12), (1.05, 0.20))
                                        if appearance.enhanced else ()):
                Color(*icon[:3], self._glow * alpha)
                Line(circle=(cx, cy, outer_r * radius_scale), width=dp(3))

            # Recessed metal bezel.
            Color(*_METAL_DARK)
            Ellipse(pos=(cx - outer_r, cy - outer_r), size=(outer_r * 2, outer_r * 2))
            Color(*_METAL)
            Line(circle=(cx, cy, outer_r), width=dp(2.2))
            Color(*theme.BORDER_DIM)
            Line(circle=(cx, cy, outer_r * 0.90), width=dp(1))

            # Dark button face and active inner ring.
            Color(1, 1, 1, 1)
            Ellipse(pos=(cx - face_r, cy - face_r), size=(face_r * 2, face_r * 2),
                    texture=fx.gradient_texture((0.10, 0.045, 0.025, 1), theme.DISPLAY_GLASS)
                    if appearance.enhanced else fx.gradient_texture(theme.DISPLAY_GLASS, theme.DISPLAY_GLASS))
            Color(icon[0], icon[1], icon[2], 0.95)
            Line(circle=(cx, cy, face_r), width=dp(2))

        with self.canvas.after:
            # Twenty-four engraved calibration ticks.
            for index in range(24):
                angle = math.radians(index * 15 - 90)
                inner = outer_r * (0.80 if index % 3 == 0 else 0.84)
                end = outer_r * 0.91
                alpha = 0.92 if index % 3 == 0 else 0.38
                Color(icon[0], icon[1], icon[2], alpha)
                Line(points=(
                    cx + math.cos(angle) * inner, cy + math.sin(angle) * inner,
                    cx + math.cos(angle) * end, cy + math.sin(angle) * end,
                ), width=dp(1.25 if index % 3 == 0 else 0.7))

            # Three radiation blades point around the central hub.
            for index in range(3):
                angle = math.radians(index * 120 - 90)
                spread = math.radians(28)
                inner = hub_r * 1.32
                outer = face_r * 0.72
                Color(*icon)
                Triangle(points=(
                    cx + math.cos(angle - spread) * inner,
                    cy + math.sin(angle - spread) * inner,
                    cx + math.cos(angle) * outer,
                    cy + math.sin(angle) * outer,
                    cx + math.cos(angle + spread) * inner,
                    cy + math.sin(angle + spread) * inner,
                ))

            Color(*theme.DISPLAY_GLASS)
            Ellipse(pos=(cx - hub_r, cy - hub_r), size=(hub_r * 2, hub_r * 2))
            Color(*icon)
            Line(circle=(cx, cy, hub_r), width=dp(1.6))
            Ellipse(pos=(cx - hub_r * 0.22, cy - hub_r * 0.22),
                    size=(hub_r * 0.44, hub_r * 0.44))

            # Four panel fasteners reinforce the physical-control look.
            Color(*theme.BORDER)
            fastener = dp(2.2)
            inset = dp(8)
            for fastener_x, fy in ((x + inset, y + inset), (x + w - inset, y + inset),
                           (x + inset, y + h - inset), (x + w - inset, y + h - inset)):
                Ellipse(pos=(fastener_x - fastener, fy - fastener),
                        size=(fastener * 2, fastener * 2))
