# 上游来源与补丁

## 固定来源

- OneBot / Frida 桥接：[yincongcyincong/wechat_chatter](https://github.com/yincongcyincong/wechat_chatter)，固定提交 `f222f37321f66d3a199cb3c7642f77f7504d85da`，许可证 GPL-3.0。
- Mach-O 注入工具：[xiaoguiwucan/wechat-mac-hook-classic](https://github.com/xiaoguiwucan/wechat-mac-hook-classic)，固定提交 `3180313e08c24bf8c38e788527360d1b8d911f3d`；改编文件 `scripts/inject_load_dylib.py` 保留来源和 GPL-3.0 声明。
- Frida Python、Gadget 和 macOS arm64 core devkit：17.8.0，独立依赖，遵循其自身许可证。
- 本地补丁：`patches/wechat_chatter-local-auth.patch`，相对上述固定 OneBot 提交生成，包含新增文件与测试。

GitHub 源码仅保存本项目代码、补丁和固定输入，不包含下载的上游工作副本、Frida 二进制或微信应用。`NOTICE` 保留第三方归属。

## 补丁内容

1. OneBot 路由统一校验 Bearer token，拒绝缺失、错误、重复鉴权头和空配置；删除未鉴权注入入口和 pprof 路由。
2. Gadget 从私有文件读取独立 token，在附加前检查文件类型、权限和格式；不回退到无鉴权连接。
3. 回调保留 `X-Signature: sha1=<HMAC-SHA1(raw_body, token)>` 协议；先验签，再解析 JSON。
4. 限制 HTTP/WS 请求大小、网络超时及并发写入；日志只保留允许的数值指标和错误类型，移除原始消息、路径、媒体密钥及转储。
5. JS 回执带 task ID，Go 只匹配当前请求；解码失败不再视为成功，迟到回执不能完成下一条发送。
6. 提供鉴权 `/local_status`。启动必须在限时 RPC 中确认 Hook 已加载；Gadget 先于核心库可用时退出，由 launchd 稍后重试。session 断开也会退出以便重连。
7. `-receive_only` / `-hook_script` 支持新版本接收观察器，并禁用旧 HTTP/WS 网络发送及媒体处理路径。

补丁不向上游旧 JSON 填入新版猜测偏移。4.1.15.54 的原生文本接收和两版原生发送均在本项目 `native/` 下，由精确版本 manifest 驱动。

## 运行边界

默认只监听 `127.0.0.1:58080`，向 `http://127.0.0.1:36060/onebot` 发送签名回调。旧网络发送入口不写入电脑聊天记录；MCP 使用原生 helper 创建本地记录，并分别报告服务器回执和接收方确认。

4.1.15 的接收只覆盖新到达文本，不覆盖媒体或历史导入。上游没有完整联系人、历史记录或撤回 HTTP API。真实验收范围见 [记录](../docs/live-validation.md)，部署遗留项见 [修复进度](../docs/security-remediation.md)。构建成功不等于其他微信 Build 获得适配。

## 从公开源码恢复

在项目根目录执行：

```sh
.venv/bin/python scripts/bootstrap-upstream.py
```

脚本克隆固定提交、检查并应用补丁，下载且核对 Frida devkit SHA-256，以 Go 1.26.9 编译 arm64 OneBot。完整测试命令见 [构建说明](../docs/build-status.md)。已有修改且与记录补丁不一致时会停止，避免静默覆盖。

手工检查必须使用该提交的干净工作树：

```sh
cd vendor/wechat_chatter
git apply --check ../../patches/wechat_chatter-local-auth.patch
git apply ../../patches/wechat_chatter-local-auth.patch
```

已经应用时不要重复执行，可用 `git apply --reverse --check` 核对。更新补丁时需要包含新增文件，不能只保存已跟踪文件的 diff。补丁继续使用上游 GPL-3.0 许可。
