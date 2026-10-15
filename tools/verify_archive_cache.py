"""Offline regression and timing for archive widget reuse."""
import os
import sys
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('KIVY_NO_ARGS', '1')
import main
import database as db
from panels.archive import ArchivePanel


def finish(panel):
    if panel._build_event is not None:
        panel._build_event.cancel()
    while panel._build_batch(0):
        pass


rows = db.search_catalog(limit=500, item_types=['strength'])
assert rows, 'Catalog is required'
with patch('panels.archive.db.search_catalog', return_value=rows):
    started = perf_counter()
    panel = ArchivePanel(None)
    finish(panel)
    cold_ms = (perf_counter() - started) * 1000
    original = tuple(panel._grid.children)
    panel._scroll.scroll_y = .42
    started = perf_counter()
    for _ in range(20):
        panel._refresh()
    warm_ms = (perf_counter() - started) * 1000 / 20
    assert tuple(panel._grid.children) == original
    assert panel._scroll.scroll_y == .42

with patch('panels.archive.db.search_catalog', return_value=rows[:6]):
    panel._active_filter = 'test-filter'
    panel._refresh()
    finish(panel)
    assert len(panel._grid.children) == 6
    assert all(card in original for card in panel._grid.children)

with patch('panels.archive.db.search_catalog', return_value=list(reversed(rows))):
    panel._active_filter = ''
    panel._refresh()
    finish(panel)
    assert panel._grid.children[-1]._exercise['id'] == rows[-1]['id']
    assert all(card in original for card in panel._grid.children)

print(f'PASS {len(rows)} cards: cold {cold_ms:.1f} ms total, unchanged refresh {warm_ms:.3f} ms')
print('PASS unchanged identity + scroll, filter reuse, usage ordering refresh')
