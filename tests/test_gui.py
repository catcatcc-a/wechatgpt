"""GUI safety tests use synthetic OCR snapshots; no desktop input is generated."""

from copy import deepcopy
import asyncio

import pytest

from wechat_local_mcp.config import Config
from wechat_local_mcp.errors import SendNotAttempted
from wechat_local_mcp.gui import GUIBackend, matching_outgoing_count, title_token, visible_lines
from wechat_local_mcp.server import Bridge


def token(text, x, y, confidence=0.98, width=100, height=18):
    return dict(text=text, x=x, y=y, confidence=confidence, width=width, height=height)


def snapshot(*extra, title="文件传输助手"):
    return {
        "window_id": 42, "window": {"X": 0, "Y": 0, "Width": 1000, "Height": 700},
        "screenshot": "/tmp/synthetic-not-a-real-screen.png",
        "tokens": sorted([token(title, 300, 23), *extra], key=lambda item: item["y"]),
    }


def test_title_requires_exact_unambiguous_header_not_sidebar():
    snap = snapshot(token("文件传输助手", 110, 110), title="另外一个人")
    assert title_token(snap, "文件传输助手") is None
    snap = snapshot(token("文件传输助手", 460, 24))
    assert title_token(snap, "文件传输助手") is None
    assert title_token(snapshot(title="文件传输助手 (2)"), "文件传输助手") is None
    snap = snapshot()
    snap["tokens"][0]["confidence"] = 0.7
    assert title_token(snap, "文件传输助手") is None


def test_message_ocr_excludes_sidebar_header_draft_and_send_control():
    snap = snapshot(
        token("side preview", 110, 220), token("incoming", 350, 220),
        token("outgoing", 760, 275), token("draft text", 360, 585),
        token("发送", 860, 665),
    )
    lines = visible_lines(snap, title_token(snap, "文件传输助手"))
    assert [line["text"] for line in lines] == ["incoming", "outgoing"]
    assert lines[1]["alignment"] == "right"


def test_duplicate_matching_supports_wrapped_outgoing_but_excludes_draft():
    snap = snapshot(token("你好", 760, 180), token("世界", 760, 201), token("你好世界", 350, 585))
    assert matching_outgoing_count(snap, title_token(snap, "文件传输助手"), "你好世界") == 1
    draft_only = snapshot(token("你好世界", 350, 585))
    assert matching_outgoing_count(draft_only, title_token(draft_only, "文件传输助手"), "你好世界") == 0


def test_outgoing_matching_never_joins_an_incoming_line():
    snap = snapshot(token("hello", 760, 180), token("world", 350, 201))
    assert matching_outgoing_count(snap, title_token(snap, "文件传输助手"), "hello world") == 0


class FakeGUI(GUIBackend):
    """Only exercise Python decision logic, replacing every native helper action."""
    def __init__(self, config, snapshots, input_values):
        super().__init__(config)
        self.snapshots = list(snapshots)
        self.input_values = list(input_values)
        self.actions = []

    async def snapshot(self):
        return deepcopy(self.snapshots.pop(0))

    async def call(self, action, snapshot=None, **kwargs):
        self.actions.append({"action": action, **kwargs})
        if action == "copy_input":
            return {"text": self.input_values.pop(0)}
        return {"ok": True}


@pytest.fixture
def gui_config(tmp_path):
    return Config(backend="gui", data_dir=tmp_path, gui={"enabled": True})


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    async def skip_sleep(_):
        pass
    monkeypatch.setattr("wechat_local_mcp.gui.asyncio.sleep", skip_sleep)


def clicks_on_send(backend):
    return [action for action in backend.actions if action["action"] == "click" and action["y"] > 640]


def staged_snapshot(text="smoke text", title="文件传输助手"):
    return snapshot(token(text, 350, 585), token("发送", 860, 662, width=50), title=title)


async def test_existing_draft_blocks_every_paste_and_send(gui_config):
    backend = FakeGUI(gui_config, [snapshot()], ["user's unsent draft"])
    with pytest.raises(RuntimeError, match="existing draft"):
        await backend.send_text("filehelper", "smoke text")
    assert not clicks_on_send(backend)
    assert not [action for action in backend.actions if action["action"] == "paste"]


async def test_title_changed_after_staging_blocks_send_click(gui_config):
    backend = FakeGUI(gui_config, [snapshot(), staged_snapshot(title="wrong person")], ["", "smoke text"])
    with pytest.raises(RuntimeError, match="chat changed"):
        await backend.send_text("filehelper", "smoke text")
    assert not clicks_on_send(backend)


async def test_existing_identical_message_is_not_false_confirmation(gui_config):
    before = snapshot(token("smoke text", 760, 220))
    backend = FakeGUI(gui_config, [before, staged_snapshot(), before], ["", "smoke text", ""])
    result = await backend.send_text("filehelper", "smoke text")
    assert result["delivery_status"] == "unverified"
    assert result["ui_verified"] is False
    assert len(clicks_on_send(backend)) == 1


async def test_new_outgoing_and_empty_draft_verify_ui_but_not_remote_delivery(gui_config):
    after = snapshot(token("smoke text", 760, 220))
    backend = FakeGUI(gui_config, [snapshot(), staged_snapshot(), after], ["", "smoke text", ""])
    result = await backend.send_text("filehelper", "smoke text")
    assert result["delivery_status"] == "unverified"
    assert result["ui_verified"] is True
    assert result["chat_type_verified"] is False
    assert len(clicks_on_send(backend)) == 1


async def test_gui_request_id_still_deduplicates_after_bridge_restart(gui_config):
    after = snapshot(token("smoke text", 760, 220))
    backend = FakeGUI(gui_config, [snapshot(), staged_snapshot(), after], ["", "smoke text", ""])
    first = await Bridge(gui_config, backend).send_text("filehelper", "smoke text", request_id="gui-retry")
    second = await Bridge(gui_config, backend).send_text("filehelper", "smoke text", request_id="gui-retry")
    assert first["delivery_status"] == "unverified" and first["ui_verified"] is True
    assert second["duplicate_request"]
    assert len(clicks_on_send(backend)) == 1


async def test_unknown_native_error_is_unverified_and_never_retried(gui_config):
    class InterruptedBackend:
        calls = 0
        async def send_text(self, *args):
            self.calls += 1
            raise RuntimeError("GUI action interrupted after a possible click")
    backend = InterruptedBackend()
    bridge = Bridge(gui_config, backend)
    result = await bridge.send_text("filehelper", "uncertain", request_id="interrupted")
    assert result["delivery_status"] == "unverified" and result["transmission"] == "unknown"
    assert not result["automatic_retry"]
    duplicate = await bridge.send_text("filehelper", "uncertain", request_id="interrupted")
    assert duplicate["duplicate_request"] and backend.calls == 1


async def test_known_preflight_failure_is_not_sent_and_recorded(gui_config):
    class NotAttemptedBackend:
        calls = 0
        async def send_text(self, *args):
            self.calls += 1
            raise SendNotAttempted("GUI disabled to avoid affecting the user's desktop")
    backend = NotAttemptedBackend()
    bridge = Bridge(gui_config, backend)
    result = await bridge.send_text("filehelper", "not sent", request_id="disabled")
    assert result["delivery_status"] == "failed"
    assert result["transmission"] == "not_sent"
    assert not result["check_wechat_ui"] and not result["automatic_retry"]
    duplicate = await Bridge(gui_config, backend).send_text("filehelper", "not sent", request_id="disabled")
    assert duplicate["duplicate_request"] and duplicate["transmission"] == "not_sent"
    assert backend.calls == 1


@pytest.mark.parametrize("operation", ["read", "list", "send"])
async def test_gui_disabled_by_default_performs_no_desktop_actions(tmp_path, operation):
    class NoInteractionGUI(GUIBackend):
        async def call(self, *args, **kwargs):
            pytest.fail("Disabled GUI must not invoke its native helper")
        async def snapshot(self):
            pytest.fail("Disabled GUI must not capture or activate WeChat")
    backend = NoInteractionGUI(Config(backend="gui", data_dir=tmp_path))
    with pytest.raises(SendNotAttempted):
        if operation == "read":
            await backend.read_messages("filehelper")
        elif operation == "list":
            await backend.list_chats()
        else:
            await backend.send_text("filehelper", "not sent")


async def test_status_is_not_ready_when_gui_is_disabled(tmp_path):
    class StatusOnlyGUI(GUIBackend):
        async def call(self, action, *args, **kwargs):
            assert action == "status"
            return {"running": True, "accessibility": True, "screen_capture": True}
    result = await StatusOnlyGUI(Config(backend="gui", data_dir=tmp_path)).status()
    assert result["ready"] is False


async def test_cancelled_send_is_persisted_as_unknown_not_silently_repeated(gui_config):
    class CancelledBackend:
        calls = 0
        async def send_text(self, *args):
            self.calls += 1
            raise asyncio.CancelledError()
    backend = CancelledBackend()
    bridge = Bridge(gui_config, backend)
    with pytest.raises(asyncio.CancelledError):
        await bridge.send_text("filehelper", "cancelled", request_id="cancelled")
    result = await bridge.send_text("filehelper", "cancelled", request_id="cancelled")
    assert result["delivery_status"] == "unverified" and result["transmission"] == "unknown"
    assert result["duplicate_request"] and not result["automatic_retry"]
    assert backend.calls == 1
