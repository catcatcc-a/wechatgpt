"""Local macOS GUI backend. OCR observations are not database message records."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import fcntl
import json
from pathlib import Path
import re
import time
import unicodedata

from .config import Config
from .errors import SendNotAttempted

ROOT = Path(__file__).resolve().parents[2]


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def title_token(snapshot: dict, target: str) -> dict | None:
    """Title must be in the chat header, never a matching sidebar row."""
    width = snapshot["window"]["Width"]
    candidates = [t for t in snapshot["tokens"]
                  if t["text"] == target and t["confidence"] >= 0.75
                  and t["y"] < 48 and max(220, width * 0.16) < t["x"] < width * 0.85]
    return candidates[0] if len(candidates) == 1 else None


def visible_lines(snapshot: dict, title: dict) -> list[dict]:
    panel_left = title["x"] - 16
    height = snapshot["window"]["Height"]
    width = snapshot["window"]["Width"]
    lines = []
    for token in snapshot["tokens"]:
        if token["x"] < panel_left + 28 or not 58 < token["y"] < height - 178:
            continue
        lines.append({"text": token["text"], "confidence": token["confidence"],
                      "alignment": "right" if token["x"] > (panel_left + width) / 2 else "left_or_center",
                      "bounds": {k: round(token[k], 2) for k in ("x", "y", "width", "height")}})
    return lines


def matching_outgoing_count(snapshot: dict, title: dict, text: str) -> int:
    # Include all chat rows to support line wrapping, but never draft/input text.
    lines = visible_lines(snapshot, title)
    needle = normalized(text)
    count = 0
    for i, line in enumerate(lines):
        if line["alignment"] != "right" or line["confidence"] < 0.75:
            continue
        joined = ""
        last_y = line["bounds"]["y"]
        for part in lines[i:i + 25]:
            y = part["bounds"]["y"]
            if part["alignment"] != "right" or part["confidence"] < 0.75 or not 0 <= y - last_y <= 35:
                break
            joined += normalized(part["text"])
            if joined == needle:
                count += 1
                break
            if not needle.startswith(joined):
                break
            last_y = y
    return count


class GUIBackend:
    def __init__(self, config: Config):
        self.config = config
        self.enabled = config.gui.get("enabled", False) is True
        self.executable = Path(config.gui.get("executable", ROOT / "bin/wechat-gui"))
        self.artifacts = config.data_dir.parent / "artifacts/gui"
        self._mutex = asyncio.Lock()

    @asynccontextmanager
    async def transaction(self):
        # Multiple MCP clients share a desktop; a process lock serializes them.
        async with self._mutex:
            self.config.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            with (self.config.data_dir / "gui.lock").open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise RuntimeError("Another MCP client is using WeChat. Try after it finishes.") from exc
                try:
                    yield
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def require_enabled(self):
        if not self.enabled:
            raise SendNotAttempted("GUI automation is disabled to avoid interrupting your mouse, keyboard, or current app. Enable it explicitly only when the desktop is idle.")

    async def call(self, action: str, snapshot: dict | None = None, **kwargs) -> dict:
        if action != "status":
            self.require_enabled()
        if not self.executable.is_file():
            raise RuntimeError("GUI helper is not built. Run ./scripts/setup.sh.")
        payload = {"action": action, **kwargs}
        if snapshot:
            payload.update(window_id=snapshot["window_id"], window=snapshot["window"])
        process = await asyncio.create_subprocess_exec(
            str(self.executable), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(json.dumps(payload, ensure_ascii=False).encode()), timeout=35)
        except (TimeoutError, asyncio.CancelledError):
            process.kill()
            await process.wait()
            raise RuntimeError("GUI action interrupted. Inspect WeChat before retrying a send.")
        try:
            result = json.loads(stdout)
        except ValueError as exc:
            raise RuntimeError("GUI helper returned an invalid response.") from exc
        if process.returncode or result.get("error"):
            raise RuntimeError(result.get("error", "GUI helper failed."))
        return result

    async def snapshot(self) -> dict:
        # Keep a bounded set of private screenshots for local verification.
        snap = await self.call("snapshot", directory=str(self.artifacts))
        images = sorted(self.artifacts.glob("wechat-*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in images[40:]:
            old.unlink(missing_ok=True)
        return snap

    async def click(self, snap: dict, token: dict):
        await self.call("click", snap, x=token["x"] + token["width"] / 2,
                        y=token["y"] + token["height"] / 2)

    @staticmethod
    def target(chat_id: str) -> str:
        target = "文件传输助手" if chat_id in {"filehelper", "文件传输助手"} else chat_id.strip()
        if not target or len(target) > 100 or any(c in target for c in "\n\r\t"):
            raise ValueError("Use an exact visible chat name (or filehelper).")
        return target

    async def open_chat(self, chat_id: str) -> tuple[dict, dict]:
        self.require_enabled()
        target = self.target(chat_id)
        snap = await self.snapshot()
        title = title_token(snap, target)
        if title:
            return snap, title
        # A displayed exact chat row is preferable to guessing a search result.
        rows = [t for t in snap["tokens"] if t["text"] == target
                and t["confidence"] >= 0.75 and 50 < t["x"] < 250 and t["y"] > 52]
        if len(rows) > 1:
            raise RuntimeError("Multiple matching chat rows. Give the contact a unique display name.")
        if not rows:
            await self.call("key", snap, key="search")
            await asyncio.sleep(0.2)
            await self.call("paste", snap, text=target, replace=True)
            await asyncio.sleep(0.6)
            snap = await self.snapshot()
            rows = [t for t in snap["tokens"] if t["text"] == target
                    and t["confidence"] >= 0.75 and 50 < t["x"] < 300 and t["y"] > 55]
            if len(rows) != 1:
                await self.call("key", snap, key="escape")
                raise RuntimeError("Could not find exactly one chat with that display name.")
        await self.click(snap, rows[0])
        await asyncio.sleep(0.35)
        snap = await self.snapshot()
        title = title_token(snap, target)
        if not title:
            raise RuntimeError("The opened chat header does not exactly match the target. No message sent.")
        return snap, title

    async def status(self) -> dict:
        status = await self.call("status")
        return {"backend": "gui", **status,
                "gui_enabled": self.enabled,
                "ready": self.enabled and status.get("running") and status.get("accessibility") and status.get("screen_capture"),
                "reason": "GUI requires an idle desktop and explicit enablement" if not self.enabled else "GUI enabled; foreground interaction required",
                "read_scope": "Visible chat text via local OCR; not full history or background callbacks",
                "send_scope": "Text via visible WeChat UI; exact display-name header verification",
                "limitations": ["WeChat must be logged in and desktop unlocked", "OCR can misread text",
                                "GUI operations use the foreground window; avoid concurrent mouse/keyboard input"]}

    async def list_chats(self, limit: int = 50) -> dict:
        self.require_enabled()
        async with self.transaction():
            snap = await self.snapshot()
            rows = [t for t in snap["tokens"] if 70 < t["x"] < 215 and 55 < t["y"] < snap["window"]["Height"] - 20]
            return {"backend": "gui", "scope": "visible_sidebar_ocr", "observations": rows[:limit],
                    "note": "Sidebar contains both chat names and previews; these are OCR observations, not canonical chat IDs.",
                    "screenshot": snap["screenshot"]}

    async def read_messages(self, chat_id: str, limit: int = 50) -> dict:
        self.require_enabled()
        async with self.transaction():
            snap, title = await self.open_chat(chat_id)
            lines = visible_lines(snap, title)
            return {"backend": "gui", "chat_id": chat_id, "observed_chat": title["text"],
                    "scope": "visible_text_ocr", "messages": lines[-limit:],
                    "note": "Each item is an OCR text line; may include timestamps or text inside images. No server message IDs.",
                    "screenshot": snap["screenshot"], "observed_at": time.time()}

    async def input_text(self, snap: dict, title: dict) -> str:
        await self.call("click", snap, x=title["x"] + 85, y=snap["window"]["Height"] - 115)
        result = await self.call("copy_input", snap)
        return result["text"]

    async def send_text(self, chat_id: str, text: str, chat_type: str = "private") -> dict:
        self.require_enabled()
        if not text.strip() or len(text) > 2000:
            raise SendNotAttempted("GUI messages must contain 1–2000 characters.")
        if "\x00" in text:
            raise SendNotAttempted("NUL is not permitted in a message.")
        attempted = False
        try:
            async with self.transaction():
                snap, title = await self.open_chat(chat_id)
                before_count = matching_outgoing_count(snap, title, text)
                existing = await self.input_text(snap, title)
                if existing:
                    raise SendNotAttempted("The target chat has an existing draft. Preserved it and cancelled sending.")
                await self.call("paste", snap, text=text)
                staged = await self.call("copy_input", snap)
                if staged["text"] != text:
                    raise SendNotAttempted("Draft content did not match the requested text. No send click was made.")
                staged_snap = await self.snapshot()
                staged_title = title_token(staged_snap, self.target(chat_id))
                if not staged_title:
                    raise SendNotAttempted("The chat changed before sending. No send click was made.")
                buttons = [t for t in staged_snap["tokens"] if t["text"] in {"发送", "Send"}
                           and t["confidence"] >= 0.75 and t["x"] > staged_snap["window"]["Width"] * 0.80
                           and t["y"] > staged_snap["window"]["Height"] - 65]
                if len(buttons) != 1:
                    raise SendNotAttempted("Cannot identify the Send button unambiguously. Draft left intact.")
                # One click only. A failure from this point can still mean it was sent.
                attempted = True
                await self.click(staged_snap, buttons[0])
                await asyncio.sleep(0.6)
                after = await self.snapshot()
                after_title = title_token(after, self.target(chat_id))
                count = matching_outgoing_count(after, after_title, text) if after_title else 0
                draft_empty = (await self.input_text(after, after_title) == "") if after_title else False
                observed = bool(after_title and draft_empty and count > before_count)
                return {"backend": "gui", "chat_id": chat_id,
                        "observed_chat": after_title["text"] if after_title else None,
                        "delivery_status": "unverified", "ui_verified": observed,
                        "chat_type_verified": False, "transmission": "send_clicked",
                        "verification": "New matching outgoing text appeared in the GUI and input is empty" if observed
                                        else "Send clicked once; could not verify a new matching outgoing text. Inspect screenshot before any retry.",
                        "delivery_semantics": "GUI observation only; does not prove remote receipt",
                        "screenshot": after["screenshot"], "sent_at": time.time(), "automatic_retry": False}
        except SendNotAttempted:
            raise
        except Exception as exc:
            if not attempted:
                raise SendNotAttempted(str(exc)) from exc
            raise
