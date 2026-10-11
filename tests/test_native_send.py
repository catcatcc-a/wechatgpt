import importlib.util
import json
from pathlib import Path
import sys

import httpx
import pytest

from wechat_local_mcp.config import Config
from wechat_local_mcp.onebot import OneBotBackend
from wechat_local_mcp.server import Bridge
from wechat_local_mcp.store import Store

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_send', ROOT / 'scripts/native-send.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.mark.parametrize('chat,text', [('姓名', 'hello'), ('filehelper', ''), ('filehelper', 'x\0x'), ('filehelper', '😀' * 1001)])
def test_reject_invalid_native_input_before_attach(chat, text):
    with pytest.raises(ValueError):
        helper.validate({'chat_id': chat, 'text': text})


def test_native_input_preserves_literal_text():
    text = '你好 $HOME `echo test` $(echo test)\n😀'
    assert helper.validate({'chat_id': 'filehelper', 'text': text}) == ('filehelper', text)


async def test_native_command_uses_stdin_and_bridge_deduplicates(tmp_path):
    helper_path = tmp_path / 'helper.py'
    count = tmp_path / 'calls.txt'
    helper_path.write_text('import sys,json,pathlib\np=json.load(sys.stdin)\n'
                          f'pathlib.Path({str(count)!r}).open("a").write("1\\n")\n'
                          'print(json.dumps({"transmission":"accepted","delivery_status":"unverified","desktop_send_echo":True,"received":p}))\n')
    config = Config(data_dir=tmp_path, native_sender_command=(sys.executable, str(helper_path)))
    def unexpected_request(request):
        raise AssertionError('Native sends must not fall back to the old network hook')
    backend = OneBotBackend(config, Store(config.database), transport=httpx.MockTransport(unexpected_request))
    bridge = Bridge(config, backend)
    text = '你好 $HOME `echo test` $(echo test)\n😀'
    first = await bridge.send_text('filehelper', text, request_id='native-idempotency')
    second = await bridge.send_text('filehelper', text, request_id='native-idempotency')
    assert first['received']['text'] == text
    assert first['desktop_send_echo'] is True
    assert second['transmission'] == 'accepted'
    assert count.read_text().splitlines() == ['1']


async def test_native_crash_is_unknown_without_fallback(tmp_path):
    config = Config(data_dir=tmp_path, native_sender_command=(sys.executable, '-c', 'raise SystemExit(1)'))
    result = await OneBotBackend(config, Store(config.database)).send_text('filehelper', 'test')
    assert result['transmission'] == 'unknown'
    assert result['automatic_retry'] is False


async def test_missing_native_helper_is_not_sent(tmp_path):
    config = Config(data_dir=tmp_path, native_sender_command=(str(tmp_path/'missing'), 'helper.py'))
    result = await OneBotBackend(config, Store(config.database)).send_text('filehelper', 'test')
    assert result['transmission'] == 'not_sent'
