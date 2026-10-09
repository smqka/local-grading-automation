"""Launcher config tests for thinking switch and backwards compatibility."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WINDOWS = Path(__file__).resolve().parents[1] / 'packaging' / 'windows'
sys.path.insert(0, str(WINDOWS))
spec = importlib.util.spec_from_file_location('launcher_v12', WINDOWS / 'launcher.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class ThinkingConfigTests(unittest.TestCase):
    def test_mode_validation(self):
        self.assertEqual(launcher.validate_thinking_mode(' ON '), 'on')
        self.assertEqual(launcher.validate_thinking_mode('off'), 'off')
        with self.assertRaises(ValueError):
            launcher.validate_thinking_mode('maybe')

    def test_model_family_detection(self):
        self.assertTrue(launcher.is_qwen_thinking_model('qwen3.7-flash-2026-07-15'))
        self.assertTrue(launcher.is_qwen_thinking_model('qwen3.7-plus'))
        self.assertFalse(launcher.is_qwen_thinking_model('gpt-6.1-sol'))

    def test_old_v11_config_defaults_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'config.json').write_text(json.dumps({
                'version': 2,
                'network_mode': 'direct',
                'proxy_url': '',
                'base_url': 'https://example.com/v1',
                'model': 'qwen3.7-flash-2026-07-15',
                'api_key_dpapi': 'fake-encrypted',
            }), encoding='utf-8')
            with patch.object(launcher, 'user_data_dir', return_value=Path(tmp)), \
                 patch.object(launcher, '_dpapi_decrypt', return_value='test-key'):
                config = launcher.load_config()
        self.assertEqual(config['thinking_mode'], 'off')

    def test_saved_mode_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(launcher, 'user_data_dir', return_value=Path(tmp)), \
                 patch.object(launcher, '_dpapi_encrypt', return_value='encrypted'), \
                 patch.object(launcher, '_dpapi_decrypt', return_value='test-key'):
                launcher.save_config({
                    'base_url': 'https://example.com/v1',
                    'model': 'qwen3.7-flash-2026-07-15',
                    'api_key': 'test-key',
                    'network_mode': 'direct',
                    'proxy_url': '',
                    'thinking_mode': 'on',
                })
                config = launcher.load_config()
                self.assertEqual(config['thinking_mode'], 'on')
                data = json.loads((Path(tmp) / 'config.json').read_text(encoding='utf-8'))
                self.assertEqual(data['api_key_dpapi'], 'encrypted')
                self.assertNotIn('api_key', data)
                self.assertEqual(data['version'], 3)


if __name__ == '__main__':
    unittest.main()
