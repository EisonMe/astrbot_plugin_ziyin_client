from __future__ import annotations
import asyncio
import importlib.util
import json
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
    def image_result(self, path): return path


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
        for name in ('ziyin_client_run', 'ziyin_client_status', 'ziyin_client_cancel', 'ziyin_client_files', 'ziyin_client_desktop_input'):
            item = llm_tools.get_func(name)
            self.assertIsNotNone(item, name)
            self.assertTrue(item.parameters.get('properties'), name)
        for name in ('ziyin_client_health', 'ziyin_client_desktop_status', 'ziyin_client_screenshot'):
            self.assertIsNotNone(llm_tools.get_func(name), name)

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

    def test_task_list_truncation_keeps_valid_json(self):
        class Client:
            async def list_tasks(self):
                return [{'id': str(i), 'status': 'completed', 'exitCode': 0} for i in range(20)]
        self.plugin.config.update(allowed_users=['test:123'], max_output_chars=100)
        self.plugin.client = lambda: Client()
        result = json.loads(asyncio.run(self.plugin.status(FakeEvent())))
        self.assertTrue(result['ok'])
        self.assertTrue(result['truncated'])
        self.assertEqual(result['count'], 20)
        self.assertGreaterEqual(len(result['tasks']), 1)

    def test_file_list_truncation_keeps_whole_entries(self):
        class Client:
            async def list_files(self, path):
                return [{'name': f'long filename {i}', 'size': 1} for i in range(20)]
        self.plugin.config.update(allowed_users=['test:123'], max_output_chars=60)
        self.plugin.client = lambda: Client()
        result = json.loads(asyncio.run(self.plugin.files(FakeEvent(), 'list')))
        self.assertTrue(result['ok'])
        self.assertTrue(result['truncated'])
        self.assertEqual(result['entries'][0]['name'], 'long filename 0')

    def test_file_delete_requires_admin_and_opt_in(self):
        class Client:
            deleted = False
            async def delete_file(self, path):
                self.deleted = True
        client = Client()
        self.plugin.client = lambda: client
        self.plugin.config['allowed_users'] = ['test:123']
        result = json.loads(asyncio.run(self.plugin.files(FakeEvent(), 'delete', 'a.txt')))
        self.assertFalse(result['ok'])
        self.plugin.config['allow_file_write'] = True
        result = json.loads(asyncio.run(self.plugin.files(FakeEvent(), 'delete', 'a.txt')))
        self.assertFalse(result['ok'])
        self.assertFalse(client.deleted)
        result = json.loads(asyncio.run(self.plugin.files(FakeEvent(admin=True, sender='999'), 'delete', 'a.txt')))
        self.assertTrue(result['ok'])
        self.assertTrue(client.deleted)

    def test_desktop_input_requires_opt_in_and_valid_action(self):
        class Client:
            called = False
            async def desktop_input(self, *args):
                self.called = True
                return {'message': 'ok'}
        client = Client()
        self.plugin.client = lambda: client
        self.plugin.config['allowed_users'] = ['test:123']
        event = FakeEvent()
        self.assertFalse(json.loads(asyncio.run(self.plugin.desktop_input(event, 'click')))['ok'])
        self.plugin.config['allow_desktop_control'] = True
        self.assertFalse(json.loads(asyncio.run(self.plugin.desktop_input(event, 'invalid')))['ok'])
        self.assertFalse(client.called)
        self.assertTrue(json.loads(asyncio.run(self.plugin.desktop_input(event, 'click')))['ok'])
        self.assertTrue(client.called)

    def test_screenshot_is_sent_and_temp_file_is_removed(self):
        class Client:
            async def screenshot(self):
                return b'\x89PNG\r\n\x1a\n' + b'picture'
        self.plugin.client = lambda: Client()
        self.plugin.config.update(allowed_users=['test:123'], allow_desktop_control=True)

        async def check():
            result = self.plugin.screenshot(FakeEvent())
            path = Path(await anext(result))
            self.assertTrue(path.is_file())
            message = json.loads(await anext(result))
            self.assertTrue(message['ok'])
            self.assertFalse(path.exists())
            await result.aclose()

        asyncio.run(check())


if __name__ == '__main__':
    unittest.main()
