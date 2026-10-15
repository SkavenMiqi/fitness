"""Exercise reference archive: browsable grid of catalog exercises with guides."""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.image import AsyncImage
from collections import OrderedDict
from time import perf_counter
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, Line
from kivy.metrics import dp
from kivy.clock import Clock

import database as db
from config import theme
import sounds
from utils import fx
from utils.appearance import state as appearance
from exercise_catalog_ui import ExerciseDetailPopup

_BODY_FILTERS = [
    ("", "全部"),
    ("common", "常用"),
    ("chest", "胸"),
    ("back", "背"),
    ("shoulders", "肩"),
    ("upper arms", "手臂"),
    ("upper legs", "腿"),
    ("lower legs", "小腿"),
    ("waist", "核心"),
]

_CATEGORY_FILTERS = [
    ("", "全部"),
    ("common", "常用"),
    ("cardio", "有氧"),
    ("warmup", "热身"),
    ("stretch", "拉伸"),
]

_EQUIPMENT_LABELS = {
    "barbell": "杠铃", "dumbbell": "哑铃", "cable": "绳索",
    "body weight": "自重", "leverage machine": "器械",
    "smith machine": "史密斯", "sled machine": "腿举机", "assisted": "辅助器械",
}


class ArchiveCard(Widget):
    """Tappable exercise tile showing thumbnail + name, opens the detail popup."""

    def __init__(self, exercise, **kwargs):
        super().__init__(size_hint=(1, None), height=dp(132), **kwargs)
        self._exercise = exercise
        self._pressed = False
        with self.canvas.before:
            self._bg_color = Color(*theme.METAL_DARK)
            self._bg = Rectangle(pos=self.pos, size=self.size)
            self._edge_color = Color(*theme.BORDER)
            self._edge = Line(rectangle=(*self.pos, *self.size), width=dp(0.8))
        self.bind(pos=self._draw, size=self._draw)
        fx.surface(self, 'panel', theme.VFD_CYAN, cut=6)
        # Keep the interactive orange focus outline above the new surface.
        with self.canvas.after:
            self._focus_color = Color(1, 0.333, 0, 0)
            self._focus_edge = Line(rectangle=(*self.pos, *self.size), width=dp(1))

        box = BoxLayout(orientation="vertical", padding=[dp(7), dp(6)], spacing=dp(3))
        self._box = box
        self.add_widget(box)

        thumb_path = db.resolve_media_path(exercise.get("thumbnail_path"))
        if thumb_path:
            img = AsyncImage(source=thumb_path, allow_stretch=True, keep_ratio=True)
            self._img = img
            box.add_widget(img)
        else:
            self._img = None
            box.add_widget(Widget())

        name = Label(text=exercise["name_zh"], color=theme.TEXT_PRIMARY,
                     font_size=dp(11), bold=True, halign="left", valign="middle",
                     size_hint_y=None, height=dp(18))
        name.bind(size=name.setter("text_size"))
        box.add_widget(name)

        eq = _EQUIPMENT_LABELS.get(exercise.get("equipment"), exercise.get("equipment") or "—")
        tag = Label(text=eq, color=theme.VFD_CYAN, font_size=dp(9),
                    halign="left", valign="middle", size_hint_y=None, height=dp(14))
        tag.bind(size=tag.setter("text_size"))
        box.add_widget(tag)

        def apply_theme(*_):
            box.padding = [dp(7), dp(6)] if appearance.enhanced else [dp(4), dp(4)]
            box.spacing = dp(3 if appearance.enhanced else 2)
        appearance.bind(enhanced=apply_theme)
        apply_theme()

    def _draw(self, *_):
        self._focus_edge.rectangle = (*self.pos, *self.size)
        self._focus_color.a = 1 if self._pressed else 0
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._edge.rectangle = (*self.pos, *self.size)
        self._box.pos = self.pos
        self._box.size = self.size
        if self._pressed:
            self._bg_color.rgba = theme.PANEL_RAISED
            self._edge_color.rgba = theme.VFD_ORANGE
        else:
            self._bg_color.rgba = theme.METAL_DARK
            self._edge_color.rgba = theme.BORDER

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            self._pressed = True
            self._draw()
            return True
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self._pressed = False
            self._draw()
            if self.collide_point(*touch.pos):
                sounds.play_click()
                ExerciseDetailPopup(exercise_id=self._exercise["id"]).open()
            return True
        return super().on_touch_up(touch)


class ArchivePanel(BoxLayout):
    """Full-page exercise reference library with body-part/category filters."""

    def __init__(self, main_layout, item_types=None, filters=None, title=None, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(8),
                         padding=[dp(theme.PAGE_MARGIN)] * 4, **kwargs)
        self.main_layout = main_layout
        self._item_types = item_types or ["strength"]
        self._filters = filters or _BODY_FILTERS
        self._active_filter = ""
        self._search_ev = None
        self._render_signature = None
        self._build_event = None
        self._card_cache = OrderedDict()
        self._pending_rows = []
        fx.chassis(self)

        header = BoxLayout(size_hint_y=None, height=dp(26))
        title_text = title or "EXERCISE ARCHIVE / 动作资料馆"
        title = Label(text=f"[color=ff9d24][b]{title_text}[/b][/color]",
                      markup=True, color=theme.TEXT_PRIMARY,
                      font_size=dp(theme.FONT_H3), bold=True,
                      halign="left", valign="middle", size_hint_x=1)
        title.bind(size=title.setter("text_size"))
        header.add_widget(title)
        self._count = Label(text="", color=theme.VFD_CYAN, font_size=dp(theme.FONT_CAPTION),
                            bold=True, halign="right", valign="middle",
                            size_hint_x=None, width=dp(90))
        self._count.bind(size=self._count.setter("text_size"))
        header.add_widget(self._count)
        self.add_widget(header)

        search_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
        inp = TextInput(text="", hint_text="搜索动作 / 器材 / 目标肌群", multiline=False,
                        font_size=dp(theme.FONT_BODY),
                        background_normal="", background_active="",
                        background_color=theme.DISPLAY_GLASS,
                        foreground_color=theme.TEXT_PRIMARY,
                        hint_text_color=theme.TEXT_MUTED,
                        cursor_color=theme.VFD_CYAN, padding=(dp(10), dp(8)))
        inp.bind(text=self._on_search_text)
        self._search = inp
        search_row.add_widget(inp)
        self.add_widget(search_row)

        filter_bar = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(4))
        self._filter_btns = {}
        for value, label in self._filters:
            btn = self._make_filter_btn(label, value)
            self._filter_btns[value] = btn
            filter_bar.add_widget(btn)
        self.add_widget(filter_bar)

        scroll = ScrollView(do_scroll_x=False)
        self._scroll = scroll
        grid = GridLayout(cols=3, spacing=dp(6), size_hint=(1, None), padding=[dp(2), dp(2)])
        self._grid = grid
        grid.bind(minimum_height=grid.setter("height"))
        scroll.add_widget(grid)
        self.add_widget(scroll)

        self._refresh()

    def _make_filter_btn(self, label, value):
        from kivy.uix.button import Button
        btn = Button(text=label, size_hint_x=1, height=dp(30),
                     background_normal="", background_color=theme.METAL_DARK,
                     color=theme.TEXT_SECONDARY, font_size=dp(theme.FONT_CAPTION), bold=True)
        with btn.canvas.before:
            Color(*theme.BORDER_DIM)
            btn._edge = Line(rectangle=(0, 0, 0, 0), width=dp(0.8))
        btn.bind(pos=lambda w, _: setattr(w._edge, "rectangle", (w.x, w.y, w.width, w.height)),
                 size=lambda w, _: setattr(w._edge, "rectangle", (w.x, w.y, w.width, w.height)))
        btn.bind(on_release=lambda _b, v=value: self._set_filter(v))
        return btn

    def _set_filter(self, value):
        if self._active_filter == value:
            return
        self._active_filter = value
        for v, btn in self._filter_btns.items():
            active = v == value
            btn.background_color = theme.VFD_ORANGE if active else theme.METAL_DARK
            btn.color = theme.CHASSIS if active else theme.TEXT_SECONDARY
        sounds.play_click()
        self._refresh()

    def _on_search_text(self, _instance, _text):
        if self._search_ev:
            Clock.unschedule(self._search_ev)
        self._search_ev = Clock.schedule_once(lambda _dt: self._refresh(), 0.25)

    def _refresh(self):
        if self._search_ev is not None:
            self._search_ev.cancel()
            self._search_ev = None
        query = self._search.text.strip()
        common_only = self._active_filter == "common"
        is_category = self._filters is _CATEGORY_FILTERS
        if common_only:
            item_type = None
            item_types = None
        elif is_category and self._active_filter:
            item_type = self._active_filter
            item_types = None
        else:
            item_type = None
            item_types = self._item_types
        body_part = "" if (common_only or (is_category and self._active_filter)) \
            else (self._active_filter if self._active_filter else "")
        if is_category and not self._active_filter:
            body_part = ""
        rows = db.search_catalog(query=query, body_part=body_part,
                                 limit=500, common_only=common_only,
                                  item_type=item_type, item_types=item_types)
        # Include ordering and visible metadata so completed exercises can still
        # reorder common entries while unchanged visits preserve every widget.
        signature = (query, self._active_filter, tuple(
            (ex['id'], ex['name_zh'], ex.get('thumbnail_path'), ex.get('equipment'))
            for ex in rows))
        if signature == self._render_signature:
            return
        self._render_signature = signature
        if self._build_event is not None:
            self._build_event.cancel()
            self._build_event = None
        self._count.text = f"{len(rows)} ITEMS"
        self._grid.clear_widgets()
        self._scroll.scroll_y = 1
        self._pending_rows = list(rows)
        self._build_index = 0
        if rows:
            self._build_batch(0)
            if self._build_index < len(rows):
                self._build_event = Clock.schedule_interval(self._build_batch, 0)
        if not rows:
            if self._active_filter == "common":
                msg = ("COMMON EMPTY / 暂无常用动作\n"
                       "完成模板训练后，用过的动作会自动出现在这里")
            else:
                msg = "NO ENTRIES / 无匹配动作"
            empty = Label(text=msg, color=theme.TEXT_MUTED,
                          font_size=dp(theme.FONT_BODY), size_hint_y=None,
                          height=dp(160), halign="center", valign="middle")
            self._grid.add_widget(empty)

    def _build_batch(self, _dt):
        """Bound widget work per frame; cached cards are reused across filters."""
        started = perf_counter()
        count = 0
        while self._build_index < len(self._pending_rows):
            ex = self._pending_rows[self._build_index]
            key = (ex['id'], ex['name_zh'], ex.get('thumbnail_path'), ex.get('equipment'))
            card = self._card_cache.pop(key, None)
            if card is None:
                card = ArchiveCard(ex)
            self._card_cache[key] = card
            self._grid.add_widget(card)
            self._build_index += 1
            count += 1
            if count >= 6 or perf_counter() - started >= 0.004:
                break
        # Bound retained widgets when the packaged catalog grows.
        while len(self._card_cache) > 500:
            self._card_cache.popitem(last=False)
        if self._build_index >= len(self._pending_rows):
            self._build_event = None
            return False
        return True
