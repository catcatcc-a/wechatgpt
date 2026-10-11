#!/usr/bin/env python3
"""Exercise the actual MCP stdio protocol. Sending is opt-in, to filehelper only."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(args):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "wechat_local_mcp.server", "serve", "--config", str(args.config.resolve())],
        env=os.environ.copy(),
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as client:
            initialized = await client.initialize()
            print(json.dumps({"server": initialized.serverInfo.model_dump()}, ensure_ascii=False))
            tools = await client.list_tools()
            print(json.dumps({"tools": [tool.name for tool in tools.tools]}, ensure_ascii=False))
            async def call(name, parameters):
                result = await client.call_tool(name, parameters)
                value = {"tool": name, "is_error": result.isError,
                         "result": result.structuredContent or [block.model_dump() for block in result.content]}
                print(json.dumps(value, ensure_ascii=False))
                if result.isError:
                    raise RuntimeError(f"MCP tool failed: {name}")
                return value
            await call("wechat_status", {})
            if args.list_chats:
                await call("wechat_list_chats", {"limit": 10})
            if args.read:
                await call("wechat_read_messages", {"chat_id": "filehelper", "limit": 10})
            if args.send:
                await call("wechat_send_text", {
                    "chat_id": "filehelper", "text": args.send,
                    "request_id": args.request_id or f"smoke-{uuid.uuid4()}",
                })
                await call("wechat_read_messages", {"chat_id": "filehelper", "limit": 10})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config.toml")
    parser.add_argument("--read", action="store_true", help="Read visible/cached File Transfer Assistant messages")
    parser.add_argument("--list-chats", action="store_true", help="List visible/cached chat names")
    parser.add_argument("--send", metavar="TEXT", help="Explicitly send TEXT to File Transfer Assistant once")
    parser.add_argument("--request-id", help="Stable send request ID; reuse it to avoid repeating a send")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
