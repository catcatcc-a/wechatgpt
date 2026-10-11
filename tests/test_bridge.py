import hashlib
import hmac
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from wechat_local_mcp.config import Config, load_config
from wechat_local_mcp.onebot import OneBotBackend
from wechat_local_mcp.server import Bridge
from wechat_local_mcp.store import Store
from wechat_local_mcp.webhook import create_app


@pytest.fixture
def config(tmp_path):
    return Config(data_dir=tmp_path, onebot_token="unit-test-token")


@pytest.fixture
def store(config):
    return Store(config.database)


def event(message_id="100", text="测试中文 🔎"):
    return {"post_type": "message", "message_type": "private", "self_id": "wxid_self", "user_id": "filehelper", "message_id": message_id, "time": 12345678, "message": [{"type": "text", "data": {"text": text}}]}


async def test_signed_webhook_deduplicates_and_reads_unicode(config, store):
    app = create_app(config, store)
    body = json.dumps(event(), ensure_ascii=False).encode()
    signature = "sha1=" + hmac.new(config.onebot_token.encode(), body, hashlib.sha1).hexdigest()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        assert (await client.post("/onebot", content=body)).status_code == 401
        good = await client.post("/onebot", content=body, headers={"X-Signature": signature})
        assert good.status_code == 200 and not good.json()["duplicate"]
        again = await client.post("/onebot", content=body, headers={"X-Signature": signature})
        assert again.json()["duplicate"]
        changed = await client.post("/onebot", content=body + b" ", headers={"X-Signature": signature})
        assert changed.status_code == 401
    records = store.messages("filehelper")
    assert len(records) == 1 and records[0]["text"] == "测试中文 🔎"
    assert records[0]["message_id"] == "100"
    assert store.path.stat().st_mode & 0o777 == 0o600


async def test_webhook_health_requires_bearer_token(config, store):
    store.ingest(event())
    app = create_app(config, store)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        unauthorized = await client.get("/health")
        assert unauthorized.status_code == 401
        assert "cached_messages" not in unauthorized.json()
        assert "last_received_at" not in unauthorized.json()
        assert (await client.get("/health", headers={"Authorization": "Bearer wrong"})).status_code == 401
        response = await client.get("/health", headers={"Authorization": "Bearer " + config.onebot_token})
        assert response.status_code == 200 and response.json()["cached_messages"] == 1
        duplicate = await client.get("/health", headers=[("Authorization", "Bearer " + config.onebot_token), ("Authorization", "Bearer wrong")])
        assert duplicate.status_code == 401
        non_ascii = await client.get("/health", headers=[(b"Authorization", b"Bearer \xff")])
        assert non_ascii.status_code == 401


async def test_webhook_health_fails_closed_without_token(config, store):
    app = create_app(replace(config, onebot_token=""), store)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        response = await client.get("/health", headers={"Authorization": "Bearer "})
        assert response.status_code == 503
        assert "cached_messages" not in response.json()


async def test_webhook_rejects_duplicate_and_non_ascii_signatures(config, store):
    app = create_app(config, store)
    body = json.dumps(event()).encode()
    signature = "sha1=" + hmac.new(config.onebot_token.encode(), body, hashlib.sha1).hexdigest()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        for headers in [[("X-Signature", signature), ("X-Signature", "wrong")], [(b"X-Signature", b"\xff")]]:
            response = await client.post("/onebot", content=body, headers=headers)
            assert response.status_code == 401
    assert store.stats()["cached_messages"] == 0


def test_incremental_cursor_is_ordered_without_skipping(store):
    for i in range(1, 7):
        store.ingest(event(str(i), str(i)))
    assert [m["text"] for m in store.messages(limit=2)] == ["5", "6"]
    assert [m["text"] for m in store.messages(limit=2, after_id=1)] == ["2", "3"]
    assert [m["text"] for m in store.messages(limit=2, after_id=3)] == ["4", "5"]


@pytest.mark.parametrize("original,expected", [
    (1791691200, 1791691200.0),
    (1791691200.125, 1791691200.125),
    (1791691200125, 1791691200.125),
    ("1791691200125", 1791691200.125),
    (0, 0.0),
])
def test_callback_time_is_unix_seconds_and_raw_event_is_preserved(store, original, expected):
    incoming = {**event(), "time": original}
    store.ingest(incoming)
    assert store.messages()[0]["timestamp"] == expected
    with store.connect() as db:
        raw = json.loads(db.execute("SELECT event_json FROM messages").fetchone()["event_json"])
    assert raw["time"] == original


def test_existing_millisecond_cache_migrates_only_once(store):
    original = 1791691200125
    store.ingest({**event(), "time": original})
    with store.connect() as db:
        db.execute("UPDATE messages SET timestamp = ?", (original,))
    reopened = Store(store.path)
    assert reopened.messages()[0]["timestamp"] == 1791691200.125
    reopened = Store(store.path)
    assert reopened.messages()[0]["timestamp"] == 1791691200.125
    with reopened.connect() as db:
        raw = json.loads(db.execute("SELECT event_json FROM messages").fetchone()["event_json"])
    assert raw["time"] == original


@pytest.mark.parametrize("status,state,ready", [
    (200, {"hook_verified": True, "send_template_ready": True}, True),
    (200, {"hook_verified": False, "send_template_ready": True}, False),
    (200, {"hook_verified": True, "send_template_ready": False}, False),
    (401, {}, False), (404, {}, False),
])
async def test_status_checks_authenticated_live_hook(config, store, status, state, ready):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=state)
    backend = OneBotBackend(config, store, httpx.MockTransport(handler))
    result = await backend.status()
    assert result["api_reachable"] is (status == 200)
    assert result["ready"] is ready and result["login_verified"] is False
    assert calls[0].url.path == "/local_status" and calls[0].method == "GET"
    assert calls[0].headers["authorization"] == "Bearer unit-test-token"


def test_phone_filehelper_routing_preserves_sender_and_dedup(store):
    incoming = {**event("phone-filehelper", "mcp接收测试"), "self_id": "filehelper", "user_id": "wxid_self"}
    first = store.ingest(incoming)
    assert not first["duplicate"]
    assert store.messages("filehelper")[0]["sender_id"] == "wxid_self"
    # Simulate a cache created before the routing fix.
    with store.connect() as db:
        db.execute("UPDATE messages SET chat_id = 'wxid_self'")
    reopened = Store(store.path)
    assert reopened.ingest(incoming)["duplicate"]
    assert len(reopened.messages("filehelper")) == 1
    assert reopened.messages("wxid_self") == []


async def test_cached_read_declares_timestamp_units(config, store):
    store.ingest({**event(), "time": 1791691200125})
    result = await OneBotBackend(config, store).read_messages("filehelper")
    assert result["timestamp_unit"] == "unix_seconds"
    assert result["messages"][0]["timestamp"] == 1791691200.125


async def test_onebot_send_auth_correct_payload_and_no_delivery_claim(config, store):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"status": "ok"})
    backend = OneBotBackend(config, store, httpx.MockTransport(handler))
    result = await backend.send_text("filehelper", "你好")
    assert len(requests) == 1
    assert requests[0].url.path == "/send_private_msg"
    assert requests[0].headers["Authorization"] == "Bearer unit-test-token"
    assert json.loads(requests[0].content) == {"user_id": "filehelper", "message": [{"type": "text", "data": {"text": "你好"}}]}
    assert result["delivery_status"] == "unverified" and result["transmission"] == "accepted"


async def test_timeout_does_not_retry(config, store):
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        raise httpx.ReadTimeout("timed out after sending", request=request)
    backend = OneBotBackend(config, store, httpx.MockTransport(handler))
    result = await backend.send_text("filehelper", "one attempt")
    assert count == 1
    assert result["delivery_status"] == "unverified" and not result["automatic_retry"]


async def test_request_id_is_durable_and_rejects_payload_change(config, store):
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(200, json={"status": "ok"})
    backend = OneBotBackend(config, store, httpx.MockTransport(handler))
    bridge = Bridge(config, backend)
    first = await bridge.send_text("filehelper", "same", request_id="stable-request")
    restarted = Bridge(config, backend)
    second = await restarted.send_text("filehelper", "same", request_id="stable-request")
    assert count == 1 and second["duplicate_request"]
    assert first["request_id"] == "stable-request"
    with pytest.raises(ValueError, match="different message"):
        await restarted.send_text("another_user", "same", request_id="stable-request")


def test_config_relative_secret_file_and_loopback_only(tmp_path, monkeypatch):
    monkeypatch.delenv("WECHAT_ONEBOT_TOKEN", raising=False)
    (tmp_path / "secret").write_text("test-token\n")
    config_path = tmp_path / "config.toml"
    config_path.write_text('[onebot]\ntoken_file="secret"\n')
    cfg = load_config(config_path)
    assert cfg.onebot_token == "test-token" and cfg.data_dir == tmp_path / "data"
    assert "test-token" not in repr(cfg)
    config_path.write_text('[onebot]\nurl="http://0.0.0.0:58080"\n')
    with pytest.raises(ValueError, match="loopback"):
        load_config(config_path)
