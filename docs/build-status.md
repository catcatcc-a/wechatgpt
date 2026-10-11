# 构建说明

项目的可复现构建分为两部分：Python MCP 和固定提交的 OneBot 上游引擎。

## Python MCP

```sh
./scripts/setup.sh
.venv/bin/python -m pytest -q
```

`setup.sh` 使用 `uv.lock` 安装 Python 依赖，并编译 `native/wechat_gui.swift`。GUI helper 只是明确授权时的验收工具，默认配置关闭。

## OneBot

```sh
.venv/bin/python scripts/bootstrap-upstream.py
```

脚本固定 `yincongcyincong/wechat_chatter` 提交 `f222f37321f66d3a199cb3c7642f77f7504d85da`，应用本地补丁，下载并校验 Frida 17.8.0 macOS arm64 devkit，然后以 `GOOS=darwin GOARCH=arm64 CGO_ENABLED=1` 编译 `vendor/wechat_chatter/onebot/onebot`。

生成的 `vendor/` 和 `downloads/` 内容都被 `.gitignore` 排除。仓库只保存补丁、固定版本说明和构建脚本，避免把上游源码副本、Frida 归档、微信应用或二进制产物提交到 GitHub。

## 固定输入

| 输入 | 固定值 |
| --- | --- |
| OneBot 上游 | `f222f37321f66d3a199cb3c7642f77f7504d85da` |
| Frida | `17.8.0` |
| 目标架构 | macOS `arm64` |
| 微信 | `4.1.11.53` / `269109` |

如果更新其中任何一个输入，必须更新版本说明并重新进行真实收发验收。
