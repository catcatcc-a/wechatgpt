# 兼容版本评估

本项目目前只接受 **微信 4.1.11.53 / Build 269109 / arm64**。`scripts/start-onebot.py`、`scripts/native-send.py` 和 `native/wechat_send.js` 都会拒绝其他 Build。

候选微信安装包来自腾讯公开地址：

`https://dldir1v6.qq.com/weixin/Universal/Mac/xWeChatMac_universal_4.1.11.53_41748.dmg`

文件名中的 `41748` 不是微信 Build；必须读取包内 `Contents/Info.plist`，确认：

- `WeChatBundleVersion = 4.1.11.53`
- `CFBundleVersion = 269109`
- Bundle ID 为 `com.tencent.xinWeChat`
- 包含 arm64 主程序和核心动态库

准备和校验步骤由 `scripts/download-assets.py`、`scripts/stage-compatible.py` 和 `scripts/inject_load_dylib.py` 完成。项目不把微信应用、Gadget 二进制或用户数据提交到 GitHub。

## 新版本适配要求

微信升级后不能只修改版本字符串。需要重新完成：

1. 读取新包的版本、Build、架构、签名和 Mach-O UUID；
2. 重新定位消息参数构造、UI 任务队列、原生发送入口和记录回执；
3. 更新版本 manifest、启动前检查和测试；
4. 在测试账号或文件传输助手中验证服务器回执、电脑本地记录和手机接收；
5. 由维护者明确记录新的偏移来源和未覆盖的功能。

在这些条件完成前，未知 Build 必须保持停用。
