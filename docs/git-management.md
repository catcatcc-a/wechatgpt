# Git 管理

本项目使用本地 Git 仓库，主分支为 `main`。源码、原生发送修复、脚本、测试、配置示例、依赖锁文件、文档和上游补丁纳入版本管理。

`config.toml`、密钥、消息缓存、日志、截图、验收原始数据、微信备份、应用包、下载文件、编译产物与虚拟环境由 `.gitignore` 排除。Git 保存的是项目代码；恢复聊天数据仍需要独立的本地备份。

## 公开历史与提交身份

2026-10-11 经用户确认删除项目根目录的旧 `.git`，以审查后的文件重新初始化 `main` 分支。初始提交包括安全审计修复和文档，不继承旧提交、reflog 或个人作者信息；未保留旧根仓库的 Git 备份。

本地仓库使用项目身份 `wechat-local-mcp contributors <contributors@wechat-local-mcp.invalid>`，避免 Git 自动使用本机用户名和主机名生成作者邮箱。该邮箱为不可投递的占位地址；配置仅作用于本仓库，不修改全局 Git 身份。后续如需关联 GitHub 作者账号，应改用确认过的 GitHub 隐私邮箱，并检查新的提交元数据。

尚未配置远程仓库。上游源码的独立 Git 工作副本用于固定版本和维护补丁，仍由根仓库忽略。公开发布仍须用户检查确认；安全遗留项见 [审计报告](security-audit.md)。

## 日常使用

在项目目录中执行：

```sh
git status
git diff
git switch -c fix/short-description
# 完成修改后运行离线测试
.venv/bin/python -m pytest -q
git add <修改的文件>
git diff --cached
git commit -m "描述这次修改"
git log --oneline -10
```

查看某个文件是否被忽略，可以运行 `git check-ignore -v <文件路径>`。不要强制添加私有数据或应用备份。

## 上游源码

`vendor/wechat_chatter/` 是独立的上游工作副本，根仓库不将它作为嵌套仓库或子模块提交。固定上游版本为 `f222f37321f66d3a199cb3c7642f77f7504d85da`，本地修改保存在 `patches/wechat_chatter-local-auth.patch`，说明见 [上游修改](../vendor/UPSTREAM_NOTES.md)。

从新的根仓库副本恢复上游源码时，推荐直接执行可复现脚本：

```sh
.venv/bin/python scripts/bootstrap-upstream.py
```

脚本会完成克隆、固定提交、补丁检查、Frida devkit 下载和 OneBot 构建。需要手动检查补丁时，也可以执行：

```sh
git clone https://github.com/yincongcyincong/wechat_chatter.git vendor/wechat_chatter
git -C vendor/wechat_chatter checkout --detach f222f37321f66d3a199cb3c7642f77f7504d85da
git -C vendor/wechat_chatter apply --check ../../patches/wechat_chatter-local-auth.patch
git -C vendor/wechat_chatter apply ../../patches/wechat_chatter-local-auth.patch
```

当前本机副本已应用补丁，不要重复执行。以后修改上游源码时也应更新根仓库中的补丁，包含新增文件和测试。构建依赖另见 [构建说明](build-status.md)。

公开发布前请先检查 README、许可证、忽略规则和 `git diff --cached`；不要把本地 token、聊天缓存、截图或微信备份上传到远程仓库。
