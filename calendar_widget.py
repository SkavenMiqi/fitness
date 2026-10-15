
import calendar as cal
from datetime import date
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.utils import escape_markup
import theme
import database as db
import sounds
from utils import fx
from utils.appearance import state as appearance

class RoundedButton(Button):
    def __init__(self, text="", bg_color=(0.1,0.1,0.1,1), color=(1,1,1,1),
                 size_hint=(None,None), size=(40,40), font_size=12,
                 bold=False, markup=False, radius=None, **kwargs):
        super().__init__(text=text, size_hint=size_hint, size=size,
                         font_size=font_size, bold=bold, markup=markup,
                         background_normal="", background_color=(0,0,0,0),
                         color=color, **kwargs)
        self._radius = radius if radius is not None else dp(theme.CONTROL_RADIUS)
        self._orig_color = bg_color
        self._bg_color = bg_color
        self.bind(pos=self._draw, size=self._draw)
        self.bind(on_press=self._on_down, on_release=self._on_up)
        appearance.bind(enhanced=self._draw)
    def _draw(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*((1, 1, 1, 1) if appearance.enhanced else self._bg_color))
            Rectangle(pos=self.pos, size=self.size,
                      texture=fx.key_texture(self._bg_color, pressed=self.state == 'down')
                      if appearance.enhanced else None)
            Color(*theme.METAL_DARK)
            Line(rectangle=(*self.pos, *self.size), width=dp(0.6))
    def set_color(self, bg_color):
        self._bg_color = bg_color
        self._draw()
    def _on_down(self, *_):
        sounds.play_click()
        self._bg_color = sounds.lighten(self._orig_color)
        self._draw()
    def _on_up(self, *_):
        self._bg_color = self._orig_color
        self._draw()

class CalendarHeatmap(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.active_dates = db.get_active_dates()
        self.nuked_dates = db.get_nuke_dates()
        self._current_date = date.today()
        self._rebuild_trigger = None
        self._touch_start = None
        self._swipe_threshold = 50
        self._animating = False
        self._grid_area = None
        self._grid = None
        self.bind(size=self._on_resize)
        Clock.schedule_once(lambda dt: self._build(), 0)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and not self._animating:
            self._touch_start = touch.pos
            return super().on_touch_down(touch)
        return False

    def on_touch_up(self, touch):
        if self._touch_start:
            dx = touch.pos[0] - self._touch_start[0]
            if abs(dx) > self._swipe_threshold:
                if dx > 0: self._prev_month()
                else: self._next_month()
                self._touch_start = None
                return True
            self._touch_start = None
        return super().on_touch_up(touch)

    def _on_resize(self, *_):
        if self._rebuild_trigger:
            Clock.unschedule(self._rebuild_trigger)
        self._rebuild_trigger = Clock.schedule_once(lambda dt: self._build(), 0.08)

    def _scale(self, base, ratio):
        return max(1, int(base * ratio))

    def _make_grid(self, year, month, w, cell_size, spacing, cols, font_size):
        cal_obj = cal.Calendar(firstweekday=0)
        month_days = cal_obj.monthdayscalendar(year, month)
        total_rows = 1 + len(month_days)
        grid_w = cell_size * cols + spacing * (cols - 1)
        grid_h = cell_size * total_rows + spacing * (total_rows - 1)
        grid = GridLayout(cols=cols, spacing=spacing, size_hint=(None,None), size=(grid_w, grid_h))
        for day_name in ["一","二","三","四","五","六","日"]:
            lbl = Label(text=day_name, font_size=font_size, color=theme.TEXT_MUTED,
                        size_hint=(None,None), size=(cell_size,cell_size),
                        halign="center", valign="middle", bold=True)
            lbl.bind(size=lbl.setter("text_size"))
            grid.add_widget(lbl)
        today = date.today()
        for week in month_days:
            for day_num in week:
                if day_num == 0:
                    grid.add_widget(BoxLayout(size_hint=(None,None), size=(cell_size,cell_size)))
                    continue
                d = date(year, month, day_num)
                d_str = d.isoformat()
                info = self.active_dates.get(d_str)
                if d > today:
                    clr = (*theme.DISPLAY_OFF[:3], 0.25)
                    tclr = theme.TEXT_MUTED
                elif info:
                    has_s = info.get("strength", False)
                    has_c = info.get("cardio", False)
                    if has_s and has_c:
                        clr = theme.VFD_CYAN; tclr = theme.CHASSIS
                    elif has_s:
                        clr = theme.VFD_ORANGE; tclr = theme.CHASSIS
                    else:
                        clr = theme.VFD_BLUE; tclr = theme.CHASSIS
                else:
                    clr = theme.DISPLAY_OFF; tclr = theme.TEXT_SECONDARY
                if d == today:
                    if info:
                        has_s = info.get("strength", False)
                        has_c = info.get("cardio", False)
                        if has_s and has_c: clr = theme.ACCENT
                        elif has_s: clr = theme.STRENGTH_ORANGE
                        else: clr = theme.CARDIO_BLUE
                    else:
                        clr = theme.TODAY_RING
                    tclr = theme.TEXT_PRIMARY
                is_nuked = d_str in self.nuked_dates
                if is_nuked:
                    display_text = "[font=Symbols]☢[/font]" + str(day_num)
                else:
                    display_text = str(day_num)
                cell = RoundedButton(text=display_text, bg_color=clr, color=tclr,
                                     size_hint=(None,None), size=(cell_size,cell_size),
                                     font_size=font_size, bold=(d == today), markup=is_nuked)
                cell.bind(on_release=lambda _, ds=d_str: self._show_day(ds))
                grid.add_widget(cell)
        return grid

    def _build(self, *args):
        if self._grid is not None:
            Animation.cancel_all(self._grid)
        self._animating = False
        self.clear_widgets()
        year = self._current_date.year
        month = self._current_date.month
        w, h = self.size
        if w < 10 or h < 10: return
        ref = 400.0
        scale = w / ref if w > 0 else 1.0
        pad_h = self._scale(10, scale)
        pad_v = self._scale(10, scale)
        spacing = max(1, self._scale(2, scale))
        cols = 7
        bottom_h = max(dp(30), int(h * 0.08))
        gap = max(1, self._scale(4, scale))
        grid_area_h = h - bottom_h - pad_v - gap
        cal_obj = cal.Calendar(firstweekday=0)
        month_days = cal_obj.monthdayscalendar(year, month)
        total_rows = 1 + len(month_days)
        cell_w = (w - pad_h * 2 - spacing * (cols - 1)) // cols
        cell_h = (grid_area_h - spacing * (total_rows - 1)) // total_rows if total_rows > 0 else 0
        cell_size = max(1, min(cell_w, cell_h))
        font_size = max(1, int(cell_size * 0.38))
        self._grid_area = FloatLayout(size_hint_y=None, height=grid_area_h)
        grid = self._make_grid(year, month, w, cell_size, spacing, cols, font_size)

        def position_grid(*_):
            grid.center_x = self._grid_area.center_x
            grid.center_y = self._grid_area.center_y

        self._grid_area.bind(pos=position_grid, size=position_grid)
        self._grid_area.add_widget(grid)
        self._grid = grid
        self.add_widget(self._grid_area)
        Clock.schedule_once(position_grid, 0)
        bar = BoxLayout(size_hint_y=None, height=bottom_h,
                        spacing=self._scale(4, scale),
                        padding=[self._scale(8, scale), 0, self._scale(8, scale), 0])
        with bar.canvas.before:
            Color(*theme.DISPLAY_GLASS)
            self._bar_bg = Rectangle(pos=bar.pos, size=bar.size)
        bar.bind(pos=lambda _, p: setattr(self._bar_bg, "pos", p),
                 size=lambda _, s: setattr(self._bar_bg, "size", s))
        arrow_fs = max(1, int(font_size * 1.3))
        prev_btn = Button(text="<", size_hint=(None, None),
                          size=(dp(28), bottom_h),
                          background_normal="", background_color=(0,0,0,0),
                          font_size=arrow_fs, color=theme.TEXT_SECONDARY, bold=True)
        sounds.bind_feedback(prev_btn, text_color=theme.TEXT_SECONDARY)
        prev_btn.bind(on_release=lambda _: self._prev_month())
        bar.add_widget(prev_btn)
        bar.add_widget(BoxLayout(size_hint_x=None, width=self._scale(6, scale)))
        bar.add_widget(Label(text=f"{year}/{month:02d}",
                             font_size=max(1, int(font_size * 0.8)),
                             color=theme.TEXT_PRIMARY,
                             size_hint_x=None, width=self._scale(70, scale)))
        bar.add_widget(BoxLayout(size_hint_x=None, width=self._scale(6, scale)))
        next_btn = Button(text=">", size_hint=(None, None),
                          size=(dp(28), bottom_h),
                          background_normal="", background_color=(0,0,0,0),
                          font_size=arrow_fs, color=theme.TEXT_SECONDARY, bold=True)
        sounds.bind_feedback(next_btn, text_color=theme.TEXT_SECONDARY)
        next_btn.bind(on_release=lambda _: self._next_month())
        bar.add_widget(next_btn)
        lf = max(1, int(font_size * 0.75))
        sq = dp(12)
        for lbl_text, shade in [("力量", theme.STRENGTH_ORANGE), ("有氧", theme.CARDIO_BLUE), ("两者", theme.ACCENT)]:
            bar.add_widget(Label(text=lbl_text, font_size=lf, size_hint_x=None,
                                 width=self._scale(28, scale), color=theme.TEXT_MUTED))
            bar.add_widget(RoundedButton(bg_color=shade, color=(1,1,1,0),
                                         size_hint=(None, None), size=(sq, sq),
                                         radius=0))
        bar.add_widget(BoxLayout())
        self.add_widget(bar)

    def _show_day(self, d_str):
        DayDetailPopup(d_str).open()

    def _animate_switch(self, direction):
        if self._animating or not self._grid_area or not self._grid: return
        self._animating = True
        w, h = self.size
        scale = w / 400.0 if w > 0 else 1.0
        pad_h = self._scale(10, scale)
        spacing = max(1, self._scale(2, scale))
        cols = 7
        grid_area_h = self._grid_area.height
        year = self._current_date.year
        month = self._current_date.month
        cal_obj = cal.Calendar(firstweekday=0)
        month_days = cal_obj.monthdayscalendar(year, month)
        total_rows = 1 + len(month_days)
        cell_w = (w - pad_h * 2 - spacing * (cols - 1)) // cols
        cell_h = (grid_area_h - spacing * (total_rows - 1)) // total_rows if total_rows > 0 else 0
        cell_size = max(1, min(cell_w, cell_h))
        font_size = max(1, int(cell_size * 0.38))
        grid_area = self._grid_area
        old_grid = self._grid
        new_grid = self._make_grid(year, month, w, cell_size, spacing, cols, font_size)
        center_x = grid_area.x + (grid_area.width - new_grid.width) / 2
        center_y = grid_area.y + (grid_area.height - new_grid.height) / 2
        offset = grid_area.width if direction == -1 else -grid_area.width
        new_grid.x = center_x + offset
        new_grid.y = center_y
        grid_area.add_widget(new_grid)
        anim_old = Animation(x=old_grid.x - offset, duration=0.18, transition="out_cubic")
        anim_new = Animation(x=center_x, duration=0.18, transition="out_cubic")
        def on_complete(*_):
            if old_grid.parent is grid_area:
                grid_area.remove_widget(old_grid)
            if self._grid_area is not grid_area:
                return
            self._grid = new_grid
            self._animating = False
        anim_new.bind(on_complete=on_complete)
        anim_old.start(old_grid)
        anim_new.start(new_grid)

    def _prev_month(self):
        if self._animating: return
        y, m = self._current_date.year, self._current_date.month
        self._current_date = date(y-1, 12, 1) if m == 1 else date(y, m-1, 1)
        self._animate_switch(1)

    def _next_month(self):
        if self._animating: return
        y, m = self._current_date.year, self._current_date.month
        self._current_date = date(y+1, 1, 1) if m == 12 else date(y, m+1, 1)
        self._animate_switch(-1)

    def refresh(self):
        self.active_dates = db.get_active_dates()
        self.nuked_dates = db.get_nuke_dates()
        self._build()


class DayDetailPopup(ModalView):
    def __init__(self, date_str, **kwargs):
        super().__init__(size_hint=(0.94, 0.92), background="",
                         background_color=theme.OVERLAY, **kwargs)
        self.date_str = date_str
        self.overview = db.get_date_overview(date_str)
        self._build_ui()

    def _build_ui(self):
        data = self.overview
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        with root.canvas.before:
            Color(*theme.CHASSIS)
            root_bg = Rectangle(pos=root.pos, size=root.size)
            Color(*theme.METAL_LIGHT)
            root_border = Line(rectangle=(*root.pos, *root.size), width=dp(1))
        root.bind(
            pos=lambda _, p: (setattr(root_bg, "pos", p),
                              setattr(root_border, "rectangle", (*p, root.width, root.height))),
            size=lambda _, s: (setattr(root_bg, "size", s),
                               setattr(root_border, "rectangle", (root.x, root.y, *s))),
        )

        header = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        status = "NUKE LOG" if data["nuked"] else "DAILY LOG"
        title = Label(
            text=f"[color=33ccff][b]{status} / {self.date_str}[/b][/color]\n训练与身体数据记录",
            markup=True, color=theme.TEXT_PRIMARY, font_size=dp(12),
            halign="left", valign="middle",
        )
        title.bind(size=title.setter("text_size"))
        header.add_widget(title)
        close = Button(text="×", size_hint_x=None, width=dp(38),
                       background_normal="", background_color=(0, 0, 0, 0),
                       color=theme.TEXT_MUTED, font_size=dp(20))
        close.bind(on_release=lambda *_: self.dismiss())
        header.add_widget(close)
        root.add_widget(header)

        summary = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(6))
        summary.add_widget(self._metric("INTAKE / 摄入", data["intake_calories"], "KCAL",
                                        theme.VFD_ORANGE))
        summary.add_widget(self._metric("OUTPUT / 训练", data["exercise_calories"], "KCAL",
                                        theme.VFD_CYAN))
        body_weight = next((row.get("weight") for row in data["body"]
                            if row.get("weight") is not None), None)
        summary.add_widget(self._metric("WEIGHT / 体重", body_weight, "KG",
                                        theme.VFD_BLUE))
        root.add_widget(summary)

        scroll = ScrollView(do_scroll_x=False, bar_width=dp(3),
                            scroll_type=["bars", "content"])
        log = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        log.bind(minimum_height=log.setter("height"))
        log.add_widget(self._section("NUTRITION INPUT / 热量与食谱", theme.VFD_ORANGE,
                                     self._meal_lines(data)))
        log.add_widget(self._section("PROGRAM / 训练模板与计划", theme.VFD_BLUE,
                                     self._plan_lines(data)))
        log.add_widget(self._section("TRAINING OUTPUT / 实际训练", theme.VFD_CYAN,
                                     self._training_lines(data)))
        log.add_widget(self._section("BODY SCAN / 身体数据", theme.LED_GREEN,
                                     self._body_lines(data)))
        scroll.add_widget(log)
        root.add_widget(scroll)
        self.add_widget(root)
        sounds.bind_feedback(root)

    def _metric(self, title, value, unit, color):
        box = BoxLayout(orientation="vertical", padding=[dp(5), dp(3)])
        with box.canvas.before:
            Color(*theme.DISPLAY_GLASS)
            bg = Rectangle(pos=box.pos, size=box.size)
            Color(*theme.METAL_DARK)
            border = Line(rectangle=(*box.pos, *box.size), width=dp(0.8))
        box.bind(
            pos=lambda _, p: (setattr(bg, "pos", p),
                              setattr(border, "rectangle", (*p, box.width, box.height))),
            size=lambda _, s: (setattr(bg, "size", s),
                               setattr(border, "rectangle", (box.x, box.y, *s))),
        )
        box.add_widget(Label(text=title, color=theme.TEXT_MUTED,
                             font_size=dp(9), halign="left", valign="middle"))
        display = "--" if value is None else _number(value)
        box.add_widget(Label(text=f"[b]{display}[/b]  {unit}", markup=True,
                             color=color, font_size=dp(13),
                             halign="left", valign="middle"))
        for label in box.children:
            label.bind(size=label.setter("text_size"))
        return box

    def _section(self, title, color, lines):
        box = BoxLayout(orientation="vertical", size_hint_y=None,
                        padding=[dp(8), dp(6)], spacing=dp(2))
        box.bind(minimum_height=box.setter("height"))
        with box.canvas.before:
            Color(*theme.DISPLAY_GLASS)
            bg = Rectangle(pos=box.pos, size=box.size)
            Color(*theme.METAL_DARK)
            border = Line(rectangle=(*box.pos, *box.size), width=dp(0.8))
        box.bind(
            pos=lambda _, p: (setattr(bg, "pos", p),
                              setattr(border, "rectangle", (*p, box.width, box.height))),
            size=lambda _, s: (setattr(bg, "size", s),
                               setattr(border, "rectangle", (box.x, box.y, *s))),
        )
        heading = Label(text=f"[b]{title}[/b]", markup=True, color=color,
                        font_size=dp(11), size_hint_y=None, height=dp(22),
                        halign="left", valign="middle")
        heading.bind(size=heading.setter("text_size"))
        box.add_widget(heading)
        if not lines:
            lines = [("未记录", theme.TEXT_MUTED)]
        for text, text_color in lines:
            row = Label(text=text, markup=True, color=text_color,
                        font_size=dp(12), size_hint_y=None,
                        halign="left", valign="top")
            row.bind(width=lambda widget, width:
                     setattr(widget, "text_size", (max(0, width), None)))
            row.bind(texture_size=lambda widget, size:
                     setattr(widget, "height", max(dp(26), size[1] + dp(8))))
            box.add_widget(row)
        return box

    def _meal_lines(self, data):
        lines = []
        for meal in data["meals"]:
            meal_type = escape_markup(str(meal["meal_type"]))
            food_summary = escape_markup(str(meal["food_summary"]))
            lines.append((
                f"[color=ff9d24][b]{meal_type}  {_number(meal['calories'])} KCAL[/b][/color]\n"
                f"{food_summary}",
                theme.TEXT_PRIMARY,
            ))
        if lines:
            lines.append((f"TOTAL INTAKE  {_number(data['intake_calories'])} KCAL",
                          theme.VFD_ORANGE))
        return lines

    def _plan_lines(self, data):
        plans = data["plans"]
        lines = []
        template = escape_markup(str(data["template_name"] or "未匹配模板"))
        done = sum(1 for item in plans if item.get("completed"))
        if plans:
            lines.append((f"TEMPLATE  [color=33ccff]{template}[/color]    "
                          f"PROGRESS  {done}/{len(plans)}", theme.TEXT_PRIMARY))
        for item in plans:
            state = "DONE" if item.get("completed") else "WAIT"
            state_color = "00e070" if item.get("completed") else "667070"
            if item["item_type"] == "strength":
                target = (f"{_number(item.get('target_sets'))}组 × "
                          f"{_number(item.get('target_reps'))}次 × "
                          f"{_number(item.get('target_weight'))}kg")
                increments = []
                if item.get("target_weight_step"):
                    increments.append(f"{float(item['target_weight_step']):+g}kg/组")
                if item.get("target_rep_step"):
                    increments.append(f"{int(item['target_rep_step']):+d}次/组")
                if increments:
                    target += "  " + " / ".join(increments)
            else:
                target = (f"{_number(item.get('target_distance'))}km  "
                          f"{_number(item.get('target_duration'))}min")
            exercise_name = escape_markup(str(item["exercise_name"]))
            lines.append((f"[color={state_color}][b]{state}[/b][/color]  "
                          f"{exercise_name}  {target}", theme.TEXT_PRIMARY))
        return lines

    def _training_lines(self, data):
        lines = []
        grouped = {}
        order = []
        for row in data["strength"]:
            key = (row["exercise_name"], row["reps"], row["weight"], row.get("notes") or "")
            if key not in grouped:
                grouped[key] = 0
                order.append(key)
            grouped[key] += row["sets"]
        for name, reps, weight, notes in order:
            detail = (f"{escape_markup(str(name))}  "
                      f"{grouped[(name, reps, weight, notes)]}组 × {reps}次 × {_number(weight)}kg")
            if notes:
                detail += f"\nNOTE  {escape_markup(str(notes))}"
            lines.append((detail, theme.TEXT_PRIMARY))
        for row in data["cardio"]:
            detail = (f"{escape_markup(str(row['exercise_type']))}  "
                      f"{_number(row['distance'])}km  "
                      f"{_number(row['duration'])}min")
            if row.get("notes"):
                detail += f"\nNOTE  {escape_markup(str(row['notes']))}"
            lines.append((detail, theme.TEXT_PRIMARY))
        if lines:
            lines.append((f"TOTAL OUTPUT  {_number(data['exercise_calories'])} KCAL",
                          theme.VFD_CYAN))
        return lines

    def _body_lines(self, data):
        lines = []
        labels = (("weight", "体重", "kg"), ("body_fat", "体脂", "%"),
                  ("chest", "胸围", "cm"), ("waist", "腰围", "cm"),
                  ("arm", "臂围", "cm"))
        for record in data["body"]:
            values = [f"{label} {_number(record.get(key))}{unit}"
                      for key, label, unit in labels if record.get(key) is not None]
            text = "    ".join(values) if values else "身体数据为空"
            if record.get("notes"):
                text += f"\nNOTE  {escape_markup(str(record['notes']))}"
            lines.append((text, theme.TEXT_PRIMARY))
        return lines


def _number(value):
    if value is None:
        return "--"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"
