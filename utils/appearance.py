"""Persistent appearance preference, independent of AI credentials."""
import json
import os

from kivy.event import EventDispatcher
from kivy.properties import BooleanProperty
from utils.platform import _data_dir


class Appearance(EventDispatcher):
    enhanced = BooleanProperty(True)

    def __init__(self):
        super().__init__()
        try:
            with open(self.path, encoding='utf-8') as stream:
                self.enhanced = json.load(stream).get('theme', 'enhanced') != 'classic'
        except (OSError, ValueError, AttributeError):
            pass

    @property
    def path(self):
        return os.path.join(_data_dir(), 'appearance.json')

    def select(self, name):
        if name not in ('classic', 'enhanced'):
            raise ValueError('Unknown theme')
        # Save first: a failed write must not silently pretend persistence succeeded.
        temporary = self.path + '.tmp'
        with open(temporary, 'w', encoding='utf-8') as stream:
            json.dump({'theme': name}, stream)
        os.replace(temporary, self.path)
        self.enhanced = name == 'enhanced'


state = Appearance()
