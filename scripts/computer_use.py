#!/usr/bin/env python3
"""Local stdio client for the installed native macOS Computer Use MCP.

Examples:
  python scripts/computer_use.py list
  python scripts/computer_use.py invoke get_app_state '{"app":"WeChat"}'
  python scripts/computer_use.py invoke click '{"app":"WeChat","element_index":"12"}'

Call get_app_state before interacting with an app in each assistant turn. Image
content is written to private local files; stdout contains paths, never base64.
"""

from __future__ import annotations

import argparse
import base64
import collections
import datetime as dt
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid


DEFAULT_CLIENT = (
    Path.home()
    / ".codex/computer-use/Codex Computer Use.app/Contents/SharedSupport"
    / "SkyComputerUseClient.app/Contents/MacOS/SkyComputerUseClient"
)
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "artifacts/computer-use"


class ComputerUseError(RuntimeError):
    pass


class ComputerUseClient:
    """One initialized MCP session. The helper application owns the UI session."""

    def __init__(self, executable: Path = DEFAULT_CLIENT, timeout: float = 45):
        self.executable = executable.expanduser().resolve()
        self.timeout = timeout
        self.process: subprocess.Popen[str] | None = None
        self.messages: queue.Queue[object] = queue.Queue()
        self.diagnostics: collections.deque[str] = collections.deque(maxlen=10)
        self.next_id = 0

    def __enter__(self):
        if not self.executable.is_file():
            raise ComputerUseError(f"Computer Use client does not exist: {self.executable}")
        self.process = subprocess.Popen(
            [str(self.executable), "mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        try:
            self.server_info = self.request(
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "wechat-local-computer-use", "version": "0.1.0"},
                },
            )
            self.notify("notifications/initialized")
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *_):
        self.close()

    def _read_stdout(self):
        assert self.process and self.process.stdout
        try:
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except json.JSONDecodeError:
                    self.messages.put(ComputerUseError("Computer Use emitted invalid JSON on stdout."))
                    return
        finally:
            self.messages.put(ComputerUseError("Computer Use process closed its output."))

    def _read_stderr(self):
        assert self.process and self.process.stderr
        for line in self.process.stderr:
            self.diagnostics.append(line.rstrip())

    def _write(self, message: dict):
        if not self.process or not self.process.stdin:
            raise ComputerUseError("Computer Use client is not started.")
        try:
            self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ComputerUseError("Computer Use process stopped accepting requests.") from exc

    def notify(self, method: str, params: dict | None = None):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._write(message)

    def request(self, method: str, params: dict | None = None):
        self.next_id += 1
        request_id = self.next_id
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                message = self.messages.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise ComputerUseError(
                    f"Computer Use {method} timed out after {self.timeout:g}s. "
                    "An interrupted UI action may already have taken effect; inspect app state before retrying."
                ) from exc
            if isinstance(message, BaseException):
                raise message
            if not isinstance(message, dict):
                raise ComputerUseError("Computer Use returned a non-object JSON-RPC message.")
            if "method" in message and "id" in message:
                reply = {"jsonrpc": "2.0", "id": message["id"]}
                if message["method"] == "ping":
                    reply["result"] = {}
                else:
                    reply["error"] = {"code": -32601, "message": "Method not supported by this client"}
                self._write(reply)
                continue
            if message.get("id") != request_id:
                continue  # Progress and other server notifications.
            if "error" in message:
                error = message["error"]
                raise ComputerUseError(f"MCP error: {json.dumps(error, ensure_ascii=False)}")
            if "result" not in message:
                raise ComputerUseError("Computer Use response has neither result nor error.")
            return message["result"]

    def list_tools(self):
        tools = []
        cursor = None
        while True:
            result = self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def invoke(self, name: str, arguments: dict):
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self):
        if self.process:
            if self.process.stdin:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            self.process = None


def save_images(value, output_dir: Path):
    """Replace every MCP image block with metadata and its absolute file path."""
    if isinstance(value, list):
        return [save_images(item, output_dir) for item in value]
    if not isinstance(value, dict):
        return value
    if value.get("type") == "image" and isinstance(value.get("data"), str):
        mime = value.get("mimeType", "application/octet-stream")
        suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime, ".bin")
        try:
            data = base64.b64decode(value["data"], validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ComputerUseError("Computer Use returned invalid image data.") from exc
        output_dir = output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = output_dir / f"screenshot-{timestamp}-{uuid.uuid4().hex[:8]}{suffix}"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        metadata = {key: val for key, val in value.items() if key != "data"}
        metadata.update(path=str(path), bytes=len(data))
        return metadata
    return {key: save_images(item, output_dir) for key, item in value.items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    list_parser = commands.add_parser("list", help="Initialize the local native MCP and print tool schemas.")
    invoke_parser = commands.add_parser("invoke", help="Call one tool. UI actions take effect immediately.")
    invoke_parser.add_argument("tool", help="A tool name returned by list.")
    invoke_parser.add_argument("arguments", help="A JSON object containing tool arguments.")
    for subparser in (list_parser, invoke_parser):
        subparser.add_argument("--client", type=Path, default=DEFAULT_CLIENT)
        subparser.add_argument("--timeout", type=float, default=45)
        subparser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 300:
        parser.error("--timeout must be greater than 0 and at most 300 seconds")
    arguments = {}
    if args.command == "invoke":
        try:
            arguments = json.loads(args.arguments)
        except json.JSONDecodeError as exc:
            parser.error(f"arguments must be valid JSON: {exc.msg}")
        if not isinstance(arguments, dict):
            parser.error("arguments must be a JSON object")
    try:
        with ComputerUseClient(args.client, args.timeout) as client:
            if args.command == "list":
                result = {"serverInfo": client.server_info.get("serverInfo"), "tools": client.list_tools()}
            else:
                result = client.invoke(args.tool, arguments)
        print(json.dumps(save_images(result, args.output_dir), ensure_ascii=False, indent=2))
        return 1 if isinstance(result, dict) and result.get("isError") else 0
    except (ComputerUseError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
