# 后台服务维护

本项目的后台服务由两个用户级 LaunchAgent 组成：

- `local.wechat-mcp.onebot`：连接微信 Gadget，提供本机 OneBot HTTP/WS。
- `local.wechat-mcp.webhook`：接收 OneBot 回调并写入 MCP 的 SQLite 缓存。

完整安装步骤见 [README](../README.md)。本页用于日常检查和开发更新。

登录后自启动、正常退出微信时的行为及停用步骤见 [日常使用](daily-use.md)。这里的服务安装和更新不负责启动或登录微信。

## 检查

```sh
launchctl print gui/$(id -u)/local.wechat-mcp.onebot
launchctl print gui/$(id -u)/local.wechat-mcp.webhook
.venv/bin/python scripts/start-onebot.py
.venv/bin/python scripts/mcp_smoke.py
.venv/bin/python scripts/doctor.py
```

不带 `--start` 的 `start-onebot.py` 只检查应用版本、配置和所需文件，不附加进程，也不启动微信。`ready=true` 表示通过鉴权的 Hook 探测及可用发送路径；它不等于接收方已读。Webhook 的 `/health` 也要求同一个 Bearer token，`/onebot` 仍使用原始正文 HMAC 签名。

## 服务文件和数据

安装后运行副本位于：

- `~/Library/Application Support/WeChatLocalMCP/`：代码副本、虚拟环境和配置。
- `~/Library/Application Support/WeChatLocalMCP/data/`：token、SQLite 缓存和日志，权限应保持为用户私有。
- `~/Library/LaunchAgents/local.wechat-mcp.{onebot,webhook}.plist`：LaunchAgent 定义。

不要把这些目录复制进 Git 或上传到 Issue。MCP 读取的是服务启动后收到的回调缓存，不会自动导入微信完整历史。

## 更新代码

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/bootstrap-upstream.py
.venv/bin/python scripts/install-services.py
```

`install-services.py` 会重建运行副本并重新加载两个后台服务，但不会操作微信窗口。若更新了 Gadget、微信版本或原生偏移，必须另行安排微信退出、备份、替换和登录维护窗口；不要在用户正常使用时热重载未知版本。

## 接口边界

MCP 原生文本发送使用 `[native]` 配置的 helper。4.1.15 的 OneBot 以 `receive_only` 模式运行，旧 HTTP/WS 发送入口被禁用，发送统一使用原生 helper；4.1.11 的旧网络发送入口仍保留，但不会补写电脑聊天记录。这两个发送接口都不是接收接口；接收由 Hook 经签名回调 POST 到 Webhook 的 `/onebot`。原生 helper 失败时不会自动回退到旧接口或 GUI。

回调使用 `X-Signature: sha1=<HMAC-SHA1(token, raw body)>`。发送回执按任务 ID 关联；无法解析或超时都返回结果不明，不自动重发。
