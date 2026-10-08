"""Unit tests for v1.1 outbound proxy settings (no live API requests)."""
import importlib.util
import pathlib
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
WINDOWS = ROOT / 'packaging' / 'windows'
sys.path.insert(0, str(WINDOWS))

from proxy_network import (
    ProxySelection, configure_child_environment,
    probe_connectivity, select_proxy, validate_network_settings,
)


class ProxyNetworkTests(unittest.TestCase):
    def test_auto_picks_system_proxy_in_user_case(self):
        result = select_proxy('https://api.hostcentral.cc/v1', 'auto',
                              static_lookup=lambda _: 'http://127.0.0.1:7897',
                              pac_lookup=lambda _: (False, None), environ={})
        self.assertEqual(result.proxy_url, 'http://127.0.0.1:7897')
        self.assertIn('Windows', result.source)

    def test_pac_direct_when_no_static_proxy(self):
        result = select_proxy('https://api.example.com/v1', 'auto',
                              static_lookup=lambda _: None,
                              pac_lookup=lambda _: (True, None), environ={})
        self.assertIsNone(result.proxy_url)

    def test_static_proxy_preferred_over_pac(self):
        result = select_proxy('https://api.example.com/v1', 'auto',
                              static_lookup=lambda _: 'http://127.0.0.1:7897',
                              pac_lookup=lambda _: (True, None), environ={})
        self.assertEqual(result.proxy_url, 'http://127.0.0.1:7897')

    def test_pac_proxy_is_selected(self):
        result = select_proxy('https://api.example.com/v1', 'auto',
                              static_lookup=lambda _: None,
                              pac_lookup=lambda _: (True, 'http://127.0.0.1:7897'), environ={})
        self.assertEqual(result.proxy_url, 'http://127.0.0.1:7897')

    def test_direct_ignores_os_and_env_proxies(self):
        result = select_proxy('https://api.example.com/v1', 'direct',
                              static_lookup=lambda _: 'http://bad:8080',
                              pac_lookup=lambda _: (True, 'http://bad:8080'),
                              environ={'HTTPS_PROXY': 'http://bad:8080'})
        self.assertIsNone(result.proxy_url)
        env = configure_child_environment({'HTTPS_PROXY': 'http://bad:8080',
                                           'https_proxy': 'http://bad:8000',
                                           'ALL_PROXY': 'http://bad:8000'}, result)
        self.assertNotIn('HTTPS_PROXY', env)
        self.assertNotIn('ALL_PROXY', env)
        self.assertEqual(env['NO_PROXY'], '*')

    def test_manual_replaces_inherited_proxy(self):
        mode, manual = validate_network_settings('manual', 'http://127.0.0.1:7897')
        result = select_proxy('https://api.example.com/v1', mode, manual)
        env = configure_child_environment({'HTTPS_PROXY': 'http://old.example:7890'}, result)
        self.assertEqual(env['HTTPS_PROXY'], 'http://127.0.0.1:7897')
        self.assertIn('localhost', env['NO_PROXY'])

    def test_manual_requires_valid_address(self):
        for address in ('', 'localhost:7897', 'https://a.test',
                        'http://user:pass@a.test:8080', 'http://a.test:8080/path'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                validate_network_settings('manual', address)

    def test_auto_uses_environment_fallback(self):
        result = select_proxy('https://api.example.com/v1', 'auto',
                              static_lookup=lambda _: None,
                              pac_lookup=lambda _: (False, None),
                              environ={'HTTPS_PROXY': 'http://localhost:7890'})
        self.assertEqual(result.proxy_url, 'http://localhost:7890')

    def test_loopback_is_never_proxied(self):
        result = select_proxy('http://127.0.0.1:8765/health', 'manual', 'http://localhost:7897')
        self.assertIsNone(result.proxy_url)

    def test_connectivity_test_treats_401_as_network_success(self):
        calls = []
        def fake_run(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, '401', '')
        success, message = probe_connectivity('https://api.example.com/v1',
                                              ProxySelection('http://127.0.0.1:7897', 'Windows'),
                                              run=fake_run)
        self.assertTrue(success)
        self.assertIn('401', message)
        args, kwargs = calls[0]
        self.assertIn('--proxy', args)
        self.assertEqual(kwargs['env']['HTTPS_PROXY'], 'http://127.0.0.1:7897')
        self.assertNotIn('Authorization', str(args))
        self.assertNotIn('chat/completions', str(args))

    def test_connectivity_failure_explains_timeout(self):
        def fake_run(args, **kwargs):
            return subprocess.CompletedProcess(args, 28, '000', 'timeout')
        ok, message = probe_connectivity('https://api.example.com/v1',
                                         ProxySelection(None, '直连'), run=fake_run)
        self.assertFalse(ok)
        self.assertIn('curl 28', message)


if __name__ == '__main__':
    unittest.main()
