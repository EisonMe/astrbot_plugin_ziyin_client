from __future__ import annotations
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASTRBOT = Path('/root/AstrBot')
sys.path.insert(0, str(ASTRBOT))
spec = importlib.util.spec_from_file_location(
    'astrbot_plugin_ziyin_client', ROOT / '__init__.py',
    submodule_search_locations=[str(ROOT)],
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
from astrbot_plugin_ziyin_client.main import ZiYinClientPlugin  # noqa: E402


class FakeEvent:
    def __init__(self, admin=False, private=True, sender='123'):
        self.admin, self.private, self.sender = admin, private, sender
        self.unified_msg_origin = 'test:private:123'
    def is_private_chat(self): return self.private
    def get_platform_id(self): return 'test'
    def get_sender_id(self): return self.sender
    def is_admin(self): return self.admin


class FakeConfig:
    def get(self, key, default=None):
        return {'admins_id': ['999']}.get(key, default)


class FakeContext:
    def get_config(self, umo=None): return FakeConfig()


class PluginContractTests(unittest.TestCase):
    def setUp(self):
        self.plugin = ZiYinClientPlugin.__new__(ZiYinClientPlugin)
        self.plugin.config = {'enabled': True, 'allowed_users': [], 'allow_group': False}
        self.plugin.context = FakeContext()

    def test_registered_tools_have_parsed_parameters(self):
        from astrbot.core.provider.register import llm_tools
        for name in ('ziyin_client_run', 'ziyin_client_status', 'ziyin_client_cancel', 'ziyin_client_files'):
            item = llm_tools.get_func(name)
            self.assertIsNotNone(item, name)
            self.assertTrue(item.parameters.get('properties'), name)

    def test_admin_role_without_configured_admin_id_is_denied(self):
        with self.assertRaisesRegex(ValueError, '管理员'):
            self.plugin.owner(FakeEvent(admin=True, sender='123'))

    def test_configured_admin_is_allowed(self):
        self.assertTrue(self.plugin.owner(FakeEvent(admin=True, sender='999')))

    def test_explicit_user_allowlist_is_allowed(self):
        self.plugin.config['allowed_users'] = ['test:123']
        self.assertTrue(self.plugin.owner(FakeEvent(sender='123')))

    def test_group_denied_by_default(self):
        with self.assertRaisesRegex(ValueError, '私聊'):
            self.plugin.owner(FakeEvent(private=False, sender='123'))


if __name__ == '__main__': unittest.main()
