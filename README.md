# wechat-local-mcp

一个运行在 macOS 本机的微信 MCP。它把微信的收发能力接到 MCP 客户端，支持后台读取实时回调消息和发送文本；原生发送路径会调用微信自己的消息创建、发送和会话更新流程，因此后台发送也会出现在电脑微信聊天记录中。

> 本项目是个人研究和技术交流项目，与腾讯或微信官方无关。它只在明确适配的微信版本上工作，不能把未知版本当作兼容版本使用。

## 功能

- 提供 `wechat_status`、`wechat_list_chats`、`wechat_read_messages`、`wechat_send_text` 和 `wechat_send_status` 五个 MCP 工具。
- 通过本机 OneBot HTTP/回调服务接收微信实时消息，并保存到本地 SQLite 缓存。
- 通过微信原生文本发送流程发送私聊、群聊或文件传输助手文本；发送请求带持久化 `request_id`，避免重试造成重复消息。
- 发送结果区分服务器回执、本地电脑记录和接收方确认，不把 HTTP 200 当作完整送达证明。
- OneBot HTTP 和回调只监听回环地址，并使用 Bearer 鉴权和 HMAC-SHA1 回调签名。
- GUI 后端默认关闭。日常后台收发不激活微信窗口、不模拟鼠标键盘，也不会在后台失败时自动切换到 GUI。
- 启动前检查微信版本、Build 和原生模块 UUID；版本不匹配时停止，不使用旧偏移强行注入。

当前已在 Apple Silicon 上验证微信 **4.1.15.54 / Build 270134** 的文件传输助手双向文本收发：MCP 后台发送取得服务器回执，电脑显示气泡，用户确认手机收到；手机发回的文本通过签名回调进入缓存，并能由 MCP 读取。此前 4.1.11.53 / Build 269109 也通过了文件传输助手测试。普通联系人和群聊仍需分别验收。

4.1.15 的接收路径仅捕获新到达的文本消息，不处理媒体。版本布局、运行验证及安装准备见 [新版适配说明](docs/wechat-4.1.15.md)；安全修复与部署状态见 [修复记录](docs/security-remediation.md)。

## 工作方式

```text
MCP 客户端
    │ stdio
    ▼
wechat-local-mcp
    ├── SQLite：请求账本和收到的回调缓存
    ├── OneBot HTTP/WS：本机收发桥接
    └── native-send.py + Frida：微信原生文本发送
                          │
                          ▼
             精确适配的微信 + Frida Gadget
```

接收消息来自服务启动后收到的回调，不是微信完整历史数据库导入。发送时，MCP 先写入请求账本，再让原生 helper 通过微信的 UI 任务队列进入微信自己的发送协程；helper 观察微信生成的本地消息记录和服务器编号后返回结果。超时或结果不明时不会自动换新的 `request_id` 重发。

## 项目来源

本项目把几个公开项目和本地修复组合成一个可供 MCP 使用的 macOS 工具：

1. OneBot 引擎来自 [yincongcyincong/wechat_chatter](https://github.com/yincongcyincong/wechat_chatter)，固定在提交 [`f222f37321f66d3a199cb3c7642f77f7504d85da`](https://github.com/yincongcyincong/wechat_chatter/commit/f222f37321f66d3a199cb3c7642f77f7504d85da)。本项目用补丁加入鉴权、状态探测、断线重连、请求匹配和回调归属修复；补丁在 `patches/wechat_chatter-local-auth.patch`。
2. 原生发送适配来自针对 4.1.11.53 / 269109 和 4.1.15.54 / 270134 的本地静态分析与真实调用链验证。发送代码在 `native/wechat_send.js`，各版本 UUID、指令指纹及布局在 `native/wechat-*.json`。4.1.15 的实时文本接收使用本项目的 `native/wechat_receive.js`，复用上游签名回调传输。
3. Mach-O 注入工具改编自 [xiaoguiwucan/wechat-mac-hook-classic](https://github.com/xiaoguiwucan/wechat-mac-hook-classic)，固定提交为 [`3180313e08c24bf8c38e788527360d1b8d911f3d`](https://github.com/xiaoguiwucan/wechat-mac-hook-classic/commit/3180313e08c24bf8c38e788527360d1b8d911f3d)，代码和归属见 `scripts/inject_load_dylib.py`。
4. Frida Gadget 和 Frida Python/Go 组件使用 Frida 17.8.0。微信安装包只从腾讯公开下载地址取得，项目不分发微信应用或用户数据。

上游来源、固定提交和补丁重新应用方式见 [`vendor/UPSTREAM_NOTES.md`](vendor/UPSTREAM_NOTES.md)。

## 兼容性

| 项目 | 已验证值 |
| --- | --- |
| 操作系统 | macOS 12 或更高版本（安装包声明的最低版本）；本机验收为 macOS 27.0.1 |
| CPU | Apple Silicon / `arm64` |
| 微信 Bundle ID | `com.tencent.xinWeChat` |
| 微信版本 | `4.1.15.54` / `4.1.11.53`（界面可能只显示前三段） |
| 微信 Build | 分别为 `270134` / `269109`，必须与版本成对匹配 |
| Frida | `17.8.0` |
| Gadget 地址 | `127.0.0.1:27042` |
| OneBot 地址 | `http://127.0.0.1:58080` |
| MCP 回调地址 | `http://127.0.0.1:36060/onebot` |

Intel Mac、Windows、Linux，以及其他未列出的微信 Build 都不属于当前已验证范围。微信版本升级后必须重新定位偏移、更新 UUID 和做真实收发验收；不能只改一个版本字符串。

## 在另一台 Apple Silicon Mac 上安装

下面的步骤会修改指定微信应用的加载库并使用 ad-hoc 签名。请先读完步骤，在测试账号或独立 macOS 用户下操作，并为微信应用和用户数据保留可恢复备份。项目不会自动退出、重启或登录微信。

### 1. 安装工具并下载项目

需要 Xcode Command Line Tools、支持自动工具链下载的 Go、Python 3.11+、`uv`、Git 和可用的网络连接。构建固定使用 Go 1.26.9（自动下载到独立缓存）。先安装 `uv`（例如 `brew install uv`），然后：

```sh
git clone https://github.com/<your-account>/wechat-local-mcp.git
cd wechat-local-mcp
./scripts/setup.sh
```

`setup.sh` 创建项目虚拟环境、安装锁定依赖并编译只在明确启用时使用的 GUI helper。它不会安装或启动微信。

### 2. 获取固定的上游引擎

```sh
.venv/bin/python scripts/bootstrap-upstream.py
```

这个脚本会：

- 克隆并固定 `wechat_chatter` 的指定提交；
- 应用本项目的鉴权和运行时补丁；
- 下载并校验 Frida 17.8.0 macOS arm64 devkit；
- 用 Go 1.26.9 和本机 clang 编译 arm64 OneBot 二进制。

上游源码和编译产物在 `vendor/`，均由 `.gitignore` 排除；公开仓库只保存固定提交说明、补丁和构建脚本。

### 3. 准备已安装的同版本微信副本

先从微信官方渠道安装上表中的精确版本。对 4.1.15，完整版本必须是 **4.1.15.54 / Build 270134**；不同 Build 会被拒绝，不会自动降级。检查已安装版本：

```sh
.venv/bin/python scripts/doctor.py
.venv/bin/python scripts/download-assets.py gadget
xz -dk downloads/frida-gadget-17.8.0-macos-universal.dylib.xz
.venv/bin/python scripts/secure-gadget.py
```

准备脚本复制 `/Applications/WeChat.app` 到项目私有目录 `runtime/security/WeChat.app`，加入 Frida Gadget、独立随机连接凭据并重签副本；核心 `wechat.dylib` 保持不变。它会核对 Build、UUID、指令指纹和签名，不操作运行中的应用。已有准备副本时会停止，避免覆盖。

每台电脑都需要在本机准备自己的副本；GitHub 项目只包含源码、补丁和脚本，**不分发修改后的微信、凭据或用户数据**。

### 4. 退出、备份并激活同版本副本

在空闲时完全退出微信，暂停已有 OneBot/回调服务，再执行：

```sh
.venv/bin/python scripts/backup-wechat.py
.venv/bin/python scripts/secure-gadget.py --activate
```

备份保存应用、微信容器数据和配置；激活再次检查应用未运行、当前应用及副本未被更改，并保留原应用。随后从 `/Applications/WeChat.app` 启动微信，按界面完成登录。如果重签后从图标启动立即退出，且诊断显示访问原微信容器被拒绝，需要由用户在系统隐私设置处理数据访问授权；[完全磁盘访问权限](https://support.apple.com/guide/mac-help/change-privacy-security-settings-mchl211c911f/mac)也包括其他应用的受保护数据，项目不会自动开启。当前本机的图标启动及辅助进程问题仍在处理，详见 [部署记录](docs/security-remediation.md)。本流程使用已安装的同版本微信；历史 `stage-compatible.py` / `install-staged-wechat.py` 是旧版实验流程，不是新版安装步骤。

### 5. 安装后台服务

确认微信已经由用户手动启动并保持登录后：

```sh
.venv/bin/python scripts/install-services.py
```

安装脚本会把服务副本放到 `~/Library/Application Support/WeChatLocalMCP/`，生成随机 OneBot token，并注册两个用户级 LaunchAgent。它不会操作微信窗口。服务状态和日志位于运行目录；token、SQLite 缓存和日志不应提交 Git。

验证静态版本和 MCP stdio 握手：

```sh
.venv/bin/python scripts/start-onebot.py
.venv/bin/python scripts/mcp_smoke.py
.venv/bin/python scripts/doctor.py
```

`start-onebot.py` 不带 `--start` 时只做检查。只有在微信已按文档完成 Gadget 安装、登录并且用户明确安排维护窗口后，才使用服务安装生成的 LaunchAgent 启动 OneBot。首次真实测试只使用文件传输助手，先确认电脑聊天窗口和手机都收到，再测试其他会话。

### 6. 接入 MCP 客户端

复制模板并把路径改成该电脑上的绝对路径：

```sh
cp mcp.example.json mcp.json
# 编辑 mcp.json，把 /absolute/path/to/wechat-local-mcp 改为当前项目目录
```

把 `mcp.json` 导入支持本地 stdio MCP 的客户端，或直接使用：

```sh
./scripts/start-mcp.sh
```

MCP 名称是 `wechat-local`。文件传输助手使用 `chat_id="filehelper"`；普通私聊使用准确的 `wxid_...`，群聊使用完整的 `@chatroom` ID，并设置 `chat_type="group"`。

## 安全、隐私和边界

- 这是本机工具，HTTP、WS 和回调默认只绑定回环地址；不要把端口暴露到局域网或公网。
- OneBot token 必须保存在本机权限为 `0600` 的文件中，不要放在命令行、截图、Issue 或 Git 提交里。
- `/health` 需要 Bearer token，OneBot 回调 `/onebot` 使用原始正文 HMAC 签名；重复鉴权头会被拒绝。
- 本地缓存和上游运行日志可能包含消息正文、会话 ID、媒体元数据和路径。分享诊断资料前先脱敏；旧日志不会因更新代码而自动清除。
- Frida Gadget 仅监听 `127.0.0.1:27042`，使用独立随机 token。准备脚本将 token 文件及应用配置设为 `0600`，两个客户端同步鉴权；不要转发端口或分享修改后的应用副本，详见 [安全说明](SECURITY.md)。旧安装需要完成维护窗口升级才能获得这些保护。
- `.gitignore` 排除了微信应用、备份、消息数据库、token、日志、截图、验收证据、下载包和虚拟环境；发布前仍应运行 `git status` 和敏感信息检查。
- 本项目会修改并重签指定微信应用。使用前备份数据，确认自己有权在该设备和账号上进行研究；项目作者不提供数据丢失、账号限制或微信升级后的兼容保证。
- 不包含完整微信历史导入、联系人枚举、撤回 API、图片/视频/文件的原生后台发送或自动登录。结果不明的消息不会自动重发。
- 微信升级、Gadget 变化或模块 UUID 变化后，必须停止服务并重新适配；不要把 4.1.11.53 的偏移用于其他版本。

## 开发与测试

```sh
.venv/bin/python -m pytest -q
git diff --check
```

离线测试覆盖 MCP stdio、配置校验、OneBot 请求/回调、请求去重、原生 helper 输入限制和 GUI 安全边界。安装 Node.js 后还会执行模拟内存中的原生接收脚本测试，验证批量边界、事件过滤和去重；测试不会连接微信。上游 Go 测试需要先执行 `scripts/bootstrap-upstream.py`，然后在 `vendor/wechat_chatter/onebot` 中运行 `go test ./...`。

贡献代码前请不要提交 `config.toml`、`mcp.json`、`data/`、`artifacts/`、`evidence/`、`backups/`、`downloads/`、`runtime/` 或 `vendor/` 下的本地副本。提交补丁或适配新微信版本时，请同时补充版本、架构、UUID、偏移来源和真实验收范围。

## 许可证和第三方声明

项目采用 GPL-3.0，完整文本见 [`LICENSE`](LICENSE)。第三方来源和许可证见 [`NOTICE`](NOTICE)。
