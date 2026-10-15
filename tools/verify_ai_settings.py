"""Offline regressions for provider drafts, custom models and lazy chat send."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('KIVY_NO_ARGS', '1')
import main
from ai_settings import AISettingsPopup
from ai_chat import AIChatPanel
from llm_config import LLMConfig


class AISettingsTests(unittest.TestCase):
    def make_popup(self):
        cfg = LLMConfig(api_key='test-only', api_base_url='https://api.openai.com/v1',
                        model='my-private-model')
        with patch('ai_settings.LLMConfig.load', return_value=cfg):
            return AISettingsPopup()

    def test_unknown_model_is_not_replaced(self):
        popup = self.make_popup()
        self.assertEqual(popup._selected_model, 'my-private-model')
        popup._read()
        self.assertEqual(popup._cfg.model, 'my-private-model')

    def test_provider_drafts_preserve_credentials_and_custom_model(self):
        popup = self.make_popup()
        popup._apply_preset('通义千问')
        self.assertEqual(popup._key.children[0].text, '')
        popup._key.children[0].text = 'qwen-test'
        popup._model_input.text = 'custom-qwen'
        popup._apply_preset('OpenAI')
        self.assertEqual(popup._key.children[0].text, 'test-only')
        self.assertEqual(popup._model_input.text, 'my-private-model')
        popup._apply_preset('通义千问')
        self.assertEqual(popup._key.children[0].text, 'qwen-test')
        self.assertEqual(popup._model_input.text, 'custom-qwen')

    def test_model_list_does_not_change_selection(self):
        popup = self.make_popup()
        popup._populate_models(['new-model', 'another-model'])
        self.assertEqual(popup._selected_model, 'my-private-model')
        popup._select_model('new-model')
        self.assertEqual(popup._model_input.text, 'new-model')

    def test_first_chat_sends_without_existing_client(self):
        cfg = LLMConfig(api_key='test-only', api_base_url='https://example.test/v1', model='test')
        with patch('ai_chat.LLMConfig.load', return_value=cfg):
            panel = AIChatPanel()
        self.assertIsNone(panel._client)
        panel._fill_prompt('测试消息')
        with patch('ai_chat.threading.Thread') as thread, patch('ai_chat.db.today_summary_text', return_value=''):
            panel._on_send()
            thread.return_value.start.assert_called_once()
        self.assertTrue(panel._busy)
        self.assertTrue(panel._send_button.disabled)
        panel._on_reply(True, '模拟回复')
        self.assertFalse(panel._send_button.disabled)


if __name__ == '__main__':
    unittest.main()
