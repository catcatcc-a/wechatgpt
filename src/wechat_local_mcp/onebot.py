"""Adapter for the actual wechat_chatter OneBot subset, not hypothetical APIs."""

import asyncio
import json
import httpx

from .config import Config
from .store import Store


class OneBotBackend:
    def __init__(self, config: Config, store: Store, transport=None):
        self.config, self.store, self.transport = config, store, transport

    def client(self):
        return httpx.AsyncClient(
            base_url=self.config.onebot_url,
            headers={"Authorization": f"Bearer {self.config.onebot_token}"},
            timeout=self.config.request_timeout,
            transport=self.transport,
            follow_redirects=False,
            trust_env=False,
        )

    async def status(self) -> dict:
        state = {}
        try:
            async with self.client() as client:
                response = await client.get("/local_status")
            reachable = response.status_code == 200
            if reachable:
                state = response.json()
                if not isinstance(state, dict):
                    raise ValueError("Invalid hook status response")
            error = None if reachable else f"Hook status HTTP {response.status_code}"
        except (httpx.HTTPError, ValueError) as exc:
            reachable, error = False, str(exc)
        hook = reachable and state.get("hook_verified") is True
        template = hook and state.get("send_template_ready") is True
        return {
            "backend": "onebot", "reachable": reachable, "error": error,
            "api_reachable": reachable, "ready": template,
            "hook_verified": hook, "send_template_ready": template,
            "login_verified": False,
            "status_scope": "Authenticated live hook probe; ready means the hook and send template are available. Login is verified by actual message traffic, not an independent login API.",
            "endpoint": self.config.onebot_url,
            "token_configured": bool(self.config.onebot_token),
            "delivery_verification": "server_ack_then_recipient_confirmation",
            "desktop_send_echo": bool(self.config.native_sender_command),
            "send_backend": "wechat_native" if self.config.native_sender_command else "onebot_network_hook",
            "history_scope": "messages received by the local webhook since it was started",
            **self.store.stats(),
        }

    async def list_chats(self, limit: int = 50) -> dict:
        return {"chats": self.store.chats(limit), "source": "local_webhook_cache", "complete_contact_list": False}

    async def read_messages(self, chat_id: str = "", limit: int = 50, after_id: int = 0) -> dict:
        messages = self.store.messages(chat_id, limit, after_id)
        return {
            "messages": messages, "source": "local_webhook_cache",
            "timestamp_unit": "unix_seconds",
            "next_cursor": max((item["id"] for item in messages), default=after_id),
            "history_scope": "received webhook events only; no historical database import",
        }

    async def send_text(self, chat_id: str, text: str, chat_type: str = "private") -> dict:
        if self.config.native_sender_command:
            return await self.send_native(chat_id, text, chat_type)
        if not self.config.onebot_token:
            return {"delivery_status": "failed", "transmission": "not_sent", "error": "Set WECHAT_ONEBOT_TOKEN or onebot.token_file before using OneBot"}
        field = "group_id" if chat_type == "group" else "user_id"
        payload = {field: chat_id, "message": [{"type": "text", "data": {"text": text}}]}
        try:
            async with self.client() as client:
                response = await client.post(f"/send_{chat_type}_msg", json=payload)
        except httpx.HTTPError as exc:
            # A timeout can occur after WeChat sent a message. Never retry implicitly.
            return {"delivery_status": "unverified", "transmission": "unknown", "error": str(exc), "check_wechat_ui": True, "automatic_retry": False}
        try:
            body = response.json()
        except ValueError:
            body = {"error": response.text[:500]}
        if response.is_success and isinstance(body, dict) and body.get("status") == "ok":
            return {
                "delivery_status": "unverified", "transmission": "accepted",
                "chat_id": chat_id, "chat_type": chat_type, "upstream_response": body,
                "check_wechat_ui": True, "automatic_retry": False,
                "message": "OneBot received a server acknowledgement. Remote receipt still needs recipient confirmation; this hook does not add a sent bubble to desktop WeChat.",
                "desktop_send_echo": False, "check_recipient": True,
            }
        rejected = response.status_code in {400, 401, 403, 404, 405, 413, 422}
        return {
            "delivery_status": "failed" if rejected else "unverified",
            "transmission": "rejected" if rejected else "unknown",
            "http_status": response.status_code, "upstream_response": body,
            "automatic_retry": False, "check_wechat_ui": not rejected,
        }

    async def send_native(self, chat_id: str, text: str, chat_type: str) -> dict:
        try:
            process = await asyncio.create_subprocess_exec(
                *self.config.native_sender_command, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except OSError as exc:
            return {"delivery_status": "failed", "transmission": "not_sent", "error": str(exc), "automatic_retry": False}
        # Shield communication so cancellation never kills a send or triggers a
        # second attempt. The enclosing Bridge ledger keeps its outcome unknown.
        communication = asyncio.create_task(process.communicate(json.dumps({"chat_id": chat_id, "text": text}).encode()))
        try:
            stdout, _ = await asyncio.wait_for(asyncio.shield(communication), timeout=35)
        except TimeoutError:
            return {"delivery_status": "unverified", "transmission": "unknown", "automatic_retry": False,
                    "error": "Native send is still running; inspect the recipient chat before any new request."}
        try:
            result = json.loads(stdout)
            if not isinstance(result, dict):
                raise ValueError("Expected a result object")
        except ValueError:
            return {"delivery_status": "unverified", "transmission": "unknown", "automatic_retry": False,
                    "error": "Native helper ended without a valid result"}
        result["chat_type"] = chat_type
        return result
