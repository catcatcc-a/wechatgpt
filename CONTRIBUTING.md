# Contributing

Keep changes focused and reproducible. Before opening a pull request:

```sh
./scripts/setup.sh
.venv/bin/python -m pytest -q
git diff --check
```

Do not commit virtual environments, upstream working copies, compiled binaries,
微信应用或数据、tokens、logs、screenshots, or message caches. Add a test for
protocol and validation changes. Do not claim a new WeChat version is supported
without recording its exact Build, architecture, module UUID, adaptation source,
and a real send/receive verification scope.

Changes derived from upstream projects must retain their attribution and update
the corresponding patch or notice file.
