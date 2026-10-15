from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.graphics import Color, Line, Rectangle
from datetime import date

import theme
import database as db
from topbar import TopBar
from calendar_widget import CalendarHeatmap
from panels import ArchivePanel, BodyPanel, StatsPanel
from panels.archive import _CATEGORY_FILTERS
from nuke_button import NukeButton
from nuke_effects import shake_widget, flash_screen, explode_particles
from battle_report import show_battle_report
from plan_popup import PlanPopup
from warmup_widget import WarmupWidget
from task_card import TaskCard
from ai_chat import AIChatPanel
from utils.card import CardHolder
from utils.instrument import StatusLamp
from utils import fx
from utils.appearance import state as appearance
from utils.platform import get_app_version


class PageBar(FloatLayout):
    def __init__(self, names, sm, **kwargs):
        super().__init__(size_hint=(None, None), size=(dp(44), dp(200)), pos_hint={"x": 0, "y": 0.08}, **kwargs)
        self._names = names; self.sm = sm
        self._touch_start = None; self._dragging = False; self._drag_cur = 0
        self._touch_uid = None
        self._wheel_time = 0
        self.bind(pos=self._draw, size=self._draw)
        sm.bind(current=self._on_screen_changed)
        appearance.bind(enhanced=self._draw)

    def _on_screen_changed(self, *_): self._draw()

    def _draw(self, *_):
        self.canvas.before.clear()
        n = len(self._names)
        if n < 2: return
        try: cur = self._names.index(self.sm.current)
        except ValueError: cur = 0
        margin = dp(16); track_w = dp(2); track_h = self.height - margin * 2
        track_x = self.center_x - track_w / 2; track_y = self.y + margin
        segment = track_h / (n - 1)
        with self.canvas.before:
            inset = dp(9 if appearance.enhanced else 7)
            Color(*(theme.DISPLAY_GLASS if appearance.enhanced else theme.METAL_DARK))
            Rectangle(pos=(self.x + inset, self.y), size=(self.width - 2 * inset, self.height))
            Color(*(theme.BORDER_DIM if appearance.enhanced else theme.METAL))
            Line(rectangle=(self.x + inset, self.y, self.width - 2 * inset, self.height), width=dp(0.8))
            Color(*theme.VFD_BLUE_DIM)
            Rectangle(pos=(track_x, track_y), size=(track_w, track_h))
            for index in range(n):
                cy = track_y + index * segment
                active = index == cur
                half_width = dp(5 if appearance.enhanced else 7)
                half_height = dp(2 if appearance.enhanced else 3)
                # Keep every slot explicit: no shared glow helper may alter the
                # canvas color/texture state used by the following slot.
                Color(*(theme.VFD_BLUE if active else theme.VFD_BLUE_DIM))
                Rectangle(pos=(self.center_x - half_width, cy - half_height),
                          size=(half_width * 2, half_height * 2))
                Color(*(theme.VFD_BLUE if active else theme.METAL_DARK))
                Line(points=(self.center_x + dp(9), cy,
                             self.center_x + dp(13), cy), width=dp(1))

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos): return False
        if getattr(touch, 'is_mouse_scrolling', False):
            import time
            now = time.monotonic()
            if now - self._wheel_time >= 0.15:
                current = self._names.index(self.sm.current)
                delta = 1 if touch.button == 'scrollup' else -1
                self._select_index(current + delta)
                self._wheel_time = now
            return True
        if self._touch_uid is not None:
            return False
        self._touch_uid = touch.uid
        self._touch_start = (touch.x, touch.y); self._dragging = False
        try: self._drag_cur = self._names.index(self.sm.current)
        except ValueError: self._drag_cur = 0
        touch.grab(self)
        return True

    def _select_index(self, index):
        if not self._names:
            return
        index = max(0, min(len(self._names) - 1, index))
        current = self._names.index(self.sm.current)
        if index == current:
            return
        # Finish an in-flight slide before starting another selection.
        if self.sm.transition.is_active:
            self.sm.transition.stop()
        self.sm.transition.direction = 'up' if index > current else 'down'
        self.sm.current = self._names[index]

    def on_touch_move(self, touch):
        if touch.uid != self._touch_uid or self._touch_start is None: return False
        dy = abs(touch.y - self._touch_start[1])
        if dy > dp(10): self._dragging = True
        if self._dragging:
            spacing = max(dp(20), (self.height - dp(32)) / max(1, len(self._names) - 1))
            idx = max(0, min(len(self._names) - 1,
                            self._drag_cur + round((touch.y - self._touch_start[1]) / spacing)))
            self._select_index(idx)
        return True

    def on_touch_up(self, touch):
        if touch.uid != self._touch_uid: return False
        touch.ungrab(self)
        # A simple press must not jump to an unrelated absolute rail position.
        self._touch_uid = None
        self._touch_start = None; self._dragging = False
        return True

    def _pos_to_idx(self, y):
        n = len(self._names); margin = dp(16)
        track_h = max(1, self.height - margin * 2); segment = track_h / max(1, n - 1)
        track_y = self.y + margin
        return max(0, min(n - 1, round((y - track_y) / segment)))


class MainLayout(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._chassis_surface = fx.chassis(self)

    def init_ui(self):
        from utils.skin import load_skin
        load_skin()
        self.sm = ScreenManager(transition=SlideTransition(duration=0.18))
        self._screen_order = ["home", "archive", "cardio", "body", "stats", "ai"]

        screens = [
            ("home", "CALENDAR\n日历", self._build_home),
            ("archive", "ARCHIVE\n资料馆", self._build_archive),
            ("cardio", "CARDIO\n有氧运动", self._build_cardio),
            ("body", "BODY DATA\n身体数据", self._build_body),
            ("stats", "STATISTICS\n统计数据", self._build_stats),
            ("ai", "AI ASSISTANT\nAI 助手", self._build_ai),
        ]
        for name, title, builder in screens:
            s = Screen(name=name)
            box = BoxLayout(orientation="vertical")
            box.add_widget(TopBar(title))
            box.add_widget(builder())
            s.add_widget(box)
            self.sm.add_widget(s)

        self.add_widget(self.sm)
        self._page_bar = PageBar(self._screen_order, self.sm)
        self.add_widget(self._page_bar)
        self._boot_overlay = BootOverlay()
        self.add_widget(self._boot_overlay)
        Clock.schedule_once(lambda _dt: self._boot_overlay.finish(), 0.82)
        # 切到资料馆/有氧页时才惰性刷新，避免每次完成训练重建大网格卡顿
        self.sm.bind(current=self._on_screen_changed)

    def _on_screen_changed(self, _sm, name):
        # 延迟到切页动画后刷新，避免占用动画帧
        pending = getattr(self, '_panel_refresh_event', None)
        if pending is not None:
            pending.cancel()
        self._panel_refresh_event = Clock.schedule_once(
            lambda dt, n=name: self._refresh_panel_for(n) if self.sm.current == n else None, 0.25)

    def _refresh_panel_for(self, name):
        if name == "archive" and hasattr(self, "_archive_panel"):
            self._archive_panel._refresh()
        elif name == "cardio" and hasattr(self, "_cardio_panel"):
            self._cardio_panel._refresh()

    def _build_home(self):
        root = BoxLayout(orientation="vertical",
                         padding=[dp(theme.PAGE_MARGIN), dp(theme.PAGE_MARGIN),
                                  dp(theme.PAGE_MARGIN), dp(theme.PAGE_MARGIN)],
                         spacing=dp(theme.CARD_SPACING))

        status = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(8),
                           padding=[dp(7), 0])
        with status.canvas.before:
            Color(*theme.DISPLAY_GLASS)
            self._home_status_bg = Rectangle(pos=status.pos, size=status.size)
            Color(*theme.VFD_BLUE_DIM)
            self._home_status_line = Line(rectangle=(*status.pos, *status.size), width=dp(0.8))
        status.bind(pos=self._redraw_home_status, size=self._redraw_home_status)
        fx.surface(status, 'glass', theme.VFD_BLUE, cut=4)
        status.add_widget(StatusLamp(color=theme.VFD_BLUE, breathe=True,
                                     pos_hint={"center_y": 0.5}))
        status_text = Label(text="[color=33ccff]ONLINE[/color]   /   今日训练控制台",
                            markup=True, color=theme.TEXT_SECONDARY,
                            font_size=dp(theme.FONT_CAPTION), halign="left", valign="middle")
        status_text.bind(size=status_text.setter("text_size"))
        status.add_widget(status_text)
        root.add_widget(status)

        top_row = BoxLayout(orientation="horizontal",
                            size_hint_y=None, height=dp(205),
                            spacing=dp(theme.CARD_SPACING))
        nuke_btn = NukeButton(size_hint=(1, 1))
        nuke_btn.bind(on_release=lambda instance: self._do_nuke(instance))
        nuke_box = BoxLayout(orientation="vertical", spacing=dp(2))
        nuke_box.add_widget(nuke_btn)
        nuke_lbl = Label(text="[color=ff5500][b]PROGRAM DEPLOY[/b][/color]  核弹部署", markup=True,
                         color=theme.TEXT_MUTED,
                         font_size=dp(theme.FONT_CAPTION), bold=True,
                         halign="center", valign="middle",
                         size_hint_y=None, height=dp(28))
        nuke_lbl.bind(size=nuke_lbl.setter("text_size"))
        nuke_box.add_widget(nuke_lbl)
        nuke_holder = CardHolder(nuke_box, padding=7, bg=theme.PANEL, accent=theme.VFD_ORANGE)
        nuke_holder.size_hint_x = 0.32
        top_row.add_widget(nuke_holder)

        self._warmup = WarmupWidget(size_hint=(1, 1),
                                    on_complete=self._on_task_completed)
        warmup_holder = CardHolder(self._warmup, padding=9, bg=theme.PANEL, accent=theme.VFD_ORANGE)
        warmup_holder.size_hint_x = 0.68
        top_row.add_widget(warmup_holder)
        root.add_widget(top_row)

        self._task_card = TaskCard()
        root.add_widget(self._task_card)

        self._heatmap = CalendarHeatmap()
        heatmap_holder = CardHolder(self._heatmap, padding=8, style='glass', accent=theme.VFD_CYAN)
        root.add_widget(heatmap_holder)

        def apply_home_theme(*_):
            status.height = dp(30 if appearance.enhanced else 24)
            status.spacing = dp(8 if appearance.enhanced else 6)
            status_text.text = ("[color=33ccff]ONLINE[/color]   /   今日训练控制台"
                                if appearance.enhanced else
                                "[color=33ccff]SYSTEM ONLINE[/color]   今日训练控制台")
            heatmap_holder._pad = dp(8 if appearance.enhanced else 6)
            heatmap_holder._layout_child()

        appearance.bind(enhanced=apply_home_theme)
        apply_home_theme()
        return root

    def _redraw_home_status(self, widget, *_):
        self._home_status_bg.pos = widget.pos
        self._home_status_bg.size = widget.size
        self._home_status_line.rectangle = (*widget.pos, *widget.size)

    def _build_archive(self):
        self._archive_panel = ArchivePanel(self)
        return self._archive_panel
    def _build_cardio(self):
        self._cardio_panel = ArchivePanel(
            self,
            item_types=["cardio", "warmup", "stretch"],
            filters=_CATEGORY_FILTERS,
            title="CARDIO / 有氧 · 热身 · 拉伸",
        )
        return self._cardio_panel
    def _build_body(self): return BodyPanel(self)
    def _build_stats(self): return StatsPanel()
    def _build_ai(self): return AIChatPanel()

    def _do_nuke(self, btn):
        is_first = not btn.nuked_today
        if is_first:
            db.add_nuke_marker(date.today().isoformat())
            btn.nuked_today = True
        popup = PlanPopup(on_confirm=lambda tid: self._on_plan_confirmed(btn, tid))
        self.add_widget(popup)

    def _on_plan_confirmed(self, btn, template_id=None):
        self._nuke_template_id = template_id
        db.start_today_training_session()
        self.refresh_heatmap(); self._task_card.refresh()
        if hasattr(self, "_warmup"): self._warmup.show_warmups_for(db.get_today_plan())
        shake_widget(self.sm); flash_screen(self)
        win_x, win_y = btn.to_window(*btn.center)
        local_x, local_y = self.to_widget(win_x, win_y)
        explode_particles(self, local_x, local_y)

    def _on_task_completed(self):
        self.refresh_heatmap()
        if hasattr(self, "_task_card"): self._task_card.refresh()
        plan = db.get_today_plan()
        if plan and all(item["completed"] for item in plan):
            Clock.schedule_once(lambda _dt: show_battle_report(self), 0.35)
        # 全部完成 → 把当前训练量同步回模板
        self._sync_to_template_if_all_done()

    def _sync_to_template_if_all_done(self):
        tid = getattr(self, "_nuke_template_id", None)
        if tid is None:
            return
        plan = db.get_today_plan()
        if not plan or not all(p["completed"] for p in plan):
            return
        tmpls = db.get_templates()
        tmpl = next((t for t in tmpls if t["id"] == tid), None)
        if not tmpl:
            self._nuke_template_id = None
            return
        updated_items = []
        for tp_item in tmpl["items"]:
            plan_item = next(
                (p for p in plan
                 if ((p.get("exercise_id") and p.get("exercise_id") == tp_item.get("exercise_id"))
                     or p["exercise_name"] == tp_item.get("name"))
                 and p["item_type"] == tp_item.get("type")), None)
            if plan_item:
                new_item = dict(tp_item)
                if plan_item["item_type"] == "strength":
                    new_item["sets"] = plan_item.get("target_sets") or tp_item.get("sets", 0)
                    new_item["reps"] = plan_item.get("target_reps") or tp_item.get("reps", 0)
                    new_item["weight"] = plan_item.get("target_weight") or tp_item.get("weight", 0)
                    new_item["weight_step"] = int(plan_item.get("target_weight_step") or tp_item.get("weight_step", 0))
                    new_item["rep_step"] = int(plan_item.get("target_rep_step") or tp_item.get("rep_step", 0))
                    new_item["rest_seconds"] = int(
                        plan_item.get("target_rest_seconds") or tp_item.get("rest_seconds", 120))
                else:
                    new_item["distance"] = plan_item.get("target_distance") or tp_item.get("distance", 0)
                    new_item["duration"] = int(plan_item.get("target_duration") or tp_item.get("duration", 0))
                updated_items.append(new_item)
            else:
                updated_items.append(tp_item)
        db.update_template(tid, tmpl["name"], updated_items)
        self._nuke_template_id = None

    def refresh_heatmap(self):
        if hasattr(self, "_heatmap"): self._heatmap.refresh()
        if hasattr(self, "_task_card"): self._task_card.refresh()


class BootOverlay(FloatLayout):
    """Short cold-start hardware check; it never delays real initialization."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.opacity = 1
        with self.canvas.before:
            Color(*theme.CHASSIS)
            self._background = Rectangle(pos=self.pos, size=self.size)
            Color(*theme.METAL)
            self._frame = Line(rectangle=(0, 0, 0, 0), width=dp(1))
        self.bind(pos=self._draw, size=self._draw)
        terminal = BoxLayout(orientation="vertical", size_hint=(0.78, None), height=dp(172),
                             pos_hint={"center_x": 0.5, "center_y": 0.5},
                             padding=[dp(16), dp(12)], spacing=dp(4))
        with terminal.canvas.before:
            Color(*theme.DISPLAY_GLASS)
            self._terminal_bg = Rectangle(pos=terminal.pos, size=terminal.size)
            Color(*theme.VFD_CYAN_DIM)
            self._terminal_line = Line(rectangle=(*terminal.pos, *terminal.size), width=dp(1))
        terminal.bind(pos=self._draw_terminal, size=self._draw_terminal)
        fx.surface(terminal, 'glass', theme.VFD_BLUE, cut=12)
        lines = (
            "[color=33ccff][b]FITNESS CONTROL TERMINAL[/b][/color]\n"
            "[color=666f70]SYSTEM CHECK / 系统自检[/color]\n\n"
            "DATABASE     [color=00ffcc]OK[/color]\n"
            "TRAINING     [color=ff5500]READY[/color]\n"
            "AI LINK      [color=33ccff]STANDBY[/color]\n\n"
            f"[color=666f70]VERSION {get_app_version()}[/color]"
        )
        label = Label(text=lines, markup=True, color=theme.TEXT_PRIMARY,
                      font_size=dp(theme.FONT_LABEL), halign="left", valign="middle")
        label.bind(size=label.setter("text_size"))
        terminal.add_widget(label)
        self.add_widget(terminal)

    def _draw(self, *_):
        self._background.pos = self.pos
        self._background.size = self.size
        self._frame.rectangle = (self.x + dp(8), self.y + dp(8),
                                 max(0, self.width - dp(16)), max(0, self.height - dp(16)))

    def _draw_terminal(self, widget, *_):
        self._terminal_bg.pos = widget.pos
        self._terminal_bg.size = widget.size
        self._terminal_line.rectangle = (*widget.pos, *widget.size)

    def finish(self):
        animation = Animation(opacity=0, duration=0.16)
        animation.bind(on_complete=lambda *_: self.parent and self.parent.remove_widget(self))
        animation.start(self)

    def on_touch_down(self, touch):
        return False

    def on_touch_move(self, touch):
        return False

    def on_touch_up(self, touch):
        return False
