"""Regression checks for the lower-left navigation rail. Run with project Python."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('KIVY_NO_ARGS', '1')

from kivy.metrics import dp
from kivy.uix.screenmanager import Screen, ScreenManager
from main_layout import PageBar
from utils.appearance import state


class Touch:
    def __init__(self, x, y, uid='pointer', button=None):
        self.x, self.y, self.uid = x, y, uid
        self.button = button
        self.is_mouse_scrolling = button in ('scrollup', 'scrolldown')
        self.grab_current = None

    @property
    def pos(self):
        return self.x, self.y

    def grab(self, widget):
        self.grab_current = widget

    def ungrab(self, widget):
        self.grab_current = None


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.manager = ScreenManager()
        self.names = ['home', 'archive', 'cardio', 'body', 'stats', 'ai']
        for name in self.names:
            self.manager.add_widget(Screen(name=name))
        self.rail = PageBar(self.names, self.manager)
        self.rail.pos = (0, 60)

    def test_tap_does_not_jump(self):
        touch = Touch(self.rail.center_x, self.rail.top - dp(4))
        self.rail.on_touch_down(touch)
        self.rail.on_touch_up(touch)
        self.assertEqual(self.manager.current, 'home')

    def test_relative_drag_no_jump_then_one_step(self):
        touch = Touch(self.rail.center_x, self.rail.top - dp(10))
        self.rail.on_touch_down(touch)
        touch.y += dp(11)
        self.rail.on_touch_move(touch)
        self.assertEqual(self.manager.current, 'home')
        touch.y += (self.rail.height - dp(32)) / 5
        self.rail.on_touch_move(touch)
        self.assertEqual(self.manager.current, 'archive')
        self.rail.on_touch_up(touch)

    def test_drag_clamps_and_interrupts_transition(self):
        touch = Touch(self.rail.center_x, self.rail.center_y)
        self.rail.on_touch_down(touch)
        touch.y += dp(1000)
        self.rail.on_touch_move(touch)
        self.assertEqual(self.manager.current, 'ai')
        touch.y -= dp(2000)
        self.rail.on_touch_move(touch)
        self.assertEqual(self.manager.current, 'home')
        self.rail.on_touch_up(touch)

    def test_wheel_never_grabs_or_leaves_drag_state(self):
        touch = Touch(self.rail.center_x, self.rail.center_y, button='scrollup')
        self.assertTrue(self.rail.on_touch_down(touch))
        self.assertEqual(self.manager.current, 'archive')
        self.assertIsNone(touch.grab_current)
        self.assertIsNone(self.rail._touch_start)

    def test_second_pointer_does_not_hijack_drag(self):
        first = Touch(self.rail.center_x, self.rail.center_y)
        other = Touch(self.rail.center_x, self.rail.center_y, uid='other')
        self.rail.on_touch_down(first)
        self.assertFalse(self.rail.on_touch_down(other))
        other.y += dp(100)
        self.assertFalse(self.rail.on_touch_move(other))
        self.assertEqual(self.manager.current, 'home')
        self.rail.on_touch_up(first)

    def test_both_theme_draw_paths(self):
        original = state.enhanced
        try:
            for enabled in (False, True):
                state.enhanced = enabled
                self.rail._draw()
                self.assertTrue(self.rail.canvas.before.children)
        finally:
            state.enhanced = original


if __name__ == '__main__':
    unittest.main()
