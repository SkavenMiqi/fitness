from datetime import date

from kivy.graphics import Color, Rectangle, Line
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

import database as db
from config import theme
import sounds
from utils import fx
from utils.appearance import state as appearance

_FIELD_COLOR = (0.30, 1.0, 0.55, 1)  # 亮绿，填入的字


class BodyPanel(BoxLayout):
    """Single latest body-data snapshot panel.

    Keeps only one body record: opening the page pre-fills the latest values,
    and saving replaces them. No date navigation, no history list.
    """

    def __init__(self, main_layout, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(8),
                         padding=[dp(theme.PAGE_MARGIN)] * 4, **kwargs)
        self.main_layout = main_layout
        self._input_refs = {}
        with self.canvas.before:
            Color(*theme.CHASSIS)
            self._chassis = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_chassis, size=self._sync_chassis)
        fx.chassis(self)

        # 内容容器：固定高度内容自然堆叠，下面用弹性占位区把表单顶到顶部
        self._content = BoxLayout(orientation="vertical", size_hint_y=None,
                                  spacing=dp(8))
        self._content.bind(minimum_height=self._content.setter("height"))
        self.add_widget(self._content)

        self._build_header()
        self._build_form()
        self._prefill()

        self._placeholder = BoxLayout(size_hint_y=1)
        with self._placeholder.canvas.before:
            Color(*theme.DISPLAY_GLASS)
            self._ph_bg = Rectangle(pos=self._placeholder.pos, size=self._placeholder.size)
            Color(*theme.BORDER_DIM)
            self._ph_border = Line(rectangle=(0, 0, 0, 0), width=dp(1))
        self._placeholder.bind(
            pos=lambda w, _: (setattr(self._ph_bg, "pos", w.pos),
                              setattr(self._ph_border, "rectangle", (*w.pos, w.width, w.height))),
            size=lambda w, _: (setattr(self._ph_bg, "size", w.size),
                               setattr(self._ph_border, "rectangle", (*w.pos, w.width, w.height))))
        fx.surface(self._placeholder, 'glass', theme.VFD_CYAN, cut=12)
        ph_label = Label(text="[color=00ffcc]BIOMETRIC / 身体档案[/color]\n\n"
                              "记录当下，见证每一次改变\n\n"
                              "[color=667577]FITNESS CONTROL SYSTEM[/color]",
                         markup=True,
                         color=theme.TEXT_MUTED, font_size=dp(theme.FONT_CAPTION),
                         halign="center", valign="middle")
        ph_label.bind(size=ph_label.setter("text_size"))
        self._placeholder.add_widget(ph_label)
        enhanced_text = ph_label.text
        def apply_theme(*_):
            ph_label.text = enhanced_text if appearance.enhanced else 'RESERVED / 预留功能区'
        appearance.bind(enhanced=apply_theme)
        apply_theme()
        self.add_widget(self._placeholder)

    def _sync_chassis(self, *_):
        self._chassis.pos = self.pos
        self._chassis.size = self.size

    def _make_input(self, text="", is_float=True):
        inp = TextInput(
            text=text, multiline=False, write_tab=False,
            input_filter="float" if is_float else None,
            font_size=dp(16),
            foreground_color=_FIELD_COLOR,
            background_color=theme.DISPLAY_GLASS,
            background_normal="", background_active="",
            cursor_color=theme.VFD_CYAN,
            hint_text_color=(0.55, 0.57, 0.56, 1),
            padding=(dp(8), dp(8)),
        )
        # Kivy 2.3.1：TextInput 文字 Rectangle 不自带 Color，继承全局 GL 状态
        # 在 MainLayout 中会被污染成灰色。这里在 canvas.before 注入前景色，
        # 让文字绘制使用绿色（_update_graphics 只 clear 主体 canvas，不清 before）。
        with inp.canvas.before:
            Color(*_FIELD_COLOR)
        self._frame_input(inp)
        return inp

    @staticmethod
    def _frame_input(inp):
        # 注意：边框必须画在 canvas.after —— Kivy 2.3.1 中 canvas.before
        # 添加指令会破坏 TextInput 的文字纹理渲染（文字变灰）。
        with inp.canvas.after:
            Color(*theme.BORDER)
            inp._edge = Line(rectangle=(0, 0, 0, 0), width=dp(1))
            Color(*theme.GLASS_HIGHLIGHT)
            inp._glass = Line(points=[], width=dp(1))

        def sync(*_):
            inp._edge.rectangle = (inp.x, inp.y, inp.width, inp.height)
            inp._glass.points = [inp.x + dp(1), inp.top - dp(1),
                                 inp.right - dp(1), inp.top - dp(1)]
        inp.bind(pos=sync, size=sync)

    def _field_row(self, label_text, key, unit=None):
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        lbl = Label(text=label_text, color=theme.TEXT_SECONDARY,
                    font_size=dp(theme.FONT_BODY), halign="left", valign="middle",
                    size_hint_x=None, width=dp(72))
        lbl.bind(size=lbl.setter("text_size"))
        row.add_widget(lbl)
        inp = self._make_input(is_float=True)
        self._input_refs[key] = inp
        row.add_widget(inp)
        if unit:
            u = Label(text=unit, color=theme.TEXT_MUTED,
                      font_size=dp(theme.FONT_CAPTION), halign="left", valign="middle",
                      size_hint_x=None, width=dp(34))
            u.bind(size=u.setter("text_size"))
            row.add_widget(u)
        return row

    def _build_header(self):
        header = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(8))
        title = Label(text="[color=ff9d24][b]BODY DATA[/b][/color]  身体数据",
                      markup=True, color=theme.TEXT_PRIMARY,
                      font_size=dp(theme.FONT_H3), bold=True,
                      halign="left", valign="middle", size_hint_x=1)
        title.bind(size=title.setter("text_size"))
        header.add_widget(title)
        self._saved = Label(text="", color=theme.LED_GREEN,
                            font_size=dp(theme.FONT_CAPTION), bold=True,
                            halign="right", valign="middle", size_hint_x=None, width=dp(90))
        self._saved.bind(size=self._saved.setter("text_size"))
        header.add_widget(self._saved)
        self._content.add_widget(header)

    def _build_form(self):
        grid = GridLayout(cols=2, size_hint_y=None, spacing=(dp(8), dp(6)))
        grid.bind(minimum_height=grid.setter("height"))
        grid.add_widget(self._field_row("体重", "weight", "kg"))
        grid.add_widget(self._field_row("体脂率", "body_fat", "%"))
        grid.add_widget(self._field_row("胸围", "chest", "cm"))
        grid.add_widget(self._field_row("腰围", "waist", "cm"))
        grid.add_widget(self._field_row("臂围", "arm", "cm"))
        self._content.add_widget(grid)

        notes = self._make_input(is_float=False)
        self._input_refs["notes"] = notes
        notes_box = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        n_lbl = Label(text="备注", color=theme.TEXT_SECONDARY,
                      font_size=dp(theme.FONT_BODY), halign="left", valign="middle",
                      size_hint_x=None, width=dp(72))
        n_lbl.bind(size=n_lbl.setter("text_size"))
        notes_box.add_widget(n_lbl)
        notes_box.add_widget(notes)
        self._content.add_widget(notes_box)

        save_btn = Button(text="SAVE / 保存", size_hint_y=None, height=dp(44),
                          background_normal="", background_color=theme.VFD_ORANGE,
                          color=theme.CHASSIS, font_size=dp(theme.FONT_H3), bold=True)
        save_btn.bind(on_release=lambda _: self._save())
        sounds.bind_feedback(save_btn, bg_color=theme.VFD_ORANGE)
        self._content.add_widget(save_btn)

        hint = Label(text="身体数据只保留最新一次，保存后覆盖更新",
                     color=theme.TEXT_MUTED, font_size=dp(theme.FONT_CAPTION),
                     size_hint_y=None, height=dp(18), halign="center", valign="middle")
        hint.bind(size=hint.setter("text_size"))
        self._content.add_widget(hint)

    def _prefill(self):
        latest = db.get_latest_body()
        if not latest:
            return
        for key in ("weight", "body_fat", "chest", "waist", "arm"):
            val = latest.get(key)
            if val:
                self._input_refs[key].text = self._fmt(val, key)
        self._input_refs["notes"].text = latest.get("notes") or ""
        self._saved.text = f"已存 {latest.get('record_date', '')}"

    @staticmethod
    def _fmt(value, key):
        num = float(value)
        if num == int(num):
            return str(int(num))
        return str(num)

    def _save(self):
        try:
            db.set_latest_body(
                weight=self._to_float("weight"),
                body_fat=self._to_float("body_fat"),
                chest=self._to_float("chest"),
                waist=self._to_float("waist"),
                arm=self._to_float("arm"),
                notes=self._input_refs["notes"].text.strip(),
            )
            from datetime import date as _d
            self._saved.text = f"已存 {_d.today().isoformat()}"
            self.main_layout.refresh_heatmap()
        except (ValueError, Exception) as e:
            self._show_error(str(e))

    def _to_float(self, key):
        text = self._input_refs[key].text.strip()
        return float(text) if text else None

    def _show_error(self, msg):
        from kivy.uix.popup import Popup
        popup = Popup(title="错误", title_color=theme.TEXT_PRIMARY,
                      content=Label(text=msg, color=theme.TEXT_PRIMARY),
                      size_hint=(0.6, 0.25), background_color=theme.PANEL)
        popup.open()
