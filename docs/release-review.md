# 发布前审阅

目标是发布可复现的 **0.1.0 源码预览**。本页是本地审阅材料，尚未创建 GitHub 仓库、远程地址、标签或 Release。公开发布需项目所有者先检查确认。

## 建议公开内容

- 项目名：`wechat-local-mcp`。
- 简介：macOS 本机微信 MCP，提供精确版本的原生文本发送与实时回调读取。
- 许可证：GPL-3.0，保留上游来源、固定提交、版权与补丁。
- 发布范围：源码、文档、测试、依赖锁、示例配置与上游补丁。
- 不发布：微信或 Frida 应用产物、本机配置、token、聊天记录、截图、日志、备份、原始验收材料。

源码预览不承诺其他电脑即装即用，也不以源码测试通过代替实机验收。

## 本轮本地验证（2026-10-11）

- 从 Git 索引导出的干净源码副本，使用 Python 3.11 和锁文件重新安装依赖，**75 项测试通过，无跳过**。
- Swift GUI helper 从源码编译通过，没有执行界面操作。
- 固定上游提交的干净副本成功应用补丁，Go 1.26.9 下完整测试通过。
- GitHub 工作流通过 actionlint 1.7.7 静态检查；云端执行尚未发生。
- 索引及可达历史的发布检查通过；额外对全部本地 Git 内容对象比对真实凭据、已知联系人信息和本机路径，未发现命中。提交身份均为项目中性身份，未配置远程仓库。
- Markdown 本地文件链接及暂存 diff 空白检查通过。

这些检查不重启微信、不重载后台服务，也不发送测试消息。源码发布检查不是全面漏洞扫描或实机兼容性保证。

## 审阅入口

| 内容 | 文件 |
| --- | --- |
| 功能、兼容版本、另一台 Mac 安装 | [README](../README.md) |
| 开机登录、自启动、停用和卸载 | [日常使用](daily-use.md) |
| 实测范围与限制 | [验收记录](live-validation.md) |
| 上游来源和补丁重放 | [来源说明](../vendor/UPSTREAM_NOTES.md)、[NOTICE](../NOTICE) |
| 授权条款 | [LICENSE](../LICENSE) |
| 安全边界与修复部署状态 | [SECURITY](../SECURITY.md)、[修复记录](security-remediation.md) |
| 贡献、离线测试及 CI | [贡献指南](../CONTRIBUTING.md)、[构建说明](build-status.md) |

## 发布前检查

先审查并暂存拟公开文件，再运行：

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/check_public_tree.py --history
git diff --cached --check
git diff --cached
git log --format=fuller
```

本机安装过服务时，还应对照实际 token 检查，不将值放在命令行：

```sh
.venv/bin/python scripts/check_public_tree.py --history \
  --secret-file data/gadget.token \
  --secret-file data/onebot.token
```

脚本只输出命中位置和规则，不输出密钥；检查索引及所有本地引用可达的提交、标签和 blob。浅克隆不能作为完整历史审查，会返回失败。它不扫描不可达对象、reflog、未跟踪文件，也不能自动识别所有姓名和聊天内容。提交身份、文件内容和发布包仍需人工检查；不要直接压缩工作目录上传。

源码归档应来自审阅通过的 Git 提交，例如：

```sh
mkdir -p dist
git archive --format=tar.gz --prefix=wechat-local-mcp/ \
  --output=dist/wechat-local-mcp-source-review.tar.gz HEAD
tar -tzf dist/wechat-local-mcp-source-review.tar.gz
```

归档只包含该提交的文件，没有 `.git`、未提交修改和被忽略的本机数据。许可证及上游补丁应随源码保留。

## 当前未完成事项

- 普通图标启动：等待用户手动授予系统数据访问权限后的最终核验；临时直接启动不能视为正常安装体验。
- 辅助进程修复：代码和重签副本已准备，尚未激活；媒体等辅助功能未验收。
- 其他设备：尚未在第二台干净 Mac 完成安装与真实双向收发；未验证全部 macOS 版本。
- 普通联系人仅验证一次发送的服务器回执、本地记录及会话预览；群聊未完成实机验收。
- 云端 CI：已准备配置，未发布所以尚未在 GitHub 运行。
- 仓库所有者、实际 clone 地址和私下安全报告入口：发布前确定；README 目前明确保留地址占位。

这些事项必须在源码预览中保留说明。发布稳定、即装即用版本前，应完成图标启动、辅助进程、重启登录恢复和第二台 Mac 验收。

## 所有者确认后才执行

确定 GitHub 所有者及仓库名，替换 README 地址占位；配置私有漏洞报告或可靠私下联系方式；检查提交内容与身份；由所有者确认后再创建仓库并推送。CI 不包含发布权限或自动 Release 步骤。
