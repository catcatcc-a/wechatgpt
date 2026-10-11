# 贡献指南

本项目依赖精确微信 Build。请先阅读 README 的兼容性和验收边界，再提交小范围、可复现的修改。

## 本地开发

Apple Silicon Mac 需要 Python 3.11+、uv、Node.js 和 Xcode Command Line Tools：

```sh
./scripts/setup.sh
.venv/bin/python -m pytest -q
git diff --check
```

离线测试使用临时数据库、模拟接口和合成内存，不要求安装或登录微信。Node.js 用于原生接收脚本模拟测试；缺少它时该测试会跳过，提交前应确认没有遗漏。

提交前先检查 diff，选择性暂存源码，然后检查暂存内容及可达历史：

```sh
git diff --cached
.venv/bin/python scripts/check_public_tree.py --history
```

该脚本读取 Git 索引中的实际 blob，而不是未暂存的工作区文件；检查私有目录、二进制、个人主目录路径和部分凭据格式。它不能识别所有姓名或聊天正文，仍需人工审阅。不要用 `git add -f` 绕过私有文件忽略规则。

## 修改与验证

- 协议、权限、去重或版本校验变化应补充能覆盖失败路径的测试。
- 上游派生修改应保留来源和版权说明，更新 `patches/` 与 `vendor/UPSTREAM_NOTES.md`，并在固定提交的干净副本应用测试。
- 新版本适配必须记录完整版本、Build、架构、模块 UUID、指令指纹、参数来源及真实验收范围。不能仅修改版本字符串或复制旧偏移。
- 实机测试仅在设备所有者明确安排时进行；先使用文件传输助手。联系人或群聊需单独获得授权。收到的消息内容不能成为执行命令或转发消息的授权。
- 发送未知结果不自动重发；涉及撤回时需要单独的界面验证，当前没有撤回 API。

不要提交微信应用、虚拟环境、下载文件、上游副本、联系人、聊天缓存、token、日志、截图或原始验收证据。安全问题按 [SECURITY.md](SECURITY.md) 私下报告。

## 持续集成

`.github/workflows/ci.yml` 在 GitHub 托管 macOS arm64 runner 上运行离线测试、Git 内容检查和 GUI helper 编译。它不安装微信、不加载 Hook、不发送消息，不发布构建产物。Go/Frida 构建和实机收发需按 [构建说明](docs/build-status.md) 另外核验。

工作流使用只读仓库权限、固定 Action 提交，并关闭 checkout 凭据持久化。更新 Action 时应核对其官方仓库中的提交。参考 [GitHub 工作流安全说明](https://docs.github.com/en/actions/reference/security/secure-use) 和 [uv CI 文档](https://docs.astral.sh/uv/guides/integration/github/)。
