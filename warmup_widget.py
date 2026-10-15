from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle, Line
from config import theme
from config.constants import ENCOURAGEMENTS
import database as db
from exercise_catalog_ui import ExerciseDetailPopup
from utils.instrument import MechanicalButton
from utils import fx


def _hex(c):
    r, g, b = int(c[0] * 255), int(c[1] * 255), int(c[2] * 255)
    return f"{r:02x}{g:02x}{b:02x}"


def _fit_text(label, max_width, max_font=dp(14), min_font=dp(9)):
    """Reduce font size until text fits on one line at max_width."""
    if max_width <= 0:
        return
    label.text_size = (max_width, None)
    font = max_font
    while font >= min_font:
        label.font_size = font
        if label.texture_size[0] <= max_width:
            return
        font -= dp(1)
    label.font_size = min_font


class WarmupWidget(BoxLayout):
    def __init__(self, on_complete=None, **kwargs):
        super().__init__(orientation="vertical",
                         padding=[dp(2), dp(2)], spacing=dp(4), **kwargs)
        self._on_complete = on_complete
        self._current_pid = None

        hdr = BoxLayout(size_hint_y=None, height=dp(30))
        self._title = Label(text="[color=ff5500][size=10sp]CURRENT TARGET[/size][/color]\n[b]当前目标[/b]",
                            markup=True, color=theme.TEXT_PRIMARY,
                            font_size=dp(theme.FONT_H3), bold=True,
                            halign="left", valign="middle", size_hint_x=1)
        self._title.bind(size=self._title.setter("text_size"))
        hdr.add_widget(self._title)
        self._count = Label(text="0/0", color=theme.TEXT_MUTED,
                            font_size=dp(theme.FONT_CAPTION), bold=True,
                            halign="right", valign="middle", size_hint_x=None, width=dp(44))
        self._count.bind(size=self._count.setter("text_size"))
        hdr.add_widget(self._count)
        self.add_widget(hdr)

        self._body = ScrollView(size_hint=(1, 1), do_scroll_x=False, do_scroll_y=True)
        self._body_inner = BoxLayout(orientation="vertical", size_hint_y=None,
                                     spacing=dp(4))
        self._body_inner.bind(minimum_height=self._body_inner.setter("height"))
        self._body.add_widget(self._body_inner)
        self.add_widget(self._body)
        self.refresh()

    def show_warmups_for(self, plan):
        self.refresh()

    def refresh(self):
        self._body_inner.clear_widgets()
        plan = db.get_today_plan()
        if not plan:
            self._title.text = "[color=ff5500][size=10sp]CURRENT TARGET[/size][/color]\n[b]当前目标[/b]"
            self._count.text = "—"
            self._body_inner.add_widget(Label(text="点击核爆按钮部署任务", color=theme.TEXT_MUTED,
                                         font_size=dp(theme.FONT_CAPTION),
                                         halign="center", valign="middle"))
            return
        total = len(plan)
        done = sum(1 for p in plan if p["completed"])
        self._count.text = f"{done}/{total}"
        current = next((p for p in plan if not p["completed"]), None)
        if current is None:
            self._title.text = "[color=00ffcc][size=10sp]MISSION COMPLETE[/size][/color]\n[b]全部完成[/b]"
            from datetime import date
            message = ENCOURAGEMENTS[date.today().toordinal() % len(ENCOURAGEMENTS)]
            notice = Label(
                text=f"[color=ff5d5d][b]RECOVERY NOTICE[/b][/color]\n{message}",
                markup=True, color=theme.TEXT_PRIMARY, font_size=dp(12),
                size_hint_y=None, halign="left", valign="top",
            )
            notice.bind(width=lambda widget, width:
                        setattr(widget, "text_size", (max(0, width), None)))
            notice.bind(texture_size=lambda widget, size:
                        setattr(widget, "height", max(dp(56), size[1] + dp(10))))
            self._body_inner.add_widget(notice)
            return
        self._title.text = "[color=ff5500][size=10sp]CURRENT TARGET[/size][/color]\n[b]当前目标[/b]"
        self._current_pid = current["id"]
        self._body_inner.add_widget(self._make_card(current))

    def _make_card(self, p):
        card = BoxLayout(orientation="vertical", padding=[dp(10), dp(6)], spacing=dp(3),
                         size_hint=(1, None))
        with card.canvas.before:
            Color(*theme.METAL_DARK)
            outer = Rectangle(pos=card.pos, size=card.size)
            Color(*theme.DISPLAY_GLASS)
            glass = Rectangle(pos=card.pos, size=card.size)
            Color(*theme.VFD_ORANGE_DIM)
            border = Line(rectangle=(*card.pos, *card.size), width=dp(1))
            Color(*theme.GLASS_HIGHLIGHT)
            reflection = Rectangle(pos=card.pos, size=(card.width, dp(1)))

        def redraw(*_):
            outer.pos = card.pos
            outer.size = card.size
            glass.pos = (card.x + dp(2), card.y + dp(2))
            glass.size = (max(0, card.width - dp(4)), max(0, card.height - dp(4)))
            border.rectangle = (*card.pos, *card.size)
            reflection.pos = (card.x + dp(5), card.top - dp(5))
            reflection.size = (max(0, card.width - dp(10)), dp(1))
        card.bind(pos=redraw, size=redraw)
        fx.surface(card, 'glass', theme.VFD_ORANGE, cut=5)
        card.bind(minimum_height=card.setter("height"))

        name = p["exercise_name"]
        if p["item_type"] == "strength":
            tag = "力量"
            tag_clr = theme.STRENGTH_ORANGE
        else:
            tag = "有氧"
            tag_clr = theme.CARDIO_BLUE

        tag_row = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(6))
        tag_lbl = Label(text=f"[color={_hex(tag_clr)}][b]{tag}[/b][/color]",
                        markup=True, font_size=dp(theme.FONT_CAPTION),
                        halign="left", valign="middle", size_hint_x=1)
        tag_lbl.bind(size=tag_lbl.setter("text_size"))
        tag_row.add_widget(tag_lbl)
        catalog_exercise = db.find_catalog_exercise(
            p.get("exercise_id"), p.get("exercise_name"))
        if catalog_exercise:
            info_btn = MechanicalButton(text="ACTION GUIDE\n动作要领", kind="system",
                              size_hint=(None, None), size=(dp(84), dp(28)),
                              color=theme.ACCENT_CYAN, font_size=dp(theme.FONT_LABEL))
            info_btn.bind(on_release=lambda _, eid=catalog_exercise["id"]:
                          ExerciseDetailPopup(exercise_id=eid).open())
            tag_row.add_widget(info_btn)
        card.add_widget(tag_row)

        name_lbl = Label(text=name, color=theme.TEXT_PRIMARY,
                         font_size=dp(14), bold=True,
                         halign="left", valign="middle",
                         size_hint_y=None, height=dp(20))
        name_lbl.bind(width=lambda i, w: _fit_text(i, w, max_font=dp(14), min_font=dp(10)))
        card.add_widget(name_lbl)

        pid = p["id"]
        stepper_row = BoxLayout(orientation="horizontal", size_hint_y=None,
                                height=dp(50), spacing=dp(6))
        self._make_main_steppers(stepper_row, p, pid)
        card.add_widget(stepper_row)

        if p["item_type"] == "strength":
            step_row = BoxLayout(orientation="vertical", size_hint_y=None,
                                 height=dp(72), spacing=dp(4))
            step_info = BoxLayout(orientation="horizontal", size_hint_y=None,
                                  height=dp(18), spacing=dp(6))
            step_lbl = Label(text="递增减", color=theme.TEXT_MUTED,
                             font_size=dp(11), size_hint_x=None, width=dp(48),
                             halign="left", valign="middle")
            step_lbl.bind(size=step_lbl.setter("text_size"))
            step_info.add_widget(step_lbl)
            self._step_preview = Label(text="", color=theme.ACCENT_CYAN, font_size=dp(11),
                                        size_hint_x=1, halign="left", valign="middle")
            self._step_preview.bind(size=self._step_preview.setter("text_size"))
            step_info.add_widget(self._step_preview)
            step_row.add_widget(step_info)
            step_controls = BoxLayout(orientation="horizontal", spacing=dp(6),
                                      size_hint_y=None, height=dp(50))
            step_controls.add_widget(self._make_stepper(pid, "target_weight_step",
                                     float(p.get("target_weight_step") or 0), "kg/组", 0.5))
            step_controls.add_widget(self._make_stepper(pid, "target_rep_step",
                                     int(p.get("target_rep_step") or 0), "次/组", 1))
            step_row.add_widget(step_controls)
            card.add_widget(step_row)
            self._update_step_preview(p)

        done_btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                              height=dp(32), spacing=dp(6))
        hard_btn = MechanicalButton(text="太吃力", kind="danger", size_hint_x=1,
                          color=(1, 1, 1, 1), font_size=dp(theme.FONT_CAPTION))
        hard_btn.bind(on_release=lambda _: self._complete_with_difficulty(self._current_pid, "hard"))
        done_btns.add_widget(hard_btn)
        ok_btn = MechanicalButton(text="正好", kind="command", size_hint_x=1,
                                  color=theme.TEXT_PRIMARY, font_size=dp(theme.FONT_CAPTION))
        ok_btn.bind(on_release=lambda _: self._complete_with_difficulty(self._current_pid, "just_right"))
        done_btns.add_widget(ok_btn)
        easy_btn = MechanicalButton(text="很轻松", kind="inset", size_hint_x=1,
                                    glow_color=theme.LED_GREEN,
                                    color=theme.LED_GREEN, font_size=dp(theme.FONT_CAPTION))
        easy_btn.bind(on_release=lambda _: self._complete_with_difficulty(self._current_pid, "easy"))
        done_btns.add_widget(easy_btn)
        card.add_widget(done_btns)
        return card

    def _make_main_steppers(self, row, p, pid):
        if p["item_type"] == "strength":
            row.add_widget(self._make_stepper(pid, "target_sets",
                                     int(p.get("target_sets") or 0), "组", 1))
            row.add_widget(self._make_stepper(pid, "target_reps",
                                     int(p.get("target_reps") or 0), "次", 1))
            row.add_widget(self._make_stepper(pid, "target_weight",
                                      float(p.get("target_weight") or 0), "kg", 0.5))
            row.add_widget(self._make_stepper(pid, "target_rest_seconds",
                                      int(p.get("target_rest_seconds") or 120), "秒休息", 15,
                                      min_value=30, max_value=300))
        else:
            row.add_widget(self._make_stepper(pid, "target_distance",
                                     float(p.get("target_distance") or 0), "km", 0.5))
            row.add_widget(self._make_stepper(pid, "target_duration",
                                     int(p.get("target_duration") or 0), "min", 1))

    def _update_step_preview(self, p):
        if not hasattr(self, "_step_preview"):
            return
        sets = int(p.get("target_sets") or 0)
        reps = int(p.get("target_reps") or 0)
        w = float(p.get("target_weight") or 0)
        ws = float(p.get("target_weight_step") or 0)
        rs = int(p.get("target_rep_step") or 0)
        lbl = getattr(self, "_step_preview", None)
        if lbl is None or sets <= 0:
            return
        per = []
        for s in range(sets):
            gw = w + ws * s
            gr = reps + rs * s
            per.append(f"{int(gw)}/{int(gr)}")
        lbl.text = "  ".join(per)

    def _make_stepper(self, pid, key, value, unit, step=1,
                      min_value=0, max_value=None):
        box = BoxLayout(orientation="vertical", size_hint_x=1, spacing=dp(2))

        def fmt(v):
            if step < 1:
                return f"{v:g} {unit}"
            return f"{int(v)} {unit}"

        def bump(delta):
            new = value + delta * step
            if step < 1:
                new = round(new, 2)
            else:
                new = int(new)
            new = max(min_value, new)
            if max_value is not None:
                new = min(max_value, new)
            db.update_plan_item(pid, **{key: new})
            self.refresh()

        val = Label(text=fmt(value), color=theme.TEXT_PRIMARY, font_size=dp(12), bold=True,
                    halign="center", valign="middle", size_hint_y=None, height=dp(18))
        val.bind(size=val.setter("text_size"))
        keys = BoxLayout(orientation="horizontal", spacing=dp(2),
                         size_hint_y=None, height=dp(28))
        down = MechanicalButton(text="−", kind="inset", color=theme.TEXT_MUTED,
                                font_size=dp(16))
        down.bind(on_release=lambda _: bump(-1))
        up = MechanicalButton(text="+", kind="inset", color=theme.GOLD,
                              font_size=dp(16))
        up.bind(on_release=lambda _: bump(1))
        keys.add_widget(down); keys.add_widget(up)
        box.add_widget(val); box.add_widget(keys)
        return box

    def _complete_with_difficulty(self, pid, level):
        if pid is None:
            return
        plan = db.get_today_plan()
        item = next((p for p in plan if p["id"] == pid), None)
        if item is None or item["completed"]:
            return
        self._write_record(item)
        if item["item_type"] == "strength" and level != "just_right":
            weight = float(item.get("target_weight", 0) or 0)
            reps = int(item.get("target_reps", 0) or 0)
            if level == "hard":
                new_weight = max(0, round(weight - 2.5, 1))
                db.update_plan_item(pid, target_weight=new_weight)
            elif level == "easy":
                if reps >= 12:
                    new_reps = reps
                    new_weight = round(weight + 2.5, 1)
                else:
                    new_reps = reps + 1
                    new_weight = weight
                db.update_plan_item(pid, target_reps=new_reps, target_weight=new_weight)
        db.complete_plan_item(pid)
        db.cancel_rest_timer(pid)
        self.refresh()
        if self._on_complete:
            self._on_complete()

    def _write_record(self, item):
        from datetime import date
        today = date.today().isoformat()
        if item["item_type"] == "strength":
            sets = int(item.get("target_sets") or 0)
            reps = int(item.get("target_reps") or 0)
            weight = float(item.get("target_weight") or 0)
            ws = float(item.get("target_weight_step") or 0)
            rs = int(item.get("target_rep_step") or 0)
            if sets <= 0:
                return
            for s in range(sets):
                db.add_strength(
                    exercise_name=item["exercise_name"],
                    sets=1,
                    reps=reps + rs * s,
                    weight=weight + ws * s,
                    record_date=today,
                    notes="",
                )
        else:
            db.add_cardio(
                exercise_type=item["exercise_name"],
                distance=item.get("target_distance") or 0,
                duration=item.get("target_duration") or 0,
                record_date=today,
                notes="",
            )
