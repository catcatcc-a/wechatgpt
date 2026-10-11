import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_official_mcp_stdio_handshake_and_tools(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('backend="onebot"\n[onebot]\nurl="http://127.0.0.1:1"\ntimeout=0.2\n')
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "wechat_local_mcp.server", "serve", "--config", str(config)],
        env=os.environ.copy(),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == {"wechat_status", "wechat_list_chats", "wechat_read_messages", "wechat_send_text", "wechat_send_status"}
            response = await client.call_tool("wechat_read_messages", {"chat_id": "filehelper"})
            assert not response.isError
            assert response.structuredContent["messages"] == []
            response = await client.call_tool("wechat_send_text", {"chat_id": "", "text": "do not send"})
            assert response.isError
