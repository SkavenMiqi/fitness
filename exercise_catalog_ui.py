"""Mechanical-panel popup for viewing SQLite-backed exercise guidance."""

from kivy.metrics import dp
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, Rectangle, Line

import database as db
from config import theme

_BODY_LABELS = {
    "chest": "胸", "back": "背", "upper legs": "腿", "lower legs": "小腿",
    "shoulders": "肩", "upper arms": "手臂", "waist": "核心",
}
_EQUIPMENT_LABELS = {
    "barbell": "杠铃", "dumbbell": "哑铃", "cable": "绳索",
    "body weight": "自重", "leverage machine": "器械",
    "smith machine": "史密斯", "sled machine": "腿举机", "assisted": "辅助器械",
}


class ExerciseDetailPopup(ModalView):
    def __init__(self, exercise_id=None, exercise_name=None, **kwargs):
        super().__init__(size_hint=(0.94, 0.92), **kwargs)
        self.background = ""
        self.background_color = theme.OVERLAY
        self._exercise = db.find_catalog_exercise(exercise_id, exercise_name)
        self._animation_event = None
        self._frame_index = 0
        self._build()

    def _build(self):
        ex = self._exercise
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        with root.canvas.before:
            Color(*theme.CHASSIS)
            self._root_bg = Rectangle(pos=root.pos, size=root.size)
            Color(*theme.METAL_LIGHT)
            self._root_border = Line(rectangle=(root.x, root.y, root.width, root.height), width=dp(1))
        root.bind(
            pos=lambda _, p: (setattr(self._root_bg, "pos", p),
                              setattr(self._root_border, "rectangle", (p[0], p[1], root.width, root.height))),
            size=lambda _, s: (setattr(self._root_bg, "size", s),
                               setattr(self._root_border, "rectangle", (root.x, root.y, s[0], s[1]))),
        )
        title = BoxLayout(size_hint_y=None, height=dp(42))
        title.add_widget(Label(
            text=f"[b]MAINTENANCE PROCEDURE / EX-{ex.get('id', '--')}[/b]\n{ex['name_zh']}" if ex else "DATA OFFLINE / 动作资料不可用",
            markup=True, color=theme.VFD_ORANGE, font_size=dp(theme.FONT_LABEL), halign="left", valign="middle"))
        close = Button(text="×", size_hint_x=None, width=dp(38), background_normal="",
                       background_color=(0, 0, 0, 0), color=theme.TEXT_MUTED, font_size=dp(20))
        close.bind(on_release=lambda _: self.dismiss())
        title.add_widget(close)
        root.add_widget(title)
        if not ex:
            self.add_widget(root)
            return
        frame_paths = [
            db.resolve_media_path(path) for path in ex.get("animation_frames", [])
        ]
        self._frames = [path for path in frame_paths if path]
        media = self._frames[0] if self._frames else db.resolve_media_path(ex["thumbnail_path"])
        if media:
            media_panel = BoxLayout(size_hint_y=None, height=dp(304), padding=dp(2))
            with media_panel.canvas.before:
                Color(*theme.DISPLAY_GLASS)
                media_bg = Rectangle(pos=media_panel.pos, size=media_panel.size)
                Color(*theme.BORDER)
                media_border = Line(rectangle=(media_panel.x, media_panel.y, media_panel.width, media_panel.height))
            media_panel.bind(
                pos=lambda _, p: (setattr(media_bg, "pos", p),
                                  setattr(media_border, "rectangle", (p[0], p[1], media_panel.width, media_panel.height))),
                size=lambda _, s: (setattr(media_bg, "size", s),
                                   setattr(media_border, "rectangle", (media_panel.x, media_panel.y, s[0], s[1]))),
            )
            self._media = Image(source=media, allow_stretch=True, keep_ratio=True)
            media_panel.add_widget(self._media)
            root.add_widget(media_panel)
            if len(self._frames) > 1:
                interval = max(0.04, float(ex.get("animation_interval") or 0.12))
                self._animation_event = Clock.schedule_interval(self._next_frame, interval)
        meta = Label(
            text=(f"ZONE  {_BODY_LABELS.get(ex['body_part'], ex['body_part'])}    "
                  f"EQUIPMENT  {_EQUIPMENT_LABELS.get(ex['equipment'], ex['equipment'])}\n"
                  f"TARGET  {ex['target']}    ASSIST  {', '.join(ex['secondary_muscles'])}"),
            color=theme.VFD_CYAN, font_size=dp(theme.FONT_CAPTION),
            size_hint_y=None, height=dp(42), halign="left", valign="middle")
        meta.bind(size=meta.setter("text_size"))
        root.add_widget(meta)
        scroll = ScrollView(do_scroll_x=False)
        steps = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        steps.bind(minimum_height=steps.setter("height"))
        for index, step in enumerate(ex["steps_zh"], 1):
            row = Label(text=f"[color=ff9d24][b]STEP {index:02d}[/b][/color]  {step}", markup=True,
                        color=theme.TEXT_PRIMARY, font_size=dp(theme.FONT_BODY),
                        size_hint_y=None, halign="left", valign="top")
            row.bind(width=lambda widget, width: setattr(widget, "text_size", (width, None)))
            row.bind(texture_size=lambda widget, size: setattr(widget, "height", max(dp(32), size[1] + dp(10))))
            steps.add_widget(row)
        scroll.add_widget(steps)
        root.add_widget(scroll)
        attribution = Label(text=ex["attribution"], color=theme.TEXT_MUTED,
                            font_size=dp(10), size_hint_y=None, height=dp(16))
        root.add_widget(attribution)
        self.add_widget(root)

    def _next_frame(self, _dt):
        if not self._frames or not hasattr(self, "_media"):
            return False
        self._frame_index = (self._frame_index + 1) % len(self._frames)
        self._media.source = self._frames[self._frame_index]
        # Changing source already loads the frame; reload() evicts its cached
        # texture and forces disk decoding again on every animation cycle.
        return True

    def on_dismiss(self):
        if self._animation_event is not None:
            self._animation_event.cancel()
            self._animation_event = None
