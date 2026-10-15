from datetime import date, timedelta
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle, Line
from kivy.core.text import Label as CoreLabel
from config import theme
import database as db
from utils import fx
from utils.appearance import state as appearance


class _ModeKey(Button):
    def __init__(self, text, active=False, width=None, **kwargs):
        sz = (dp(width or 56), dp(30))
        super().__init__(text=text, size_hint=(1, None), size=sz,
                         background_normal="", background_color=(0, 0, 0, 0),
                         font_size=dp(theme.FONT_LABEL), bold=active, **kwargs)
        self._active = active
        self.bind(pos=self._draw, size=self._draw)
        appearance.bind(enhanced=self._draw)

    def set_active(self, active):
        self._active = active
        self.bold = active
        self._draw()

    def _draw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            bg = theme.VFD_ORANGE if self._active else theme.METAL_DARK
            Color(*bg)
            Rectangle(pos=self.pos, size=self.size)
            Color(*(theme.METAL_LIGHT if self._active else theme.BORDER))
            Line(rectangle=(self.x, self.y, self.width, self.height), width=dp(1))
            Color(*theme.GLASS_HIGHLIGHT)
            Line(points=[self.x + dp(1), self.top - dp(1),
                         self.right - dp(1), self.top - dp(1)], width=dp(1))
        self.color = theme.CHASSIS if self._active else theme.TEXT_SECONDARY


class StatsPanel(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(theme.CARD_SPACING),
                         padding=[dp(theme.PAGE_MARGIN), dp(theme.PAGE_MARGIN),
                                  dp(theme.PAGE_MARGIN), dp(theme.PAGE_MARGIN)], **kwargs)
        self._view_mode = "week"
        self._metric_mode = "cal"
        with self.canvas.before:
            Color(*theme.CHASSIS)
            self._chassis = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_chassis, size=self._sync_chassis)
        fx.chassis(self)
        self._build_ui()

    def _sync_chassis(self, *_):
        self._chassis.pos = self.pos
        self._chassis.size = self.size

    def _build_ui(self):
        self.clear_widgets()
        self._content = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_y=None,
                                  padding=0)
        self._content.bind(minimum_height=self._content.setter("height"))
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False, do_scroll_y=True)
        scroll.add_widget(self._content)
        self.add_widget(scroll)

        wt_bar = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        wt_bar.add_widget(Label(text="体重", color=theme.TEXT_SECONDARY,
                                font_size=dp(theme.FONT_BODY), size_hint_x=None, width=dp(40),
                                halign="right", valign="middle"))
        bw = db.get_user_weight()
        self._wt_inp = TextInput(text=str(bw), multiline=False, size_hint_x=None,
                                  width=dp(64), halign="center",
                                  background_normal="", background_active="",
                                   background_color=theme.DISPLAY_GLASS,
                                   foreground_color=theme.TEXT_PRIMARY,
                                   cursor_color=theme.VFD_CYAN,
                                  font_size=dp(theme.FONT_BODY), padding=[0, dp(10)])
        self._wt_inp.bind(text=self._on_weight_change)
        with self._wt_inp.canvas.after:
            Color(*theme.BORDER)
            self._wt_inp._display_border = Line(rectangle=(0, 0, 0, 0), width=dp(1))
            Color(*theme.GLASS_HIGHLIGHT)
            self._wt_inp._display_glint = Line(points=[], width=dp(1))

        def sync_weight_display(inp, *_):
            inp._display_border.rectangle = (inp.x, inp.y, inp.width, inp.height)
            inp._display_glint.points = [inp.x + dp(1), inp.top - dp(1),
                                         inp.right - dp(1), inp.top - dp(1)]
        self._wt_inp.bind(pos=sync_weight_display, size=sync_weight_display)
        wt_bar.add_widget(self._wt_inp)
        wt_bar.add_widget(Label(text="kg", color=theme.TEXT_MUTED,
                                font_size=dp(theme.FONT_LABEL), size_hint_x=None, width=dp(24)))
        wt_bar.add_widget(Label(text="", size_hint_x=1))
        imp_btn = Button(text="导入历史", size_hint=(None, None), size=(dp(70), dp(30)),
                         background_normal="", background_color=theme.METAL_DARK,
                         color=theme.VFD_CYAN, font_size=dp(theme.FONT_LABEL), bold=True)
        with imp_btn.canvas.before:
            Color(*theme.BORDER)
            imp_btn._edge = Line(rectangle=(0, 0, 0, 0), width=dp(1))
        imp_btn.bind(pos=lambda w, _: setattr(w._edge, "rectangle", (w.x, w.y, w.width, w.height)),
                     size=lambda w, _: setattr(w._edge, "rectangle", (w.x, w.y, w.width, w.height)))
        imp_btn.bind(on_release=lambda _: self._open_import())
        wt_bar.add_widget(imp_btn)
        self._content.add_widget(wt_bar)
        fx.surface(wt_bar, 'glass', theme.VFD_CYAN, cut=4)

        self._content.add_widget(Label(text="今日汇总", color=theme.VFD_ORANGE,
                                        font_size=dp(theme.FONT_H3), bold=True,
                                        size_hint_y=None, height=dp(22),
                                        halign="left", valign="middle"))
        self._table_box = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None)
        self._table_box.bind(minimum_height=self._table_box.setter("height"))
        self._content.add_widget(self._table_box)
        fx.surface(self._table_box, 'glass', theme.VFD_CYAN, cut=4)

        toggle = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        self._view_pills = {}
        for mode, label, w in [("week", "本周", 56), ("month", "本月", 56), ("last_month", "上月", 56)]:
            p = _ModeKey(label, active=(self._view_mode == mode), width=w)
            p.bind(on_press=lambda _, m=mode: self._set_view(m))
            self._view_pills[mode] = p
            toggle.add_widget(p)
        toggle.add_widget(BoxLayout(size_hint_x=None, width=dp(8)))
        self._metric_pills = {}
        for metric, label, w in [("cal", "热量", 56), ("vol", "训练量", 72)]:
            p = _ModeKey(label, active=(self._metric_mode == metric), width=w)
            p.bind(on_press=lambda _, m=metric: self._set_metric(m))
            self._metric_pills[metric] = p
            toggle.add_widget(p)
        self._content.add_widget(toggle)

        self._chart_label = Label(text="每日消耗趋势 (大卡)", color=theme.TEXT_MUTED,
                                   font_size=dp(theme.FONT_CAPTION), size_hint_y=None,
                                   height=dp(18), halign="left", valign="middle")
        self._content.add_widget(self._chart_label)
        self.refresh()
        self._build_chart()

    def _build_chart(self):
        if hasattr(self, "_chart") and self._chart.parent:
            self._chart.parent.remove_widget(self._chart)
        self._chart = ChartWidget(size_hint_y=None, height=dp(220))
        self._content.add_widget(self._chart)
        self.refresh_chart()

    def refresh(self):
        self._build_summary()

    def refresh_chart(self):
        today = date.today()
        days, labels = [], []
        if self._view_mode == "week":
            start = today - timedelta(days=today.weekday())
            for i in range(7):
                days.append((start + timedelta(days=i)).isoformat())
                labels.append(["一", "二", "三", "四", "五", "六", "日"][i])
        elif self._view_mode == "month":
            start = today.replace(day=1)
            nxt = today.replace(month=today.month % 12 + 1, day=1) if today.month < 12 else today.replace(year=today.year + 1, month=1, day=1)
            dim = (nxt - timedelta(days=1)).day
            for i in range(min(dim, 31)):
                days.append((start + timedelta(days=i)).isoformat())
                labels.append(str(i + 1))
        else:
            start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            nxt = today.replace(month=today.month % 12 + 1, day=1) if today.month < 12 else today.replace(year=today.year + 1, month=1, day=1)
            dim = (nxt - timedelta(days=1)).day
            for i in range(min(dim, 31)):
                days.append((start + timedelta(days=i)).isoformat())
                labels.append(str(i + 1))
        bw = db.get_user_weight()
        values = []
        for d in days:
            s_rows, c_rows = db.get_date_detail(d)
            day_total = 0
            if self._metric_mode == "cal":
                for r in s_rows:
                    day_total += db.calc_strength_calories(r["exercise_name"], r["sets"], r["reps"], r["weight"], bw)
                for r in c_rows:
                    day_total += db.calc_cardio_calories(r["exercise_type"], r["duration"], bw)
            else:
                for r in s_rows:
                    day_total += r["sets"] * r["weight"]
                for r in c_rows:
                    day_total += r["distance"] * 10
            values.append(round(day_total, 1))
        unit = "大卡" if self._metric_mode == "cal" else "训练量"
        self._chart.draw(values, labels, unit)
        self._chart_label.text = f"每日消耗趋势 ({unit})"

    def _build_summary(self):
        self._table_box.clear_widgets()
        hdr = BoxLayout(size_hint_y=None, height=dp(22), spacing=dp(4),
                        padding=[dp(4), 0])
        for txt, sx, align in [("项目", 0.26, "left"), ("类型", 0.14, "left"),
                                ("热量(大卡)", 0.24, "right"), ("训练量", 0.36, "right")]:
            hdr.add_widget(Label(text=txt, color=theme.TEXT_MUTED,
                                 font_size=dp(theme.FONT_CAPTION), size_hint_x=sx,
                                 halign=align, valign="middle", bold=True))
        self._table_box.add_widget(hdr)
        today_str = date.today().isoformat()
        s_rows, c_rows = db.get_date_detail(today_str)
        bw = db.get_user_weight()
        total_cal = 0
        for r in s_rows:
            cal = db.calc_strength_calories(r["exercise_name"], r["sets"], r["reps"], r["weight"], bw)
            total_cal += cal
            self._table_box.add_widget(self._summary_row(r["exercise_name"], "力量", cal,
                                                         f"{r['sets']}组×{r['reps']}次×{r['weight']}kg"))
        for r in c_rows:
            cal = db.calc_cardio_calories(r["exercise_type"], r["duration"], bw)
            total_cal += cal
            self._table_box.add_widget(self._summary_row(r["exercise_type"], "有氧", cal,
                                                         f"{r['distance']}km/{r['duration']}min"))
        if not s_rows and not c_rows:
            self._table_box.add_widget(Label(text="今天还没有训练记录", color=theme.TEXT_MUTED,
                                             font_size=dp(theme.FONT_LABEL), size_hint_y=None,
                                             height=dp(28), halign="center", valign="middle"))
        total_row = BoxLayout(size_hint_y=None, height=dp(26), spacing=dp(4),
                              padding=[dp(4), 0])
        total_row.add_widget(Label(text="[b]总计[/b]", color=theme.VFD_ORANGE,
                                   font_size=dp(theme.FONT_LABEL), markup=True,
                                   size_hint_x=0.40, halign="left", valign="middle"))
        total_row.add_widget(Label(text=f"[b]{total_cal:.0f}[/b]", color=theme.VFD_ORANGE,
                                   markup=True, font_size=dp(theme.FONT_H3),
                                   size_hint_x=0.24, halign="right", valign="middle"))
        total_row.add_widget(Label(text="", size_hint_x=0.36))
        self._table_box.add_widget(total_row)

    def _summary_row(self, name, etype, cal, vol_text):
        row = BoxLayout(size_hint_y=None, height=dp(24), spacing=dp(4), padding=[dp(4), 0])
        row.add_widget(Label(text=name, color=theme.TEXT_PRIMARY,
                             font_size=dp(theme.FONT_LABEL), size_hint_x=0.26,
                             halign="left", valign="middle"))
        row.add_widget(Label(text=etype, color=theme.TEXT_SECONDARY,
                             font_size=dp(theme.FONT_LABEL), size_hint_x=0.14,
                             halign="left", valign="middle"))
        row.add_widget(Label(text=f"{cal:.0f}", color=theme.TEXT_PRIMARY,
                             font_size=dp(theme.FONT_LABEL), size_hint_x=0.24,
                             halign="right", valign="middle"))
        row.add_widget(Label(text=vol_text, color=theme.TEXT_MUTED,
                             font_size=dp(theme.FONT_CAPTION), size_hint_x=0.36,
                             halign="right", valign="middle"))
        return row

    def _set_view(self, mode):
        self._view_mode = mode
        for m, p in self._view_pills.items():
            p.set_active(m == mode)
        self._build_ui()
        self.refresh_chart()

    def _set_metric(self, mode):
        self._metric_mode = mode
        for m, p in self._metric_pills.items():
            p.set_active(m == mode)
        self._build_ui()
        self.refresh_chart()

    def _on_weight_change(self, instance, value):
        try:
            db.set_user_weight(date.today().isoformat(), float(value))
        except ValueError:
            pass

    def _open_import(self):
        from import_backup import ImportBackupDialog
        popup = ImportBackupDialog(on_done=lambda: self.refresh())
        popup.open()


class ChartWidget(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(size_hint=(1, None), **kwargs)
        self._data = []
        self._labels = []
        self._ylabel = "大卡"
        self.bind(pos=self._draw, size=self._draw)
        appearance.bind(enhanced=self._draw)

    def draw(self, values, labels, ylabel):
        self._data = values
        self._labels = labels
        self._ylabel = ylabel
        self._draw()

    def _draw(self, *args):
        self.canvas.after.clear()
        self.canvas.before.clear()
        w, h = self.width, self.height
        if not self._data or w < 10 or h < 10:
            return
        ox, oy = self.x, self.y
        with self.canvas.before:
            Color(*theme.DISPLAY_GLASS)
            Rectangle(pos=self.pos, size=self.size)
            Color(*theme.BORDER)
            Line(rectangle=(self.x, self.y, self.width, self.height), width=dp(1))
            Color(*theme.GLASS_HIGHLIGHT)
            Line(points=[self.x + dp(1), self.top - dp(1),
                         self.right - dp(1), self.top - dp(1)], width=dp(1))
        panel = fx.Plate('glass', accent_color=theme.VFD_CYAN)
        panel.overlay = True
        panel.update(self.x, self.y, self.width, self.height)
        self.canvas.before.add(panel.group)
        margin_left = dp(42)
        margin_bottom = dp(24)
        margin_top = dp(20)
        chart_w = w - margin_left - dp(10)
        chart_h = h - margin_bottom - margin_top
        bar_count = len(self._data)
        step = chart_w / bar_count
        bar_w = max(dp(3), step * 0.62)
        max_val = max(self._data) if max(self._data) > 0 else 1
        baseline_y = oy + margin_bottom
        with self.canvas.before:
            Color(*theme.BORDER_DIM)
            Line(points=[ox + margin_left, baseline_y,
                          ox + margin_left + chart_w, baseline_y], width=1)
            for grid_i in range(1, 5):
                gy = baseline_y + chart_h * grid_i / 5
                Line(points=[ox + margin_left, gy,
                             ox + margin_left + chart_w, gy], width=dp(0.5))
            for i, val in enumerate(self._data):
                bar_h = (val / max_val) * chart_h if val > 0 else 1
                bx = ox + margin_left + i * step + step * 0.2
                by = baseline_y
                segment_h = dp(5)
                segment_gap = dp(2)
                segment_count = max(1, int(bar_h / (segment_h + segment_gap))) if val > 0 else 0
                Color(*theme.VFD_CYAN)
                for segment in range(segment_count):
                    fx.draw_segment_glow(self.canvas.before,
                        bx, by + segment * (segment_h + segment_gap), bar_w, segment_h,
                        theme.VFD_CYAN, glow=segment == segment_count - 1)
            for i, val in enumerate(self._data):
                bar_h = (val / max_val) * chart_h if val > 0 else 0
                bx = ox + margin_left + i * step + step * 0.2
                by = baseline_y + bar_h + dp(2)
                if val > 0 and (bar_count <= 14 or i % max(1, bar_count // 10) == 0):
                    lbl = CoreLabel(text=str(int(val)), font_size=dp(11),
                                    color=theme.VFD_CYAN, font_name="Roboto")
                    lbl.refresh()
                    tex, ts = lbl.texture, lbl.texture.size
                    with self.canvas.before:
                        Color(*theme.VFD_CYAN)
                        Rectangle(texture=tex, pos=(bx + bar_w / 2 - ts[0] / 2, by), size=ts)
            for i, lbl_text in enumerate(self._labels):
                bx = ox + margin_left + i * step + step * 0.2 + bar_w / 2
                if bar_count <= 14 or i % max(1, bar_count // 10) == 0:
                    cl = CoreLabel(text=lbl_text, font_size=dp(10),
                                    color=theme.TEXT_MUTED, font_name="Roboto")
                    cl.refresh()
                    tex, ts = cl.texture, cl.texture.size
                    with self.canvas.before:
                        Color(*theme.TEXT_MUTED)
                        Rectangle(texture=tex, pos=(bx - ts[0] / 2, baseline_y - dp(14)), size=ts)
