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
| Go 工具链 | `go1.26.9` |
| 目标架构 | macOS `arm64` |
| 微信 | `4.1.15.54` / `270134`；`4.1.11.53` / `269109` |

如果更新其中任何一个输入，必须更新版本说明并重新进行真实收发验收。

## Go 测试

完成 bootstrap 后，从项目根目录运行：

```sh
cd vendor/wechat_chatter/onebot
GOTOOLCHAIN=go1.26.9 GOMAXPROCS=2 CGO_ENABLED=1 \
  CGO_CFLAGS="-I$(pwd)/../frida-devkit" \
  CGO_LDFLAGS="-L$(pwd)/../frida-devkit -lfrida-core" \
  go test -p=2 ./...
```

这些测试不连接微信。不要仅执行不带 devkit 路径的 `go test` 后，将链接失败误判为微信适配错误。

## 干净副本与 CI

公开仓库应能从 Git 管理的源码恢复 Python 环境并运行离线测试，不依赖 `config.toml`、运行副本或消息缓存。GitHub 工作流选择 `macos-15` arm64 runner，检查最低声明的 Python 3.11；Node.js 模拟接收脚本不允许静默遗漏。Swift helper 仅编译，不执行界面操作。

工作流不做实机验证或云端发布。macOS 15 的编译测试不能替代 macOS 12 或其他系统上的安装验收。runner 规格参见 [GitHub 官方说明](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)。当前锁文件使用公开 TUNA PyPI 镜像地址；`uv sync --locked` 会核对包哈希，访问镜像失败时不会自动更换依赖版本。
