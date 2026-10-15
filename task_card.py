from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle, Line
from kivy.utils import escape_markup
from config import theme
from utils import fx
from utils.appearance import state as appearance
import database as db


class TaskCard(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical",
                         size_hint_y=None, height=dp(102),
                         padding=[dp(theme.CARD_PADDING), dp(12)],
                         spacing=dp(6), **kwargs)
        with self.canvas.before:
            Color(*theme.PANEL)
            self._bg = Rectangle(pos=self.pos, size=self.size)
            Color(*theme.BORDER)
            self._border = Line(rectangle=(*self.pos, *self.size), width=dp(1))
            Color(*theme.METAL_LIGHT)
            self._top_edge = Rectangle(pos=self.pos, size=(self.width, dp(1)))
        self.bind(pos=self._redraw, size=self._redraw)
        fx.surface(self, 'panel', theme.VFD_CYAN)

        header = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(6))
        self._title = Label(text="[color=ff5500][size=10sp]MISSION STATUS[/size][/color]\n[b]今日任务[/b]", markup=True,
                            color=theme.TEXT_PRIMARY, font_size=dp(theme.FONT_H3),
                            halign="left", valign="middle", size_hint_x=1)
        self._title.bind(size=self._title.setter("text_size"))
        header.add_widget(self._title)
        self._count = Label(text="0/0", color=theme.GOLD, font_size=dp(theme.FONT_H3),
                            bold=True, halign="right", valign="middle",
                            size_hint_x=None, width=dp(56))
        self._count.bind(size=self._count.setter("text_size"))
        header.add_widget(self._count)
        self.add_widget(header)

        self._track = BoxLayout(size_hint_y=None, height=dp(8), padding=0)
        self._progress_ratio = 0.0
        with self._track.canvas.before:
            Color(*theme.DISPLAY_GLASS)
            self._track_bg = Rectangle(pos=self._track.pos, size=self._track.size)
        self._track.bind(pos=self._redraw_track, size=self._redraw_track)
        self.add_widget(self._track)

        self._sub = Label(text="点击核爆按钮生成计划", color=theme.TEXT_MUTED,
                           font_size=dp(theme.FONT_CAPTION), halign="left", valign="middle",
                           markup=True, size_hint_y=None, height=dp(28))
        self._sub.bind(size=lambda widget, size:
                       setattr(widget, "text_size", (size[0], None)))
        self.add_widget(self._sub)
        self.refresh()
        appearance.bind(enhanced=self._redraw_track)

    def _redraw(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rectangle = (*self.pos, *self.size)
        self._top_edge.pos = (self.x + dp(1), self.top - dp(2))
        self._top_edge.size = (max(0, self.width - dp(2)), dp(1))

    def _redraw_track(self, *_):
        self._track_bg.pos = self._track.pos
        self._track_bg.size = self._track.size
        self._track.canvas.after.clear()
        segments = 24
        gap = dp(2)
        segment_w = max(dp(1), (self._track.width - gap * (segments - 1)) / segments)
        lit = round(self._progress_ratio * segments)
        with self._track.canvas.after:
            for index in range(segments):
                fx.draw_segment_glow(self._track.canvas.after,
                    self._track.x + index * (segment_w + gap), self._track.y + dp(1),
                    segment_w, max(0, self._track.height - dp(2)),
                    theme.VFD_CYAN if index < lit else theme.VFD_CYAN_DIM,
                    glow=index < lit)

    def refresh(self):
        plan = db.get_today_plan()
        if not plan:
            self._progress_ratio = 0.0
            self._title.text = "[color=ff5500][size=10sp]MISSION STATUS[/size][/color]\n[b]今日任务[/b]"
            self._count.text = "—"
            self._count.color = theme.TEXT_MUTED
            self._sub.text = "点击核爆按钮生成计划"
            self._redraw_track()
            return
        total = len(plan)
        done = sum(1 for p in plan if p["completed"])
        self._progress_ratio = done / total if total else 0
        self._count.text = f"{done}/{total}"
        self._count.color = theme.GOLD if done < total else theme.ACCENT_CYAN
        self._title.text = "[color=ff5500][size=10sp]MISSION STATUS[/size][/color]\n[b]今日任务[/b]"
        gold_hex = "00ffcc"
        muted_hex = "666f70"
        parts = []
        visible = plan[:4]
        for p in visible:
            name = escape_markup(str(p["exercise_name"]))
            if p["completed"]:
                parts.append(f"[color={gold_hex}]{name}[/color]")
            else:
                parts.append(f"[color={muted_hex}]{name}[/color]")
        remaining = len(plan) - len(visible)
        suffix = f"  [color=33ccff]+{remaining} 项[/color]" if remaining else ""
        self._sub.text = "  ".join(parts) + suffix
        self._redraw_track()
