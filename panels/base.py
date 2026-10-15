from datetime import date, timedelta
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle, Line
from kivy.metrics import dp

from config import theme
import sounds
from utils import fx


class FormPanel(BoxLayout):
    def __init__(self, main_layout, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(8),
                         padding=[dp(theme.PAGE_MARGIN), dp(theme.PAGE_MARGIN),
                                  dp(theme.PAGE_MARGIN), dp(theme.PAGE_MARGIN)], **kwargs)
        self.main_layout = main_layout
        self._view_date = date.today()
        self._touch_start = None
        with self.canvas.before:
            Color(*theme.CHASSIS)
            self._chassis = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_chassis, size=self._sync_chassis)
        fx.chassis(self)

        self.form_scroll = ScrollView(do_scroll_x=False)
        self.form_area = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        self.form_area.bind(minimum_height=self.form_area.setter("height"))
        self.form_scroll.add_widget(self.form_area)
        self.add_widget(self.form_scroll)

        date_bar = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        for arrow, delta in [("\u2039", -1), ("\u203a", 1)]:
            btn = Button(text=arrow, size_hint=(None, None), size=(dp(36), dp(32)),
                         background_normal="", background_color=theme.METAL_DARK,
                         font_size=dp(18), color=theme.TEXT_SECONDARY, bold=True)
            with btn.canvas.before:
                Color(*theme.METAL_LIGHT)
                btn._edge_top = Line(points=[], width=dp(1))
                Color(*theme.BORDER)
                btn._edge = Line(rectangle=(0, 0, 0, 0), width=dp(1))
            btn.bind(pos=self._sync_key, size=self._sync_key)
            btn.bind(on_release=lambda _, d=delta: self._shift_date(d))
            sounds.bind_feedback(btn, bg_color=theme.METAL_DARK)
            date_bar.add_widget(btn)
        self._date_label = Label(text=self._view_date.isoformat(), font_size=dp(theme.FONT_H3),
                                 color=theme.TEXT_PRIMARY, size_hint_x=1, bold=True,
                                 halign="center", valign="middle")
        self._date_label.bind(size=self._date_label.setter("text_size"))
        date_bar.add_widget(self._date_label)
        today_btn = Button(text="今天", size_hint=(None, None), size=(dp(56), dp(32)),
                           background_normal="", background_color=theme.VFD_ORANGE,
                           font_size=dp(theme.FONT_LABEL), color=theme.CHASSIS, bold=True)
        with today_btn.canvas.before:
            Color(*theme.METAL_LIGHT)
            today_btn._edge_top = Line(points=[], width=dp(1))
            Color(*theme.METAL_DARK)
            today_btn._edge = Line(rectangle=(0, 0, 0, 0), width=dp(1))
        today_btn.bind(pos=self._sync_key, size=self._sync_key)
        today_btn.bind(on_release=lambda _: self._goto_today())
        sounds.bind_feedback(today_btn, bg_color=theme.VFD_ORANGE)
        date_bar.add_widget(today_btn)
        self.add_widget(date_bar)

        list_label = Label(text="记录", color=theme.TEXT_MUTED,
                           font_size=dp(theme.FONT_CAPTION), bold=True,
                           size_hint_y=None, height=dp(16), halign="left", valign="middle")
        list_label.bind(size=list_label.setter("text_size"))
        self.add_widget(list_label)

        list_scroll = ScrollView(do_scroll_x=False)
        self.record_list = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.record_list.bind(minimum_height=self.record_list.setter("height"))
        list_scroll.add_widget(self.record_list)
        self.add_widget(list_scroll)

        self._input_refs = {}
        self._build_form()
        self._refresh_list()

    def _shift_date(self, delta):
        self._view_date = self._view_date + timedelta(days=delta)
        self._date_label.text = self._view_date.isoformat()
        self._refresh_list()

    def _sync_chassis(self, *_):
        self._chassis.pos = self.pos
        self._chassis.size = self.size

    @staticmethod
    def _sync_key(btn, *_):
        btn._edge.rectangle = (btn.x, btn.y, btn.width, btn.height)
        btn._edge_top.points = [btn.x + dp(1), btn.top - dp(1),
                                btn.right - dp(1), btn.top - dp(1)]

    def _goto_today(self):
        self._view_date = date.today()
        self._date_label.text = self._view_date.isoformat()
        self._refresh_list()

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self._touch_start = (touch.x, touch.y)
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if self._touch_start is not None:
            dx = touch.x - self._touch_start[0]
            dy = touch.y - self._touch_start[1]
            if abs(dx) > dp(60) and abs(dx) > abs(dy) * 1.3:
                self._shift_date(-1 if dx > 0 else 1)
        self._touch_start = None
        return super().on_touch_up(touch)

    def _build_form(self):
        pass

    def _make_textinput(self, is_text=True):
        inp = TextInput(text="", multiline=False, font_size=dp(theme.FONT_BODY),
                        input_filter=None if is_text else "float", write_tab=False,
                        background_normal="", background_active="",
                        background_color=theme.DISPLAY_GLASS,
                        foreground_color=theme.TEXT_PRIMARY,
                        cursor_color=theme.VFD_CYAN, padding=(dp(10), dp(10)))
        self._frame_input(inp)
        return inp

    @staticmethod
    def _frame_input(inp):
        with inp.canvas.after:
            Color(*theme.BORDER)
            inp._input_border = Line(rectangle=(0, 0, 0, 0), width=dp(1))
            Color(*theme.GLASS_HIGHLIGHT)
            inp._glass_line = Line(points=[], width=dp(1))
        inp.bind(pos=FormPanel._sync_input, size=FormPanel._sync_input)

    @staticmethod
    def _frame_command(btn):
        with btn.canvas.before:
            Color(*theme.METAL_LIGHT)
            btn._edge_top = Line(points=[], width=dp(1))
            Color(*theme.METAL_DARK)
            btn._edge = Line(rectangle=(0, 0, 0, 0), width=dp(1))
        btn.bind(pos=FormPanel._sync_key, size=FormPanel._sync_key)

    @staticmethod
    def _sync_input(inp, *_):
        inp._input_border.rectangle = (inp.x, inp.y, inp.width, inp.height)
        inp._glass_line.points = [inp.x + dp(1), inp.top - dp(1),
                                  inp.right - dp(1), inp.top - dp(1)]

    def _add_field(self, label, key, is_text=True):
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        lbl = Label(text=label, size_hint_x=0.28, font_size=dp(theme.FONT_BODY),
                    color=theme.TEXT_SECONDARY, halign="right", valign="middle")
        lbl.bind(size=lbl.setter("text_size"))
        row.add_widget(lbl)
        inp = self._make_textinput(is_text)
        self._input_refs[key] = inp
        row.add_widget(inp)
        self.form_area.add_widget(row)

    def _add_date_field(self):
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        lbl = Label(text="日期", size_hint_x=0.28, font_size=dp(theme.FONT_BODY),
                    color=theme.TEXT_SECONDARY, halign="right", valign="middle")
        lbl.bind(size=lbl.setter("text_size"))
        row.add_widget(lbl)
        self._input_date = self._make_textinput(is_text=True)
        self._input_date.text = date.today().isoformat()
        row.add_widget(self._input_date)
        self.form_area.add_widget(row)

    def _add_notes_field(self):
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        lbl = Label(text="备注", size_hint_x=0.28, font_size=dp(theme.FONT_BODY),
                    color=theme.TEXT_SECONDARY, halign="right", valign="middle")
        lbl.bind(size=lbl.setter("text_size"))
        row.add_widget(lbl)
        self._input_notes = self._make_textinput(is_text=True)
        row.add_widget(self._input_notes)
        self.form_area.add_widget(row)

    def _add_save_button(self, callback):
        self.form_area.add_widget(BoxLayout(size_hint_y=None, height=dp(4)))
        btn = Button(text="保存", size_hint_y=None, height=dp(44),
                     background_normal="", background_color=theme.VFD_ORANGE,
                     color=theme.CHASSIS, font_size=dp(theme.FONT_H3), bold=True)
        with btn.canvas.before:
            Color(*theme.METAL_LIGHT)
            btn._edge_top = Line(points=[], width=dp(1))
            Color(*theme.METAL_DARK)
            btn._edge = Line(rectangle=(0, 0, 0, 0), width=dp(1))
        btn.bind(pos=self._sync_key, size=self._sync_key)
        btn.bind(on_release=lambda _: callback())
        sounds.bind_feedback(btn, bg_color=theme.VFD_ORANGE)
        self.form_area.add_widget(btn)

    def _clear_inputs(self, keys):
        for k in keys:
            if k in self._input_refs:
                self._input_refs[k].text = ""
        if hasattr(self, "_input_notes"):
            self._input_notes.text = ""

    def _show_error(self, msg):
        popup = Popup(title="错误", title_color=theme.TEXT_PRIMARY,
                      content=Label(text=msg, color=theme.TEXT_PRIMARY),
                      size_hint=(0.6, 0.25), background_color=theme.PANEL)
        popup.open()

    def _refresh_list(self):
        saved = self.form_scroll.scroll_y
        self._do_refresh_list()
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: setattr(self.form_scroll, 'scroll_y', saved), 0.05)

    def _do_refresh_list(self):
        pass

    def _make_record_row(self, text, record_id, on_delete):
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8),
                        padding=[dp(12), 0])
        with row.canvas.before:
            Color(*theme.PANEL)
            bg = Rectangle(pos=row.pos, size=row.size)
            Color(*theme.BORDER)
            border = Line(rectangle=(row.x, row.y, row.width, row.height), width=dp(1))
        row._bg_rect = bg
        row._border_line = border
        row.bind(pos=self._redraw_row, size=self._redraw_row)
        fx.surface(row, 'panel', theme.VFD_CYAN, cut=3)
        lbl = Label(text=text, font_size=dp(theme.FONT_LABEL), color=theme.TEXT_SECONDARY,
                    size_hint_x=1, halign="left", valign="middle")
        lbl.bind(size=lbl.setter("text_size"))
        row.add_widget(lbl)
        del_btn = Button(text="×", size_hint=(None, None), size=(dp(28), dp(28)),
                         background_normal="", background_color=(0, 0, 0, 0),
                         color=theme.DANGER, font_size=dp(16), bold=True)
        del_btn.bind(on_release=lambda _, rid=record_id: on_delete(rid))
        sounds.bind_feedback(del_btn, text_color=theme.DANGER)
        row.add_widget(del_btn)
        return row

    def _redraw_row(self, row, *_):
        if hasattr(row, "_bg_rect"):
            row._bg_rect.pos = row.pos
            row._bg_rect.size = row.size
        if hasattr(row, "_border_line"):
            row._border_line.rectangle = (row.x, row.y, row.width, row.height)
