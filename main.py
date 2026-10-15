from kivy.app import App
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
import os

def _try_font(name, filename):
    paths = [
        os.path.join(os.path.dirname(__file__), "assets", "fonts", filename),
        os.path.join(os.path.dirname(__file__), "..", "assets", "fonts", filename),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts", filename),
    ]
    for p in paths:
        if os.path.exists(p):
            LabelBase.register(name=name, fn_regular=p)
            return True
    return False

_try_font("Roboto", "roboto_regular.ttf")
_try_font("Symbols", "symbols.ttf")

import sys, threading, traceback as _tb

def _write_crash(msg: str) -> None:
    for p in (os.path.join(os.path.dirname(__file__), "crash.log"),
              "/data/local/tmp/fitness_crash.log",
              "/sdcard/Android/data/org.fitness.fitnessapp/files/crash.log"):
        try:
            with open(p, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass

def _sys_hook(exc_type, exc_value, exc_tb):
    _write_crash("".join(_tb.format_exception(exc_type, exc_value, exc_tb)))
    sys.__excepthook__(exc_type, exc_value, exc_tb)

def _thread_hook(args):
    _write_crash("THREAD: " + "".join(
        _tb.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))

sys.excepthook = _sys_hook
threading.excepthook = _thread_hook

_CRASH_LOG = os.path.join(os.path.dirname(__file__), "crash.log")
# Android 上项目目录只读，用 SD 卡路径
_CRASH_LOG_ANDROID = "/sdcard/Android/data/org.fitness.fitnessapp/files/crash.log"


def _show_crash_dialog_if_needed():
    """检测旧 crash.log 并清空（不再弹窗干扰启动流程）。"""
    for p in (_CRASH_LOG, _CRASH_LOG_ANDROID):
        try:
            if os.path.isfile(p):
                open(p, "w", encoding="utf-8").close()
        except Exception:
            pass


class FitnessApp(App):
    def build(self):
        Window.clearcolor = (0.07, 0.08, 0.1, 1)
        import traceback, io, sys
        try:
            import theme
            import database as db
            from utils.skin import load_skin
            load_skin()
            from main_layout import MainLayout
            db.init_db()
            root = MainLayout()
            root.init_ui()
            # 延迟弹崩溃报告（等 UI 完全渲染后）
            from kivy.clock import Clock as _Clock
            _Clock.schedule_once(lambda dt: _show_crash_dialog_if_needed(), 1.0)
            return root
        except Exception:
            buf = io.StringIO()
            traceback.print_exc(file=buf)
            msg = buf.getvalue()
            for p in [os.path.join(os.path.dirname(__file__), "crash.log"),
                      "/data/local/tmp/fitness_crash.log",
                      "/sdcard/Android/data/org.fitness.fitnessapp/files/crash.log"]:
                try:
                    with open(p, "w") as f:
                        f.write(msg)
                except:
                    pass
            lbl = Label(text=msg, font_size=14, color=(1,0,0,1), halign="left", valign="top",
                        text_size=(Window.width-20, None), size_hint_y=None)
            lbl.bind(texture_size=lambda *_: setattr(lbl, "height", lbl.texture_size[1]))
            sv = ScrollView(size_hint=(1,1))
            sv.add_widget(lbl)
            return sv

if __name__ == "__main__":
    FitnessApp().run()
