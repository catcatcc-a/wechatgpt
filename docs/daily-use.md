# 日常使用、自启动与停止服务

完成 README 安装流程后，日常使用顺序是：登录 macOS，打开并登录微信，再在已配置 `wechat-local` 的 AI 客户端中使用 MCP。只关闭微信窗口而不退出应用时，后台连接仍可工作；退出微信后，无法接收新消息或发送，已有回调缓存仍可读取。

## 哪些部分自动启动

| 组件 | 启动方式 | 未启动时的行为 |
| --- | --- | --- |
| OneBot 与 Webhook | 安装脚本注册用户级 LaunchAgent；登录 macOS 时启动 | launchd 会在进程退出后重启；微信恢复运行后尝试重连 |
| MCP stdio 进程 | MCP 客户端按配置启动 `scripts/start-mcp.sh` | 由客户端连接或重连，不是系统常驻服务 |
| 微信 | 用户打开应用并完成登录 | 项目不会自动打开、退出微信或替用户登录 |

这是**用户登录后自启动**，不在开机登录界面运行。两个 LaunchAgent 设置了 `RunAtLoad`、`KeepAlive` 和 15 秒启动节流；这不是精确的恢复时限。微信版本不匹配、凭据不一致和系统权限错误不会通过自动重试解决。

AI 客户端调用 `wechat_status` 可检查当前连接。`ready=true` 表示 Hook 和发送路径可用，不代表联系人已经收到消息；发送结果以回执、电脑记录及接收方确认分别描述。`login_verified=false` 目前不能单独用来判断退出登录，需要结合实际消息流量。

## 日常检查

在项目根目录执行：

```sh
.venv/bin/python scripts/mcp_smoke.py
launchctl print "gui/$(id -u)/local.wechat-mcp.onebot"
launchctl print "gui/$(id -u)/local.wechat-mcp.webhook"
```

第一条只检查 MCP 握手和状态，不发送消息。不要把终端输出或日志未经脱敏贴到公开 Issue。

源码升级后，运行副本不会自动跟随更新。按 [维护说明](onebot-setup.md) 测试并重新部署，再在 AI 客户端重连 MCP，以加载新 Python 代码。无需为了重连 MCP 而重启微信。

## 暂停和恢复

暂停两个后台服务，不退出微信，不删除缓存：

```sh
launchctl bootout "gui/$(id -u)/local.wechat-mcp.onebot"
launchctl bootout "gui/$(id -u)/local.wechat-mcp.webhook"
```

未加载的服务会报告找不到服务。此操作只停止当前登录会话中的服务；保留 plist 时，下次登录仍会启动。恢复已停止的服务：

```sh
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.wechat-mcp.webhook.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.wechat-mcp.onebot.plist"
```

不要对正在运行的服务重复 bootstrap。启动顺序先 Webhook，再 OneBot，避免接收端尚未就绪。

**暂停后台服务不会禁用 MCP 的原生发送 helper，也不会从微信中卸载 Gadget。** 若要停止整个集成，还需在 AI 客户端禁用 `wechat-local`；彻底移除 Gadget 必须恢复原应用。

## 停用自启动与移除集成

1. 在 MCP 客户端禁用或移除 `wechat-local`。
2. 用上述 bootout 命令停止后台服务。
3. 把 `~/Library/LaunchAgents/` 中的 `local.wechat-mcp.onebot.plist` 和 `local.wechat-mcp.webhook.plist` 移到私有备份目录。下次登录不会再加载它们。
4. 如需移除 Gadget，安排空闲时间退出微信，备份当前数据，再恢复安装时保留的**同版本原应用**，或重新安装已核对版本的官方应用。只停止服务不等于恢复微信签名。
5. 确认不再需要后，可手动删除 `~/Library/Application Support/WeChatLocalMCP/`。这会删除 MCP 缓存、发送去重账本和凭据；不应因此删除微信自身的数据目录。确认原应用不再使用 Gadget 后，再处理旧凭据和私有副本。

项目里的 `runtime/`、`backups/`、`artifacts/`、`data/` 也属于私有数据。应用回滚不等于聊天数据回滚，不能用旧数据覆盖已经产生新消息的现有数据库。

## 常见情况

- **微信打开后仍无法使用**：先核对精确 Build，再检查服务状态和 token 是否来自同一次安装。不要换用旧版本偏移。
- **图标启动立即退出**：重签后，系统可能拒绝微信访问原聊天数据，即使完全磁盘访问开关仍显示开启。按 [修复记录](security-remediation.md) 核对系统拒绝记录和应用路径；若确认旧授权不再匹配当前签名，应在用户同意后重新授权并复测。自动重试不能修复权限。
- **视频能点开但不播放**：检查 `scripts/doctor.py` 输出中的 `wechat.signature.helper_sandbox`。若为 `incompatible`，主程序与播放器等辅助程序的沙盒继承配置不一致；仅通过代码签名校验不足以排除这个问题。须在退出微信的维护窗口安装辅助签名已修复的副本，保留原应用，再实测播放。
- **发送超时**：查询原 `request_id` 的 `wechat_send_status`，核对会话；不要换新 ID 自动重发。
- **看不到旧消息**：MCP 只保存运行期间收到的回调，不导入完整微信历史。
- **只有昵称，没有会话 ID**：当前没有完整联系人查询接口。昵称必须与准确会话 ID 建立可靠对应，不能把显示姓名直接当作 OneBot 收件人。
