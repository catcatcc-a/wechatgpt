# wechat_chatter 本地检查与补丁

检查日期：2026-10-11。

- 上游：<https://github.com/yincongcyincong/wechat_chatter>
- 固定提交：`f222f37321f66d3a199cb3c7642f77f7504d85da`，2026-09-28。
- 工作副本：`vendor/wechat_chatter/`。
- 本地补丁：`patches/wechat_chatter-local-auth.patch`（相对本项目根目录）。
- 补丁包含鉴权、Hook 状态 RPC、断线退出重连、回执 task ID 关联；未修改版本偏移。已在 4.1.11.53 / 269109 上完成文本收发，详见 [验收记录](../docs/live-validation.md)。

## 准备阶段的版本调查（历史）

本机 `/Applications/WeChat.app/Contents/Info.plist` 实测版本为 **4.1.15 / Build 270134**。
当前上游完整配置最高为 `wechat_version/4_1_12_53_mac.json`，运行默认值仍为
`4_1_11_53_mac.json`。不能将旧配置套用到本机版本。

上游 `tools/addrfind/` 可利用旧版 dylib 生成候选偏移，但其文档显示跨到 4.1.13
时只自动定位到 5/18 个目标；候选仍需额外验证。它不构成 4.1.15 已适配的证据。
v0.0.18 发布包于 2026-07-10 发布，与当前源码补丁和本机版本均不等价。

上游构建依赖 Go 1.25、CGO 和 Frida core devkit。当前构建脚本默认使用
Frida 17.8.0，而 Gadget 安装说明仍引用 17.5.2，需要另行确认匹配。
运行依赖工作目录中的 `script.js`，因此应在 `vendor/wechat_chatter/onebot/` 启动。

## 本地鉴权补丁

1. 新增 `onebot/server.go`，以独立 `http.ServeMux` 注册业务路由，统一在路由边界
   校验 `Authorization: Bearer <token>`。WebSocket 在升级连接之前校验。
2. 缺失、错误、重复 Authorization 头、非 Bearer 方式和空配置 token 均拒绝。
   不接受 URL 查询参数 token，比较采用常量时间 `hmac.Equal`。
3. 移除未鉴权的 `/test_ws` 消息注入入口和函数。
4. 移除 `net/http/pprof` 自动注册导入；独立 mux 防止其他库的默认 mux 调试路由暴露。
5. 移除启动时打印 token；取消公开默认值 `MuseBot`。通过 `WECHAT_ONEBOT_TOKEN`
   或 `-token` 显式设置，未设置时在附加微信进程之前退出。

回调签名协议保持兼容：`X-Signature: sha1=<HMAC-SHA1(raw_body, token)>`。
接收回调时应先对原始字节验签，再解析 JSON。

## 可封装接口及边界

默认监听 `127.0.0.1:58080`，默认将实时消息 POST 至
`http://127.0.0.1:36060/onebot`，分别可用 `-receive_host` 和 `-send_url` 覆盖。

- `POST /send_private_msg`：`{"user_id":"filehelper","message":[{"type":"text","data":{"text":"测试文本"}}]}`。
- `POST /send_group_msg`：改为 `group_id`，其值是完整 `@chatroom` 标识。
- `GET /ws`：WebSocket 握手，需要同样的 Bearer 头。

HTTP 响应为 `{"status":"ok"}` 或带 error 的失败结果，没有可供撤回的消息 ID。
文本发送会等待上游响应通道，但该通道未按任务 ID 匹配，响应解码失败还会被上游
视为成功；不能用此响应替代微信界面验收。

回调包含 `self_id`、`user_id`、`sender`、`group_id`、`message_id`、`message_type`、
`message`、`raw_message` 等字段。其 `time` 是生成事件时的 Unix 毫秒，非完整的
历史消息时间。上游没有 HTTP 历史记录、联系人枚举或撤回 API；如使用此后端，
MCP 的读取能力应明确为启动后收集到本地的实时回调消息。

## 验证

可独立于 Frida 运行的鉴权与路由测试：

```sh
cd vendor/wechat_chatter/onebot
GOMAXPROCS=2 CGO_CFLAGS="-I$(pwd)/../frida-devkit" CGO_LDFLAGS="-L$(pwd)/../frida-devkit -lfrida-core" go test -p=2 ./...
```

已通过：未鉴权请求不能触达发送/WS 处理器；正确 token 到达正确处理器；空 token
和重复 Authorization 拒绝；`/test_ws` 与 pprof 路径即使带正确 token 也返回 404；
响应不包含 token。`git diff --check` 通过。

2026-10-11 后续使用本机已有代理完成依赖下载，并下载／核对官方 Frida devkit 17.8.0
的 SHA256。以 Go 1.26.1、`nice -n 10`、`GOMAXPROCS=2`、`-p=2` 完成完整源码构建；
`go test -p=2 -count=1 ./...` 通过。产物静态检查为 macOS arm64，未执行该产物。
官方同版本 Gadget 已下载并解压至项目 `downloads/`，未安装或加载。
详见 [构建与摘要记录](../docs/build-status.md)。

微信 Hook 与真实收发仍未验证；本机 4.1.15 不因编译成功而成为已适配版本。
本次没有启动 Hook 后端或通过它发送微信消息。

## 在同一提交重新应用

```sh
cd vendor/wechat_chatter
git apply --check ../../patches/wechat_chatter-local-auth.patch
git apply ../../patches/wechat_chatter-local-auth.patch
```

本工作副本已应用；不要重复应用。补丁仍沿用上游 GPL-3.0 许可。

公开仓库不提交这个上游工作副本。其他电脑应运行项目内的
`scripts/bootstrap-upstream.py`，它会固定同一提交、应用补丁、下载 Frida devkit
并编译 arm64 OneBot；不要依赖某台电脑上的 `vendor/` 临时目录。

## 后续运行修复与实测（以此节为准）

- 新增鉴权 `/local_status`，通过 live Frida RPC 验证 Hook 与发送模板。
- Gadget session 断开时退出，由 LaunchAgent 重连；退出时显式 detach。
- JS 回执携带 task ID；Go 只匹配当前任务，迟到回执不再误完成后续请求。
- 回执解码失败返回错误，不再视为成功。
- Python 缓存修复手机到文件传输助手的 chat_id，并迁移旧记录、保持原始数据和去重键。
- 真实手机确认首条后台发送，真实 MCP 读取手机返回测试文本；后台服务安装与重连通过。
- 当前补丁包括新增文件，反向 `git apply --reverse --check` 已通过。热重载卡住的观察及恢复步骤见验收记录。

## 安全加固及新版适配候选

- 构建脚本固定 Go 1.26.9；此前 Go 1.26.1 的构建记录仅为历史记录。
- Gadget 通过私有凭据文件鉴权，Go 在附加前验证权限和格式；HTTP/WS 增加消息大小、超时和写入并发控制。
- 日志采用数值指标白名单，移除原始错误、JS payload、媒体密钥和文件转储。
- `-receive_only` 和 `-hook_script` 支持新版接收观察器；此模式拒绝旧 HTTP/WS 网络发送并跳过旧媒体处理 RPC。原生文本发送由 MCP helper 完成。
- 新版的地址与布局存在项目 `native/` manifest，不向上游 JSON 填入猜测的媒体偏移。4.1.15.54 / 270134 目前仍待真实收发验收，见 [适配说明](../docs/wechat-4.1.15.md)。
