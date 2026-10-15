"""Card container: chamfered titanium plate with shadow, gradient, brushed metal."""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.metrics import dp
from config import theme
from utils import fx


class Card(BoxLayout):
    """Titanium plate container with chamfered corners and precision module styling."""

    def __init__(self, radius=None, padding=None, bg=None, border=True,
                 style='panel', accent=None, **kwargs):
        if padding is None:
            padding = (dp(theme.CARD_PADDING), dp(theme.CARD_PADDING))
        super().__init__(padding=padding, **kwargs)
        cut = radius if radius is not None else theme.CHAMFER
        self._plate = fx.Plate(style=style, accent_color=accent or theme.VFD_CYAN,
                               bg=bg, border=border, cut_tr=cut, cut_bl=cut)
        self.canvas.before.add(self._plate.group)
        self.bind(pos=self._update_plate, size=self._update_plate)
        self._update_plate()

    def _update_plate(self, *_):
        self._plate.update(self.x, self.y, self.width, self.height)


class CardHolder(FloatLayout):
    """Transparent shell that wraps any widget in a chamfered plate (no layout intrusion)."""

    def __init__(self, child, radius=None, padding=0, bg=None, border=True,
                 style='panel', accent=None, **kwargs):
        super().__init__(**kwargs)
        self._pad = dp(padding)
        cut = radius if radius is not None else theme.CHAMFER
        self._plate = fx.Plate(style=style, accent_color=accent or theme.VFD_CYAN,
                               bg=bg, border=border, cut_tr=cut, cut_bl=cut)
        self.canvas.before.add(self._plate.group)
        self.bind(pos=self._update_plate, size=self._update_plate)
        self._child = child
        child.pos_hint = {}
        child.size_hint = (None, None)
        self.add_widget(child)
        self.bind(pos=self._layout_child, size=self._layout_child)
        self._update_plate()
        self._layout_child()

    def _update_plate(self, *_):
        self._plate.update(self.x, self.y, self.width, self.height)

    def _layout_child(self, *_):
        p = self._pad
        self._child.x = self.x + p
        self._child.y = self.y + p
        self._child.width = max(0, self.width - p * 2)
        self._child.height = max(0, self.height - p * 2)
