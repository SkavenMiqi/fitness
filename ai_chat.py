"""AI 聊天面板：消息气泡 + 输入框 + 图片选择，后台线程调用 LLM，回主线程刷新。"""

import base64
import json
import os
import time as _time
import threading
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image
from kivy.uix.modalview import ModalView
from kivy.uix.filechooser import FileChooserListView
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, RoundedRectangle
from config import theme
from llm_config import LLMConfig
import llm_client
import database as db
from ai_settings import AISettingsPopup
import sounds

try:
    from android import activity as _android_activity  # noqa: E402
    from jnius import autoclass  # noqa: E402
    _Intent = autoclass("android.content.Intent")
    _PythonActivity = autoclass("org.kivy.android.PythonActivity")
    _File = autoclass("java.io.File")
    _MediaRecorder = autoclass("android.media.MediaRecorder")
    _AudioSource = autoclass("android.media.MediaRecorder$AudioSource")
    _OutputFormat = autoclass("android.media.MediaRecorder$OutputFormat")
    _AudioEncoder = autoclass("android.media.MediaRecorder$AudioEncoder")
    _AudioRecord = autoclass("android.media.AudioRecord")
    _AudioFormat = autoclass("android.media.AudioFormat")
    _JArray = autoclass("java.lang.reflect.Array")
    _JByte = autoclass("java.lang.Byte")
    _JFOS = autoclass("java.io.FileOutputStream")
    _ANDROID_VOICE = True
except Exception:
    _ANDROID_VOICE = False

_IMG_FILTERS = ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif"]
_MAX_IMG_BYTES = 4 * 1024 * 1024  # 4MB 上限，避免 base64 爆炸

# AI 可调用的工具（function calling）：让 AI 能改计划/查数据
AI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_today_plan",
            "description": "列出今日训练计划所有项目及完成状态",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_plan_item",
            "description": "向今日训练计划添加一个项目（动作）。用 search_catalog 查到的动作会自动关联 GIF 指导。添加后自动注册到力量/有氧面板的预设列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_type": {"type": "string", "enum": ["strength", "cardio"]},
                    "exercise_name": {"type": "string", "description": "动作名，如 卧推/跑步"},
                    "sets": {"type": "integer"},
                    "reps": {"type": "integer"},
                    "weight": {"type": "number"},
                    "weight_step": {"type": "number"},
                    "rep_step": {"type": "integer"},
                    "distance": {"type": "number"},
                    "duration": {"type": "integer"},
                },
                "required": ["item_type", "exercise_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_plan_item",
            "description": "修改今日计划中某个项目的目标值",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "integer"},
                    "sets": {"type": "integer"},
                    "reps": {"type": "integer"},
                    "weight": {"type": "number"},
                    "weight_step": {"type": "number"},
                    "rep_step": {"type": "integer"},
                    "distance": {"type": "number"},
                    "duration": {"type": "integer"},
                },
                "required": ["plan_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_plan_item",
            "description": "删除今日计划中的某个项目",
            "parameters": {
                "type": "object",
                "properties": {"plan_id": {"type": "integer"}},
                "required": ["plan_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_plan_item",
            "description": "把今日计划中某个项目标记为已完成",
            "parameters": {
                "type": "object",
                "properties": {"plan_id": {"type": "integer"}},
                "required": ["plan_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_calories",
            "description": "查询今日热量收支：摄入、TDEE、运动消耗、赤字/盈余、体重",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_user_weight",
            "description": "记录今日体重(kg)",
            "parameters": {
                "type": "object",
                "properties": {"weight": {"type": "number"}},
                "required": ["weight"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_deficit_goal",
            "description": "设置每日热量目标赤字(kcal)。正值=减脂赤字(如500表示每日摄入比消耗少500kcal)；负值=增肌盈余(如-300表示每日摄入比消耗多300kcal)；0=维持。",
            "parameters": {
                "type": "object",
                "properties": {"deficit_goal": {"type": "integer", "description": "目标赤字kcal，正数减脂/负数增肌/0维持"}},
                "required": ["deficit_goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_templates",
            "description": "列出所有训练模板（核弹模板）及其包含的项目",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_template_items",
            "description": "修改某个训练模板的项目（整体替换该模板的动作列表）",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {"type": "integer"},
                    "items": {
                        "type": "array",
                        "description": "新项目列表，会整体替换原列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["strength", "cardio"]},
                                "name": {"type": "string"},
                                "sets": {"type": "integer"},
                                "reps": {"type": "integer"},
                                "weight": {"type": "number"},
                                "weight_step": {"type": "number"},
                                "rep_step": {"type": "integer"},
                                "distance": {"type": "number"},
                                "duration": {"type": "integer"},
                            },
                            "required": ["type", "name"],
                        },
                    },
                },
                "required": ["template_id", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_template",
            "description": "新建一个训练模板",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "模板名，如 胸日/拉A"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["strength", "cardio"]},
                                "name": {"type": "string"},
                                "sets": {"type": "integer"},
                                "reps": {"type": "integer"},
                                "weight": {"type": "number"},
                                "weight_step": {"type": "number"},
                                "rep_step": {"type": "integer"},
                                "distance": {"type": "number"},
                                "duration": {"type": "integer"},
                            },
                            "required": ["type", "name"],
                        },
                    },
                },
                "required": ["name", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_template",
            "description": "删除一个训练模板",
            "parameters": {
                "type": "object",
                "properties": {"template_id": {"type": "integer"}},
                "required": ["template_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_today_meals",
            "description": "列出今日饮食记录（含每条 ID，用于后续删除）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_meal",
            "description": "删除某条饮食记录（通过 list_today_meals 获取 id）",
            "parameters": {
                "type": "object",
                "properties": {"meal_id": {"type": "integer"}},
                "required": ["meal_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_today_meals",
            "description": "清空今日全部饮食记录（用户说「今天的记录全删了」时调用）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_meal",
            "description": "向今日饮食记录添加一餐。当用户口诉/打字说了吃了什么时，你分析食物种类和数量并估算热量后，调用此工具保存。示例：用户说「早餐吃了两个鸡蛋一碗粥」→ meal_type=早餐, food_summary=鸡蛋2个/粥1碗, total_kcal≈230",
            "parameters": {
                "type": "object",
                "properties": {
                    "meal_type": {"type": "string", "enum": ["早餐", "午餐", "晚餐", "加餐"]},
                    "food_summary": {"type": "string", "description": "食物摘要，如 鸡蛋2个140kcal/牛奶1杯90kcal"},
                    "total_kcal": {"type": "number", "description": "该餐总热量千卡"},
                    "items_json": {"type": "string", "description": "可选，JSON数组字符串：各食物明细"},
                },
                "required": ["meal_type", "food_summary", "total_kcal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_date_overview",
            "description": "查询任意日期的完整汇总：饮食(餐别/食物/热量)、力量训练、有氧训练、训练计划、身体数据(体重/体脂/围度)、摄入总热量、训练消耗热量、匹配模板。日期格式 YYYY-MM-DD。示例：问「昨天吃了什么」→ 计算昨天日期后调用此工具；问「7月14日的训练记录」→ 用 2026-07-14 调用",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "日期，格式 YYYY-MM-DD，如 2026-07-14"},
                },
                "required": ["date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": "搜索动作资料库（已有 GIF 动画和指导步骤的动作）。返回匹配的动作名、部位、器械、是否含动画帧。当用户说「加一个练胸的动作」「有没有深蹲的教学」时，先搜此库再建议。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词，支持中英文动作名/器械/肌群"},
                    "body_part": {"type": "string", "description": "部位过滤，如 chest/back/upper legs/shoulders/upper arms/waist"},
                },
                "required": ["query"],
            },
        },
    },
]


def _detect_image_mime(path: str) -> str:
    with open(path, "rb") as f:
        head = f.read(16)
    if len(head) < 4:
        return "unknown"
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if head[:4] == b"\x89PNG":
        return "png"
    if head[:3] == b"GIF":
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:2] == b"BM":
        return "bmp"
    if head[4:8] == b"ftyp":
        return "heic"
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return {"jpg": "jpeg", "jpeg": "jpeg", "png": "png",
            "webp": "webp", "gif": "gif", "bmp": "bmp"}.get(ext, "unknown")


def _detect_audio_mime(path: str) -> str:
    with open(path, "rb") as f:
        head = f.read(12)
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"RIFF":
        return "wav"
    if head[:3] == b"ID3" or (head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
        return "mp3"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand[:3] == b"3gp" or brand == b"3g2a":
            return "3gpp"
        return "m4a"
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return {"m4a": "m4a", "mp4": "m4a", "mp3": "mp3",
            "wav": "wav", "ogg": "ogg", "flac": "flac"}.get(ext, "m4a")


def _ensure_jpeg_android(path: str) -> str:
    """Use Android BitmapFactory to re-encode as JPEG (solves HEIC/WebP issues).

    Raises RuntimeError on decode failure so the caller surfaces a clear error
    instead of silently sending an unsupported format to the API.

    注意：pyjnius 不能用 `Bitmap.CompressFormat` 这种 OuterClass.NestedClass
    访问嵌套类，必须 `autoclass("...$NestedClass")` 字符串形式加载。
    """
    try:
        from jnius import autoclass
        BitmapFactory = autoclass("android.graphics.BitmapFactory")
        BitmapCompressFormat = autoclass("android.graphics.Bitmap$CompressFormat")
        ByteArrayOutputStream = autoclass("java.io.ByteArrayOutputStream")
        File = autoclass("java.io.File")
        FileOutputStream = autoclass("java.io.FileOutputStream")
        bm = BitmapFactory.decodeFile(path)
        if bm is None:
            _plog(f"_ensure_jpeg: BitmapFactory.decodeFile returned None for {path}")
            raise RuntimeError("无法解码此图片，请选 JPG/PNG/WebP 格式")
        baos = ByteArrayOutputStream()
        ok = bm.compress(BitmapCompressFormat.JPEG, 85, baos)
        bm.recycle()
        if not ok:
            raise RuntimeError("图片转码失败，请换一张图")
        cache_dir = _PythonActivity.mActivity.getCacheDir()
        out = File(cache_dir, "ai_pick_converted.jpg")
        fos = FileOutputStream(out)
        fos.write(baos.toByteArray())
        fos.close()
        result = out.getAbsolutePath()
        with open(result, "rb") as _f:
            _head = _f.read(3)
        if _head[:3] != b"\xff\xd8\xff":
            _plog(f"_ensure_jpeg: output not JPEG, head={_head.hex()}")
            raise RuntimeError("转码后仍非 JPEG，请换一张图")
        _plog(f"_ensure_jpeg: converted -> {result} ({baos.size()} bytes)")
        return result
    except RuntimeError:
        raise
    except Exception as e:
        _plog(f"_ensure_jpeg error: {e}")
        raise RuntimeError(f"图片转码异常：{e}") from e

def _image_data_url(path: str) -> str:
    mime = _detect_image_mime(path)
    with open(path, "rb") as f:
        raw = f.read()
    _plog(f"_image_data_url: path={path} mime={mime} size={len(raw)} head={raw[:16].hex()}")
    b64 = base64.b64encode(raw).decode()
    return f"data:image/{mime};base64,{b64}"


def _fix_m4a_brand(path: str) -> None:
    """Patch ftyp major brand to 'M4A ' so MiMo recognises the file as m4a.

    Android MediaRecorder (MPEG_4/AAC) emits brand 'isom'/'mp42', which MiMo's
    detector rejects with 'invalid audio format'. 'M4A ' is the only brand MiMo
    accepts for m4a. In-place 4-byte rewrite at offset 8; file size unchanged.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(32)
        if len(head) >= 12 and head[4:8] == b"ftyp":
            old = head[8:12]
            with open(path, "r+b") as f:
                f.seek(8)
                f.write(b"M4A ")
            _plog(f"_fix_m4a_brand: patched {old!r} -> b'M4A '")
        else:
            _plog(f"_fix_m4a_brand: no ftyp box, head={head[:16].hex()}")
    except Exception as e:
        _plog(f"_fix_m4a_brand error: {e}")


def _mi_mo_multimodal_ok(model: str, base_url: str) -> bool:
    """检查当前模型是否支持多模态（图片/音频）。"""
    if "xiaomimimo" not in base_url.lower():
        return True  # 非 MiMo 默认放行
    return model in ("mimo-v2.5",)


def _audio_data_url(path: str) -> str:
    mime = _detect_audio_mime(path)
    with open(path, "rb") as f:
        raw = f.read()
    _plog(f"_audio_data_url: path={path} mime={mime} size={len(raw)} head={raw[:16].hex()}")
    b64 = base64.b64encode(raw).decode()
    return f"data:audio/{mime};base64,{b64}"


_TOOL_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_tool.log")


def _tlog(msg: str) -> None:
    try:
        with open(_TOOL_LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


_ERR_LOG: list[str] = []
_ERR_LOG_MAX = 50


def _push_err(tag: str, text: str) -> None:
    """保存完整错误文本到内存缓冲，供「错误日志」弹窗查看（界面只显示截断版）。"""
    line = f"[{_time.strftime('%H:%M:%S')}] {tag}: {text}"
    _ERR_LOG.append(line)
    if len(_ERR_LOG) > _ERR_LOG_MAX:
        del _ERR_LOG[: len(_ERR_LOG) - _ERR_LOG_MAX]
    _tlog(line)


def _read_log_files() -> str:
    """尝试读取 ai_pick.log / ai_tool.log 全文（多个候选路径）。"""
    out: list[str] = []
    candidates: list[str] = [_TOOL_LOG, "/sdcard/Download/ai_pick.log"]
    if _ANDROID_VOICE:
        try:
            candidates.append(
                _PythonActivity.mActivity.getFilesDir().getAbsolutePath() + "/ai_pick.log")
        except Exception:
            pass
    for p in candidates:
        try:
            with open(p, "r", encoding="utf-8") as f:
                out.append(f"===== {p} =====")
                out.append(f.read())
        except Exception:
            pass
    return "\n".join(out) if out else ""


def _plog(msg: str) -> None:
    """写 Android 可见日志（app 私有 + /sdcard/Download）+ 本地 ai_tool.log。"""
    paths = [_TOOL_LOG, "/sdcard/Download/ai_pick.log"]
    if _ANDROID_VOICE:
        try:
            paths.append(
                _PythonActivity.mActivity.getFilesDir().getAbsolutePath()
                + "/ai_pick.log")
        except Exception:
            pass
    for p in paths:
        try:
            with open(p, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass


class _LogPopup(ModalView):
    """错误日志弹窗：显示内存错误缓冲 + 日志文件，可复制到剪贴板。"""

    def __init__(self, **kwargs):
        super().__init__(size_hint=(0.96, 0.92), **kwargs)
        self.background = ""
        self.background_color = (0, 0, 0, 0.7)
        self._build_ui()

    def _build_ui(self):
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10))
        title = Label(text="[b]ERROR LOG / 错误日志[/b]  长按可选中复制", markup=True,
                      color=theme.LED_RED, font_size=dp(12), size_hint_y=None,
                      height=dp(28))
        box.add_widget(title)
        self._ti = TextInput(
            text=self._gather(), readonly=True, multiline=True,
            size_hint_y=1, font_size=dp(10),
            background_color=theme.DISPLAY_GLASS, foreground_color=theme.TEXT_PRIMARY)
        box.add_widget(self._ti)
        btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=dp(44), spacing=dp(8))
        copy = Button(text="复制全部", background_normal="",
                      background_color=theme.VFD_CYAN,
                      color=(0.04, 0.06, 0.1, 1), font_size=dp(12))
        copy.bind(on_release=lambda _: self._copy())
        refresh = Button(text="刷新", background_normal="",
                        background_color=theme.PANEL_RAISED,
                        color=theme.TEXT_PRIMARY, font_size=dp(12))
        refresh.bind(on_release=lambda _: self._refresh())
        close = Button(text="关闭", background_normal="",
                       background_color=theme.PANEL_RAISED,
                       color=theme.LED_RED, font_size=dp(12))
        close.bind(on_release=lambda _: self.dismiss())
        btns.add_widget(copy)
        btns.add_widget(refresh)
        btns.add_widget(close)
        box.add_widget(btns)
        self.add_widget(box)

    @staticmethod
    def _gather() -> str:
        parts: list[str] = []
        if _ERR_LOG:
            parts.append("===== 内存错误缓冲 =====")
            parts.append("\n".join(_ERR_LOG))
        files = _read_log_files()
        if files:
            parts.append(files)
        return "\n\n".join(parts) if parts else "（暂无日志）"

    def _refresh(self):
        self._ti.text = self._gather()

    def _copy(self):
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(self._ti.text)
            self._ti.text = "[已复制到剪贴板，可粘贴发给我]\n\n" + self._ti.text
        except Exception as e:
            self._ti.text = f"复制失败：{e}\n" + self._ti.text


class _DeficitGoalPopup(ModalView):
    """热量目标赤字编辑弹窗：正值=减脂赤字，负值=增肌盈余，0=维持。"""

    def __init__(self, current=500, on_saved=None, **kwargs):
        super().__init__(size_hint=(0.8, 0.5), **kwargs)
        self.background = ""
        self.background_color = (0, 0, 0, 0.7)
        self._on_saved = on_saved
        self._build_ui(current)

    def _build_ui(self, current):
        box = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(16))
        box.add_widget(Label(
            text="[b]ENERGY TARGET / 热量目标赤字[/b]", markup=True,
            color=theme.VFD_ORANGE, font_size=dp(13), size_hint_y=None,
            height=dp(26)))
        box.add_widget(Label(
            text="正值=减脂赤字(如500)\n负值=增肌盈余(如-300)\n0=维持",
            color=theme.TEXT_MUTED, font_size=dp(10), size_hint_y=None,
            height=dp(44), halign="left", valign="top"))
        center = BoxLayout(orientation="horizontal", size_hint_y=None,
                           height=dp(54), spacing=dp(8))
        for v, txt, col in [(-300, "增肌+300", theme.VFD_ORANGE),
                            (0, "维持", theme.VFD_CYAN),
                            (500, "减脂-500", theme.VFD_CYAN)]:
            b = Button(text=txt, font_size=dp(11), background_normal="",
                       background_color=col, color=(0.04, 0.06, 0.1, 1),
                       size_hint_x=1)
            b.bind(on_release=lambda _, vv=v: self._set_val(vv))
            center.add_widget(b)
        box.add_widget(center)
        self._ti = TextInput(text=str(current), font_size=dp(16),
                              foreground_color=theme.TEXT_PRIMARY,
                              background_normal="",
                               background_color=theme.DISPLAY_GLASS,
                               cursor_color=theme.VFD_CYAN,
                              padding=[dp(8), dp(8)], size_hint_y=None,
                              height=dp(44), input_filter="int")
        box.add_widget(self._ti)
        btns = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=dp(44), spacing=dp(8))
        ok = Button(text="保存", background_normal="",
                    background_color=theme.VFD_ORANGE,
                    color=(0.05, 0.05, 0.08, 1), font_size=dp(13))
        ok.bind(on_release=lambda _: self._save())
        cancel = Button(text="取消", background_normal="",
                        background_color=theme.PANEL_RAISED,
                        color=theme.TEXT_MUTED, font_size=dp(13))
        cancel.bind(on_release=lambda _: self.dismiss())
        btns.add_widget(ok)
        btns.add_widget(cancel)
        box.add_widget(btns)
        self.add_widget(box)

    def _set_val(self, v):
        self._ti.text = str(v)

    def _save(self):
        try:
            dg = int(self._ti.text.strip() or "0")
        except ValueError:
            return
        db.set_profile(deficit_goal=dg)
        cb = self._on_saved
        self.dismiss()
        if cb:
            cb()


class _MealTypePopup(ModalView):
    """餐别选择弹窗：先选早/午/晚/加餐，再打开相册传图。"""

    MEALS = ["早餐", "午餐", "晚餐", "加餐"]

    def __init__(self, on_select, **kwargs):
        super().__init__(size_hint=(0.85, 0.45), **kwargs)
        self.background = ""
        self.background_color = (0, 0, 0, 0.7)
        self._on_select = on_select
        self._build_ui()

    def _build_ui(self):
        box = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(16))
        box.add_widget(Label(
            text="[b]MEAL INPUT / 选择餐别[/b]", markup=True,
            color=theme.VFD_CYAN, font_size=dp(13), size_hint_y=None,
            height=dp(26)))
        grid = BoxLayout(orientation="horizontal", spacing=dp(8),
                         size_hint_y=None, height=dp(48))
        for m in self.MEALS:
            b = Button(text=m, font_size=dp(13), background_normal="",
                       background_color=theme.VFD_CYAN,
                       color=(0.04, 0.06, 0.1, 1))
            b.bind(on_release=lambda _, mm=m: self._pick(mm))
            grid.add_widget(b)
        box.add_widget(grid)
        cancel = Button(text="取消", font_size=dp(12), background_normal="",
                         background_color=theme.PANEL_RAISED,
                        color=theme.TEXT_MUTED, size_hint_y=None, height=dp(38))
        cancel.bind(on_release=lambda _: self.dismiss())
        box.add_widget(cancel)
        self.add_widget(box)

    def _pick(self, meal_type):
        self.dismiss()
        cb = self._on_select
        if cb:
            cb(meal_type)


class _MealsDetailPopup(ModalView):
    """今日摄入明细弹窗：列出每餐及热量，底部可删。"""

    def __init__(self, **kwargs):
        super().__init__(size_hint=(0.92, 0.8), **kwargs)
        self.background = ""
        self.background_color = (0, 0, 0, 0.7)
        self._build_ui()

    def _build_ui(self):
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(14))
        box.add_widget(Label(
            text="[b]INTAKE LOG / 今日饮食摄入[/b]", markup=True,
            color=theme.VFD_ORANGE, font_size=dp(13), size_hint_y=None, height=dp(26)))
        scroll = ScrollView(do_scroll_x=False)
        inner = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        inner.bind(minimum_height=inner.setter("height"))
        scroll.add_widget(inner)
        self._inner = inner
        box.add_widget(scroll)
        total_lbl = Label(text="", markup=True, color=theme.TEXT_PRIMARY,
                          font_size=dp(13), size_hint_y=None, height=dp(22),
                          halign="left")
        total_lbl.bind(size=total_lbl.setter("text_size"))
        self._total_lbl = total_lbl
        box.add_widget(total_lbl)
        close = Button(text="关闭", font_size=dp(13), background_normal="",
                       background_color=theme.PANEL_RAISED, color=theme.TEXT_MUTED,
                       size_hint_y=None, height=dp(40))
        close.bind(on_release=lambda _: self.dismiss())
        box.add_widget(close)
        self.add_widget(box)
        self._refresh()

    def _refresh(self):
        self._inner.clear_widgets()
        try:
            meals = db.get_today_meals()
        except Exception:
            meals = []
        total = 0
        for m in meals:
            total += int(m.get("calories", 0))
            row = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=dp(42), spacing=dp(6))
            info = Label(
                text=f"[b]{m.get('meal_type','')}[/b]  {int(m.get('calories',0))}kcal\n"
                     f"{(m.get('food_summary') or '')[:40]}",
                markup=True, color=theme.TEXT_PRIMARY, font_size=dp(10),
                halign="left", valign="middle", size_hint_x=1)
            info.bind(size=info.setter("text_size"))
            row.add_widget(info)
            mid = m.get("id")
            if mid is not None:
                del_btn = Button(text="✕", font_size=dp(12), size_hint_x=None,
                                 width=dp(34), background_normal="",
                                 background_color=(0, 0, 0, 0), color=theme.DANGER)
                del_btn.bind(on_release=lambda _, i=mid: self._del(i))
                row.add_widget(del_btn)
            self._inner.add_widget(row)
        if not meals:
            self._inner.add_widget(Label(
                text="（今日还没记录饮食）", color=theme.TEXT_MUTED,
                font_size=dp(11), size_hint_y=None, height=dp(30)))
        self._total_lbl.text = f"[b]合计：{total} kcal[/b]"

    def _del(self, meal_id):
        try:
            db.delete_meal(meal_id)
        except Exception:
            pass
        self._refresh()


class _ImagePicker(ModalView):
    def __init__(self, on_select, **kwargs):
        super().__init__(size_hint=(0.92, 0.9), **kwargs)
        self._on_select = on_select
        self.background = ""
        self.background_color = (0, 0, 0, 0.6)
        self._build_ui()

    @staticmethod
    def _default_image_dir() -> str:
        # 桌面测试优先用项目内 test_images；否则回退用户主目录
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_images")
        if os.path.isdir(d):
            return d
        return os.path.expanduser("~")

    def _build_ui(self):
        box = BoxLayout(orientation="vertical", padding=[dp(10), dp(10)],
                        spacing=dp(8), size_hint=(0.98, 0.98),
                        pos_hint={"center_x": 0.5, "center_y": 0.5})
        with box.canvas.before:
            Color(*theme.CHASSIS)
            picker_bg = RoundedRectangle(pos=box.pos, size=box.size,
                                         radius=[dp(theme.CARD_RADIUS)])
        box.bind(pos=lambda _, p: setattr(picker_bg, "pos", p),
                 size=lambda _, s: setattr(picker_bg, "size", s))

        hdr = BoxLayout(size_hint_y=None, height=dp(28))
        hdr.add_widget(Label(text="[b]IMAGE INPUT / 选择图片[/b]", markup=True,
                             color=theme.VFD_CYAN, font_size=dp(13)))
        close = Button(text="✕", size_hint_x=None, width=dp(32),
                       background_normal="", background_color=(0, 0, 0, 0),
                       color=theme.TEXT_MUTED, font_size=dp(15))
        close.bind(on_release=lambda _: self.dismiss())
        hdr.add_widget(close)
        box.add_widget(hdr)

        self._fc = FileChooserListView(filters=_IMG_FILTERS,
                                       rootpath=self._default_image_dir(),
                                       multiselect=False, size_hint=(1, 1))
        box.add_widget(self._fc)

        btns = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        cancel = Button(text="取消", background_normal="",
                         background_color=theme.PANEL_RAISED,
                        color=theme.TEXT_PRIMARY, font_size=dp(14))
        cancel.bind(on_release=lambda _: self.dismiss())
        ok = Button(text="确定", background_normal="",
                    background_color=theme.VFD_CYAN,
                    color=(0.05, 0.05, 0.08, 1), font_size=dp(14))
        ok.bind(on_release=lambda _: self._confirm())
        btns.add_widget(cancel)
        btns.add_widget(ok)
        box.add_widget(btns)
        self.add_widget(box)

    def _confirm(self):
        sel = self._fc.selection
        if sel:
            self._on_select(sel[0])
        self.dismiss()


class AIChatPanel(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._cfg = LLMConfig.load()
        self._client = None
        self._messages = []
        self._busy = False
        self._meal_busy = False
        self._plan_changed = False
        self._pending_image = None
        self._build_ui()
        self._rebuild_messages()

    def _build_ui(self):
        from utils import fx
        root = BoxLayout(orientation="vertical")
        with root.canvas.before:
            Color(*theme.CHASSIS)
            self._root_bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=lambda _, p: setattr(self._root_bg, "pos", p),
                  size=lambda _, s: setattr(self._root_bg, "size", s))
        fx.chassis(root)
        root.add_widget(self._build_topbar())
        root.add_widget(self._build_calorie_bar())

        shortcuts = BoxLayout(size_hint_y=None, height=dp(40),
                              spacing=dp(6), padding=[dp(12), dp(4)])
        for caption, prompt in (
                ('今日分析', '请分析我今天的训练和热量收支，给出建议。'),
                ('训练建议', '请根据我的近期训练记录，给出下一次训练建议。'),
                ('饮食记录', '我想记录一餐饮食，请引导我提供食物和份量。')):
            button = Button(text=caption, font_size=dp(12), background_normal='',
                            background_color=theme.PANEL_RAISED, color=theme.VFD_BLUE)
            button.bind(on_release=lambda _, text=prompt: self._fill_prompt(text))
            shortcuts.add_widget(button)
        root.add_widget(shortcuts)

        self._msg_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                  spacing=dp(8), padding=[dp(12), dp(8)])
        self._msg_box.bind(minimum_height=self._msg_box.setter("height"))
        self._scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        self._scroll.add_widget(self._msg_box)
        root.add_widget(self._scroll)

        # 图片预览条（无图时高度 0 隐藏）
        self._preview_bar = BoxLayout(orientation="horizontal",
                                      size_hint_y=None, height=0,
                                      spacing=dp(8), padding=[dp(12), dp(4)])
        root.add_widget(self._preview_bar)

        root.add_widget(self._build_input_bar())
        self.add_widget(root)

    def _build_topbar(self):
        from utils import fx
        bar = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=dp(54), spacing=dp(8), padding=[dp(12), dp(6)])
        with bar.canvas.before:
            Color(*theme.PANEL_RAISED)
            top_bg = Rectangle(pos=bar.pos, size=bar.size)
            Color(*theme.METAL_LIGHT)
            top_line = Rectangle(pos=(bar.x, bar.y), size=(bar.width, dp(1)))
        bar.bind(pos=lambda _, p: (setattr(top_bg, "pos", p),
                                  setattr(top_line, "pos", p)),
                 size=lambda _, s: (setattr(top_bg, "size", s),
                                    setattr(top_line, "size", (s[0], dp(1)))))
        self._status_dot = Label(text="\u25cf", color=theme.TEXT_MUTED,
                                 font_size=dp(12), size_hint_x=None, width=dp(18))
        bar.add_widget(self._status_dot)
        self._status_lbl = Label(text="", color=theme.TEXT_MUTED,
                                  font_size=dp(11), halign="left", valign="middle",
                                  size_hint_x=1)
        self._status_lbl.bind(size=self._status_lbl.setter("text_size"))
        self._status_lbl.shorten = True
        self._status_lbl.shorten_from = 'right'
        bar.add_widget(self._status_lbl)
        log_btn = Button(text="[font=Symbols]\u2630[/font]", markup=True,
                        size_hint_x=None, width=dp(40),
                        background_normal="", background_color=(0, 0, 0, 0),
                        color=theme.DANGER, font_size=dp(16))
        log_btn.bind(on_release=lambda _: self._open_log_popup())
        bar.add_widget(log_btn)
        gear = Button(text="[font=Symbols]\u2699[/font]", markup=True,
                      size_hint_x=None, width=dp(40),
                      background_normal="", background_color=(0, 0, 0, 0),
                      color=theme.VFD_CYAN, font_size=dp(18))
        gear.bind(on_release=lambda _: self._open_settings())
        bar.add_widget(gear)
        fx.surface(bar, 'panel', theme.VFD_BLUE, cut=5)
        return bar

    def _open_log_popup(self):
        try:
            _LogPopup().open()
        except Exception as e:
            import traceback
            self._render_append(("warn", f"日志弹窗出错：{e}\n{traceback.format_exc()[:400]}"))
            _push_err("日志弹窗", f"{e}\n{traceback.format_exc()}")

    def _build_calorie_bar(self):
        from utils import fx
        bar = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=dp(36), spacing=dp(6), padding=[dp(12), dp(2)])
        with bar.canvas.before:
            Color(*theme.DISPLAY_GLASS)
            self._cbg = Rectangle(pos=bar.pos, size=bar.size)
        bar.bind(pos=lambda _, p: setattr(self._cbg, "pos", p),
                 size=lambda _, s: setattr(self._cbg, "size", s))
        self._calorie_lbl = Label(text="", markup=True, font_size=dp(10),
                                  halign="left", valign="middle",
                                  size_hint_x=1, size_hint_y=1)
        self._calorie_lbl.bind(
            width=lambda lbl, w: setattr(lbl, "text_size", (w, None)))
        self._calorie_lbl.bind(on_ref_press=self._on_calorie_ref_press)
        bar.add_widget(self._calorie_lbl)
        add_meal = Button(text="识图录入", size_hint_x=None, width=dp(64),
                          background_normal="", background_color=theme.VFD_CYAN,
                         color=(0.04, 0.06, 0.1, 1), font_size=dp(11))
        add_meal.bind(on_release=lambda _: self._open_meal_picker())
        bar.add_widget(add_meal)
        self._refresh_calorie_bar()
        fx.surface(bar, 'glass', theme.VFD_CYAN, cut=4)
        return bar

    def _refresh_calorie_bar(self, *_):
        try:
            b = db.today_balance()
            w = db.get_user_weight()
        except Exception:
            return
        bal = b["balance"]
        if bal < 0:
            bal_txt = f"[color=88ffaa]赤字 {abs(int(bal))}kcal[/color]"
        else:
            bal_txt = f"[color=ff8888]盈余 {int(bal)}kcal[/color]"
        dg = b["deficit_goal"]
        if dg > 0:
            goal_txt = f"[ref=deficit][color=88ccff]目标{dg}>[/color][/ref]"
        elif dg < 0:
            goal_txt = f"[ref=deficit][color=ffcc88]目标+{abs(dg)}>[/color][/ref]"
        else:
            goal_txt = f"[ref=deficit][color=88cc88]维持>[/color][/ref]"
        self._calorie_lbl.text = (
            f"[b]今日[/b] [ref=intake][color=88ccff]{int(b['intake'])}kcal>[/color][/ref]\n"
            f"TDEE{int(b['tdee'])} + 运动{int(b['exercise'])}  {bal_txt}  "
            f"{goal_txt}  体重{w}kg"
        )

    def _on_calorie_ref_press(self, lbl, ref):
        if ref == "intake":
            _MealsDetailPopup().open()
        elif ref == "deficit":
            self._open_deficit_editor()

    def _open_deficit_editor(self):
        try:
            cur = db.get_profile().get("deficit_goal", 500)
        except Exception:
            cur = 500
        _DeficitGoalPopup(current=cur, on_saved=self._refresh_calorie_bar).open()

    def _build_input_bar(self):
        from utils import fx
        bar = BoxLayout(orientation="horizontal", size_hint_y=None,
                        height=dp(60), spacing=dp(6), padding=[dp(10), dp(8)])
        with bar.canvas.before:
            Color(*theme.PANEL)
            self._bbg = Rectangle(pos=bar.pos, size=bar.size)
            Color(*theme.METAL_LIGHT)
            self._bline = Rectangle(pos=(bar.x, bar.top - dp(1)), size=(bar.width, dp(1)))
        bar.bind(
            pos=lambda _, p: (setattr(self._bbg, "pos", p),
                              setattr(self._bline, "pos", (p[0], p[1] + bar.height - dp(1)))),
            size=lambda _, s: (setattr(self._bbg, "size", s),
                               setattr(self._bline, "size", (s[0], dp(1)))),
        )
        fx.surface(bar, 'panel', theme.VFD_BLUE, cut=4)
        img_btn = Button(text="[font=Symbols]\u25ce[/font]", markup=True,
                         size_hint_x=None, width=dp(36),
                          background_normal="", background_color=theme.METAL_DARK,
                          color=theme.VFD_ORANGE, font_size=dp(16))
        img_btn.bind(on_release=lambda _: self._open_image_picker())
        bar.add_widget(img_btn)
        voice_btn = Button(text="[font=Symbols]\u266a[/font]", markup=True,
                           size_hint_x=None, width=dp(36),
                            background_normal="", background_color=theme.METAL_DARK,
                            color=theme.VFD_CYAN, font_size=dp(16))
        voice_btn.bind(on_press=self._voice_press, on_release=self._voice_release)
        self._voice_btn = voice_btn
        bar.add_widget(voice_btn)
        self._input = TextInput(multiline=False, font_size=dp(14),
                                foreground_color=theme.TEXT_PRIMARY,
                                background_normal="",
                                 background_color=theme.DISPLAY_GLASS,
                                 cursor_color=theme.VFD_CYAN, padding=[dp(10), dp(6)],
                                 hint_text="聊训练、饮食、身体数据…", hint_text_color=theme.TEXT_MUTED)
        self._input.bind(on_text_validate=self._on_send)
        bar.add_widget(self._input)
        send = Button(text="发送", size_hint_x=None, width=dp(64),
                       background_normal="", background_color=theme.VFD_BLUE,
                      color=(0.05, 0.05, 0.08, 1), font_size=dp(14))
        send.bind(on_release=lambda _: self._on_send())
        self._send_button = send
        bar.add_widget(send)
        return bar

    def _fill_prompt(self, text):
        if not self._busy:
            self._input.text = text
            self._input.focus = True

    def _open_image_picker(self):
        if _ANDROID_VOICE:
            self._picker_target = "chat"
            self._pick_image_intent()
        else:
            _ImagePicker(on_select=self._on_image_selected).open()

    def _on_image_selected(self, path):
        try:
            size = os.path.getsize(path)
        except OSError:
            self._render_append(("warn", "无法读取该图片。"))
            return
        if size > _MAX_IMG_BYTES:
            self._render_append(
                ("warn", f"图片太大（{size // 1024}KB），请选小于 4MB 的图。"))
            return
        self._pending_image = path
        self._preview_bar.clear_widgets()
        self._preview_bar.height = dp(64)
        thumb = Image(source=path, size_hint_x=None, width=dp(60),
                      size_hint_y=None, height=dp(58),
                      allow_stretch=True, keep_ratio=True)
        self._preview_bar.add_widget(thumb)
        name = os.path.basename(path)
        lbl = Label(text=f"[b]已选图：[/b] {name[:24]}", markup=True,
                    color=theme.TEXT_SECONDARY, font_size=dp(11),
                    halign="left", valign="middle", size_hint_x=1)
        lbl.bind(size=lbl.setter("text_size"))
        self._preview_bar.add_widget(lbl)
        clr = Button(text="✕", size_hint_x=None, width=dp(36),
                     background_normal="", background_color=(0, 0, 0, 0),
                     color=theme.DANGER, font_size=dp(15))
        clr.bind(on_release=lambda _: self._clear_image())
        self._preview_bar.add_widget(clr)

    def _clear_image(self):
        self._pending_image = None
        self._preview_bar.clear_widgets()
        self._preview_bar.height = 0

    # —— 语音输入（长按录音，松开发送音频给 AI） ——
    def _voice_press(self, btn):
        if not _ANDROID_VOICE:
            self._render_append(("warn", "语音输入仅在 Android 上可用。"))
            return
        self._voice_press_time = _time.time()
        self._voice_longpress = False
        self._voice_longevent = Clock.schedule_once(self._on_voice_longpress, 0.3)

    def _on_voice_longpress(self, dt):
        self._voice_longpress = True
        self._voice_longevent = None
        self._start_recording()

    def _voice_release(self, btn):
        ev = getattr(self, "_voice_longevent", None)
        if ev:
            ev.cancel()
            self._voice_longevent = None
        if not getattr(self, "_voice_longpress", False):
            return  # 短按忽略
        if getattr(self, "_voice_cancel", False):
            self._voice_cancel = False
            return
        self._stop_recording()

    def _start_recording(self):
        if getattr(self, "_recorder", None):
            return
        try:
            from android.permissions import request_permissions, Permission, check_permission
            if not check_permission("android.permission.RECORD_AUDIO"):
                request_permissions([Permission.RECORD_AUDIO])
                self._render_append(("warn", "需要「录音」权限才能使用语音输入，请在系统设置中授予"))
                return
        except Exception:
            pass
        try:
            m4a_file = _File(_PythonActivity.mActivity.getCacheDir(), "voice_input.m4a")
            m4a_path = m4a_file.getAbsolutePath()
            rec = _MediaRecorder()
            rec.setAudioSource(_AudioSource.MIC)
            rec.setOutputFormat(_OutputFormat.MPEG_4)
            rec.setAudioEncoder(_AudioEncoder.AAC)
            rec.setAudioSamplingRate(16000)
            rec.setAudioEncodingBitRate(32000)
            rec.setOutputFile(m4a_path)
            rec.prepare()
            rec.start()
            self._recorder = rec
            self._m4a_path = m4a_path
            self._voice_cancel = False
            self._voice_btn.text = "●"
            self._voice_btn.background_color = theme.LED_RED
            self._voice_btn.color = (1, 1, 1, 1)
            _plog(f"recording started: MediaRecorder m4a -> {m4a_path}")
        except Exception as e:
            self._render_append(("warn", f"启动录音失败：{e}"))
            _plog(f"_start_recording error: {e}")

    def _stop_recording(self):
        rec = getattr(self, "_recorder", None)
        if rec is None:
            return
        try:
            rec.stop()
        except Exception as e:
            _plog(f"_stop_recording stop error: {e}")
        try:
            rec.release()
        except Exception:
            pass
        self._recorder = None
        self._voice_btn.text = "[font=Symbols]\u266a[/font]"
        self._voice_btn.background_color = theme.METAL_DARK
        self._voice_btn.color = theme.VFD_CYAN
        m4a_path = getattr(self, "_m4a_path", "")
        _plog(f"_stop_recording: m4a_path={m4a_path}")
        if m4a_path:
            try:
                fsize = os.path.getsize(m4a_path)
            except OSError:
                fsize = 0
            _plog(f"_stop_recording: m4a size={fsize}")
            if fsize < 800:
                self._render_append(("warn", "录音太短，已取消"))
            else:
                _fix_m4a_brand(m4a_path)
                self._send_audio(m4a_path)
        else:
            self._render_append(("warn", "录音太短，已取消"))

    def _cancel_recording(self):
        self._voice_cancel = True
        rec = getattr(self, "_recorder", None)
        if rec:
            try:
                rec.stop()
            except Exception:
                pass
            try:
                rec.release()
            except Exception:
                pass
            self._recorder = None
        self._voice_btn.text = "[font=Symbols]\u266a[/font]"
        self._voice_btn.background_color = theme.METAL_DARK
        self._voice_btn.color = theme.VFD_CYAN

    def _send_audio(self, path):
        if self._busy:
            return
        if not _mi_mo_multimodal_ok(self._cfg.model, self._cfg.api_base_url):
            self._render_append(("warn", f"模型 {self._cfg.model} 不支持音频，请在设置选 mimo-v2.5"))
            return
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except Exception as e:
            self._render_append(("warn", f"读取录音失败：{e}"))
            return
        b64 = base64.b64encode(raw).decode()
        _fmt = _detect_audio_mime(path)
        _plog(f"_send_audio: path={path} size={len(raw)} head={raw[:16].hex()} fmt={_fmt}")
        request_msg = {
            "role": "user",
            "content": [
                {"type": "input_audio",
                 "input_audio": {"data": b64, "format": _fmt}},
                {"type": "text", "text": "请听这段语音录音，转写为文字并理解内容，然后回复。"},
            ],
        }
        self._busy = True
        self._render_append(("typing", "正在处理语音..."))
        try:
            calorie_ctx = [{"role": "system", "content": db.today_summary_text()}]
        except Exception:
            calorie_ctx = []
        request_messages = (
            [self._messages[0]] + calorie_ctx + self._messages[1:] + [request_msg]
            if self._messages else [request_msg]
        )
        self._messages.append({"role": "user", "content": "(语音消息)"})

        def worker():
            try:
                text = self._run_with_tools(request_messages)
                ok, payload = True, text
            except Exception as e:
                ok, payload = False, str(e)
                _push_err("语音识别", payload)
            Clock.schedule_once(lambda dt: self._on_reply(ok, payload), 0)

        threading.Thread(target=worker, daemon=True).start()

    # —— 系统相册选图（Android） ——
    def _pick_image_intent(self):
        if not _ANDROID_VOICE:
            _ImagePicker(on_select=self._on_image_selected).open()
            return
        try:
            if not getattr(self, "_picker_bound", False):
                _android_activity.bind(on_activity_result=self._on_image_result)
                self._picker_bound = True
                _plog("picker: bound on_activity_result")
            activity = _PythonActivity.mActivity
            intent = _Intent(_Intent.ACTION_PICK)
            intent.setType("image/*")
            activity.startActivityForResult(intent, 1002)
            _plog("picker: startActivityForResult sent (1002)")
        except Exception as e:
            _plog(f"picker: open album failed: {e}")
            self._render_append(("warn", f"打开相册失败：{e}"))

    def _uri_to_cache(self, uri):
        """URI → JPEG 缓存文件。

        用 BitmapFactory.decodeStream 从 ContentResolver 输入流解码为 Bitmap，
        再 compress 成 JPEG。这样：(1) 绕开 pyjnius 对 native byte[] 读取的
        pass-by-reference bug（直接拷字节流会写出全零文件）；(2) 顺便把
        HEIC/WEBP 等系统相册常见格式转成 MiMo 支持的 JPEG。

        注意：pyjnius 不能用 `Bitmap.CompressFormat` 这种 OuterClass.NestedClass
        访问嵌套类，必须 `autoclass("...$NestedClass")` 字符串形式加载。
        """
        from jnius import autoclass
        BitmapFactory = autoclass("android.graphics.BitmapFactory")
        BitmapCompressFormat = autoclass("android.graphics.Bitmap$CompressFormat")
        ByteArrayOutputStream = autoclass("java.io.ByteArrayOutputStream")
        File = autoclass("java.io.File")
        FOS = autoclass("java.io.FileOutputStream")
        activity = _PythonActivity.mActivity
        _plog(f"uri_to_cache: uri={uri}")
        cr = activity.getContentResolver()
        ins = cr.openInputStream(uri)
        _plog("uri_to_cache: got inputStream, decoding bitmap")
        bm = BitmapFactory.decodeStream(ins)
        ins.close()
        if bm is None:
            _plog("uri_to_cache: BitmapFactory.decodeStream returned None")
            raise RuntimeError("无法解码此图片")
        baos = ByteArrayOutputStream()
        ok = bm.compress(BitmapCompressFormat.JPEG, 90, baos)
        bm.recycle()
        if not ok:
            _plog("uri_to_cache: bitmap.compress returned false")
            raise RuntimeError("图片转码失败")
        jpg_bytes = baos.toByteArray()
        baos.close()
        tmp = File(activity.getCacheDir(), "ai_pick.jpg")
        fos = FOS(tmp)
        fos.write(jpg_bytes)
        fos.flush()
        fos.close()
        _plog(f"uri_to_cache: -> {tmp.getAbsolutePath()} ({len(jpg_bytes)} bytes JPEG)")
        return tmp.getAbsolutePath()

    def _on_image_result(self, request_code, result_code, intent):
        _plog(f"on_image_result req={request_code} res={result_code} intent={intent is not None}")
        if request_code != 1002:
            return
        if result_code != -1:
            rc = result_code
            Clock.schedule_once(
                lambda dt, r=rc: self._render_append(
                    ("warn", f"选图未完成（result={r}），已取消或失败")), 0)
            return
        try:
            uri = intent.getData()
            path = self._uri_to_cache(uri)
        except Exception as e:
            _plog(f"on_image_result copy error: {e}")
            err = str(e)
            Clock.schedule_once(
                lambda dt, m=err: self._render_append(
                    ("warn", f"读取所选图片失败：{m}")), 0)
            return
        try:
            fsize = os.path.getsize(path)
        except OSError:
            fsize = 0
        _plog(f"on_image_result: file_size={fsize}")
        if fsize < 100:
            Clock.schedule_once(
                lambda dt: self._render_append(
                    ("warn", "图片读取失败（文件为空），请重试")), 0)
            return
        try:
            with open(path, "rb") as _f:
                _head = _f.read(16)
        except Exception:
            _head = b""
        _plog(f"on_image_result: head={_head.hex()}")
        try:
            mime = _detect_image_mime(path)
        except Exception as e:
            _plog(f"on_image_result detect error: {e}")
            mime = "unknown"
        _plog(f"on_image_result: path={path} mime={mime} size={fsize}")
        if mime not in ("jpeg", "png", "gif", "webp", "bmp"):
            msg = ("不支持 HEIC/HEIF 格式，请选 JPG/PNG/WebP 格式图片"
                   if mime == "heic" else
                   f"无法识别图片格式（{mime}），请选 JPG/PNG/WebP")
            Clock.schedule_once(
                lambda dt, m=msg: self._render_append(("warn", m)), 0)
            return
        target = getattr(self, "_picker_target", "chat")
        if target == "meal":
            mt = getattr(self, "_meal_type", "加餐")
            Clock.schedule_once(
                lambda dt, p=path, m=mt: self._estimate_meal(p, m), 0)
        else:
            Clock.schedule_once(lambda dt, p=path: self._on_image_selected(p), 0)

    # —— 加餐识图算热量 ——
    def _open_meal_picker(self):
        if not self._cfg.is_configured:
            self._render_append(("warn", "请先配置 API Key 并选一个支持识图的模型。"))
            return

        def _after_meal_type(meal_type):
            self._meal_type = meal_type
            self._picker_target = "meal"
            if _ANDROID_VOICE:
                self._pick_image_intent()
            else:
                _ImagePicker(on_select=lambda p, m=meal_type: self._estimate_meal(p, m)).open()

        _MealTypePopup(on_select=_after_meal_type).open()

    def _estimate_meal(self, path, meal_type="加餐"):
        if self._meal_busy:
            return
        try:
            size = os.path.getsize(path)
        except OSError:
            self._render_append(("warn", "无法读取该图片。"))
            return
        if size > _MAX_IMG_BYTES:
            self._render_append(("warn", f"图片太大（{size // 1024}KB），请选小于 4MB 的图。"))
            return
        self._meal_busy = True
        if not _mi_mo_multimodal_ok(self._cfg.model, self._cfg.api_base_url):
            self._meal_busy = False
            self._render_append(("warn", f"模型 {self._cfg.model} 不支持图片，请在设置选 mimo-v2.5"))
            return
        self._render_append(("typing", f"正在识别 {meal_type} 食物并估算热量..."))
        data_url = _image_data_url(path)
        prompt = ("分析图中食物，估算每样的克数与热量(千卡)。只返回JSON，"
                  "格式：{\"meal_type\":\"%s\"," % meal_type
                  + "\"items\":[{\"name\":\"食物名\",\"grams\":0,\"kcal\":0}],"
                  + "\"total_kcal\":0,\"note\":\"简短说明\"}。不要输出JSON以外内容。")
        messages = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}]
        # MiMo 多模态请求建议带 system message
        if _mi_mo_multimodal_ok(self._cfg.model, self._cfg.api_base_url):
            sys_txt = self._cfg.system_prompt or "You are a helpful assistant."
            messages.insert(0, {"role": "system", "content": sys_txt})

        def worker():
            try:
                self._ensure_client()
                resp = self._client.chat(messages, max_tokens=4096)
                ok, payload = True, resp["text"]
            except Exception as e:
                ok, payload = False, str(e)
                _push_err("加餐识图", payload)
            msg = payload
            Clock.schedule_once(
                lambda dt, o=ok, m=msg, mt=meal_type: self._on_meal_result(o, m, mt), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _on_meal_result(self, ok, text, meal_type="加餐"):
        self._meal_busy = False
        self._pop_typing()
        if not ok:
            self._render_append(("warn", "识别失败：" + text[:160]))
            return
        try:
            data = json.loads(text)
        except Exception:
            self._render_append(("ai", "AI 返回：" + text[:300]))
            return
        items = data.get("items", [])
        total = data.get("total_kcal")
        if not total:
            total = sum(i.get("kcal", 0) for i in items)
        # 用户已在前一步选了餐别，AI 返回的 meal_type 仅作参考，以用户选择为准
        saved_type = meal_type
        summary = "，".join(
            f"{i.get('name','?')}{i.get('grams','?')}g/{i.get('kcal','?')}kcal"
            for i in items) or data.get("note", "一餐")
        try:
            db.add_meal(saved_type, summary, total,
                        items_json=json.dumps(items, ensure_ascii=False))
        except Exception as e:
            self._render_append(("warn", f"保存失败：{e}"))
            return
        self._refresh_calorie_bar()
        self._render_append(("ai", f"🍽 {saved_type}  约 {int(total)}kcal\n{summary}"))

    # —— tool calling：AI 执行 app 操作 ——
    def _dispatch_tool(self, name, args):
        _tlog(f"[tool] call {name} args={args}")
        try:
            if name == "list_today_plan":
                plan = db.get_today_plan()
                return json.dumps([{
                    "id": p["id"], "type": p["item_type"], "name": p["exercise_name"],
                    "sets": p.get("target_sets"), "reps": p.get("target_reps"),
                    "weight": p.get("target_weight"),
                    "weight_step": p.get("target_weight_step"),
                    "rep_step": p.get("target_rep_step"),
                    "distance": p.get("target_distance"),
                    "duration": p.get("target_duration"),
                    "completed": bool(p.get("completed")),
                } for p in plan], ensure_ascii=False)
            if name == "add_plan_item":
                item_type = args["item_type"]
                exercise_name = args["exercise_name"]
                # 自动注册到 custom_exercises，让面板预设列表可见
                db.add_custom_exercise(item_type, exercise_name)
                # 匹配已有动作资料库条目，关联 GIF 和指导步骤
                catalog_exercise = db.find_catalog_exercise(None, exercise_name)
                exercise_id = catalog_exercise["id"] if catalog_exercise else None
                from config.constants import get_default_rest_seconds
                db.add_plan_item(
                    item_type=item_type, exercise_name=exercise_name,
                    target_sets=args.get("sets"), target_reps=args.get("reps"),
                    target_weight=args.get("weight"),
                    target_weight_step=args.get("weight_step", 0),
                    target_rep_step=args.get("rep_step", 0),
                    target_distance=args.get("distance"),
                    target_duration=args.get("duration"),
                    target_rest_seconds=get_default_rest_seconds(exercise_name),
                    exercise_id=exercise_id)
                self._plan_changed = True
                catalog_msg = "，已关联动作指导" if catalog_exercise else ""
                return f"ok: 已添加 {exercise_name}{catalog_msg}"
            if name == "update_plan_item":
                pid = args["plan_id"]
                fld = {"sets": "target_sets", "reps": "target_reps",
                       "weight": "target_weight", "weight_step": "target_weight_step",
                       "rep_step": "target_rep_step", "distance": "target_distance",
                       "duration": "target_duration"}
                kw = {fld[k]: args[k] for k in fld if k in args}
                if kw:
                    db.update_plan_item(pid, **kw)
                self._plan_changed = True
                return "ok: 已更新项目"
            if name == "delete_plan_item":
                db.delete_plan_item(args["plan_id"])
                self._plan_changed = True
                return "ok: 已删除项目"
            if name == "complete_plan_item":
                db.complete_plan_item(args["plan_id"])
                self._plan_changed = True
                return "ok: 已标记完成"
            if name == "get_today_calories":
                return json.dumps(db.today_balance(), ensure_ascii=False)
            if name == "set_user_weight":
                from datetime import date
                db.set_user_weight(date.today().isoformat(), args["weight"])
                return "ok: 已记录体重"
            if name == "set_deficit_goal":
                dg = int(args["deficit_goal"])
                db.set_profile(deficit_goal=dg)
                Clock.schedule_once(lambda dt: self._refresh_calorie_bar(), 0)
                label = ("减脂赤字" if dg > 0 else "增肌盈余" if dg < 0 else "维持平衡")
                return f"ok: 已设置目标{label} {abs(dg)}kcal"
            if name == "list_templates":
                tpls = db.get_templates()
                return json.dumps([{
                    "id": t["id"], "name": t["name"],
                    "items": t["items"],
                } for t in tpls], ensure_ascii=False)
            if name == "update_template_items":
                tid = args["template_id"]
                tpls = db.get_templates()
                tpl = next((t for t in tpls if t["id"] == tid), None)
                if not tpl:
                    return f"error: 找不到模板 id={tid}"
                db.update_template(tid, tpl["name"], args["items"])
                return "ok: 已更新模板项目"
            if name == "add_template":
                db.add_template(args["name"], args["items"])
                return "ok: 已新建模板"
            if name == "delete_template":
                db.delete_template(args["template_id"])
                return "ok: 已删除模板"
            if name == "list_today_meals":
                meals = db.get_today_meals()
                return json.dumps(meals, ensure_ascii=False)
            if name == "delete_meal":
                db.delete_meal(args["meal_id"])
                Clock.schedule_once(lambda dt: self._refresh_calorie_bar(), 0)
                return "ok: 已删除该餐记录"
            if name == "clear_today_meals":
                meals = db.get_today_meals()
                for m in meals:
                    db.delete_meal(m["id"])
                Clock.schedule_once(lambda dt: self._refresh_calorie_bar(), 0)
                return f"ok: 已清空今日 {len(meals)} 条饮食记录"
            if name == "add_meal":
                db.add_meal(
                    meal_type=args["meal_type"],
                    food_summary=args["food_summary"],
                    calories=args["total_kcal"],
                    items_json=args.get("items_json", ""),
                    source="ai",
                )
                Clock.schedule_once(lambda dt: self._refresh_calorie_bar(), 0)
                return f"ok: 已添加{args['meal_type']}，{args['food_summary']}，约{int(args['total_kcal'])}kcal"
            if name == "get_date_overview":
                return json.dumps(db.get_date_overview(args["date"]), ensure_ascii=False, default=str)
            if name == "search_catalog":
                results = db.search_catalog(query=args.get("query", ""),
                                            body_part=args.get("body_part", ""),
                                            limit=12)
                summary = [{
                    "name": e["name_zh"],
                    "name_en": e["name_en"],
                    "body_part": e["body_part"],
                    "equipment": e["equipment"],
                    "has_animation": len(e.get("animation_frames", [])) > 0,
                    "common": bool(e.get("is_common", 1)),
                } for e in results]
                return json.dumps(summary, ensure_ascii=False)
            return f"error: 未知工具 {name}"
        except Exception as e:
            return f"error: {e}"

    def _run_with_tools(self, messages):
        """带 tool calling 的多轮调用，返回最终文本。"""
        self._ensure_client()
        msgs = list(messages)
        last_text = ""
        for i in range(8):
            try:
                resp = self._client.chat(msgs, max_tokens=2048, tools=AI_TOOLS, tool_choice="auto")
            except Exception as e:
                _tlog(f"[tool] round {i} chat error: {e}")
                raise
            tcs = resp.get("tool_calls")
            last_text = resp.get("text", "") or ""
            _tlog(f"[tool] round {i} text={last_text[:80]!r} tool_calls={tcs is not None}")
            if tcs:
                _tlog(f"[tool] round {i} calls={[tc.get('function', {}).get('name') for tc in tcs]}")
            if not tcs:
                return last_text
            msgs.append({"role": "assistant", "content": last_text, "tool_calls": tcs})
            for tc in tcs:
                fn = tc.get("function", {})
                nm = fn.get("name", "")
                try:
                    a = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    a = {}
                result = self._dispatch_tool(nm, a)
                _tlog(f"[tool] {nm} -> {result[:80]}")
                msgs.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                             "content": result})
        return last_text or "（工具调用轮数超限）"

    def _open_settings(self):
        popup = AISettingsPopup()
        popup.bind(on_dismiss=lambda *_: self._refresh_cfg())
        popup.open()

    def _refresh_cfg(self, *_):
        cfg = LLMConfig.load()
        if cfg != self._cfg:
            self._cfg = cfg
            self._rebuild_messages()
        # 注意：不要 return True，否则 ModalView.dismiss() 会取消关闭
        return None

    def _ensure_client(self):
        """在后台线程惰性创建 LLMClient（构造 httpx 不应阻塞主线程）。"""
        if self._client is None:
            self._client = llm_client.LLMClient(
                api_key=self._cfg.api_key, api_base_url=self._cfg.api_base_url,
                model=self._cfg.model, temperature=self._cfg.temperature,
                max_tokens=self._cfg.max_tokens, max_retries=self._cfg.max_retries,
                retry_base_delay=self._cfg.retry_base_delay, timeout=self._cfg.timeout,
            )
        return self._client

    def _rebuild_messages(self):
        if self._client is not None:
            self._client.close()
            self._client = None
        if self._cfg.is_configured:
            # client 惰性构造（在后台线程 _ensure_client），避免保存配置时
            # 主线程同步初始化 httpx（Android 上可能卡死）
            self._messages = [{"role": "system", "content": self._cfg.system_prompt}]
            self._status_dot.color = theme.LED_GREEN
            self._status_lbl.text = "AI 助手 · 已配置\n" + self._cfg.model
            self._render([("info", "你好，我是你的健身助手。\n可分析训练、查询历史、记录饮食与调整计划。\n\n选择上方快捷问题，或直接输入消息。")])
        else:
            self._messages = []
            self._status_dot.color = theme.TEXT_MUTED
            self._status_lbl.text = "DATA LINK / 未配置"
            self._render([("info", "未配置。点击右上角齿轮填写 API Key 后保存。")])

    def _on_send(self, *_):
        if self._busy:
            return
        text = self._input.text.strip()
        image = self._pending_image
        if not text and not image:
            return
        if not self._cfg.is_configured:
            self._render_append(("warn", "请先在设置里配置 API Key。"))
            return
        self._input.text = ""
        self._clear_image()
        self._busy = True

        shown_text = text or "(图片)"
        if image:
            if not _mi_mo_multimodal_ok(self._cfg.model, self._cfg.api_base_url):
                self._busy = False
                self._render_append(("warn", f"模型 {self._cfg.model} 不支持图片，请在设置选 mimo-v2.5"))
                return
            data_url = _image_data_url(image)
            request_msg = {"role": "user", "content": [
                {"type": "text", "text": text or "请分析这张图片"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}
            history_msg = {"role": "user", "content": shown_text}
        else:
            request_msg = {"role": "user", "content": text}
            history_msg = request_msg

        self._render_append(("user", shown_text, image))
        self._render_append(("typing", "正在思考..."))

        # 注入今日热量上下文，让 AI 能查饮食/热量数据
        try:
            calorie_ctx = [{"role": "system",
                            "content": db.today_summary_text()}]
        except Exception:
            calorie_ctx = []
        request_messages = ([self._messages[0]] + calorie_ctx
                            + self._messages[1:] + [request_msg]
                            if self._messages else [request_msg])
        self._messages.append(history_msg)

        def worker():
            try:
                text = self._run_with_tools(request_messages)
                ok, payload = True, text
            except Exception as e:
                ok, payload = False, str(e)
                _push_err("发送图片" if image else "聊天", payload)
            msg = payload
            Clock.schedule_once(lambda dt: self._on_reply(ok, msg), 0)

        threading.Thread(target=worker, daemon=True).start()
        self._send_button.disabled = True
        self._send_button.text = '思考中'

    def _on_reply(self, ok, payload):
        self._busy = False
        self._send_button.disabled = False
        self._send_button.text = '发送'
        self._pop_typing()
        self._refresh_calorie_bar()
        if getattr(self, "_plan_changed", False):
            self._plan_changed = False
            try:
                from kivy.app import App
                ml = App.get_running_app().root
                if hasattr(ml, "refresh_heatmap"):
                    ml.refresh_heatmap()
                if hasattr(ml, "_task_card"):
                    ml._task_card.refresh()
                if hasattr(ml, "_warmup"):
                    ml._warmup.refresh()
                # 资料馆/有氧页在切页时惰性刷新（见 MainLayout._on_screen_changed）
            except Exception:
                pass
        if ok:
            self._messages.append({"role": "assistant", "content": payload})
            self._render_append(("ai", payload))
        else:
            self._render_append(("warn", "失败：" + payload[:160]))

    def _pop_typing(self):
        if self._msg_box.children and getattr(self._msg_box.children[0], "_kind", None) == "typing":
            self._msg_box.remove_widget(self._msg_box.children[0])

    def _render(self, items):
        self._msg_box.clear_widgets()
        for item in items:
            self._render_append(item)

    def _render_append(self, item):
        kind = item[0]
        text = item[1]
        image = item[2] if len(item) > 2 else None
        bubble = _Bubble(kind, text, image=image)
        self._msg_box.add_widget(bubble)
        Clock.schedule_once(lambda dt: self._scroll.scroll_to(bubble), 0.05)


class _Bubble(BoxLayout):
    def __init__(self, kind, text, image=None, **kwargs):
        align = "left"
        if kind == "user":
            bg, fg, align = (0.025, 0.075, 0.10, 1), theme.TEXT_PRIMARY, "right"
        elif kind == "ai":
            bg, fg = theme.DISPLAY_GLASS, theme.TEXT_PRIMARY
        elif kind == "typing":
            bg, fg = theme.DISPLAY_GLASS, theme.VFD_CYAN
        elif kind == "warn":
            bg, fg = theme.DISPLAY_GLASS, theme.LED_RED
        else:
            bg, fg = theme.PANEL, theme.TEXT_SECONDARY
        super().__init__(orientation="vertical", size_hint_y=None,
                         padding=[dp(12), dp(8)], spacing=dp(2), **kwargs)
        self._kind = kind
        self.bind(minimum_height=self.setter("height"))
        with self.canvas.before:
            self._bubble_color = Color(*bg)
            self._r = Rectangle(pos=self.pos, size=self.size)
            Color(*(theme.VFD_BLUE if kind == "user" else theme.BORDER_DIM))
            self._edge = Rectangle(pos=self.pos, size=(dp(2), self.height))
        self.bind(pos=lambda _, p: setattr(self._r, "pos", p),
                  size=lambda _, s: setattr(self._r, "size", s))
        self.bind(pos=lambda _, p: setattr(self._edge, "pos", p),
                  size=lambda _, s: setattr(self._edge, "size", (dp(2), s[1])))
        from utils import fx
        fx.surface(self, 'glass', theme.VFD_BLUE if kind == 'user' else
                   theme.LED_RED if kind == 'warn' else theme.VFD_CYAN, cut=8)
        source = {"user": "LOCAL TX", "ai": "AI DATA RX", "typing": "LINK ACTIVE",
                  "warn": "SYSTEM ALERT"}.get(kind, "SYSTEM STATUS")
        source_color = (theme.VFD_BLUE if kind == "user" else
                        theme.LED_RED if kind == "warn" else theme.VFD_CYAN)
        source_label = Label(text=source, color=source_color,
                              font_size=dp(9), size_hint_y=None, height=dp(12),
                              halign="left", valign="middle")
        self.add_widget(source_label)
        if image:
            img = Image(source=image, size_hint_y=None, height=dp(150),
                       allow_stretch=True, keep_ratio=True)
            self.add_widget(img)
        inp = TextInput(text=text, readonly=True, font_size=dp(13),
                        foreground_color=fg,
                        background_normal="", background_active="",
                        background_color=(0, 0, 0, 0),
                        cursor_color=(0, 0, 0, 0),
                        padding=[dp(2), dp(2)], size_hint_y=None)

        def _resize_inp(_inp=None):
            _inp = _inp or inp
            try:
                _inp.text_size = (_inp.width - dp(4), None)
                Clock.schedule_once(lambda dt: _set_inp_height(_inp))
            except Exception:
                pass

        def _set_inp_height(_inp):
            try:
                lines = _inp._lines if hasattr(_inp, "_lines") else [""]
                _inp.height = max(dp(28), len(lines) * _inp.line_height + _inp.padding[1] * 2 + dp(2))
            except Exception:
                _inp.height = dp(28)

        inp.bind(width=lambda i, w: _resize_inp(i))
        Clock.schedule_once(lambda dt: _resize_inp(inp))
        self.add_widget(inp)
        from utils.appearance import state as appearance

        def update_theme(*_):
            if kind == 'user':
                self._bubble_color.rgba = bg if appearance.enhanced else theme.VFD_BLUE
                inp.foreground_color = theme.TEXT_PRIMARY if appearance.enhanced else theme.CHASSIS
                source_label.color = theme.VFD_BLUE if appearance.enhanced else theme.CHASSIS

        appearance.bind(enhanced=update_theme)
        update_theme()
